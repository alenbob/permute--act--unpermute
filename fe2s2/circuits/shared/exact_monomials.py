"""Exact variable-order optimization of a shared monomial-prefix tree.

For an already visited variable set S, appending j creates one node for each
distinct m & S among masks m containing j. This increment depends only on S,
not its order. Subset dynamic programming therefore searches all n! orders in
O(n 2**n len(masks)) work, with lexicographic tie-breaking.
"""
from functools import lru_cache

@lru_cache(None)
def optimum(masks, low):
    masks = tuple(sorted(set((m for m in masks if m))))
    assert all((0 <= m < 1 << low for m in masks))
    full = (1 << low) - 1

    @lru_cache(None)
    def solve(used):
        if used == full:
            return (0, ())
        choices = []
        for j in range(low):
            if used >> j & 1:
                continue
            added = len({m & used for m in masks if m >> j & 1})
            cost, tail = solve(used | 1 << j)
            choices.append((added + cost, (j,) + tail))
        return min(choices)
    return solve(0)

def emit(b, ctrl, bits, masks, action, exact_wide=True):
    if len(bits) <= 6 or exact_wide:
        order = optimum(tuple(masks), len(bits))[1]
    else:
        order = tuple(sorted(range(len(bits)), key=lambda j: (-sum((m >> j & 1 for m in masks)), j)))
    tree = {}
    for mask in sorted(masks):
        node = tree
        for j in order:
            if mask >> j & 1:
                node = node.setdefault(j, {})
        node[None] = mask

    def go(node, control):
        if None in node:
            action(control, node[None])
        for j in sorted((k for k in node if k is not None)):
            q = b.and_compute(control, bits[j])
            go(node[j], q)
            b.and_release(q, control, bits[j])
    go(tree, ctrl)
