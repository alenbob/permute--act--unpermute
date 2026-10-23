"""Executable family-specific PAUs with shared orbital generators.

This experiment does not replace the validated common-core frontier. Family
actions are zero off-family; their permutations may still execute and cancel.
Consequently every emitted sandwich is charged, with no probability weighting.
"""
from functools import lru_cache
import hashlib
from common import HERE
from circuit import compress
from tradeoff import ref, anf
from routing import support, transform, pair_skeleton, pair_controls, pair_quantum_controls, fermionic_swap, parity_wire, un_parity
from pau_grouped import prepared, inplace_decode
from pau_spin import table as old_table
from pau_composed import BASIS, ORDER
from pau_permutation_core import group, controls
from pau_banked import xor_shared_flags
from pau_decode import flag_data, flag_map
from pau_wide import combine
from pau_tq import measure_release
from refined_repair import repair_records
from permuted_lookup import load
from uncompute import Builder
from uncompute.gadgets import declare_registers
EVEN = tuple(range(0, 40, 2))
ODD = tuple(range(1, 40, 2))
NAMES = ('one_diagonal', 'two_diagonal', 'hopping', 'three_mixed', 'three_same', 'four_mixed', 'four_same')
SCHEMES = {'two': (('diagonal', (0, 1), 'diagonal'), ('offdiagonal', (2, 3, 4, 5, 6), 'four')), 'three': (('diagonal', (0, 1), 'diagonal'), ('two_flip', (2, 3, 4), 'two_flip'), ('four_flip', (5, 6), 'four')), 'seven': tuple(((name, (j,), name) for j, name in enumerate(NAMES)))}

def family(base):
    f, z = ref()._fz(base)
    a = support(f, z)
    if not f:
        return len(a) - 1
    if len(a) == 2:
        return 2
    return (3 if len(a) == 3 else 5) + int(len({i % 2 for i in a}) == 1)

def stages(kind, shared_pair=False):
    """(operation, physical pool); fixed moves are fermionic Clifford swaps."""
    first = [('pair', EVEN)]
    if kind == 'one_diagonal':
        return [('single', EVEN)]
    if kind in ('diagonal', 'two_diagonal'):
        return [('pair', tuple(range(40)))]
    if kind == 'hopping':
        tail = []
    elif kind == 'three_mixed':
        tail = [('single', ODD)]
    elif kind == 'three_same':
        tail = [('single', EVEN[2:]), ('fixed', (1, 4))]
    elif kind == 'four_mixed':
        tail = [('pair', ODD)]
    elif kind == 'four_same':
        tail = [('pair', EVEN[2:]), ('fixed', (1, 4)), ('fixed', (3, 6))]
    elif kind in ('two_flip', 'four'):
        tail = [('exchange', tuple(((4 + 2 * j, 1 + 2 * j) for j in range(18)))), ('single' if kind == 'two_flip' else 'pair', ODD)]
    else:
        raise ValueError(kind)
    return ([] if shared_pair else first) + tail

def stage_width(stage):
    op, pool = stage
    if op == 'fixed':
        return 0
    if op == 'exchange':
        return 1
    return (len(pool) - 1).bit_length() * (2 if op == 'pair' else 1)

def single_schedule(pool, position):
    out = []
    for bit in range((len(pool) - 1).bit_length()):
        for j in range(0, len(pool), 2 << bit):
            if j + (1 << bit) < len(pool):
                out.append((pool[j], pool[j + (1 << bit)], position >> bit & 1))
    return out

def chosen_pair(base, normalized, partition, padding):
    f, z = ref()._fz(base)
    if normalized:
        f, z, _ = transform(f, z, 0, tuple((i ^ 1 for i in range(40))))
    active = support(f, z)
    selected = [i for i in active if i % 2 == 0]
    endpoints = [i for i in selected if f >> i & 1]
    if f.bit_count() == 2 and len(endpoints) == 2:
        selected = endpoints
    if len(selected) > 2:
        positions = ((0, 1, 2, 3), (0, 2, 1, 3), (0, 3, 1, 2))[partition % 3]
        if partition >= 3:
            positions = positions[2:] + positions[:2]
        selected = [selected[j] for j in positions if j < len(selected)][:2]
    candidates = [i for i in EVEN if i not in selected]
    if padding == 'high':
        candidates.reverse()
    selected += candidates[:2 - len(selected)]
    return tuple(sorted(selected))

