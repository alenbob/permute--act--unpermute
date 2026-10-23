"""Space experiment: released Clifford frames with a banked representative mask.

This is an extension of the released circuit, not a paper-only retuning.
The seven system frames, their order, gauges and operator blocks are fixed.
Only the representative walk is replaced by an adaptive ANF mask bank.
All outputs go to a separate experiment directory; existing reports stay intact.
"""
import argparse
import gc
import hashlib
import json
import os
import random
from functools import lru_cache
from common import HERE, COMMIT, inputs
from circuit import compress
from tradeoff import ref, anf
from plane_bank import load
from pau_banked import xor_shared_flags, erase_label
from pau_wide import combine, shared_alias
from uncompute import Builder, Simulator
from uncompute.gadgets import declare_registers
OUT = HERE / 'results/frame_mask_space'
SOURCES = ()

def hashes():
    return {}

@lru_cache(None)
def table():
    """Representatives and their exact residual sign polynomials, per block."""
    r = ref()
    _, linear, nonlinear, hosted = r.sign_tables()
    active = {base: {(j,) for j in linear.get(base, ())} | set(nonlinear.get(base, ())) for base in r.SPAN_AT}
    for (lo, span), terms in hosted.items():
        for base in r.SPAN_AT:
            if lo <= base < lo + span:
                active[base].symmetric_difference_update(terms)
    terms = tuple(sorted(set().union(*active.values()), key=lambda t: (len(t), t)))
    values = [0] * r.L
    for base, span in r.SPAN_AT.items():
        value = r.MASKS[base] & (1 << 80) - 1 | r.SIGN[base] << 80
        value |= sum((1 << 81 + j for j, term in enumerate(terms) if term in active[base]))
        values[base:base + span] = [value] * span
    encoded, basis, constant = compress(values)
    return (tuple(values), tuple(encoded), tuple(basis), constant, terms)

@lru_cache(None)
def bank_data(log_bank):
    values, encoded, basis, _, _ = table()
    rank = len(basis)
    k = 1 << log_bank
    words = [0] * len(values)
    for gens, lo, hi in ref().REGIONS:
        span = 1 << len(gens)
        for first in range(lo & ~(k * span - 1), hi, k * span):
            valid = max(first, lo)
            group = [encoded[first + j * span] if lo <= first + j * span < hi else encoded[valid] for j in range(k)]
            coefficients = anf(tuple(group), log_bank)[0]
            packed = sum((v << rank * j for j, v in enumerate(coefficients)))
            words[max(first, lo):min(first + k * span, hi)] = [packed] * (min(first + k * span, hi) - max(first, lo))
    return tuple(words)

def act(b, sel, compressed, system):
    """Apply the affine mask directly: no expanded 88-wire mask register."""
    _, _, basis, constant, terms = table()
    labels = [(None, constant)] + list(zip(compressed, basis))
    for shift, gate, controlled in ((40, b.z, b.cz), (0, b.x, b.cx)):
        for control, value in labels:
            for j, target in enumerate(system):
                if value >> shift + j & 1:
                    gate(target) if control is None else controlled(control, target)
    for control, value in labels:
        if value >> 80 & 1:
            b.neg() if control is None else b.z(control)
    products = {(j,): sel[j] for term in terms for j in term}
    trail = []

    def product(term):
        if term not in products:
            a, c = (product(term[:-1]), sel[term[-1]])
            q = b.and_compute(a, c)
            products[term] = q
            trail.append((q, a, c))
        return products[term]
    for j, term in enumerate(terms):
        q = product(term)
        for control, value in labels:
            if value >> 81 + j & 1:
                b.z(q) if control is None else b.cz(control, q)
    for q, a, c in reversed(trail):
        b.and_release(q, a, c)

