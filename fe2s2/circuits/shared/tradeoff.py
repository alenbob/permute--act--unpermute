"""Low-space decoder search and gate-level space--time tradeoff circuits.

The coefficient lookup and measurement repair use vector-valued algebraic
normal form (ANF) on low address bits, a content-pruned high-address walk,
and a shared prefix tree for the required monomials. The baseline SELECT
is retained for the low-space comparator; PAU variants remain separate.
"""
import argparse
import gc
import hashlib
import itertools
import json
import math
import os
from functools import lru_cache
from pathlib import Path
from common import HERE, upstream
from uncompute import Builder
from uncompute.gadgets import declare_registers, xor_word, xor_outcomes

@lru_cache(None)
def ref():
    return upstream()

def anf(values, low):
    """Vector-valued Boolean Moebius transform, separately per low-bit cube."""
    width = 1 << low
    out = []
    for base in range(0, len(values), width):
        block = list(values[base:base + width])
        block += [block[0]] * (width - len(block))
        for j in range(low):
            for mask in range(width):
                if mask >> j & 1:
                    block[mask] ^= block[mask ^ 1 << j]
        out.append(tuple(block))
    return tuple(out)

def prefixes(masks, order):
    return {tuple((j for j in order if mask >> j & 1))[:n] for mask in masks for n in range(1, mask.bit_count() + 1)}

@lru_cache(None)
def monomial_order(masks, low):
    masks = tuple((m for m in masks if m))
    if low <= 6:
        return min(itertools.permutations(range(low)), key=lambda p: (len(prefixes(masks, p)), p))
    return tuple(sorted(range(low), key=lambda j: (-sum((m >> j & 1 for m in masks)), j)))

def monomials(b, ctrl, bits, masks, emit):
    """Compute shared AND prefixes; every close uses the native MBU gadget."""
    masks = tuple(sorted(masks))
    order = monomial_order(masks, len(bits))
    tree = {}
    for mask in masks:
        node = tree
        for j in order:
            if mask >> j & 1:
                node = node.setdefault(j, {})
        node[None] = mask

    def go(node, control):
        if None in node:
            emit(control, node[None])
        for j in sorted((k for k in node if k is not None)):
            q = b.and_compute(control, bits[j])
            go(node[j], q)
            b.and_release(q, control, bits[j])
    go(tree, ctrl)

@lru_cache(None)
def plan(low, log_window, hold, cleanup):
    r = ref()
    table = anf(tuple(r.DATA), low)
    k = 1 << log_window
    padded = list(table) + [tuple([0] * (1 << low))] * (-len(table) % k)
    payload = tuple((tuple(padded[a:a + k]) for a in range(0, len(padded), k)))
    masksets = [tuple((m for m in range(1 << low) if any((row[m] for row in p)))) for p in payload]
    loads = [max((m.bit_count() for m in masks), default=0) for masks in masksets]
    length = len(payload)

    def uniform(lo, span):
        return all((v == payload[lo] for v in payload[lo + 1:min(lo + span, length)]))

    def skip(lo, span):
        half = span // 2
        count = min(lo + span, length) - (lo + half)
        return count > 0 and payload[lo:lo + count] == payload[lo + half:lo + half + count]
    root = r._content_tree(0, 1 << 16 - low - log_window, length, uniform, skip, lambda lo: loads[lo])
    walk_cost, policy = r._walk_policy(root, hold)
    leaves = []

    def collect(node):
        if node.kind == 'leaf':
            leaves.append(node.lo)
        else:
            for child in node.kids:
                collect(child)
    collect(root)
    poly_cost = sum((len(prefixes(masksets[lo], monomial_order(masksets[lo], low))) for lo in leaves))
    cost = walk_cost + poly_cost + (k - 1 if cleanup else 0)
    return dict(root=root, policy=policy, payload=payload, masks=masksets, cost=cost, walk_cost=walk_cost, polynomial_cost=poly_cost, leaves=len(leaves), low=low, log_window=log_window, hold=hold)

def lookup(b, idx, target, low, hold):
    r = ref()
    p = plan(low, 0, hold, False)

    def leaf(lo, ctrl):
        coeff = p['payload'][lo][0]
        monomials(b, ctrl, idx[:low], p['masks'][lo], lambda q, m: xor_word(b, q, coeff[m], target))
    with b.phase('anf-alias/lookup'):
        r._policy_walk(b, p['root'], p['policy'], hold, lambda n: idx[low + n.span.bit_length() - 2], leaf)

def repair(b, idx, outcomes, low, log_window, hold):
    r = ref()
    p = plan(low, log_window, hold, True)
    k = 1 << log_window
    mid = idx[low:low + log_window]
    with b.phase('anf-alias/repair-prep'):
        u = b.qubits(k)
        b.x(u[0])
        for j in reversed(range(log_window)):
            for s in range(0, k, 2 << j):
                b.cswap(mid[j], u[s], u[s + (1 << j)])
    cache = {0: None}

    def parity(word):
        if word not in cache:
            cache[word] = xor_outcomes([outcomes[j] for j in range(32) if word >> j & 1])
        return cache[word]

    def leaf(lo, ctrl):

        def emit(q, mask):
            for v, row in enumerate(p['payload'][lo]):
                outcome = parity(row[mask])
                if outcome is not None:
                    b.cz(q, u[v], cond=outcome)
        monomials(b, ctrl, idx[:low], p['masks'][lo], emit)
    with b.phase('anf-alias/repair-fixup'):
        r._policy_walk(b, p['root'], p['policy'], hold, lambda n: idx[low + log_window + n.span.bit_length() - 2], leaf)
    with b.phase('anf-alias/repair-unprep'):
        for j in range(log_window):
            for s in range(0, k, 2 << j):
                v = u[s + (1 << j)]
                b.cx(v, u[s])
                b.and_release(v, mid[j], u[s])
        b.x(u[0])
        b.recycle(u[0])

def build(configuration):
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs['i'], regs['sigma'], regs['x'])
    alias = b.qubits(32)
    keep, sel = (alias[:16], alias[16:])
    l = configuration['lookup']
    f = configuration['repair']
    lookup(b, idx, alias, l['low'], l['hold'])
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
    repair(b, idx, outcomes, f['low'], f['log_window'], f['hold'])
    assert b.active_qubits == 72
    summary = b.phase_summary()
    assert summary['total_emitted_toffoli'] == configuration['toffoli']
    assert summary['peak_qubits'] <= configuration['peak_budget']
    return (b, summary)
