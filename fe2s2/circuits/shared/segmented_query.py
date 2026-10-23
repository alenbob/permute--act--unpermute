"""Complete native query using segmented alias banks and the 259-Toffoli PAU."""
import hashlib, json, os
from common import HERE
from composed_query import SOURCES, select
from segmented_alias import alias_decode
from refined_repair import repair_records
from pau_tq import measure_release
from tradeoff import ref
from uncompute import Builder
from uncompute.gadgets import declare_registers

def hashes():
    return {}

def build(base_slices, family='pau', alias_mode='shared', log_alias=2, log_correction=1, alias_hold=14, select_mode='banked', flag_mode='shared', log_label=2, label_hold=14, label_low=6, label_window=6, label_repair_hold=7, alias_low=2, alias_window=7, alias_repair_hold=8, padding='high', partition=0, lookup_plan=None):
    config = dict(locals())
    assert family in ('pau', 'frame') and alias_mode == 'shared'
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, system = (regs[n] for n in ('i', 'sigma', 'x'))
    alias, records, values = alias_decode(b, idx, base_slices, log_correction, lookup_plan['correction'])
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    select(b, sel, system, family, select_mode, flag_mode, log_label, label_hold, label_low, label_window, label_repair_hold, padding, partition, lookup_plan=lookup_plan)
    with b.phase('alias/restore'):
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
        r.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    outcomes = measure_release(b, alias) + records
    with b.phase('current-alias/final-repair'):
        repair_records(b, idx, outcomes, values, alias_low, alias_window, alias_repair_hold)
    assert b.active_qubits == 72
    s = b.phase_summary()
    s.update(configuration=config, family='segmented_alias_' + family, tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'])
    if family == 'pau':
        assert sum((p['toffoli'] for p in s['phases'] if p['name'].startswith('spin/'))) == 259
    return (b, regs, s)

def emit(key, configuration):
    b, regs, s = build(**configuration)
    out = HERE / 'results' / key
    out.mkdir(exist_ok=True)
    (out / 'resources.json').write_text(json.dumps(s, indent=2) + '\n')
    os.environ['UNCOMPUTE_OPS_PATH'] = str(out / 'circuit.ops')
    b.emit()
    return (b, regs, s)
