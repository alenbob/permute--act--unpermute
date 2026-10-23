"""Minimum-weight commuting permutation basis with native PAU switches.

All 63 nonidentity elements of the six-generator permutation subgroup are
enumerated. Greedy binary-matroid basis selection minimizes the sum of
transposition counts over this finite generator-basis family. Each controlled
fermionic transposition uses routing.fermionic_swap's one-AND construction.
The published Clifford gauges are preserved by an exact flag polynomial.
"""
import argparse
import contextlib
import hashlib
import json
import os
from functools import lru_cache
from common import HERE
from tradeoff import ref
from plane_bank import build as build_decoder
from routing import fermionic_swap, parity_wire, un_parity
GENERATORS = (0, 2, 3, 4, 5, 6)

@lru_cache(None)
def basis_plan():
    r = ref()
    perms = [list(range(40))]
    for mask in range(1, 64):
        j = (mask & -mask).bit_length() - 1
        g = GENERATORS[j]
        p = [v ^ 1 for v in range(40)] if g == 0 else r.PERM_MACH[g][0]
        perms.append([p[v] for v in perms[mask ^ 1 << j]])
    for p in perms:
        assert all((p[p[i]] == i for i in range(40)))
    swaps = [[(i, j) for i, j in enumerate(p) if i < j] for p in perms]
    pivots = {}
    basis = []
    for mask in sorted(range(1, 64), key=lambda m: (len(swaps[m]), m)):
        rem = mask
        while rem:
            bit = rem.bit_length() - 1
            if bit not in pivots:
                pivots[bit] = rem
                basis.append(mask)
                break
            rem ^= pivots[bit]
        if len(basis) == 6:
            break
    assert len(basis) == 6
    encode = {}
    for bits in range(64):
        mask = 0
        for j, g in enumerate(basis):
            if bits >> j & 1:
                mask ^= g
        encode[mask] = bits
    assert len(encode) == 64
    controls = [tuple((GENERATORS[i] for i in range(6) if encode[1 << i] >> j & 1)) for j in range(6)]
    return dict(basis=basis, controls=controls, swaps=[swaps[m] for m in basis], original_swaps=sum((len(swaps[1 << i]) for i in range(6))), optimized_swaps=sum((len(swaps[m]) for m in basis)), candidates=63, encode=encode)

def gauge(b, flags, x):
    """Exact residual Z gauge after all six permutations.

    A denotes modes 0..3 and B denotes modes 36..39. The residual is
    Z_A^(g3 XOR g4) Z_(A XOR B)^majority(g2,g3,g4). Majority needs one AND.
    """
    r = ref()
    assert r.sign_tables()[0] == {3: 15, 4: 15} and (not r.GAUGE_A)
    a, c, d = (flags[2], flags[3], flags[4])
    lin = parity_wire(b, [c, d])
    for j in range(4):
        b.cz(lin, x[j])
    un_parity(b, lin, [c, d])
    b.cx(a, c)
    b.cx(a, d)
    q = b.and_compute(c, d)
    b.cx(a, q)
    for j in list(range(4)) + list(range(36, 40)):
        b.cz(q, x[j])
    b.cx(a, q)
    b.and_release(q, c, d)
    b.cx(a, d)
    b.cx(a, c)

def conjugate(b, flags, x, inverse=False):
    plan = basis_plan()
    if inverse:
        gauge(b, flags, x)
    seq = list(zip(plan['controls'], plan['swaps']))
    if inverse:
        seq.reverse()
    for gs, swaps in seq:
        wires = [flags[g] for g in gs]
        ctrl = parity_wire(b, wires)
        for i, j in reversed(swaps) if inverse else swaps:
            fermionic_swap(b, ctrl, x, i, j)
        un_parity(b, ctrl, wires)
    ref().conjugate_c(b, flags[1], x)
    if not inverse:
        gauge(b, flags, x)

@contextlib.contextmanager
def use_multiframe():
    """Scoped emitter adapter; pinned vendor source and other builds are unchanged."""
    r = ref()
    old_open, old_close = (r.conjugate_open, r.conjugate_close)
    flags = {}

    def opened(b, ctrl, x, g):
        flags[g] = ctrl
        if g == 0:
            assert set(flags) == set(r.PRIORITY)
            conjugate(b, flags, x)

    def closed(b, ctrl, x, g):
        assert ctrl == flags[g]
        if g == 0:
            conjugate(b, flags, x, inverse=True)
    r.conjugate_open, r.conjugate_close = (opened, closed)
    try:
        yield
    finally:
        r.conjugate_open, r.conjugate_close = (old_open, old_close)

def build(hold=10, log_bank=1):
    with use_multiframe():
        b, s = build_decoder(2, log_bank, hold, 32)
    s['family'] = 'minimum_permutation_basis_plane_bank'
    s['configuration']['multiframe'] = basis_plan()
    for n in ('multiframe.py', 'routing.py'):
        pass
    return (b, s)
