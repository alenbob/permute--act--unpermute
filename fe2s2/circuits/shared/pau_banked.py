"""Four-site PAU with an early-erased bank of orbit labels and phase coefficients.

The lookup holds coefficients of the residual sign polynomial, rather than
evaluating that polynomial separately in every orbit leaf. All system action
is the published PAU pattern implemented by pau_orbit.local_select.
"""
import argparse
import gc
import hashlib
import json
import os
from functools import lru_cache
from common import HERE
from circuit import compress
from tradeoff import ref, anf, monomials, repair as alias_repair
from pau_grouped import prepared, inplace_decode
from pau_orbit import table as orbit_table, local_select
from plane_bank import decode_alias, load, sparse_xor, content
from uncompute import Builder
from uncompute.gadgets import declare_registers, erase_register, xor_outcomes

@lru_cache(None)
def table():
    r = ref()
    _, linear, nonlinear, hosted = r.sign_tables()
    combined = {base: set(ms) for base, ms in nonlinear.items()}
    for (lo, span), ms in hosted.items():
        for base in r.SPAN_AT:
            if lo <= base < lo + span:
                combined.setdefault(base, set()).symmetric_difference_update(ms)
    terms = tuple(sorted({(j,) for js in linear.values() for j in js} | {m for ms in combined.values() for m in ms}))
    values = []
    for row, (base, _, _) in enumerate(prepared()[4]):
        active = {(j,) for j in linear.get(base, ())} | combined.get(base, set())
        values.append(orbit_table()[0][row] | sum((int(m in active) << 36 + j for j, m in enumerate(terms))))
    encoded, basis, constant = compress(values)
    return (tuple(values), tuple(encoded), tuple(basis), constant, terms)

@lru_cache(None)
def bank_data(low, log_bank):
    rank = len(table()[2])
    planes = anf(table()[1], low)
    grouped = anf(tuple((p[0] for p in planes)), log_bank)
    words = tuple((sum((v << rank * j for j, v in enumerate(p))) for p in grouped))
    rest = tuple((tuple((p[m] for p in planes)) for m in range(1, 1 << low)))
    return (words, rest)

def decode_labels(b, sel, low, log_bank, hold, window):
    rank = len(table()[2])
    k = 1 << log_bank
    values, rest = bank_data(low, log_bank)
    bank = b.qubits(rank * k)
    label = bank[:rank]
    with b.phase('pau/label-bank-lookup'):
        load(b, sel[low + log_bank:], values, bank, hold)
    with b.phase('pau/label-bank-combine'):
        for mask in range(1, k):
            bits = [sel[low + j] for j in range(log_bank) if mask >> j & 1]
            trail = []
            ctrl = bits[0]
            for q in bits[1:]:
                dst = b.and_compute(ctrl, q)
                trail.append((dst, ctrl, q))
                ctrl = dst
            for a, t in zip(bank[rank * mask:rank * (mask + 1)], label):
                b.ccx(ctrl, a, t)
            for dst, a, c in reversed(trail):
                b.and_release(dst, a, c)
    with b.phase('pau/label-bank-early-erase'):
        if log_bank:
            erase_register(b, bank[rank:], sel[low + log_bank:], len(values), [v >> rank for v in values], window, range(len(values)), 'pau/label-bank-disposable', free=True, phase='pau/label-bank-early-repair')
    with b.phase('pau/label-sparse-corrections'):
        for mask, vals in enumerate(rest, 1):
            if not any(vals):
                continue
            bits = [sel[j] for j in range(low) if mask >> j & 1]
            trail = []
            ctrl = bits[0]
            for q in bits[1:]:
                dst = b.and_compute(ctrl, q)
                trail.append((dst, ctrl, q))
                ctrl = dst
            sparse_xor(b, sel[low:], vals, label, ctrl)
            for dst, a, c in reversed(trail):
                b.and_release(dst, a, c)
    return label

