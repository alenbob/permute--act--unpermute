"""Executable complete alias--PAU SELECT--unlookup in the paper's gate model.

No resource formula stands in for a decoder: every lookup, swap, comparator,
measurement and phase repair is emitted through the pinned upstream Builder.
"""
import argparse
import gc
import json
import os
from functools import lru_cache
from pathlib import Path
from common import HERE, inputs, upstream
from routing import labels, apply_pau
from uncompute import Builder
from uncompute.gadgets import walk, xor_word, erase_register, berry_ku, declare_registers
from uncompute.gadgets.qrom import swap_perm, phase_fixup, xor_outcomes

def compress(values):
    """Affine GF(2) encoding; decoding is X/CNOT only, with exact roundtrip."""
    constant = values[0]
    pivots = {}
    basis = []
    encoded = []
    for v in values:
        rem = v ^ constant
        code = 0
        while rem:
            p = rem.bit_length() - 1
            if p not in pivots:
                k = len(basis)
                basis.append(rem)
                pivots[p] = (rem, 1 << k)
            row, coeff = pivots[p]
            rem ^= row
            code ^= coeff
        encoded.append(code)
    for v, c in zip(values, encoded):
        out = constant
        for j, base in enumerate(basis):
            if c >> j & 1:
                out ^= base
        assert out == v
    return (encoded, basis, constant)

def decode(b, encoded, basis, constant, width):
    out = b.qubits(width)
    xor_word(b, None, constant, out)
    for q, w in zip(encoded, basis):
        xor_word(b, q, w, out)
    return out

def undec(b, out, encoded, basis, constant):
    for q, w in reversed(list(zip(encoded, basis))):
        xor_word(b, q, w, out)
    xor_word(b, None, constant, out)
    for q in reversed(out):
        b.recycle(q)

def blocked_lookup(b, addr, values, width, k, name, erasure='high'):
    """Clean SELECT-SWAP bank, retained until matched erasure.

    Undo the word swaps, then erase the entire bank against the high address.
    This confines Berry's phase-repair table to ceil(L/k) rows.
    """
    assert k > 0 and k & k - 1 == 0
    log = k.bit_length() - 1
    high = addr[log:]
    count = (len(values) + k - 1) // k
    length = len(values)
    values = list(values) + [0] * (count * k - len(values))
    chunks = [sum((values[h * k + j] << width * j for j in range(k))) for h in range(count)]
    bank = b.qubits(width * k)

    def leaf(ctrl, h):
        xor_word(b, ctrl, chunks[h], bank)
    with b.phase(name + '/lookup'):
        walk(b, high, None, len(high) - 1, 0, 1 << len(high), 0, count, leaf)
    schedule = [(addr[t], width * s + j, width * (s + (1 << t)) + j) for t in range(log) for s in range(0, k, 2 << t) for j in range(width)]
    with b.phase(name + '/swap'):
        for c, a, d in schedule:
            b.cswap(c, bank[a], bank[d])

    def close():
        if erasure == 'full':
            with b.phase(name + '/measure-permuted-bank'):
                outcomes = [b.hmr(q) for q in bank]
                for q in reversed(bank):
                    b.recycle(q)
                caches = [{0: None} for _ in range((len(outcomes) + 11) // 12)]

                def partial(group, mask):
                    cache = caches[group]
                    if mask not in cache:
                        bit = mask & -mask
                        rest = partial(group, mask ^ bit)
                        out = outcomes[12 * group + bit.bit_length() - 1]
                        cache[mask] = out if rest is None else rest ^ out
                    return cache[mask]
                permutations = swap_perm(k)
                fix = {}
                for av in range(length):
                    base, low = (av // k * k, av % k)
                    word = sum((values[base + j] << width * s for s, j in enumerate(permutations[low])))
                    terms = []
                    group = 0
                    while word:
                        part = word & 4095
                        if part:
                            terms.append(partial(group, part))
                        word >>= 12
                        group += 1
                    out = xor_outcomes(terms)
                    if out is not None:
                        fix[av] = out
                phase_fixup(b, addr, length, berry_ku(length), fix, phase=name + '/full-repair')
            return
        with b.phase(name + '/unswap'):
            for c, a, d in reversed(schedule):
                b.cswap(c, bank[a], bank[d])
        erase_register(b, bank, high, count, chunks, berry_ku(count), range(count), name + '/erase', free=True, phase=name + '/repair')
    return (bank[:width], close)

@lru_cache(None)
def prepared(family='pair', order=0, padding='low'):
    contract, table, words, masks = inputs()
    native = labels(masks, words, family, order, padding)
    encoded, basis, constant = compress(native)
    return (native, encoded, basis, constant)

def build(family='pair', order=0, padding='low', alias_k=32, label_k=32, alias_method='blocked', erasure='full'):
    _, _, words, _ = inputs()
    if family != 'frame':
        native, encoded, basis, constant = prepared(family, order, padding)
    ref = upstream()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs['i'], regs['sigma'], regs['x'])
    if alias_method == 'blocked':
        alias, close_alias = blocked_lookup(b, idx, [w & 4294967295 for w in words], 32, alias_k, 'alias', erasure)
    else:
        alias = b.qubits(32)
        with b.phase('alias/published-lookup'):
            ref.lookup_walk(b, list(idx[::-1]), lambda lo, ctrl: xor_word(b, ctrl, ref.DATA[lo], alias))

        def close_alias():
            mk = ref.erase_wires(b, alias[:16])
            ma = ref.erase_wires(b, alias[16:])
            for q in alias:
                b.recycle(q)
            ref.b2_fixup(b, idx, mk, ma)
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        ref.compare_into(b, sigma, keep, flag)
        for i in range(16):
            b.cswap(flag, sel[i], idx[i])
    if family == 'frame':
        ref.select_pauli(b, sel, x)
    else:
        compressed, close_label = blocked_lookup(b, sel, encoded, len(basis), label_k, 'label', erasure)
        with b.phase('pau/decode-controls'):
            label = decode(b, compressed, basis, constant, 81 if family == 'direct' else 33)
            apply_pau(b, label, x, family)
            undec(b, label, compressed, basis, constant)
        close_label()
    with b.phase('alias/restore'):
        for i in range(16):
            b.cswap(flag, sel[i], idx[i])
        ref.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    close_alias()
    assert b.active_qubits == 72
    return (b, regs)
