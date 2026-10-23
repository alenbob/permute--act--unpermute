"""Explicit PAU schedules, including nonadjacent fermionic transposition signs.

All prepared addresses are classical table fields, loaded coherently by QROM.
The pair network follows the current manuscript, including its even-size
exception; it is not the orientation truth table in the supplied draft.
"""
from functools import lru_cache
N = 40
MASK = (1 << N) - 1

def support(f, z):
    flips = [j for j in range(N) if f >> j & 1]
    assert len(flips) % 2 == 0
    jw = 0
    for a, b in zip(flips[::2], flips[1::2]):
        jw ^= (1 << b) - 1 ^ (1 << a + 1) - 1
    return [j for j in range(N) if (f | (z ^ jw) & ~f) >> j & 1]

def pad_support(active, policy='low'):
    selected = list(active)
    candidates = [j for j in range(N) if j not in selected]
    if policy == 'near':
        candidates.sort(key=lambda j: (min((abs(j - k) for k in selected)), j))
    elif policy == 'high':
        candidates.reverse()
    selected += candidates[:4 - len(selected)]
    return sorted(selected)

def transform(f, z, sign, data):
    """Conjugate (-1)^sign X^f Z^z by a fermionic mode permutation."""
    pi = [0] * N
    for new, old in enumerate(data):
        pi[old] = new
    ff = zz = 0
    flips = [i for i in range(N) if f >> i & 1]
    for i in range(N):
        zi = z >> i & 1 ^ sum(((i < j) != (pi[i] < pi[j]) for j in flips if i != j)) & 1
        ff |= (f >> i & 1) << pi[i]
        zz |= zi << pi[i]
    sign ^= sum((pi[i] > pi[j] for a, i in enumerate(flips) for j in flips[a + 1:])) & 1
    return (ff, zz, sign)

def leaf_number(n, value):
    """Invertible linear relabeling sending n/2-1 to 1."""
    last = n // 2 - 1
    pivot = (last & -last).bit_length() - 1

    def exchange(v):
        d = (v ^ v >> pivot) & 1
        return v ^ d ^ d << pivot
    v, end = (exchange(value), exchange(last))
    return v ^ (end ^ 1 if v & 1 else 0)

