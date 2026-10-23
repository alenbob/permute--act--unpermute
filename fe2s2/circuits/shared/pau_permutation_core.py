"""Compose the published PAU routers using stable XOR-controlled swaps.

Adjacent equal transpositions combine by XOR of their unchanged controls.
Disjoint mode transpositions commute, including their fermionic signs.
"""
from functools import lru_cache
from multiframe import GENERATORS
from tradeoff import ref
from routing import pair_skeleton, leaf_number
ONE = 1 << 63

def group():
    r = ref()
    perms = [tuple(range(40))]
    swaps = [()]
    for mask in range(1, 64):
        j = (mask & -mask).bit_length() - 1
        g = GENERATORS[j]
        p = [v ^ 1 for v in range(40)] if g == 0 else r.PERM_MACH[g][0]
        perm = tuple((p[v] for v in perms[mask ^ 1 << j]))
        perms.append(perm)
        assert all((perm[perm[i]] == i for i in range(40)))
        swaps.append(tuple(((i, j) for i, j in enumerate(perm) if i < j)))
    return (perms, swaps)

def pair_schedule(stage):
    p = [1 << 7 + 10 * stage + j for j in range(5)]
    q = [1 << 12 + 10 * stage + j for j in range(5)]
    psi = {t: 1 << 40 + 3 * stage + t - 2 for t in (2, 3, 4)}
    product = 1 << 46 + stage
    out = []
    for a, c, spec in pair_skeleton(20):
        if spec[0] == 'orient':
            rr = spec[1]
            control = p[0]
            for t in range(2, 6):
                if (rr >> t - 2 ^ rr >> t - 1) & 1:
                    control ^= p[0] ^ q[0] ^ ONE if t == 5 else psi[t]
        elif spec[0] == 'special':
            control = q[0] ^ product ^ ONE
        else:
            _, parity, t, special = spec
            addr = p if parity == 0 else q
            control = 0
            for k in range(4):
                if leaf_number(20, 1 << k) >> t & 1:
                    control ^= addr[k + 1]
            if special:
                control ^= addr[0] ^ (ONE if parity else 0)
        out.append((2 * a + stage, 2 * c + stage, control))
    return out

def tail():
    return pair_schedule(0) + [(4 + 2 * j, 1 + 2 * j, 1 << 7 + 20) for j in range(18)] + pair_schedule(1)

def reduce(gates):
    last = [None] * 40
    out = []
    trace = []
    for source, (a, b, c) in enumerate(gates):
        a, b = sorted((a, b))
        i = last[a]
        if i is not None and i == last[b]:
            old = out[i]
            assert (old[0], old[1]) == (a, b)
            assert all((not {a, b} & {x[0], x[1]} for x in out[i + 1:] if x[2]))
            trace.append(dict(source=source, kept=i, edge=[a, b], old_control=old[2], added_control=c))
            old[2] ^= c
            if not old[2]:
                last[a], last[b] = (old[3], old[4])
        else:
            out.append([a, b, c, last[a], last[b]])
            last[a] = last[b] = len(out) - 1
    return ([(a, b, c) for a, b, c, _, _ in out if c], trace)

def controls(basis):
    encoded = {}
    for bits in range(64):
        mask = 0
        for j, g in enumerate(basis):
            if bits >> j & 1:
                mask ^= g
        assert mask not in encoded
        encoded[mask] = bits
    return [sum((1 << GENERATORS[j] for j in range(6) if encoded[1 << j] >> i & 1)) for i in range(6)]

def schedule(basis, order):
    _, swaps = group()
    gates = [(a, b, 1 << i) for i in order for a, b in swaps[basis[i]]] + tail()
    reduced, trace = reduce(gates)
    return (gates, reduced, trace)
