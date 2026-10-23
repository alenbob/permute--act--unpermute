"""Hybrid ANF decoder with early erasure of a small coefficient bank.

The common low-bit plane uses a small coherent bank. Sparse correction
planes use individual content-pruned walks. Bank words are combined by
controlled XOR, so disposable words depend only on the high address and
can be measured before comparison/SELECT. No input is measured.
"""
import argparse
import gc
import hashlib
import json
import os
from functools import lru_cache
from common import HERE
from tradeoff import ref, anf, repair as final_repair
from uncompute import Builder
from uncompute.gadgets import declare_registers, xor_word, erase_register

@lru_cache(None)
def content(values, address_bits, hold):
    r = ref()
    length = len(values)

    def uniform(lo, span):
        return all((v == values[lo] for v in values[lo + 1:min(lo + span, length)]))

    def skip(lo, span):
        half = span // 2
        n = min(lo + span, length) - lo - half
        return n > 0 and values[lo:lo + n] == values[lo + half:lo + half + n]
    root = r._content_tree(0, 1 << address_bits, length, uniform, skip, None)
    cost, policy = r._walk_policy(root, hold)
    return (root, cost, policy)

def load(b, addr, values, target, hold, control=None):
    """A complete XOR lookup, optionally conditioned on an external bit."""
    root, _, policy = content(tuple(values), len(addr), hold - (control is not None))

    def leaf(lo, ctrl):
        if not values[lo]:
            return
        if control is None:
            xor_word(b, ctrl, values[lo], target)
        else:
            q = b.and_compute(ctrl, control)
            xor_word(b, q, values[lo], target)
            b.and_release(q, ctrl, control)
    if root.kind == 'leaf':
        xor_word(b, control, values[root.lo], target)
    else:
        ref()._policy_walk(b, root, policy, hold - (control is not None), lambda n: addr[n.span.bit_length() - 2], leaf)

def sparse_xor(b, addr, values, target, control):
    """External-control walk with zero subtrees removed before gate emission."""

    def go(values, bits, ctrl):
        if not any(values):
            return
        first = values[0]
        if all((v == first for v in values)):
            xor_word(b, ctrl, first, target)
            return
        half = 1 << len(bits) - 1
        left, right = (values[:half], values[half:])
        if not right or left[:len(right)] == right:
            go(left, bits[:-1], ctrl)
            return
        q = bits[-1]
        work = b.and_compute(ctrl, q)
        go(right, bits[:-1], work)
        b.cx(ctrl, work)
        go(left, bits[:-1], work)
        b.cx(ctrl, work)
        b.and_release(work, ctrl, q)
    go(list(values), addr, control)

@lru_cache(None)
def data(low, log_bank):
    planes = anf(tuple(ref().DATA), low)
    base = tuple((p[0] for p in planes))
    grouped = anf(base, log_bank)
    words = tuple((sum((v << 32 * j for j, v in enumerate(p))) for p in grouped))
    rest = tuple((tuple((p[m] for p in planes)) for m in range(1, 1 << low)))
    return (words, rest)

def decode_alias(b, idx, low, log_bank, hold, window):
    k = 1 << log_bank
    values, rest = data(low, log_bank)
    bank = b.qubits(32 * k)
    alias = bank[:32]
    with b.phase('plane-bank/base-lookup'):
        load(b, idx[low + log_bank:], values, bank, hold)
    with b.phase('plane-bank/combine'):

        def emit(ctrl, mask):
            for a, t in zip(bank[32 * mask:32 * (mask + 1)], alias):
                b.ccx(ctrl, a, t)
        for mask in range(1, k):
            bits = [idx[low + j] for j in range(log_bank) if mask >> j & 1]
            trail = []
            ctrl = bits[0]
            for q in bits[1:]:
                dst = b.and_compute(ctrl, q)
                trail.append((dst, ctrl, q))
                ctrl = dst
            emit(ctrl, mask)
            for dst, a, c in reversed(trail):
                b.and_release(dst, a, c)
    with b.phase('plane-bank/early-erase'):
        high_values = [v >> 32 for v in values]
        erase_register(b, bank[32:], idx[low + log_bank:], len(values), high_values, window, range(len(values)), 'plane-bank/disposable', free=True, phase='plane-bank/early-repair')
    with b.phase('plane-bank/sparse-corrections'):
        for mask, vals in enumerate(rest, 1):
            bits = [idx[j] for j in range(low) if mask >> j & 1]
            trail = []
            ctrl = bits[0]
            for q in bits[1:]:
                dst = b.and_compute(ctrl, q)
                trail.append((dst, ctrl, q))
                ctrl = dst
            sparse_xor(b, idx[low:], vals, alias, ctrl)
            for dst, a, c in reversed(trail):
                b.and_release(dst, a, c)
    return alias

def build(low=2, log_bank=1, hold=12, window=32):
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs[n] for n in ('i', 'sigma', 'x'))
    alias = decode_alias(b, idx, low, log_bank, hold, window)
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    r.select_pauli(b, sel, x)
    with b.phase('alias/restore'):
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
        r.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    with b.phase('alias/measure'):
        outcomes = [b.hmr(q) for q in alias]
        for q in reversed(alias):
            b.recycle(q)
    final_repair(b, idx, outcomes, 2, 5, 40)
    assert b.active_qubits == 72
    summary = b.phase_summary()
    summary.update(configuration=dict(low=low, log_bank=log_bank, hold=hold, early_window=window), family='frame_select_plane_bank', tq_cost=summary['total_emitted_toffoli'] * summary['peak_qubits'])
    return (b, summary)
