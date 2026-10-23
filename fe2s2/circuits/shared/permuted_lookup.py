"""Content-pruned lookup in an arbitrary address-bit permutation.

Only addresses >= len(values) are unspecified. In particular, an in-domain
zero word remains specified. The emitted walker is the pinned native DP.
"""
from functools import lru_cache
import numpy as np
from tradeoff import ref
from uncompute.gadgets import xor_word

def tokens(values, bits):
    ids = {}
    words = []
    result = np.full(1 << bits, -1, dtype=np.int32)
    for i, value in enumerate(values):
        if value not in ids:
            ids[value] = len(words)
            words.append(value)
        result[i] = ids[value]
    return (result, tuple(words))

@lru_cache(64)
def tree(values, order):
    n = len(order)
    assert sorted(order) == list(range(n)) and len(values) <= 1 << n
    ids, words = tokens(values, n)
    ids = ids.reshape((2,) * n).transpose(tuple((n - 1 - j for j in order))).reshape(-1)
    r = ref()

    def make(v):
        valid = v[v >= 0]
        if len(valid) == 0:
            return r._WNode('leaf', lo=len(words), span=len(v))
        if np.all(valid == valid[0]):
            return r._WNode('leaf', lo=int(valid[0]), span=len(v))
        h = len(v) // 2
        a, c = (v[:h], v[h:])
        if np.all((a < 0) | (c < 0) | (a == c)):
            return r._WNode('skip', (make(np.where(a < 0, c, a)),), span=len(v))
        return r._WNode('two', (make(a), make(c)), span=len(v))
    return (make(ids), words + (0,))

def load(b, addr, values, target, hold, order):
    order = tuple(order)
    root, words = tree(tuple(values), order)
    if root.kind == 'leaf':
        xor_word(b, None, words[root.lo], target)
        return
    cost, policy = ref()._walk_policy(root, hold)
    assert cost < ref()._INF, ('infeasible lookup hold', hold, order)

    def leaf(lo, ctrl):
        xor_word(b, ctrl, words[lo], target)
    ref()._policy_walk(b, root, policy, hold, lambda node: addr[order[len(order) - node.span.bit_length() + 1]], leaf)
