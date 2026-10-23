"""Retain comparator borrows through SELECT, then erase them by measurement.

With k retained borrows, compute+cleanup uses 32-k native Toffolis instead
of 32. The last borrow itself is the selection flag, so SELECT gains k-1
live qubits. The low prefix is recomputed only when cleanup needs it.
Sigma and keep are restored exactly; they are deliberately unavailable to
intervening work while their upper bits are in the ripple representation.
"""
from tradeoff import ref

def open_compare(b, sigma, keep, retain):
    assert len(sigma) == len(keep) == 16 and 0 <= retain <= 16
    if not retain:
        flag = b.qubit()
        ref().compare_into(b, sigma, keep, flag)

        def close():
            ref().compare_into(b, sigma, keep, flag)
            b.recycle(flag)
        return (flag, close)
    split = 16 - retain

    def prefix(n):
        seed = b.qubit()
        prev = seed
        trail = []
        for j in range(n):
            a, c = (sigma[j], keep[j])
            b.x(a)
            b.cx(prev, a)
            b.cx(prev, c)
            q = b.and_compute(a, c)
            b.cx(prev, q)
            trail.append((q, a, c, prev))
            prev = q
        return (seed, trail, prev)

    def release(trail):
        for q, a, c, prev in reversed(trail):
            b.cx(prev, q)
            b.and_release(q, a, c)
            b.cx(prev, c)
            b.cx(prev, a)
            b.x(a)
    seed, trail, _ = prefix(16)
    flag = trail[-1][0]
    q, a, c, prev = trail[split]
    b.cx(prev, c)
    b.cx(prev, a)
    b.x(a)
    release(trail[:split])
    b.recycle(seed)

    def close():
        release(trail[split + 1:])
        seed, low, prev = prefix(split)
        b.x(a)
        b.cx(prev, a)
        b.cx(prev, c)
        b.cx(prev, q)
        b.and_release(q, a, c)
        b.cx(prev, c)
        b.cx(prev, a)
        b.x(a)
        release(low)
        b.recycle(seed)
    return (flag, close)