def route_branch(base, kind, normalized, shared_pair, partition, padding):
    r = ref()
    f, z = r._fz(base)
    s = r.SIGN[base]
    if normalized:
        f, z, s = transform(f, z, s, tuple((i ^ 1 for i in range(40))))
    active = set(support(f, z))
    data = list(range(40))
    word = 0
    shift = 0
    switches = []
    first = chosen_pair(base, normalized, partition, padding)

    def apply(a, c, on):
        switches.append((a, c, on))
        if on:
            data[a], data[c] = (data[c], data[a])
    first_word = 0
    if shared_pair:
        p, q = (EVEN.index(i) for i in first)
        first_word = p | q << 5
        for (a, c, _), on in zip(pair_skeleton(20), pair_controls(20, p, q)):
            apply(EVEN[a], EVEN[c], on)
    for op, pool in stages(kind, shared_pair):
        if op == 'fixed':
            apply(*pool, 1)
            continue
        if op == 'exchange':
            on = int(any((data[i] in active for i in EVEN[2:])))
            word |= on << shift
            shift += 1
            for a, c in pool:
                apply(a, c, on)
            continue
        needed = 2 if op == 'pair' else 1
        selected = [i for i in pool if data[i] in active]
        if pool == EVEN and op == 'pair':
            selected = [data.index(i) for i in first]
        assert len(selected) <= needed or (pool == EVEN and op == 'pair')
        candidates = [i for i in pool if i not in selected]
        if padding == 'high':
            candidates.reverse()
        selected += candidates[:needed - len(selected)]
        positions = sorted((pool.index(i) for i in selected))
        width = (len(pool) - 1).bit_length()
        for j, p in enumerate(positions):
            word |= p << shift + j * width
        shift += needed * width
        if op == 'pair':
            for (a, c, _), on in zip(pair_skeleton(len(pool)), pair_controls(len(pool), *positions)):
                apply(pool[a], pool[c], on)
        else:
            for a, c, on in single_schedule(pool, positions[0]):
                apply(a, c, on)
    ff, zz, sgn = transform(f, z, s, data)
    target_width = {'one_diagonal': 1, 'diagonal': 2, 'two_diagonal': 2, 'hopping': 3, 'three_mixed': 3, 'three_same': 3, 'two_flip': 3}.get(kind, 4)
    assert ff | zz < 1 << target_width, (base, kind, ff, zz, data[:5])
    return (word | ff << shift | zz << shift + target_width | sgn << shift + 2 * target_width, tuple(data), tuple(switches), first_word)