def select(b, sel, system, log_bank, hold=14):
    r = ref()
    rank = len(table()[2])
    words = bank_data(log_bank)
    flags = b.qubits(7 + log_bank)
    with b.phase('frame-mask/flags'):
        xor_shared_flags(b, sel, flags, log_bank)
    bank = b.qubits(rank * (1 << log_bank))
    with b.phase('frame-mask/lookup'):
        load(b, sel, words, bank, hold)
    with b.phase('frame-mask/combine'):
        combine(b, flags[7:], bank, rank)
    with b.phase('frame-mask/open'):
        for g in reversed(r.PRIORITY):
            r.conjugate_open(b, flags[g], system, g)
    with b.phase('frame-mask/action'):
        act(b, sel, bank[:rank], system)
    with b.phase('frame-mask/close'):
        for g in r.PRIORITY:
            r.conjugate_close(b, flags[g], system, g)
    with b.phase('frame-mask/flags-close'):
        xor_shared_flags(b, sel, flags, log_bank)
    for q in reversed(flags):
        b.recycle(q)
    values = tuple((v | word >> rank << rank for v, word in zip(table()[1], words)))
    with b.phase('frame-mask/joint-repair'):
        erase_label(b, sel, bank, 4, 6, values=values)

def build(log_bank=2, log_alias=4, retain_alias=False):
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, system = (regs[n] for n in ('i', 'sigma', 'x'))
    alias, close_alias = shared_alias(b, idx, log_alias, 1, retain=retain_alias)
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    select(b, sel, system, log_bank)
    with b.phase('alias/restore'):
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
        r.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    close_alias()
    assert b.active_qubits == 72
    summary = b.phase_summary()
    summary.update(configuration=dict(log_bank=log_bank, log_alias=log_alias, retain_alias=retain_alias), family='released_frames_banked_mask_extension', method_scope='Released seven system frames and blocks; new banked mask/sign lookup and shared alias decoder.', upstream_commit=COMMIT)
    summary['tq_cost'] = summary['total_emitted_toffoli'] * summary['peak_qubits']
    return (b, regs, summary)

def check(b, regs, complete, exhaustive_rows=True):
    """All rows, signed Fock-state samples and symbolic measurement cleanup.

    Complete calls cover both alias branches at the exact comparator boundary.
    This is not the upstream full evaluator suite or a dense state simulation.
    """
    _, _, words, masks = inputs()
    rng = random.Random(261022367)
    rows = list(range(len(words))) if exhaustive_rows else sorted({0, 1, len(words) - 1} | {rng.randrange(len(words)) for _ in range(2048)})
    count = 0
    for start in range(0, len(rows), 2048):
        ids = rows[start:start + 2048] * 2
        states = [rng.getrandbits(40) for _ in ids]
        sim = Simulator(b, batch=len(ids), seed=start + 13, strict=True)
        sim.write(regs['i'], ids)
        if complete:
            half = len(ids) // 2
            sigma = [(words[i] & 65535) - 1 if k < half and words[i] & 65535 else words[i] & 65535 for k, i in enumerate(ids)]
            sim.write(regs['sigma'], sigma)
            selected = [i if s < words[i] & 65535 else words[i] >> 16 & 65535 for i, s in zip(ids, sigma)]
        else:
            selected = ids
        sim.write(regs['x'], states)
        sim.run()
        want = []
        phase = 0
        for lane, (i, state) in enumerate(zip(selected, states)):
            f, z = (masks[i] & (1 << 40) - 1, masks[i] >> 40 & (1 << 40) - 1)
            sign = (words[i] >> 33 ^ masks[i] >> 80) & 1
            want.append(state ^ f)
            phase |= (sign ^ (state & z).bit_count() & 1) << lane
        assert sim.read(regs['x']) == want
        assert sim.read(regs['i']) == ids
        if complete:
            assert sim.read(regs['sigma']) == sigma
        sim.assert_clean(phase=phase)
        assert sim.stats.toffoli == len(ids) * b.phase_summary()['total_emitted_toffoli']
        count += len(ids)
    return dict(status='PASS', samples=count, every_row=exhaustive_rows, symbolic_measurement_cleanup=True, scope='Two Fock-state samples per row; complete circuit uses keep-1 and keep alias boundary inputs (keep=0 uses 0 twice).')
