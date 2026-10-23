"""Spin-structured four-site PAU for the fixed Fe2S2 representative table.

Two published pair routers act on 20-mode pools. A controlled exchange of
18 modes selects the second pool. Every system action is a fermionic mode
permutation, a four-site local action, and the exact inverse.
"""
import argparse
import gc
import hashlib
import json
import os
from functools import lru_cache
from common import HERE
from tradeoff import ref, anf
from circuit import compress
from plane_bank import load
from pau_banked import table as old_table, xor_shared_flags
from pau_grouped import prepared, group_permute, inplace_decode
from pau_wide import combine
from pau_recycle import alias_decode
from pau_tq import measure_release, repair_records
from routing import support, pair_controls, pair_skeleton, leaf_number, transform, fermionic_swap, parity_wire, un_parity
from uncompute import Builder
from uncompute.gadgets import declare_registers

@lru_cache(None)
def route(base, padding='high', partition=0):
    r = ref()
    f, z = r._fz(base)
    active = support(f, z)
    alpha = [i for i in active if i % 2 == 0]
    beta = [i for i in active if i % 2]
    same = len(alpha) > 2
    assert len(beta) <= 2 and (not same or not beta), (base, active)
    target = 4 if same else 2
    for parity, selected, needed in ((0, alpha, target), (1, beta, 0 if same else 2)):
        candidates = [i for i in range(parity, 40, 2) if i not in selected]
        if padding == 'high':
            candidates.reverse()
        selected += candidates[:needed - len(selected)]
        selected.sort()
    if same:
        part = ((0, 1, 2, 3), (0, 2, 1, 3), (0, 3, 1, 2))[partition % 3]
        chosen = [alpha[i] for i in part]
        if partition >= 3:
            chosen = chosen[2:] + chosen[:2]
        first, second = (chosen[:2], chosen[2:])
    else:
        first, second = (alpha, beta)
    data = list(range(40))
    word = int(same) << 20
    switches = []

    def apply(a, c, control):
        switches.append((a, c, control))
        if control:
            data[a], data[c] = (data[c], data[a])
    for stage, pool, selected in ((0, list(range(0, 40, 2)), first), (1, list(range(1, 40, 2)), second)):
        if stage:
            for j in range(18):
                apply(4 + 2 * j, 1 + 2 * j, int(same))
        p, q = sorted((pool.index(data.index(a)) for a in selected))
        word |= (p | q << 5) << 10 * stage
        for (a, c, _), control in zip(pair_skeleton(20), pair_controls(20, p, q)):
            apply(pool[a], pool[c], control)
        assert set((data[i] for i in pool[:2])) == set(selected)
    ff, zz, sgn = transform(f, z, r.SIGN[base], data)
    assert ff | zz < 16, (base, ff, zz)
    word |= ff << 21 | zz << 25 | sgn << 29
    word |= ((f & 15).bit_count() & 1) << 30
    word |= ((f & (15 | 15 << 36)).bit_count() & 1) << 31
    word |= r._s(f) << 32
    return (word, tuple(data), tuple(switches))

@lru_cache(None)
def table(padding='high', partition=0):
    values = []
    for row, (base, _, _) in enumerate(prepared()[4]):
        values.append(route(base, padding, partition)[0] | old_table()[0][row] >> 36 << 33)
    encoded, basis, constant = compress(values)
    return (tuple(values), tuple(encoded), tuple(basis), constant, old_table()[4])

@lru_cache(None)
def bank_data(log_bank, padding='high', partition=0):
    values = table(padding, partition)[1]
    rank = len(table(padding, partition)[2])
    k = 1 << log_bank
    words = [0] * len(values)
    sizes = [0] * len(values)
    for gens, lo, hi in ref().REGIONS:
        n = len(gens)
        span = 1 << n
        for first in range(lo & ~(k * span - 1), hi, k * span):
            valid = max(first, lo)
            block = [values[first + j * span] if lo <= first + j * span < hi else values[valid] for j in range(k)]
            coefficients = anf(tuple(block), log_bank)[0]
            packed = sum((v << rank * j for j, v in enumerate(coefficients)))
            for row in range(max(first, lo), min(first + k * span, hi)):
                words[row] = packed
                sizes[row] = n
    return (tuple(words), tuple(sizes))

