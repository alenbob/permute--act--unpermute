#!/usr/bin/env python3
"""Rebuild a published point from modular emitters and an explicit configuration."""
from __future__ import annotations
import argparse
from contextlib import contextmanager, nullcontext
import hashlib
import importlib
import json
import lzma
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'shared'), str(ROOT / 'upstream')]


def configuration(name):
    if Path(name).name != name:
        raise ValueError('Use a circuit ID from configurations/')
    return json.loads((ROOT / 'configurations' / (name + '.json')).read_text())


@contextmanager
def overrides(config):
    # Import before replacing bindings, including module-local imported aliases.
    import branch_pau, composed_query, consistent_query, segmented_query
    import unary_repair, refined_repair, pau_tq, sparse_payload_lookup
    from tradeoff import ref
    from cost_query import correction_tree
    originals = (refined_repair.repair_records, pau_tq.repair_records)
    saved, walks, seen = [], [], set()
    def repair(b, address, outcomes, values, low, window, hold):
        plan = config['alias_repair'] if 'alias' in b.current_phase else config['select_repair']
        if plan is None:
            return originals[0](b, address, outcomes, values, low, window, hold)
        return unary_repair.repair_records(b, address, outcomes, values,
                                          plan['low'], plan['window'], plan['hold'])
    for module in list(sys.modules.values()):
        if module is None: continue
        old = getattr(module, 'repair_records', None)
        if any(old is f for f in originals):
            saved.append((module, old)); module.repair_records = repair
    plan = config['lookup_holds']
    for module in (ref(), sparse_payload_lookup):
        old = module._policy_walk; walks.append((module, old))
        def walk(b, root, policy, hold, bit_of, leaf, module=module, old=old):
            if b.current_phase in plan:
                hold = plan[b.current_phase]
                cost, policy = module._walk_policy(root, hold)
                assert cost < ref()._INF
                seen.add(b.current_phase)
            return old(b, root, policy, hold, bit_of, leaf)
        module._policy_walk = walk
    try:
        with correction_tree(config['cost_tree']): yield
        assert seen == set(plan), (seen, plan)
    finally:
        for module, old in walks: module._policy_walk = old
        for module, old in saved: module.repair_records = old


def build(config):
    if config['engine'] == 'frame_paper':
        from frame_paper import build as frame
        b, summary = frame(**config['parameters'])
        return b, summary
    selector = config['selector']; module = importlib.import_module(selector['engine'])
    import reuse_query
    with overrides(config):
        if selector['interface'] == 'family' and selector['engine'] in ('branch_pau','reuse_query'):
            b, _, summary = module.build(config['alias'], selector['configuration'], config['retained_borrows'])
        else:
            c = selector['configuration']
            def select(b, sel, x, **unused):
                if selector['interface'] == 'family':
                    return module.select(b, sel, x, **c)
                from multiframe import use_multiframe
                with use_multiframe() if selector['multiframe'] else nullcontext():
                    args = [b, sel, x] + [c[k] for k in ('family','select_mode','flag_mode','log_label',
                        'label_hold','label_low','label_window','label_repair_hold','padding','partition')]
                    kw = {} if selector['engine'] == 'consistent_query' else {'lookup_plan':c.get('lookup_plan')}
                    return module.select(*args, **kw)
            old = reuse_query.select; reuse_query.select = select
            try:
                b, _, summary = reuse_query.build(config['alias'], {'scheme':'explicit_selector'}, config['retained_borrows'])
            finally: reuse_query.select = old
    return b, summary


def normalized(op):
    """Translate a native tuple without changing its gate or outcome IDs."""
    from uncompute.ops import OpKind, NO_OUT, NO_BIT, NO_REG
    from uncompute.compact import KIND_OPERANDS, _FIELD_SLOT
    kind, qa, qb, qt, ot, oc, rt, ct, cc = op
    if rt != NO_REG or ct != NO_BIT or cc != NO_BIT:
        raise ValueError('Unexpected classical input or legacy register operand')
    name = OpKind(kind).name
    operands = tuple(int(op[_FIELD_SLOT[k]]) for k in KIND_OPERANDS[kind])
    cond = int(oc) if oc != NO_OUT and name != 'OXOR' else None
    return name, operands, cond


def text_lines(b):
    from uncompute.compact import Regs
    regs = Regs(b._registers).registers
    assert len(regs) == 3 and all(k == 0 for k, _ in regs)
    yield 'FE2S2-GATES 1\n'
    for name, (_, ids) in zip(('index','coin','system'), regs):
        yield 'REGISTER ' + name + ' ' + ' '.join(map(str, ids)) + '\n'
    count = 0
    for op in b.iter_expanded():
        name, args, cond = normalized(op)
        yield ' '.join([name, *map(str,args), *([] if cond is None else ['@'+str(cond)])]) + '\n'
        count += 1
    yield f'END {count}\n'


def liveness(b):
    """Replay allocation events independently of the allocator's counters."""
    live, peak, events = set(), 0, []
    for event, q, pos, claimed_live in b.wire_log:
        if event == 'alloc':
            assert q not in live, ('double allocation', q); live.add(q)
        elif event == 'free':
            assert q in live, ('free without allocation', q); live.remove(q)
        elif event in ('mark', 'mirror-begin', 'mirror-end', 'claim', 'release'): pass
        else: raise ValueError(event)
        assert len(live) == claimed_live
        peak = max(peak, len(live)); events.append([event,q,pos,len(live)])
    assert peak == b.peak_qubits and len(live) == 72
    return dict(peak_total_qubits=peak, final_live_qubits=sorted(live), events=events,
                scope='Allocator event replay; semantic cleanliness is checked separately.')


def generate(name, output):
    config = configuration(name); b, summary = build(config); expected = config['expected']
    assert (summary['total_emitted_toffoli'], b.peak_qubits) == (expected['toffoli'], expected['peak_total_qubits'])
    life = liveness(b)
    output.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with lzma.open(output / (name+'.gates.xz'), 'wb') as f:
        for line in text_lines(b):
            data=line.encode('ascii');h.update(data);f.write(data)
    assert h.hexdigest() == expected['text_sha256'], ('Gate sequence changed',name,h.hexdigest(),expected['text_sha256'])
    with lzma.open(output/(name+'.ops.xz'),'wb') as f:b.emit(meta=False,dest=f)
    with lzma.open(output/(name+'.liveness.json.xz'),'wt') as f:json.dump(life,f,separators=(',',':'))
    report=dict(id=name,status='PASS',text_sha256=h.hexdigest(),toffoli=expected['toffoli'],
                peak_total_qubits=life['peak_total_qubits'],allocation_events=len(life['events']),
                final_live_qubits=len(life['final_live_qubits']),phases=summary['phases'],
                configuration_sha256=hashlib.sha256((ROOT/'configurations'/(name+'.json')).read_bytes()).hexdigest(),
                source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for folder in ('shared','upstream') for p in sorted((ROOT/folder).rglob('*'))
                    if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.so','.pyc')})
    report['source_sha256']['generate.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    return {k:report[k] for k in ('id','status','toffoli','peak_total_qubits','allocation_events','text_sha256')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('id');p.add_argument('--output',type=Path,default=ROOT/'output')
    a=p.parse_args();print(json.dumps(generate(a.id,a.output),indent=2))
