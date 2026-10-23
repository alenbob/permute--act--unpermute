"""Share identical pair-router control products across the two PAU tails.

Affine label projections remain read-only and live until both tails finish.
Only the address products are shared: both system permutations, local actions,
inverse permutations, and all measurement corrections still execute.
"""
from contextlib import contextmanager
import compact_families as cf
import family_pau as fp
from routing import parity_wire, un_parity, pair_skeleton, leaf_number

@contextmanager
def reuse(b):
    old_views = cf.AffineViews
    old_pair = cf.pair_quantum_controls
    old_fp_pair = fp.pair_quantum_controls
    cache = {}
    trail = []

    def pair(builder, n, p, q):
        assert builder is b
        m = (n - 1).bit_length()
        key = (m, tuple(p), tuple(q))
        if key not in cache:
            psi = {m: parity_wire(b, [p[0], q[0]], 1)}
            local = []
            for t in range(m - 1, 1, -1):
                eq = parity_wire(b, [p[t], q[t]], 1)
                psi[t] = b.and_compute(psi[t + 1], eq)
                local.append((psi[t], psi[t + 1], eq, t))
            prod = b.and_compute(p[0], q[0])
            cache[key] = (psi, prod)

            def cleanup():
                b.and_release(prod, p[0], q[0])
                for dst, src, eq, t in reversed(local):
                    b.and_release(dst, src, eq)
                    un_parity(b, eq, [p[t], q[t]], 1)
                un_parity(b, psi[m], [p[0], q[0]], 1)
            trail.append(cleanup)
        psi, prod = cache[key]
        controls = []
        for a, c, spec in pair_skeleton(n):
            if spec[0] == 'orient':
                r = spec[1]
                wires = [p[0]] + [psi[t] for t in range(2, m + 1) if (r >> t - 2 ^ r >> t - 1) & 1]
                constant = 0
            elif spec[0] == 'special':
                wires, constant = ([q[0], prod], 1)
            else:
                _, parity, t, special = spec
                addr = p if parity == 0 else q
                wires = [addr[k + 1] for k in range(m - 1) if leaf_number(n, 1 << k) >> t & 1]
                constant = 0
                if special:
                    wires = wires + [addr[0]]
                    constant = parity
            controls.append((a, c, wires, constant))
        return (controls, lambda: None)

    class Views(old_views):

        def __init__(self, builder):
            super().__init__(builder)
            self.closures = []

        def acquire(self, expressions):
            wires, close = super().acquire(expressions)
            first = not self.closures
            self.closures.append(close)

            def flush():
                if first:
                    for fn in reversed(trail):
                        fn()
                    for fn in reversed(self.closures):
                        fn()
                    self.closures.clear()
                    trail.clear()
                    cache.clear()
            return (wires, flush)
    cf.AffineViews = Views
    cf.pair_quantum_controls = fp.pair_quantum_controls = pair
    try:
        yield
    finally:
        cf.AffineViews = old_views
        cf.pair_quantum_controls = old_pair
        fp.pair_quantum_controls = old_fp_pair
        assert not trail and (not cache), 'Router products were not cleaned before label measurement'
