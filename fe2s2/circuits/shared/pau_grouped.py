"""Summer--Jamet PAU with a composed support permutation for Fe2S2.

The support permutation first removes a six-generator orbital/spin
permutation, then collects four sites with the two all-to-all pair routers.
The only system action between the permutation and its inverse is a local
four-qubit X/Z mask. No representative-Pauli walk or diagonal frame acts on
the system. All residual signs and local masks are decoded coherently.
"""
import argparse
import gc
import hashlib
import json
import os
from functools import lru_cache
from common import HERE
from tradeoff import ref, anf, repair as alias_repair
from routing import MASK, support, pad_support, route, transform, apply_pau
from routing import fermionic_swap, parity_wire, un_parity
from multiframe import basis_plan, GENERATORS
from plane_bank import content, load, decode_alias
from circuit import compress, decode, undec
from uncompute import Builder
from uncompute.gadgets import declare_registers, erase_register, berry_ku

def inplace_decode(b, encoded, basis, constant, width):
    """Invertible Clifford change of coordinates, with only width-rank zeros."""
    columns = list(basis)
    pivots = {}

    def add(v):
        z = v
        while z:
            j = z.bit_length() - 1
            if j not in pivots:
                pivots[j] = z
                return True
            z ^= pivots[j]
        return False
    for c in columns:
        assert add(c)
    for j in range(width):
        if add(1 << j):
            columns.append(1 << j)
    assert len(columns) == width
    matrix = [sum(((c >> j & 1) << k for k, c in enumerate(columns))) for j in range(width)]
    ops = []
    for j in range(width):
        if not matrix[j] >> j & 1:
            k = next((k for k in range(j + 1, width) if matrix[k] >> j & 1))
            for a, c in ((j, k), (k, j), (j, k)):
                matrix[c] ^= matrix[a]
                ops.append((a, c))
        for k in range(width):
            if k != j and matrix[k] >> j & 1:
                matrix[k] ^= matrix[j]
                ops.append((j, k))
    assert matrix == [1 << j for j in range(width)]
    extra = b.qubits(width - len(encoded))
    out = list(encoded) + extra
    for a, c in reversed(ops):
        b.cx(out[a], out[c])
    for j in range(width):
        if constant >> j & 1:
            b.x(out[j])

    def close():
        for j in range(width):
            if constant >> j & 1:
                b.x(out[j])
        for a, c in ops:
            b.cx(out[a], out[c])
        for q in reversed(extra):
            b.recycle(q)
    return (out, close)

@lru_cache(None)
def prepared(order=3, padding='high'):
    r = ref()
    values = []
    rows = []
    for gens, lo, hi in r.REGIONS:
        span = 1 << len(gens)
        for base in range(lo, hi, span):
            f, z = r._fz(base)
            target = pad_support(support(f, z), padding)
            data, address, _ = route(tuple(target), 'pair', order)
            for row in range(base, base + span):
                flags = [0] * 7
                for j, g in enumerate(gens):
                    flags[g] = row - base >> j & 1
                perm = list(range(40))
                for g in GENERATORS:
                    if flags[g]:
                        p = [j ^ 1 for j in range(40)] if g == 0 else r.PERM_MACH[g][0]
                        perm = [p[j] for j in perm]
                f, z = r._fz(row)
                ff, zz, sgn = transform(f, z, r.SIGN[row], perm)
                ff, zz, sgn = transform(ff, zz, sgn, data)
                assert ff | zz < 16, (row, base, ff, zz)
                values.append(address | ff << 24 | zz << 28 | sgn << 32)
                rows.append((base, tuple(flags), tuple(perm)))
    assert len(values) == r.L
    encoded, basis, constant = compress(values)
    return (tuple(values), tuple(encoded), tuple(basis), constant, tuple(rows))

def group_permute(b, flags, x, inverse=False):
    """A true fermionic mode permutation: no Clifford frame/gauge layer."""
    plan = basis_plan()
    seq = list(zip(plan['controls'], plan['swaps']))
    if inverse:
        seq.reverse()
    for gs, swaps in seq:
        wires = [flags[g] for g in gs]
        ctrl = parity_wire(b, wires)
        for i, j in reversed(swaps) if inverse else swaps:
            fermionic_swap(b, ctrl, x, i, j)
        un_parity(b, ctrl, wires)

def bank_lookup(b, addr, values, width, log_bank, hold, window, name):
    """ANF bank: combine into word zero and immediately erase other words."""
    planes = anf(tuple(values), log_bank)
    k = 1 << log_bank
    words = tuple((sum((v << width * j for j, v in enumerate(p))) for p in planes))
    bank = b.qubits(width * k)
    root = bank[:width]
    with b.phase(name + '/lookup'):
        load(b, addr[log_bank:], words, bank, hold)
    with b.phase(name + '/combine'):

        def go(mask, ctrl, start):
            for a, t in zip(bank[width * mask:width * (mask + 1)], root):
                b.ccx(ctrl, a, t)
            for j in range(start, log_bank):
                q = b.and_compute(ctrl, addr[j])
                go(mask | 1 << j, q, j + 1)
                b.and_release(q, ctrl, addr[j])
        for j in range(log_bank):
            go(1 << j, addr[j], j + 1)
    if k > 1:
        with b.phase(name + '/early-erase'):
            erase_register(b, bank[width:], addr[log_bank:], len(words), [v >> width for v in words], window, range(len(words)), name + '/discard', free=True, phase=name + '/early-repair')

    def close():
        erase_register(b, root, addr, len(values), values, window, range(len(values)), name + '/root', free=True, phase=name + '/final-repair')
    return (root, close)

def build(log_alias=1, log_label=1, hold=12, window=32, grouped=True):
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs[n] for n in ('i', 'sigma', 'x'))
    alias = decode_alias(b, idx, 2, log_alias, hold, 32)
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    if grouped:
        native, encoded, basis, constant, _ = prepared()
    else:
        from circuit import prepared as flat_prepared
        native, encoded, basis, constant = flat_prepared('pair', 3, 'high')
    compressed, close_label = bank_lookup(b, sel, encoded, len(basis), log_label, hold, window, 'pau-label')
    with b.phase('pau/affine-label'):
        label, close_affine = inplace_decode(b, compressed, basis, constant, 33)
    if grouped:
        with b.phase('pau/group-controls'):
            flags = b.qubits(7)
            r.xor_gate_flags(b, sel, flags)
        with b.phase('pau/group-in'):
            group_permute(b, flags, x)
    apply_pau(b, label, x, 'pair')
    if grouped:
        with b.phase('pau/group-out'):
            group_permute(b, flags, x, inverse=True)
        with b.phase('pau/group-controls-close'):
            r.xor_gate_flags(b, sel, flags)
            for q in reversed(flags):
                b.recycle(q)
    close_affine()
    close_label()
    with b.phase('alias/restore'):
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
        r.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    outcomes = [b.hmr(q) for q in alias]
    for q in reversed(alias):
        b.recycle(q)
    alias_repair(b, idx, outcomes, 2, 5, 40)
    assert b.active_qubits == 72
    s = b.phase_summary()
    s.update(family='published_pau_composed_support' if grouped else 'published_pau_two_pair_early', configuration=dict(log_alias=log_alias, log_label=log_label, hold=hold, window=window, grouped=grouped), prepared_width=len(basis), tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'])
    return (b, s)
