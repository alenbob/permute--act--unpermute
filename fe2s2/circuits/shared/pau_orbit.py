"""Four-site PAU with orbit-shared decoding and short-lived control scratch.

The released orbit partition is used as classical table structure. SELECT
contains only fermionic transpositions, a four-site target action, and their
inverse; the representative-Pauli walk and diagonal frames are absent.
"""
import argparse
import gc
import hashlib
import json
import os
from functools import lru_cache
from common import HERE
from tradeoff import ref, anf, monomials, prefixes, monomial_order, repair as alias_repair
from circuit import compress
from pau_grouped import prepared, group_permute, inplace_decode
from routing import pair_skeleton, leaf_number, fermionic_swap, parity_wire, un_parity
from plane_bank import decode_alias
from uncompute import Builder
from uncompute.gadgets import declare_registers, xor_word, xor_outcomes

@lru_cache(None)
def table():
    r = ref()
    native = prepared()[0]
    values = []
    for row, (base, flags, _) in enumerate(prepared()[4]):
        word = native[base]
        f, z = r._fz(base)
        word |= ((f & 15).bit_count() & 1) << 33
        word |= ((f & (15 | 15 << 36)).bit_count() & 1) << 34
        word |= r._s(f) << 35
        values.append(word)
    encoded, basis, constant = compress(values)
    return (tuple(values), tuple(encoded), tuple(basis), constant)

def signs(b, ctrl, bits, linear, nonlinear):
    for j in linear:
        b.cz(ctrl, bits[j])
    for mn in nonlinear:
        wires = [ctrl] + [bits[j] for j in mn]
        trail = []
        while len(wires) > 3:
            a, c = wires[:2]
            q = b.and_compute(a, c)
            trail.append((q, a, c))
            wires = [q] + wires[2:]
        b.ccz(*wires)
        for q, a, c in reversed(trail):
            b.and_release(q, a, c)

def lookup(b, sel, target, hold=10):
    r = ref()
    _, encoded, _, _ = table()
    _, linear, nonlinear, hosted = r.sign_tables()
    combined = {base: set(ms) for base, ms in nonlinear.items()}
    for (lo, span), ms in hosted.items():
        for base in r.SPAN_AT:
            if lo <= base < lo + span:
                combined.setdefault(base, set()).symmetric_difference_update(ms)

    def leaf(row, ctrl):
        xor_word(b, ctrl, encoded[row], target)
        signs(b, ctrl, sel, linear.get(row, ()), sorted(combined.get(row, ())))
    root = r._content_tree(0, 1 << 16, r.L, lambda lo, span: r.SPAN_AT.get(lo) == span, None, lambda lo: max([0] + [max(0, len(m) - 2) for m in combined.get(lo, ())]))
    _, policy = r._walk_policy(root, hold)
    r._policy_walk(b, root, policy, hold, lambda n: sel[n.span.bit_length() - 2], leaf)

@lru_cache(None)
def repair_plan(low=2, log_window=5, hold=14):
    values = table()[1]
    p = anf(values, low)
    k = 1 << log_window
    p = list(p) + [tuple([0] * (1 << low))] * (-len(p) % k)
    payload = tuple((tuple(p[a:a + k]) for a in range(0, len(p), k)))
    masks = tuple((tuple((m for m in range(1 << low) if any((v[m] for v in block)))) for block in payload))
    loads = [max((m.bit_count() for m in mm), default=0) for mm in masks]
    n = len(payload)
    r = ref()

    def uniform(lo, span):
        return all((v == payload[lo] for v in payload[lo + 1:min(lo + span, n)]))

    def skip(lo, span):
        h = span // 2
        nn = min(lo + span, n) - lo - h
        return nn > 0 and payload[lo:lo + nn] == payload[lo + h:lo + h + nn]
    root = r._content_tree(0, 1 << 16 - low - log_window, n, uniform, skip, lambda lo: loads[lo])
    cost, policy = r._walk_policy(root, hold)
    return (root, policy, payload, masks, cost)

def erase_label(b, sel, compressed, low=2, log_window=5, hold=14):
    root, policy, payload, masks, _ = repair_plan(low, log_window, hold)
    outcomes = [b.hmr(q) for q in compressed]
    for q in reversed(compressed):
        b.recycle(q)
    k = 1 << log_window
    mid = sel[low:low + log_window]
    u = b.qubits(k)
    b.x(u[0])
    for j in reversed(range(log_window)):
        for s in range(0, k, 2 << j):
            b.cswap(mid[j], u[s], u[s + (1 << j)])
    cache = {0: None}

    def parity(v):
        if v not in cache:
            cache[v] = xor_outcomes([o for j, o in enumerate(outcomes) if v >> j & 1])
        return cache[v]

    def leaf(lo, ctrl):

        def emit(q, m):
            for j, v in enumerate(payload[lo]):
                o = parity(v[m])
                if o is not None:
                    b.cz(q, u[j], cond=o)
        monomials(b, ctrl, sel[:low], masks[lo], emit)
    ref()._policy_walk(b, root, policy, hold, lambda n: sel[low + log_window + n.span.bit_length() - 2], leaf)
    for j in range(log_window):
        for s in range(0, k, 2 << j):
            v = u[s + (1 << j)]
            b.cx(v, u[s])
            b.and_release(v, mid[j], u[s])
    b.x(u[0])
    b.recycle(u[0])

