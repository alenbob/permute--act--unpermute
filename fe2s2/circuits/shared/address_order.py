"""Optimize coherent lookup variable order, with out-of-domain don't-cares.

Only addresses outside the pinned benchmark's valid domain are don't-cares.
All valid input amplitudes use a single coherent, fully emitted circuit.
"""
import argparse
import gc
import hashlib
import json
import os
from functools import lru_cache
from common import HERE
from tradeoff import ref, repair
from uncompute import Builder
from uncompute.gadgets import declare_registers, xor_word

def tree(values, order, materialize=False):
    depth = len(order)
    if not any(values):
        return (0, None)
    first = next((v for v in values if v))
    if all((not v or v == first for v in values)):
        return (0, ('leaf', first) if materialize else None)
    half = len(values) // 2
    left, right = (values[:half], values[half:])
    bit = order[-depth]
    rest = order[1:]
    if all((not a or not b or a == b for a, b in zip(left, right))):
        merged = tuple((a or b for a, b in zip(left, right)))
        return tree(merged, rest, materialize)
    a, lt = tree(left, rest, materialize)
    b, rt = tree(right, rest, materialize)
    return (1 + a + b, ('split', bit, lt, rt) if materialize else None)

def reorder(values, order):
    table = [0] * (1 << len(order))
    for i, value in enumerate(values):
        address = 0
        for bit in order:
            address = address << 1 | i >> bit & 1
        table[address] = value
    return tuple(table)

@lru_cache(None)
def score(order):
    nodes, _ = tree(reorder(ref().DATA, order), order)
    return max(0, nodes - 1)

def lookup(b, idx, target, order):
    cost, root = tree(reorder(ref().DATA, tuple(order)), tuple(order), True)

    def walk(node, ctrl):
        if node[0] == 'leaf':
            xor_word(b, ctrl, node[1], target)
            return
        _, bit, left, right = node
        q = idx[bit]
        if ctrl is None:
            b.x(q)
            walk(left, q)
            b.x(q)
            walk(right, q)
        else:
            anc = b.and_compute(ctrl, q)
            walk(right, anc)
            b.cx(ctrl, anc)
            walk(left, anc)
            b.cx(ctrl, anc)
            b.and_release(anc, ctrl, q)
    with b.phase('ordered-alias/lookup'):
        walk(root, None)
    return max(0, cost - 1)

def build(peak):
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs['i'], regs['sigma'], regs['x'])
    alias = b.qubits(32)
    keep, sel = (alias[:16], alias[16:])
    config = json.loads((HERE / 'results/address_order_search.json').read_text())
    cost = lookup(b, idx, alias, config['best_order'])
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
    choices = json.loads((HERE / 'results/tradeoff_search.json').read_text())['candidates']
    choice = next((x for x in choices if x['peak_budget'] == peak))
    f = choice['repair']
    repair(b, idx, outcomes, f['low'], f['log_window'], f['hold'])
    assert b.active_qubits == 72
    summary = b.phase_summary()
    assert summary['total_emitted_toffoli'] == cost + 3861 + 64 + f['cost']
    assert summary['peak_qubits'] <= peak
    summary.update(configuration=dict(lookup_order=config['best_order'], lookup_cost=cost, repair=f, peak_budget=peak), family='frame_select_ordered_alias', tq_cost=summary['peak_qubits'] * summary['total_emitted_toffoli'])
    return (b, summary)
