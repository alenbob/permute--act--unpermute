"""Read-only affine label views for genuine multiple-family PAU circuits.

A decoded field which equals an existing bank bit borrows that wire. Identical
fields share one reference-counted wire; constant-zero fields share one clean
wire. Projection consumers must only read labels, and the all-row tests check
that the root is restored before measurement and phase repair.
"""
import hashlib
from contextlib import contextmanager
from family_pau import *
import family_pau as fp
import phase_pau as pp
import phase_query as pq
import family_layouts
from pau_permutation_core import reduce as reduce_swaps
from copy import deepcopy
from functools import lru_cache
_stripped_layout = pp.stripped_layout

@lru_cache(None)
def pooled_layout(scheme, shared_pair, padding, partition):
    """Store one common local mask and explicit family-enable bits."""
    spec = deepcopy(_stripped_layout(scheme, shared_pair, padding, partition))
    spec['enable_offset'] = spec['widths'][0]
    spec['widths'][0] += len(spec['branches'])
    values = [list(v) for v in spec['values']]
    for row, (base, _, _) in enumerate(prepared()[4]):
        fam = family(base)
        chosen = next((j for j, v in enumerate(spec['branches']) if fam in v['members']))
        branch = spec['branches'][chosen]
        a, w = (branch['address_width'], branch['target_width'])
        f = values[chosen + 1][row] >> a & (1 << w) - 1
        z = values[chosen + 1][row] >> a + w & (1 << w) - 1
        values[0][row] |= 1 << spec['enable_offset'] + chosen
        for j, branch in enumerate(spec['branches']):
            a, w = (branch['address_width'], branch['target_width'])
            mask = (1 << w) - 1
            values[j + 1][row] = values[j + 1][row] & (1 << a) - 1 | (f & mask) << a | (z & mask) << a + w
    spec['values'] = tuple((tuple(v) for v in values))
    return spec

def enabled_action(b, flags, label, x, branch, enable):
    """Project the shared local mask into this branch with temporary ANDs."""
    a, w = (branch['address_width'], branch['target_width'])
    projected = []
    cache = {}
    for q in label[a:a + 2 * w]:
        if q not in cache:
            cache[q] = q if q == enable else b.and_compute(enable, q)
        projected.append(cache[q])
    branch_action(b, flags, label[:a] + projected + label[a + 2 * w:], x, branch)
    for q, t in reversed(list(cache.items())):
        if q != enable:
            b.and_release(t, enable, q)

def routing_kind(members):
    members = set(members)
    if members <= {0, 1, 2, 3, 4}:
        return 'two_flip'
    if members <= {0, 1, 2, 3, 5}:
        return 'four_mixed'
    if members <= {4, 6}:
        return 'four_same'
    return 'four'
BINARY_SCHEMES = []
for mask in range(1, 127, 2):
    left = tuple((j for j in range(7) if mask >> j & 1))
    right = tuple((j for j in range(7) if not mask >> j & 1))
    name = f'binary_{mask:02x}'
    family_layouts.SCHEMES[name] = tuple(((f'branch_{k}', m, routing_kind(m)) for k, m in enumerate((left, right))))
    BINARY_SCHEMES.append(name)

def shared_prefix(b, flags, glob, x):
    """Merge commuting equal fermionic swaps across G / first-pair boundary."""
    one = 1 << 4096
    _, swaps = group()
    dual = controls(BASIS)
    gates = []
    for i in ORDER:
        wires = [flags[j] for j in range(7) if dual[i] >> j & 1]
        if BASIS[i] == 1:
            wires.append(glob[0])
        mask = 0
        for q in wires:
            mask ^= 1 << q
        gates.extend(((a, c, mask) for a, c in swaps[BASIS[i]]))
    schedule, close = pair_quantum_controls(b, 20, glob[11:16], glob[16:21])
    for a, c, wires, k in schedule:
        mask = one if k else 0
        for q in wires:
            mask ^= 1 << q
        gates.append((EVEN[a], EVEN[c], mask))
    reduced, _ = reduce_swaps(gates)

    def run(inverse=False):
        for a, c, mask in reversed(reduced) if inverse else reduced:
            constant = int(bool(mask & one))
            mask &= ~one
            wires = list(pp.set_bits(mask))
            ctrl = parity_wire(b, wires, constant)
            fermionic_swap(b, ctrl, x, a, c)
            un_parity(b, ctrl, wires, constant)
    return (run, close)