def residual_phase(b, sel, label):
    cache = {(j,): sel[j] for j in range(len(sel))}
    trail = []

    def product(term):
        if term not in cache:
            a = product(term[:-1])
            c = sel[term[-1]]
            q = b.and_compute(a, c)
            cache[term] = q
            trail.append((q, a, c))
        return cache[term]
    for j, term in enumerate(table()[4]):
        b.cz(label[36 + j], product(term))
    for q, a, c in reversed(trail):
        b.and_release(q, a, c)

@lru_cache(None)
def repair_plan(values, low, log_window, hold):
    p = list(anf(values, low))
    k = 1 << log_window
    p += [tuple([0] * (1 << low))] * (-len(p) % k)
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

def erase_label(b, sel, compressed, low, log_window, hold=14, values=None):
    values = table()[1] if values is None else tuple(values)
    root, policy, payload, masks, _ = repair_plan(values, low, log_window, hold)
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

@lru_cache(None)
def adaptive_data(log_bank):
    """ANF banks of neighbouring orbit representatives within each region.

    The selected bank address is the first row bit above the orbit bits.
    Partial banks at region boundaries are padded only on invalid branches;
    no assumption is made about equal orbit sizes in different regions.
    """
    values = table()[1]
    rank = len(table()[2])
    k = 1 << log_bank
    words = [0] * len(values)
    sizes = [0] * len(values)
    for gens, lo, hi in ref().REGIONS:
        n = len(gens)
        span = 1 << n
        for first in range(lo & ~(k * span - 1), hi, k * span):
            valid = max(first, lo)
            block = [values[first + j * span] if lo <= first + j * span < hi else values[valid] for j in range(k)]
            coeff = anf(tuple(block), log_bank)[0]
            packed = sum((v << rank * j for j, v in enumerate(coeff)))
            for row in range(max(first, lo), min(first + k * span, hi)):
                words[row] = packed
                sizes[row] = n
    return (tuple(words), tuple(sizes))

def adaptive_selectors(b, sel, controls, sizes, hold=14):
    root, _, policy = content(sizes, len(sel), hold - len(controls))

    def leaf(lo, ctrl):
        for j, target in enumerate(controls):
            b.ccx(ctrl, sel[sizes[lo] + j], target)
    ref()._policy_walk(b, root, policy, hold - len(controls), lambda n: sel[n.span.bit_length() - 2], leaf)

def xor_shared_flags(b, sel, targets, log_bank):
    """Share interval-comparator prefixes between orbit and bank flags.

    This is the released constant-comparison trie, with an extended set of
    XOR destinations. Equal endpoint contributions cancel over GF(2).
    """
    r = ref()
    uses = {}

    def add(K, p, g):
        if K:
            uses.setdefault(K, {}).setdefault(p, set()).symmetric_difference_update({g})
    for g in r.PRIORITY:
        for p, lo, hi in r.GEN_IVS[g]:
            add(lo, p, g)
            add(hi, p, g)
    for gens, lo, hi in r.REGIONS:
        for j in range(log_bank):
            add(lo, len(gens) + j, 7 + j)
            add(hi, len(gens) + j, 7 + j)
    uses = {K: {p: gs for p, gs in pp.items() if gs} for K, pp in uses.items()}
    groups = {}
    for K, pp in uses.items():
        if pp:
            groups.setdefault((K & -K).bit_length() - 1, []).append(K)
    for lo_bit, ks in sorted(groups.items()):
        ks.sort(key=lambda K: tuple((K >> j & 1 for j in range(lo_bit + 1, 16))))
        stack = []

        def unwind(depth):
            while len(stack) > depth:
                _, t, a, c, pol, xed, _ = stack.pop()
                if xed:
                    b.x(t)
                b.and_release(t, a, c, pol=pol)
        for K in ks:
            keep = 0
            for d, st in enumerate(stack):
                if K & (1 << st[0] + 1) - 1 != st[6]:
                    break
                keep = d + 1
            unwind(keep)
            if stack:
                cur, cpol, start = (stack[-1][1], True, stack[-1][0] + 1)
            else:
                cur, cpol, start = (sel[lo_bit], False, lo_bit + 1)
            for j in range(start, 16):
                xed = bool(K >> j & 1)
                pol = (True, not cpol) if xed else (False, cpol)
                t = b.and_compute(sel[j], cur, pol=pol)
                if xed:
                    b.x(t)
                stack.append((j, t, sel[j], cur, pol, xed, K & (1 << j + 1) - 1))
                cur, cpol = (t, True)
            assert cpol
            for p, gs in sorted(uses[K].items()):
                q = b.and_compute(sel[p], cur)
                for g in sorted(gs):
                    b.cx(q, targets[g])
                b.and_release(q, sel[p], cur)
        unwind(0)