@lru_cache(None)
def layout(scheme='three', shared_pair=False, padding='high', partition=0):
    definitions = SCHEMES[scheme]
    metadata = prepared()[4]
    old = old_table()[0]
    branches = []
    for name, members, kind in definitions:
        share = shared_pair and (not set(members) & {0, 1})
        recipe = stages(kind, share)
        address = sum(map(stage_width, recipe))
        width = {'one_diagonal': 1, 'diagonal': 2, 'two_diagonal': 2, 'hopping': 3, 'three_mixed': 3, 'three_same': 3, 'two_flip': 3}.get(kind, 4)
        branches.append(dict(name=name, members=members, kind=kind, shared=share, address_width=address, target_width=width, width=address + 2 * width + 1))
    values = [[] for _ in range(1 + len(branches))]
    census = [0] * 7
    route_cache = {}
    norm_cache = {}
    for row, (base, _, _) in enumerate(metadata):
        fam = family(base)
        census[fam] += 1
        chosen = next((i for i, v in enumerate(branches) if fam in v['members']))
        branch = branches[chosen]
        f, z = ref()._fz(base)
        normalize = int(branch['kind'] in ('two_flip', 'three_mixed') and bool(f & sum((1 << i for i in ODD))))
        if shared_pair and fam in (2, 3, 4):
            normalize = int(bool(f & sum((1 << i for i in ODD))))
        norm_cache[base] = normalize
        key = (base, chosen)
        if key not in route_cache:
            route_cache[key] = route_branch(base, branch['kind'], normalize, branch['shared'], partition, padding)
        native, _, _, first_word = route_cache[key]
        global_word = normalize | (old[row] >> 30 & 1023) << 1
        if shared_pair:
            global_word |= first_word << 11
        values[0].append(global_word)
        for j, v in enumerate(branches):
            values[j + 1].append(native if j == chosen else 0)
    widths = [11 + (10 if shared_pair else 0)] + [v['width'] for v in branches]
    for branch, words in zip(branches, values[1:]):
        a, w = (branch['address_width'], branch['target_width'])
        columns = {}
        for j in range(w):
            column = tuple((v >> a + j & 1 for v in words))
            if any(column):
                columns.setdefault(column, []).append(j)
        branch['flip_groups'] = list(columns.values())
    return dict(branches=branches, widths=widths, values=tuple((tuple(v) for v in values)), census=census, terms=old_table()[4], normalization=norm_cache, route_cache=route_cache)

@lru_cache(None)
def data(scheme, shared_pair, padding, partition, decode_mode, log_bank):
    spec = layout(scheme, shared_pair, padding, partition)
    if decode_mode == 'joint':
        vals = [0] * ref().L
        offset = 0
        for width, component in zip(spec['widths'], spec['values']):
            vals = [v | c << offset for v, c in zip(vals, component)]
            offset += width
        native = [tuple(vals)]
    else:
        assert decode_mode == 'stream'
        native = list(spec['values'])
    out = []
    for values in native:
        encoded, basis, constant = compress(values)
        rank = len(basis)
        words = [0] * len(values)
        k = 1 << log_bank
        for gens, lo, hi in ref().REGIONS:
            span = 1 << len(gens)
            for first in range(lo & ~(k * span - 1), hi, k * span):
                valid = max(first, lo)
                group = [encoded[first + j * span] if lo <= first + j * span < hi else encoded[valid] for j in range(k)]
                coefficients = anf(tuple(group), log_bank)[0]
                packed = sum((v << rank * j for j, v in enumerate(coefficients)))
                for row in range(max(first, lo), min(first + k * span, hi)):
                    words[row] = packed
        out.append((tuple(values), tuple(encoded), tuple(basis), constant, tuple(words)))
    return tuple(out)

def fixed_swap(b, x, a, c):
    a, c = sorted((a, c))
    b.cz(x[a], x[c])
    for j in range(a + 1, c):
        b.cz(x[a], x[j])
        b.cz(x[c], x[j])
    b.swap(x[a], x[c])

def quantum_route(b, label, x, recipe):
    gates = []
    closes = []
    offset = 0
    for stage in recipe:
        op, pool = stage
        width = stage_width(stage)
        bits = label[offset:offset + width]
        offset += width
        if op == 'fixed':
            gates.append((*pool, None, 1))
        elif op == 'exchange':
            gates.extend(((a, c, [bits[0]], 0) for a, c in pool))
        elif op == 'single':
            for t in range(width):
                for j in range(0, len(pool), 2 << t):
                    if j + (1 << t) < len(pool):
                        gates.append((pool[j], pool[j + (1 << t)], [bits[t]], 0))
        else:
            m = width // 2
            schedule, close = pair_quantum_controls(b, len(pool), bits[:m], bits[m:])
            closes.append(close)
            gates.extend(((pool[a], pool[c], w, k) for a, c, w, k in schedule))

    def run(inverse=False):
        for a, c, w, k in reversed(gates) if inverse else gates:
            if w is None:
                fixed_swap(b, x, a, c)
            else:
                control = parity_wire(b, w, k)
                fermionic_swap(b, control, x, a, c)
                un_parity(b, control, w, k)

    def close():
        for fn in reversed(closes):
            fn()
    return (run, close)

