"""Content-exact lookup trees with a separate variable order in each branch.

All specified input rows remain exact; only out-of-domain addresses are don't
cares. A greedy unique-word bound chooses wide splits. Small residual cubes
search every next bit until the distinct-word lower bound is reached. The
pinned native walker still counts every AND and measurement cleanup.
"""
from functools import lru_cache
import numpy as np
from permuted_lookup import tokens
from tradeoff import ref
from uncompute.gadgets import xor_word

class Node:
    __slots__ = ('kids', 'kind', 'lo', 'load', 'span', 'bit', 'branches')

    def __init__(self, kind, kids=(), lo=0, span=0, bit=0):
        self.kind, self.kids, self.lo, self.span, self.bit = (kind, kids, lo, span, bit)
        self.load = 0
        self.branches = int(kind == 'two') + sum((c.branches for c in kids))

@lru_cache(12)
def tree(values, order, exact=6, tie='priority'):
    order = tuple(order)
    n = len(order)
    ids, words = tokens(values, n)
    memo = {}

    def make(v, bits):
        valid = v[v >= 0]
        unique = np.unique(valid)
        if len(unique) <= 1:
            return Node('leaf', lo=int(unique[0]) if len(unique) else len(words), span=len(v))
        key = (bits, v.tobytes()) if len(bits) <= exact else None
        if key is not None and key in memo:
            return memo[key]
        candidates = []
        for j, bit in enumerate(bits):
            pair = v.reshape((-1, 2, 1 << j))
            a, c = (pair[:, 0, :].reshape(-1), pair[:, 1, :].reshape(-1))
            merged = np.where(a < 0, c, a)
            if np.all((a < 0) | (c < 0) | (a == c)):
                child = make(merged, bits[:j] + bits[j + 1:])
                out = Node('skip', (child,), span=len(v), bit=bit)
                if key is not None:
                    memo[key] = out
                return out
            na = len(np.unique(a[a >= 0]))
            nc = len(np.unique(c[c >= 0]))
            secondary = order.index(bit) if tie == 'priority' else abs(na - nc)
            candidates.append((na + nc, secondary, order.index(bit), j, a, c))
        candidates.sort(key=lambda t: t[:3])
        best = None
        for _, _, _, j, a, c in candidates if len(bits) <= exact else candidates[:1]:
            rest = bits[:j] + bits[j + 1:]
            out = Node('two', (make(a, rest), make(c, rest)), span=len(v), bit=bits[j])
            if best is None or out.branches < best.branches:
                best = out
            if best.branches == len(unique) - 1:
                break
        if key is not None:
            memo[key] = best
        return best
    return (make(ids, tuple(range(n))), words + (0,))

def load(b, address, values, target, hold, order, exact=6, tie='priority'):
    root, words = tree(tuple(values), tuple(order), exact, tie)
    if root.kind == 'leaf':
        xor_word(b, None, words[root.lo], target)
        return
    cost, policy = ref()._walk_policy(root, hold)
    assert cost < ref()._INF
    ref()._policy_walk(b, root, policy, hold, lambda n: address[n.bit], lambda number, control: xor_word(b, control, words[number], target))

def project(values, order, hold=14, exact=6, tie='priority'):
    from uncompute import Builder
    root, _ = tree(tuple(values), tuple(order), exact, tie)
    cost, policy = ref()._walk_policy(root, hold)
    if cost >= ref()._INF:
        return None
    b = Builder()
    addr = b.qubits(len(order))
    if root.kind != 'leaf':
        ref()._policy_walk(b, root, policy, hold, lambda n: addr[n.bit], lambda *a: None)
    s = b.phase_summary()
    assert s['total_emitted_toffoli'] == cost
    return dict(toffoli=cost, scratch=s['peak_qubits'] - len(addr), branches=root.branches)