def local_select(b, flags, label, x):
    schedules = []
    closes = []
    for stage in range(2):
        p = label[10 * stage:10 * stage + 5]
        q = label[10 * stage + 5:10 * stage + 10]
        psi = {5: parity_wire(b, [p[0], q[0]], 1)}
        for t in range(4, 1, -1):
            eq = parity_wire(b, [p[t], q[t]], 1)
            psi[t] = b.and_compute(psi[t + 1], eq)
            un_parity(b, eq, [p[t], q[t]], 1)
            if t == 4:
                un_parity(b, psi[5], [p[0], q[0]], 1)
        product = b.and_compute(p[0], q[0])
        schedule = []
        for a, c, spec in pair_skeleton(20):
            if spec[0] == 'orient':
                rr = spec[1]
                w = [p[0]]
                constant = 0
                for t in range(2, 6):
                    if (rr >> t - 2 ^ rr >> t - 1) & 1:
                        w += [p[0], q[0]] if t == 5 else [psi[t]]
                        constant ^= t == 5
            elif spec[0] == 'special':
                w = [q[0], product]
                constant = 1
            else:
                _, parity, t, special = spec
                addr = p if parity == 0 else q
                w = [addr[k + 1] for k in range(4) if leaf_number(20, 1 << k) >> t & 1]
                constant = 0
                if special:
                    w += [addr[0]]
                    constant = parity
            schedule.append((2 * a + stage, 2 * c + stage, w, int(constant)))
        schedules.append(schedule)

        def close(psi=psi, p=p, q=q, product=product):
            b.and_release(product, p[0], q[0])
            for t in range(2, 5):
                eq = parity_wire(b, [p[t], q[t]], 1)
                parent = psi[t + 1] if t < 4 else parity_wire(b, [p[0], q[0]], 1)
                b.and_release(psi[t], parent, eq)
                if t == 4:
                    un_parity(b, parent, [p[0], q[0]], 1)
                un_parity(b, eq, [p[t], q[t]], 1)
        closes.append(close)

    def run(schedule):
        for a, c, w, k in schedule:
            ctrl = parity_wire(b, w, k)
            fermionic_swap(b, ctrl, x, a, c)
            un_parity(b, ctrl, w, k)
    with b.phase('spin/support-permute'):
        group_permute(b, flags, x)
    with b.phase('spin/alpha-pair'):
        run(schedules[0])
    with b.phase('spin/pool-select'):
        for j in range(18):
            fermionic_swap(b, label[20], x, 4 + 2 * j, 1 + 2 * j)
    with b.phase('spin/second-pair'):
        run(schedules[1])
    with b.phase('spin/local-target'):
        b.cz(label[30], flags[3])
        b.cz(label[30], flags[4])
        a, c, d = (flags[2], flags[3], flags[4])
        b.cx(a, c)
        b.cx(a, d)
        v = b.and_compute(c, d)
        b.cx(a, v)
        b.cz(v, label[31])
        b.cx(a, v)
        b.and_release(v, c, d)
        b.cx(a, d)
        b.cx(a, c)
        b.cz(label[32], flags[1])
        for j in range(4):
            b.cz(label[25 + j], x[j])
            b.ccz(flags[1], label[21 + j], x[j])
        for j in range(4):
            b.cx(label[21 + j], x[j])
        b.z(label[29])
    with b.phase('spin/second-pair-inverse'):
        run(reversed(schedules[1]))
    with b.phase('spin/pool-select-inverse'):
        for j in reversed(range(18)):
            fermionic_swap(b, label[20], x, 4 + 2 * j, 1 + 2 * j)
    with b.phase('spin/alpha-pair-inverse'):
        run(reversed(schedules[0]))
    with b.phase('spin/support-unpermute'):
        group_permute(b, flags, x, inverse=True)
    for close in reversed(closes):
        close()

def label_decode(b, sel, log_label, hold, low, window, repair_hold, padding, partition):
    native, encoded, basis, constant, terms = table(padding, partition)
    rank = len(basis)
    words, sizes = bank_data(log_label, padding, partition)
    flags = b.qubits(7 + log_label)
    with b.phase('spin-label/flags'):
        xor_shared_flags(b, sel, flags, log_label)
    bank = b.qubits(rank * (1 << log_label))
    root = bank[:rank]
    with b.phase('spin-label/lookup'):
        load(b, sel, words, bank, hold)
    with b.phase('spin-label/combine'):
        combine(b, flags[7:], bank, rank)
    with b.phase('spin-label/early-measure'):
        spare_records = measure_release(b, bank[rank:])
    expanded, close = inplace_decode(b, root, basis, constant, 40)
    with b.phase('spin-label/residual-sign'):
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
            b.cz(expanded[33 + j], product(term))
        for v, a, c in reversed(trail):
            b.and_release(v, a, c)

    def cleanup():
        close()
        outcomes = measure_release(b, root) + spare_records + measure_release(b, flags)
        flag_values = [sum((v << j for j, v in enumerate(meta[1]))) | (i >> sizes[i] & (1 << log_label) - 1) << 7 for i, meta in enumerate(prepared()[4])]
        values = tuple((v | w >> rank << rank | f << rank * (1 << log_label) for v, w, f in zip(encoded, words, flag_values)))
        with b.phase('spin-label/joint-repair'):
            repair_records(b, sel, outcomes, values, low, window, repair_hold)
    return (flags[:7], expanded, cleanup)

def build(log_alias=4, log_correction=1, log_label=3, alias_hold=14, label_hold=14, label_low=6, label_window=6, label_repair_hold=14, alias_low=2, alias_window=7, alias_repair_hold=14, padding='high', partition=0):
    config = dict(locals())
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs[n] for n in ('i', 'sigma', 'x'))
    alias, records, values = alias_decode(b, idx, log_alias, log_correction, alias_hold)
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    flags, label, close = label_decode(b, sel, log_label, label_hold, label_low, label_window, label_repair_hold, padding, partition)
    with b.phase('spin/control-products-and-close'):
        local_select(b, flags, label, x)
    close()
    with b.phase('alias/restore'):
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
        r.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    outcomes = measure_release(b, alias) + records
    with b.phase('recycle-alias/final-repair'):
        repair_records(b, idx, outcomes, values, alias_low, alias_window, alias_repair_hold)
    assert b.active_qubits == 72
    summary = b.phase_summary()
    summary.update(configuration=config, family='published_pau_spin_pools', prepared_width=len(table(padding, partition)[2]), tq_cost=summary['total_emitted_toffoli'] * summary['peak_qubits'])
    return (b, summary)

def emit(name, configuration):
    b, s = build(**configuration)
    out = HERE / 'results' / name
    out.mkdir(exist_ok=True)
    (out / 'resources.json').write_text(json.dumps(s, indent=2) + '\n')
    os.environ['UNCOMPUTE_OPS_PATH'] = str(out / 'circuit.ops')
    b.emit()
    return dict(key=name, toffoli=s['total_emitted_toffoli'], peak=s['peak_qubits'], tq=s['tq_cost'])
