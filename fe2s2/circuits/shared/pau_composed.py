"""Published PAU action with a composed 123-swap forward permutation.

The selected basis/order is exhaustive-best among all 256 minimum-weight
bases and their 720 orders, and a fixed point under all single-generator
exchanges with every order retuned. This is a finite circuit-family result.
"""
from functools import lru_cache
from pau_permutation_core import schedule, controls, ONE
from routing import parity_wire, un_parity, fermionic_swap
BASIS = (8, 16, 32, 14, 44, 1)
ORDER = (0, 2, 5, 4, 1, 3)

@lru_cache(None)
def plan():
    original, reduced, trace = schedule(BASIS, ORDER)
    assert len(original) == 128 and len(reduced) == 123 and (len(trace) == 5)
    return (tuple(reduced), tuple(controls(BASIS)))

def local_select(b, flags, label, x):
    gates, group_controls = plan()
    wiremap = {7 + j: [q] for j, q in enumerate(label)}
    closes = []
    for i, mask in enumerate(group_controls):
        wiremap[i] = [q for j, q in enumerate(flags) if mask >> j & 1]
    for stage in range(2):
        p = label[10 * stage:10 * stage + 5]
        q = label[10 * stage + 5:10 * stage + 10]
        psi = {5: parity_wire(b, [p[0], q[0]], 1)}
        for t in range(4, 1, -1):
            eq = parity_wire(b, [p[t], q[t]], 1)
            psi[t] = b.and_compute(psi[t + 1], eq)
            un_parity(b, eq, [p[t], q[t]], 1)
            if t == 4:
                un_parity(b, psi[5], [p[0], q[0]], 1)
            wiremap[40 + 3 * stage + t - 2] = [psi[t]]
        product = b.and_compute(p[0], q[0])
        wiremap[46 + stage] = [product]

        def close(psi=psi, p=p, q=q, product=product):
            b.and_release(product, p[0], q[0])
            for t in range(2, 5):
                eq = parity_wire(b, [p[t], q[t]], 1)
                parent = psi[t + 1] if t < 4 else parity_wire(b, [p[0], q[0]], 1)
                b.and_release(psi[t], parent, eq)
                if t == 4:
                    un_parity(b, parent, [p[0], q[0]], 1)
                un_parity(b, eq, [p[t], q[t]], 1)
        closes.append(close)

    def run(sequence):
        for a, c, expression in sequence:
            wires = set()
            for bit in range(48):
                if expression >> bit & 1:
                    wires.symmetric_difference_update(wiremap[bit])
            wires = sorted(wires)
            constant = int(bool(expression & ONE))
            control = parity_wire(b, wires, constant)
            fermionic_swap(b, control, x, a, c)
            un_parity(b, control, wires, constant)
    with b.phase('spin/composed-permutation'):
        run(gates)
    with b.phase('spin/local-target'):
        b.cz(label[30], flags[3])
        b.cz(label[30], flags[4])
        a, c, d = (flags[2], flags[3], flags[4])
        b.cx(a, c)
        b.cx(a, d)
        v = b.and_compute(c, d)
        b.cx(a, v)
        b.cz(v, label[31])
        b.cx(a, v)
        b.and_release(v, c, d)
        b.cx(a, d)
        b.cx(a, c)
        b.cz(label[32], flags[1])
        for j in range(4):
            b.cz(label[25 + j], x[j])
            b.ccz(flags[1], label[21 + j], x[j])
        for j in range(4):
            b.cx(label[21 + j], x[j])
        b.z(label[29])
    with b.phase('spin/composed-inverse'):
        run(reversed(gates))
    for close in reversed(closes):
        close()
