"""Skip control construction for a zero XOR payload, retaining its constraints.

The planner/emitter below are the pinned native walk with one explicit addition:
an empty payload leaf has zero cost and emits no operations. Zero input rows
remain specified in the tree, so nonzero siblings keep all address controls.
This is different from treating a valid zero row as an out-of-domain don't-care.
"""
from functools import lru_cache
from tradeoff import ref
from uncompute.gadgets import xor_word
import adaptive_lookup as adaptive
from permuted_lookup import tree as fixed_tree
_INF = ref()._INF
_chain_hold = ref()._chain_hold
_chain_unwind = ref()._chain_unwind
_acc_build = ref()._acc_build
_acc_teardown = ref()._acc_teardown

def _walk_policy(root, H):
    """-> (minimum walk ANDs under hold budget H, realizing choice per
    (node, r, t) state).  Leaf loads are the payload's own transient
    wires (plane ANDs), priced into feasibility.
    """
    memo = {}
    choice = {}

    def f(n, r, t):
        if n.kind == 'empty':
            return 0
        if t > r + 1:
            return _INF
        key = (id(n), r, t)
        v = memo.get(key)
        if v is not None:
            return v
        if n.kind == 'leaf':
            if t >= 2:
                v, ch = (_INF, None)
                if t - 1 + n.load <= r:
                    v, ch = (t - 1, ('chain',))
                if t - 1 <= r and 1 + n.load <= r and (2 * t - 3 < v):
                    v, ch = (2 * t - 3, ('acc',))
                choice[key] = ch
            else:
                v = 0 if n.load <= r else _INF
        elif n.kind in ('skip', 'one'):
            v = f(n.kids[0], r, t)
            ch = ('desc',)
            if t >= 2 and t - 1 <= r:
                alt = 2 * t - 3 + f(n.kids[0], r - 1, 1)
                if alt < v:
                    v, ch = (alt, ('conv-desc',))
            choice[key] = ch
        else:
            left, right = n.kids
            best, ch = (_INF, None)

            def opts(r0, t0):
                res = []
                if t0 == 0:
                    res.append((f(left, r0, 1) + f(right, r0, 1), 'bare'))
                elif t0 == 1 and r0 >= 1:
                    res.append((1 + f(left, r0 - 1, 1) + f(right, r0 - 1, 1), 'split'))
                if t0 >= 1:
                    res.append((f(left, r0, t0 + 1) + f(right, r0, t0 + 1), 'lit'))
                return res
            for c, name in opts(r, t):
                if c < best:
                    best, ch = (c, (name,))
            if t >= 2 and t - 1 <= r:
                for c, name in opts(r - 1, 1):
                    if 2 * t - 3 + c < best:
                        best, ch = (2 * t - 3 + c, ('conv', name))
            choice[key] = ch
            v = best
        memo[key] = v
        return v
    return (f(root, H, 0), choice)

def _policy_walk(b, root, choice, H, bit_of, leaf_body):
    """Emit the walk the DP policy prescribes, byte-idiom-identical to
    the chain/accumulator helpers above.
    """

    def go(n, r, lits):
        if n.kind == 'empty':
            return
        t = len(lits)
        if n.kind == 'leaf':
            assert t >= 1
            if t == 1:
                w, pol = lits[0]
                if not pol:
                    b.x(w)
                leaf_body(n.lo, w)
                if not pol:
                    b.x(w)
            elif choice[id(n), r, t][0] == 'chain':
                acc, chain = _chain_hold(b, lits)
                leaf_body(n.lo, acc)
                _chain_unwind(b, chain)
            else:
                acc = _acc_build(b, lits)
                leaf_body(n.lo, acc)
                _acc_teardown(b, lits, acc)
            return
        if n.kind in ('skip', 'one'):
            if choice.get((id(n), r, t), ('desc',))[0] == 'conv-desc':
                acc = _acc_build(b, lits)
                go(n.kids[0], r - 1, [(acc, True)])
                _acc_teardown(b, lits, acc)
            else:
                go(n.kids[0], r, lits)
            return
        ch = choice[id(n), r, t]
        if ch[0] == 'conv':
            acc = _acc_build(b, lits)
            split(n, r - 1, [(acc, True)], ch[1])
            _acc_teardown(b, lits, acc)
        else:
            split(n, r, lits, ch[0])

    def split(n, r, lits, action):
        left, right = n.kids
        hb = bit_of(n)
        if action == 'bare':
            b.x(hb)
            go(left, r, [(hb, True)])
            b.x(hb)
            go(right, r, [(hb, True)])
        elif action == 'split':
            w, pol = lits[0]

            def flip():
                if not pol:
                    b.x(w)
                b.cx(w, anc)
                if not pol:
                    b.x(w)
            anc = b.and_compute(w, hb, pol=(pol, True))
            b.claim('hold', [anc])
            go(right, r - 1, [(anc, True)])
            flip()
            go(left, r - 1, [(anc, True)])
            flip()
            b.release('hold', [anc])
            b.and_release(anc, w, hb, pol=(pol, True))
        else:
            go(left, r, lits + [(hb, False)])
            go(right, r, lits + [(hb, True)])
    go(root, H, [])

@lru_cache(12)
def tree(values, order, kind='fixed', exact=6, tie='priority'):
    source, words = fixed_tree(values, order) if kind == 'fixed' else adaptive.tree(values, order, exact, tie)

    def clone(n):
        bit = order[len(order) - n.span.bit_length() + 1] if n.kind != 'leaf' and kind == 'fixed' else getattr(n, 'bit', 0)
        node = adaptive.Node('empty' if n.kind == 'leaf' and words[n.lo] == 0 else n.kind, tuple((clone(c) for c in n.kids)), n.lo, n.span, bit)
        return node
    return (clone(source), words)

def load(b, address, values, target, hold, order, kind='fixed', exact=6, tie='priority'):
    root, words = tree(tuple(values), tuple(order), kind, exact, tie)
    if root.kind == 'empty':
        return
    if root.kind == 'leaf':
        xor_word(b, None, words[root.lo], target)
        return
    cost, policy = _walk_policy(root, hold)
    assert cost < _INF
    _policy_walk(b, root, policy, hold, lambda n: address[n.bit], lambda number, control: xor_word(b, control, words[number], target))

def project(values, order, hold=14, kind='fixed', exact=6, tie='priority'):
    from uncompute import Builder
    root, _ = tree(tuple(values), tuple(order), kind, exact, tie)
    cost, policy = _walk_policy(root, hold)
    if cost >= _INF:
        return None
    b = Builder()
    addr = b.qubits(len(order))
    if root.kind not in ('leaf', 'empty'):
        _policy_walk(b, root, policy, hold, lambda n: addr[n.bit], lambda *a: None)
    s = b.phase_summary()
    assert s['total_emitted_toffoli'] == cost
    return dict(toffoli=cost, scratch=s['peak_qubits'] - len(addr))