def generators(b, flags, normalize, x, inverse=False):
    _, swaps = group()
    dual = controls(BASIS)
    for i in reversed(ORDER) if inverse else ORDER:
        wires = [flags[j] for j in range(7) if dual[i] >> j & 1]
        if BASIS[i] == 1:
            wires.append(normalize)
        q = parity_wire(b, wires)
        for a, c in reversed(swaps[BASIS[i]]) if inverse else swaps[BASIS[i]]:
            fermionic_swap(b, q, x, a, c)
        un_parity(b, q, wires)

def gauge(b, sel, flags, glob, terms):
    b.cz(glob[1], flags[3])
    b.cz(glob[1], flags[4])
    a, c, d = flags[2:5]
    b.cx(a, c)
    b.cx(a, d)
    v = b.and_compute(c, d)
    b.cx(a, v)
    b.cz(v, glob[2])
    b.cx(a, v)
    b.and_release(v, c, d)
    b.cx(a, d)
    b.cx(a, c)
    b.cz(glob[3], flags[1])
    products = {(j,): sel[j] for j in range(16)}
    trail = []

    def product(term):
        if term not in products:
            a, c = (product(term[:-1]), sel[term[-1]])
            v = b.and_compute(a, c)
            products[term] = v
            trail.append((v, a, c))
        return products[term]
    for j, term in enumerate(terms):
        b.cz(glob[4 + j], product(term))
    for v, a, c in reversed(trail):
        b.and_release(v, a, c)

def branch_action(b, flags, label, x, branch):
    a = branch['address_width']
    w = branch['target_width']
    f = label[a:a + w]
    z = label[a + w:a + 2 * w]
    for j in range(w):
        b.cz(z[j], x[j])
    for positions in branch['flip_groups']:
        product = b.and_compute(flags[1], f[positions[0]])
        for j in positions:
            b.cz(product, x[j])
        b.and_release(product, flags[1], f[positions[0]])
    for j in range(w):
        b.cx(f[j], x[j])
    b.z(label[a + 2 * w])