def controls(label):
    result = []
    for stage, n in enumerate((40, 38)):
        offset = stage * 12
        p = label[offset:offset + 6]
        q = label[offset + 6:offset + 12]
        psi = {t: [label[36 + 5 * stage + 5 - t]] for t in range(2, 6)}
        psi[6] = [p[0], q[0]]
        for a, c, spec in pair_skeleton(n):
            if spec[0] == 'orient':
                rr = spec[1]
                w = [p[0]]
                const = 0
                for t in range(2, 7):
                    if (rr >> t - 2 ^ rr >> t - 1) & 1:
                        w += psi[t]
                        const ^= t == 6
            elif spec[0] == 'special':
                w = [q[0], label[40 + 5 * stage]]
                const = 1
            else:
                _, parity, t, special = spec
                addr = p if parity == 0 else q
                w = [addr[k + 1] for k in range(5) if leaf_number(n, 1 << k) >> t & 1]
                const = 0
                if special:
                    w += [addr[0]]
                    const = parity
            result.append((a + 2 * stage, c + 2 * stage, w, int(const)))
    return result

def local_select(b, flags, label, x):
    products = []
    closes = []
    for stage in range(2):
        p = label[12 * stage:12 * stage + 6]
        q = label[12 * stage + 6:12 * stage + 12]
        psi = {6: parity_wire(b, [p[0], q[0]], 1)}
        for t in range(5, 1, -1):
            eq = parity_wire(b, [p[t], q[t]], 1)
            psi[t] = b.and_compute(psi[t + 1], eq)
            un_parity(b, eq, [p[t], q[t]], 1)
            if t == 5:
                un_parity(b, psi[6], [p[0], q[0]], 1)
        prod = b.and_compute(p[0], q[0])
        products.extend([psi[t] for t in range(5, 1, -1)] + [prod])

        def close(psi=psi, p=p, q=q, prod=prod):
            b.and_release(prod, p[0], q[0])
            for t in range(2, 6):
                eq = parity_wire(b, [p[t], q[t]], 1)
                parent = psi[t + 1] if t < 5 else parity_wire(b, [p[0], q[0]], 1)
                b.and_release(psi[t], parent, eq)
                if t == 5:
                    un_parity(b, parent, [p[0], q[0]], 1)
                un_parity(b, eq, [p[t], q[t]], 1)
        closes.append(close)
    with b.phase('pau/support-permute'):
        group_permute(b, flags, x)

    def run(schedule):
        for a, c, w, k in schedule:
            q = parity_wire(b, w, k)
            fermionic_swap(b, q, x, a, c)
            un_parity(b, q, w, k)
    schedule = controls(list(label) + products)
    with b.phase('pau/collect-four'):
        run(schedule)
    with b.phase('pau/local-target'):
        b.cz(label[33], flags[3])
        b.cz(label[33], flags[4])
        a, c, d = (flags[2], flags[3], flags[4])
        b.cx(a, c)
        b.cx(a, d)
        q = b.and_compute(c, d)
        b.cx(a, q)
        b.cz(q, label[34])
        b.cx(a, q)
        b.and_release(q, c, d)
        b.cx(a, d)
        b.cx(a, c)
        b.cz(label[35], flags[1])
        for j in range(4):
            b.cz(label[28 + j], x[j])
            b.ccz(flags[1], label[24 + j], x[j])
        for j in range(4):
            b.cx(label[24 + j], x[j])
        b.z(label[32])
    with b.phase('pau/restore-four'):
        run(reversed(schedule))
    with b.phase('pau/support-unpermute'):
        group_permute(b, flags, x, inverse=True)
    for close in reversed(closes):
        close()

def build(log_alias=1, hold=12, repair_low=4, repair_window=5, label_hold=12):
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs[n] for n in ('i', 'sigma', 'x'))
    alias = decode_alias(b, idx, 2, log_alias, hold, 32)
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    flags = b.qubits(7)
    with b.phase('pau/orbit-flags'):
        r.xor_gate_flags(b, sel, flags)
    _, encoded, basis, constant = table()
    compressed = b.qubits(len(basis))
    with b.phase('pau/orbit-label-lookup'):
        lookup(b, sel, compressed, label_hold)
    label, close = inplace_decode(b, compressed, basis, constant, 36)
    with b.phase('pau/control-products-and-close'):
        local_select(b, flags, label, x)
    close()
    with b.phase('pau/orbit-label-erase'):
        erase_label(b, sel, compressed, repair_low, repair_window)
    with b.phase('pau/orbit-flags-close'):
        r.xor_gate_flags(b, sel, flags)
    for q in reversed(flags):
        b.recycle(q)
    with b.phase('alias/restore'):
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
        r.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    outcomes = [b.hmr(q) for q in alias]
    for q in reversed(alias):
        b.recycle(q)
    alias_repair(b, idx, outcomes, 2, 5, 40)
    assert b.active_qubits == 72
    s = b.phase_summary()
    s.update(family='published_pau_orbit_decoded', prepared_width=len(basis), configuration=dict(log_alias=log_alias, hold=hold, repair_low=repair_low, repair_window=repair_window, label_hold=label_hold), tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'])
    return (b, s)
