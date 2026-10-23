"""Exact phase repair with an in-place binary-to-one-hot window.

The address window is temporarily part of the unary register. At each split,
the original address bit is the XOR of all high children because the parents
are one-hot. Compute all but the final high child and obtain that final child
by CNOT parity. Reverse the process before releasing each temporary AND.
"""
from contextlib import contextmanager
import sys
from pau_banked import repair_plan
from tradeoff import ref
from exact_monomials import emit as monomials
from uncompute.gadgets import xor_outcomes
from refined_repair import repair_records as original_repair

def unary_window(b, address):
    seed = b.qubit()
    b.x(seed)
    unary = [seed]
    levels = []
    for bit in address:
        parents = list(unary)
        children = [b.and_compute(parent, bit) for parent in parents[:-1]]
        for child in children:
            b.cx(child, bit)
        children.append(bit)
        for parent, child in zip(parents, children):
            b.cx(child, parent)
        levels.append((bit, parents, children))
        unary = parents + children

    def close():
        for bit, parents, children in reversed(levels):
            for parent, child in zip(parents, children):
                b.cx(child, parent)
            for child in children[:-1]:
                b.cx(child, bit)
            for parent, child in reversed(list(zip(parents[:-1], children[:-1]))):
                b.and_release(child, parent, bit)
        b.x(seed)
        b.recycle(seed)
    return (unary, close)

def repair_records(b, address, outcomes, values, low, log_window, hold):
    root, policy, payload, masks, _ = repair_plan(tuple(values), low, log_window, hold)
    unary, close = unary_window(b, address[low:low + log_window])
    cache = {0: None}

    def parity(value):
        if value not in cache:
            cache[value] = xor_outcomes([o for j, o in enumerate(outcomes) if value >> j & 1])
        return cache[value]

    def leaf(lo, ctrl):

        def emit(q, mask):
            for j, v in enumerate(payload[lo]):
                outcome = parity(v[mask])
                if outcome is not None:
                    b.cz(q, unary[j], cond=outcome)
        monomials(b, ctrl, address[:low], masks[lo], emit)
    ref()._policy_walk(b, root, policy, hold, lambda n: address[low + log_window + n.span.bit_length() - 2], leaf)
    close()

@contextmanager
def use():
    """Replace only references to the pinned refined repair, then restore."""
    patched = []
    for module in list(sys.modules.values()):
        pass
    try:
        yield
    finally:
        for module in patched:
            module.repair_records = original_repair