def decode_adaptive(b, sel, log_bank, hold, repair_low, repair_window, shared_flags):
    rank = len(table()[2])
    k = 1 << log_bank
    values, sizes = adaptive_data(log_bank)
    flags = b.qubits(7) if shared_flags else []
    controls = b.qubits(log_bank)
    with b.phase('pau/adaptive-bank-address'):
        if shared_flags:
            xor_shared_flags(b, sel, flags + controls, log_bank)
        else:
            adaptive_selectors(b, sel, controls, sizes)
    bank = b.qubits(rank * k)
    label = bank[:rank]
    with b.phase('pau/adaptive-bank-lookup'):
        load(b, sel, values, bank, hold)
    with b.phase('pau/adaptive-bank-combine'):
        for mask in range(1, k):
            bits = [controls[j] for j in range(log_bank) if mask >> j & 1]
            trail = []
            ctrl = bits[0]
            for q in bits[1:]:
                dst = b.and_compute(ctrl, q)
                trail.append((dst, ctrl, q))
                ctrl = dst
            for a, t in zip(bank[rank * mask:rank * (mask + 1)], label):
                b.ccx(ctrl, a, t)
            for dst, a, c in reversed(trail):
                b.and_release(dst, a, c)
    with b.phase('pau/adaptive-bank-early-erase'):
        erase_label(b, sel, bank[rank:], repair_low, repair_window, values=tuple((v >> rank for v in values)))

    def close():
        with b.phase('pau/adaptive-bank-address-close'):
            if shared_flags:
                xor_shared_flags(b, sel, flags + controls, log_bank)
            else:
                adaptive_selectors(b, sel, controls, sizes)
        for q in reversed(flags + controls):
            b.recycle(q)
    return (label, flags, close)

def build(log_alias=2, hold=12, low=3, log_bank=1, label_hold=10, window=32, repair_low=4, repair_window=5, adaptive=False, shared_flags=True):
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
    flags = []
    close_bank = None
    if adaptive:
        compressed, flags, close_bank = decode_adaptive(b, sel, log_bank, label_hold, repair_low, repair_window, shared_flags)
    else:
        compressed = decode_labels(b, sel, low, log_bank, label_hold, window)
    _, _, basis, constant, terms = table()
    label, close = inplace_decode(b, compressed, basis, constant, 36 + len(terms))
    with b.phase('pau/residual-phase'):
        residual_phase(b, sel, label)
    if not flags:
        flags = b.qubits(7)
        with b.phase('pau/orbit-flags'):
            r.xor_gate_flags(b, sel, flags)
    with b.phase('pau/control-products-and-close'):
        local_select(b, flags, label[:36], x)
    if adaptive and shared_flags:
        close_bank()
    else:
        with b.phase('pau/orbit-flags-close'):
            r.xor_gate_flags(b, sel, flags)
        for q in reversed(flags):
            b.recycle(q)
        if close_bank:
            close_bank()
    close()
    with b.phase('pau/orbit-label-erase'):
        erase_label(b, sel, compressed, repair_low, repair_window)
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
    s.update(family='published_pau_banked_labels', prepared_width=len(basis), configuration=dict(log_alias=log_alias, hold=hold, low=low, log_bank=log_bank, label_hold=label_hold, window=window, repair_low=repair_low, repair_window=repair_window, adaptive=adaptive, shared_flags=shared_flags), tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'])
    return (b, s)