def select(b, sel, x, scheme='three', shared_pair=False, decode_mode='stream', log_label=1, label_hold=14, label_low=6, label_window=6, label_repair_hold=8, padding='high', partition=0, order=None, flag_mode='shared', lookup_plans=None, repair=True):
    spec = layout(scheme, shared_pair, padding, partition)
    tables = data(scheme, shared_pair, padding, partition, decode_mode, log_label)
    order = tuple(order or reversed(range(16)))
    flags = b.qubits(7 + log_label)
    records = []
    values = [0] * ref().L
    offset = 0
    if flag_mode == 'separate':
        with b.phase('family-label/flags'):
            xor_shared_flags(b, sel, flags, log_label)

    def measured(wires, table):
        nonlocal offset
        records.extend(measure_release(b, wires))
        for i, v in enumerate(table):
            values[i] |= v << offset
        offset += len(wires)

    def lookup(table, number):
        native, encoded, basis, constant, words = table
        rank = len(basis)
        bank = b.qubits(rank * (1 << log_label))
        target = bank
        meta = []
        if number == 0 and flag_mode == 'shared':
            meta_values, meta_basis, meta_constant, factors, _ = flag_data(log_label)
            meta = b.qubits(len(meta_basis))
            target = bank + meta
            words = tuple((w | m << len(bank) for w, m in zip(words, meta_values)))
        plan = (lookup_plans or {}).get(str(number), dict(hold=label_hold, order=order))
        with b.phase(f'family-label/lookup-{number}'):
            load(b, sel, words, target, plan['hold'], plan['order'])
        if meta:
            with b.phase('family-label/flags'):
                flag_map(b, sel, meta, flags, meta_basis, meta_constant, factors)
            measured(meta, meta_values)
        with b.phase(f'family-label/combine-{number}'):
            combine(b, flags[7:], bank, rank)
        measured(bank[rank:], tuple((v >> rank for v in table[4])))
        return bank[:rank]

    def projection(root, table, part):
        shift = sum(spec['widths'][:part])
        width = spec['widths'][part]
        mask = (1 << width) - 1
        native, encoded, basis, constant, _ = table
        out = b.qubits(width)
        for j, q in enumerate(out):
            if constant >> shift + j & 1:
                b.x(q)
            for c, v in zip(root, basis):
                if v >> shift + j & 1:
                    b.cx(c, q)

        def close():
            for j, q in reversed(list(enumerate(out))):
                for c, v in zip(root, basis):
                    if v >> shift + j & 1:
                        b.cx(c, q)
                if constant >> shift + j & 1:
                    b.x(q)
                b.recycle(q)
        return (out, close)
    joint = lookup(tables[0], 0)
    if decode_mode == 'joint':
        glob, close_global = projection(joint, tables[0], 0)
    else:
        glob, close_global = inplace_decode(b, joint, tables[0][2], tables[0][3], spec['widths'][0])
    with b.phase('family-pau/gauges'):
        gauge(b, sel, flags, glob, spec['terms'])
    with b.phase('family-pau/generators-in'):
        generators(b, flags, glob[0], x)
    shared_run = shared_close = None
    for number, branch in enumerate(spec['branches'], 1):
        if branch['shared'] and shared_run is None:
            with b.phase('family-pau/common-pair-in'):
                shared_run, shared_close = quantum_route(b, glob[11:], x, [('pair', EVEN)])
                shared_run()
        if decode_mode == 'joint':
            label, close = projection(joint, tables[0], number)
        else:
            table = tables[number]
            root = lookup(table, number)
            label, close = inplace_decode(b, root, table[2], table[3], spec['widths'][number])
        with b.phase('family-pau/' + branch['name']):
            run, end = quantum_route(b, label, x, stages(branch['kind'], branch['shared']))
            run()
            branch_action(b, flags, label, x, branch)
            run(True)
            end()
        close()
        if decode_mode == 'stream':
            measured(root, table[1])
    if shared_run:
        with b.phase('family-pau/common-pair-out'):
            shared_run(True)
            shared_close()
    with b.phase('family-pau/generators-out'):
        generators(b, flags, glob[0], x, True)
    close_global()
    measured(joint, tables[0][1])
    flag_values = flag_data(log_label)[4]
    measured(flags, flag_values)
    assert len(records) == offset
    if repair:
        with b.phase('family-label/repair'):
            repair_records(b, sel, records, values, label_low, label_window, label_repair_hold)
    return tuple(values)

def hashes():
    return {}

def build(alias_configuration, selector_configuration):
    from composed_query import alias_decode
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs[n] for n in ('i', 'sigma', 'x'))
    c = alias_configuration
    if 'base_slices' in c:
        from segmented_alias import alias_decode as segmented
        alias, records, values = segmented(b, idx, c['base_slices'], c['log_correction'], c['lookup_plan']['correction'])
    else:
        alias, records, values = alias_decode(b, idx, c['alias_mode'], c['log_alias'], c['log_correction'], c['alias_hold'], c.get('lookup_plan'))
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, t in zip(idx, sel):
            b.cswap(flag, a, t)
    if selector_configuration.get('scheme') == 'common_even':
        from composed_query import select as common_select
        from pau_even_action import use_core
        with use_core():
            common_select(b, sel, x, 'pau', c['select_mode'], c['flag_mode'], c['log_label'], c['label_hold'], c['label_low'], c['label_window'], c['label_repair_hold'], c['padding'], c['partition'], lookup_plan=c.get('lookup_plan'))
    else:
        select(b, sel, x, **selector_configuration)
    with b.phase('alias/restore'):
        for a, t in zip(idx, sel):
            b.cswap(flag, a, t)
        r.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    outcomes = measure_release(b, alias) + records
    with b.phase('current-alias/final-repair'):
        repair_records(b, idx, outcomes, values, c['alias_low'], c['alias_window'], c['alias_repair_hold'])
    assert b.active_qubits == 72
    s = b.phase_summary()
    s.update(configuration=dict(alias=c, selector=selector_configuration), family='multiple_family_pau', tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'])
    if selector_configuration.get('scheme') == 'common_even':
        pass
    return (b, regs, s)