@lru_cache(None)
def pair_skeleton(n):
    out = [(a, a + 1, ('orient', a // 2)) for a in range(2, n - 2, 2)]
    out.append((1, n - 2, ('special',)))
    for parity in (0, 1):
        nodes = {leaf_number(n, v): 2 * v + parity for v in range(n // 2)}
        for t in range((n // 2 - 1).bit_length()):
            merged = {}
            for key in sorted({k >> 1 for k in nodes}):
                left, right = (nodes.get(2 * key), nodes.get(2 * key + 1))
                if left is not None and right is not None:
                    out.append((left, right, ('tree', parity, t, t == 0 and key == 0)))
                merged[key] = left if left is not None else right
            nodes = merged
    assert len(out) == 3 * (n - 2) // 2
    return out

def pair_controls(n, p, q):
    m = (n - 1).bit_length()
    psi = {m: 1 ^ p & 1 ^ q & 1}
    for t in range(m - 1, 1, -1):
        psi[t] = psi[t + 1] & (1 ^ p >> t & 1 ^ q >> t & 1)
    controls = []
    for _, _, spec in pair_skeleton(n):
        if spec[0] == 'orient':
            r = spec[1]
            c = p & 1 ^ sum((((r >> t - 2 ^ r >> t - 1) & 1) * psi[t] for t in range(2, m + 1))) & 1
        elif spec[0] == 'special':
            c = 1 ^ q & 1 ^ p & 1 & (q & 1)
        else:
            _, parity, t, special = spec
            address = p if parity == 0 else q
            c = leaf_number(n, address // 2) >> t & 1
            if special:
                c ^= p & 1 if parity == 0 else 1 ^ q & 1
        controls.append(c)
    return controls

@lru_cache(None)
def route(selected, family='pair', order=0):
    """Return full permutation, native address word and controlled switches."""
    selected = list(selected)
    if family == 'pair':
        partitions = [(0, 1, 2, 3), (0, 2, 1, 3), (0, 3, 1, 2)]
        perm = partitions[order % 3]
        selected = [selected[i] for i in perm]
        if order >= 3:
            selected = selected[2:] + selected[:2]
    elif order:
        selected.reverse()
    data = list(range(N))
    word = 0
    switches = []
    if family == 'pair':
        for stage in range(2):
            offset, n = (2 * stage, N - 2 * stage)
            p, q = sorted((data.index(a) - offset for a in selected[2 * stage:2 * stage + 2]))
            word |= (p | q << 6) << 12 * stage
            for (a, b, spec), c in zip(pair_skeleton(n), pair_controls(n, p, q)):
                a, b = (a + offset, b + offset)
                switches.append((a, b, c))
                if c:
                    data[a], data[b] = (data[b], data[a])
            assert set(data[offset:offset + 2]) == set(selected[2 * stage:2 * stage + 2])
    else:
        for stage, a in enumerate(selected):
            address = data.index(a) - stage
            word |= address << 6 * stage
            for t in range((N - stage - 1).bit_length()):
                step = 1 << t
                for u in range(0, N - stage, 2 * step):
                    if u + step >= N - stage:
                        continue
                    c = address >> t & 1
                    u, v = (u + stage, u + step + stage)
                    switches.append((u, v, c))
                    if c:
                        data[u], data[v] = (data[v], data[u])
            assert data[stage] == a
    return (data, word, switches)

def labels(masks, words, family='pair', order=0, padding='low'):
    result = []
    for mask, alias in zip(masks, words):
        f, z = (mask & MASK, mask >> N & MASK)
        sign = (mask >> 80 ^ alias >> 33) & 1
        if family == 'direct':
            result.append(f | z << 40 | sign << 80)
            continue
        active = support(f, z)
        assert 1 <= len(active) <= 4
        data, address, _ = route(tuple(pad_support(active, padding)), family, order)
        ff, zz, s = transform(f, z, sign, data)
        assert ff | zz < 16
        result.append(address | ff << 24 | zz << 28 | s << 32)
    return result

def fermionic_swap(b, control, x, i, j):
    """One CCX opening, exact outcome-corrected close, all JW parity CZs."""
    i, j = sorted((i, j))
    b.cx(x[j], x[i])
    work = b.and_compute(control, x[i])
    b.cz(control, x[j])
    b.cz(work, x[j])
    for k in range(i + 1, j):
        b.cz(work, x[k])
    b.cx(work, x[j])
    b.and_release(work, control, x[i])
    b.cx(x[j], x[i])

def parity_wire(b, wires, constant=0):
    q = b.qubit()
    if constant:
        b.x(q)
    for w in wires:
        b.cx(w, q)
    return q

def un_parity(b, q, wires, constant=0):
    for w in reversed(wires):
        b.cx(w, q)
    if constant:
        b.x(q)
    b.recycle(q)

def pair_quantum_controls(b, n, p, q):
    m = (n - 1).bit_length()
    psi = {m: parity_wire(b, [p[0], q[0]], 1)}
    trail = []
    for t in range(m - 1, 1, -1):
        eq = parity_wire(b, [p[t], q[t]], 1)
        psi[t] = b.and_compute(psi[t + 1], eq)
        trail.append((psi[t], psi[t + 1], eq, t))
    prod = b.and_compute(p[0], q[0])
    controls = []
    for a, c, spec in pair_skeleton(n):
        if spec[0] == 'orient':
            r = spec[1]
            wires = [p[0]] + [psi[t] for t in range(2, m + 1) if (r >> t - 2 ^ r >> t - 1) & 1]
            const = 0
        elif spec[0] == 'special':
            wires, const = ([q[0], prod], 1)
        else:
            _, parity, t, special = spec
            addr = p if parity == 0 else q
            wires = [addr[k + 1] for k in range(m - 1) if leaf_number(n, 1 << k) >> t & 1]
            const = 0
            if special:
                wires = wires + [addr[0]]
                const = parity
        controls.append((a, c, wires, const))

    def cleanup():
        b.and_release(prod, p[0], q[0])
        for dst, src, eq, t in reversed(trail):
            b.and_release(dst, src, eq)
            un_parity(b, eq, [p[t], q[t]], 1)
        un_parity(b, psi[m], [p[0], q[0]], 1)
    return (controls, cleanup)

def apply_pau(b, label, x, family):
    if family == 'direct':
        for j in range(N):
            b.cz(label[40 + j], x[j])
        for j in range(N):
            b.cx(label[j], x[j])
        b.z(label[80])
        return
    controls = []
    cleanup = []
    if family == 'pair':
        for stage in range(2):
            r, close = pair_quantum_controls(b, N - 2 * stage, label[12 * stage:12 * stage + 6], label[12 * stage + 6:12 * stage + 12])
            controls += [(a + 2 * stage, c + 2 * stage, w, k) for a, c, w, k in r]
            cleanup.append(close)
    else:
        for stage in range(4):
            for t in range((N - stage - 1).bit_length()):
                for u in range(0, N - stage, 2 << t):
                    if u + (1 << t) < N - stage:
                        controls.append((u + stage, u + (1 << t) + stage, [label[6 * stage + t]], 0))

    def run(schedule):
        for a, c, w, k in schedule:
            ctrl = parity_wire(b, w, k)
            fermionic_swap(b, ctrl, x, a, c)
            un_parity(b, ctrl, w, k)
    with b.phase('pau/route-in'):
        run(controls)
    with b.phase('pau/target'):
        for j in range(4):
            b.cz(label[28 + j], x[j])
        for j in range(4):
            b.cx(label[24 + j], x[j])
        b.z(label[32])
    with b.phase('pau/route-out'):
        run(reversed(controls))
    for close in reversed(cleanup):
        close()