class AffineViews:

    def __init__(self, b):
        self.b = b
        self.live = {}

    def acquire(self, expressions):
        wires = []
        keys = []
        for terms, constant in expressions:
            key = (terms, constant)
            if key not in self.live:
                borrowed = len(terms) == 1 and (not constant)
                q = terms[0] if borrowed else self.b.qubit()
                if not borrowed:
                    if constant:
                        self.b.x(q)
                    for c in terms:
                        self.b.cx(c, q)
                self.live[key] = [q, 0, borrowed]
            self.live[key][1] += 1
            wires.append(self.live[key][0])
            keys.append(key)

        def close():
            for key in reversed(keys):
                entry = self.live[key]
                entry[1] -= 1
                if entry[1]:
                    continue
                q, _, borrowed = entry
                terms, constant = key
                if not borrowed:
                    for c in reversed(terms):
                        self.b.cx(c, q)
                    if constant:
                        self.b.x(q)
                    self.b.recycle(q)
                del self.live[key]
        return (wires, close)

def joint_select(b, sel, x, scheme='three', shared_pair=False, decode_mode='stream', log_label=1, label_hold=14, label_low=6, label_window=6, label_repair_hold=8, padding='high', partition=0, order=None, flag_mode='shared', lookup_plans=None, repair=True, merge_prefix=True, pooled_actions=False):
    assert decode_mode == 'joint'
    views = AffineViews(b)
    spec = fp.layout(scheme, shared_pair, padding, partition)
    tables = fp.data(scheme, shared_pair, padding, partition, decode_mode, log_label)
    order = tuple(order or reversed(range(16)))
    flags = None
    records = []
    values = [0] * ref().L
    offset = 0
    if flag_mode == 'separate':
        flags = b.qubits(7 + log_label)
        with b.phase('family-label/flags'):
            xor_shared_flags(b, sel, flags, log_label)

    def measured(wires, table):
        nonlocal offset
        records.extend(measure_release(b, wires))
        for i, v in enumerate(table):
            values[i] |= v << offset
        offset += len(wires)

    def lookup(table, number):
        nonlocal flags
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
            fp.load(b, sel, words, target, plan['hold'], plan['order'])
        if flags is None:
            flags = b.qubits(7 + log_label)
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
        expressions = []
        for j in range(width):
            terms = tuple((c for c, v in zip(root, basis) if v >> shift + j & 1))
            expressions.append((terms, constant >> shift + j & 1))
        return views.acquire(expressions)
    joint = lookup(tables[0], 0)
    if decode_mode == 'joint':
        glob, close_global = projection(joint, tables[0], 0)
    else:
        glob, close_global = inplace_decode(b, joint, tables[0][2], tables[0][3], spec['widths'][0])
    with b.phase('family-pau/gauges'):
        fp.gauge(b, sel, flags, glob, spec['terms'])
    shared_run = shared_close = None
    merged = merge_prefix and all((v['shared'] for v in spec['branches']))
    if merged:
        with b.phase('family-pau/merged-prefix-in'):
            shared_run, shared_close = shared_prefix(b, flags, glob, x)
            shared_run()
    else:
        with b.phase('family-pau/generators-in'):
            generators(b, flags, glob[0], x)
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
            if pooled_actions:
                enabled_action(b, flags, label, x, branch, glob[spec['enable_offset'] + number - 1])
            else:
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
    if not merged:
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

def select(b, sel, x, **configuration):
    old = pp._select
    old_layout = pp.stripped_layout
    pp._select = joint_select
    if configuration.get('pooled_actions'):
        pp.stripped_layout = pooled_layout
    try:
        return pp.select(b, sel, x, **configuration)
    finally:
        pp._select = old
        pp.stripped_layout = old_layout

def build(alias_configuration, selector_configuration, retained_borrows=0):
    old = pq.select
    pq.select = select
    try:
        b, regs, s = pq.build(alias_configuration, selector_configuration, retained_borrows)
    finally:
        pq.select = old
    s['family'] = 'compact_multiple_family_pau'
    return (b, regs, s)
