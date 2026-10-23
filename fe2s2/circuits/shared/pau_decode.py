"""PAU with shared label/region lookup and factored routing-flag decoding.

The native 269-Toffoli spin-pool system action is unchanged. A region-dependent
linear map produces support/bank flags from the preserved selected address.
Its coefficients share the existing label lookup and are measured early;
their outcomes enter the same exact joint measurement-phase repair.
"""
import argparse
import gc
import hashlib
import json
import os
from functools import lru_cache
from common import HERE
from tradeoff import ref
from circuit import compress
from plane_bank import load
from pau_spin import table, bank_data, local_select
from pau_recycle import alias_decode
from pau_tq import measure_release, repair_records
from pau_grouped import prepared, inplace_decode
from pau_wide import combine
from routing import parity_wire, un_parity
from uncompute import Builder
from uncompute.gadgets import declare_registers, xor_word

@lru_cache(None)
def flag_data(log_label):
    """Independent region matrix; test every decoded flag against fixed rows."""
    r = ref()
    width = 7 + log_label
    values = [0] * r.L
    expected = [0] * r.L
    for gens, lo, hi in r.REGIONS:
        n = len(gens)
        assert lo % (1 << n) == 0
        matrix = sum((1 << width * p + g for p, g in enumerate(gens)))
        matrix |= sum((1 << width * (n + j) + 7 + j for j in range(log_label)))
        for i in range(lo, hi):
            values[i] = matrix
            expected[i] = sum((v << j for j, v in enumerate(prepared()[4][i][1]))) | (i >> n & (1 << log_label) - 1) << 7
            actual = 0
            for p in range(16):
                if i >> p & 1:
                    actual ^= matrix >> width * p & (1 << width) - 1
            assert actual == expected[i], i
    encoded, basis, constant = compress(values)
    factors = []
    for p in range(16):
        columns = [v >> width * p & (1 << width) - 1 for v in basis]
        codes, outs, zero = compress([0] + columns)
        assert zero == 0
        for j, out in enumerate(outs):
            mask = sum(((code >> j & 1) << q for q, code in enumerate(codes[1:])))
            factors.append((p, mask, out))
    return (tuple(encoded), tuple(basis), constant, tuple(factors), tuple(expected))

def flag_map(b, address, meta, flags, basis, constant, factors):
    width = len(flags)
    mask = (1 << width) - 1
    for p in range(16):
        xor_word(b, address[p], constant >> width * p & mask, flags)
    for p, coeff, out in factors:
        wires = [q for j, q in enumerate(meta) if coeff >> j & 1]
        ctrl = parity_wire(b, wires)
        if out.bit_count() == 1:
            b.ccx(address[p], ctrl, flags[out.bit_length() - 1])
        else:
            prod = b.and_compute(address[p], ctrl)
            xor_word(b, prod, out, flags)
            b.and_release(prod, address[p], ctrl)
        un_parity(b, ctrl, wires)

@lru_cache(None)
def label_data(log_label, padding, partition):
    words, sizes = bank_data(log_label, padding, partition)
    rank = len(table(padding, partition)[2])
    meta, basis, constant, factors, flags = flag_data(log_label)
    bank_width = rank * (1 << log_label)
    combined = tuple((w | m << bank_width for w, m in zip(words, meta)))
    return (combined, rank, bank_width, meta, basis, constant, factors, flags)

def label_decode(b, sel, log_label, hold, low, window, repair_hold, padding, partition):
    _, encoded, basis, constant, terms = table(padding, partition)
    words, rank, bank_width, meta_values, meta_basis, meta_constant, factors, flag_values = label_data(log_label, padding, partition)
    bank = b.qubits(bank_width)
    root = bank[:rank]
    meta = b.qubits(len(meta_basis))
    with b.phase('decode-label/shared-lookup'):
        load(b, sel, words, bank + meta, hold)
    flags = b.qubits(7 + log_label)
    with b.phase('decode-label/flag-map'):
        flag_map(b, sel, meta, flags, meta_basis, meta_constant, factors)
    with b.phase('decode-label/metadata-measure'):
        meta_records = measure_release(b, meta)
    with b.phase('decode-label/combine'):
        combine(b, flags[7:], bank, rank)
    with b.phase('decode-label/spare-measure'):
        spare_records = measure_release(b, bank[rank:])
    expanded, close = inplace_decode(b, root, basis, constant, 40)
    with b.phase('decode-label/residual-sign'):
        products = {(j,): sel[j] for j in range(16)}
        trail = []

        def product(term):
            if term not in products:
                a, c = (product(term[:-1]), sel[term[-1]])
                v = b.and_compute(a, c)
                products[term] = v
                trail.append((v, a, c))
            return products[term]
        for j, term in enumerate(terms):
            b.cz(expanded[33 + j], product(term))
        for v, a, c in reversed(trail):
            b.and_release(v, a, c)

    def cleanup():
        close()
        outcomes = measure_release(b, root) + spare_records + meta_records + measure_release(b, flags)
        raw = bank_data(log_label, padding, partition)[0]
        values = tuple((v | w >> rank << rank | m << bank_width | f << bank_width + len(meta_basis) for v, w, m, f in zip(encoded, raw, meta_values, flag_values)))
        with b.phase('decode-label/joint-repair'):
            repair_records(b, sel, outcomes, values, low, window, repair_hold)
    return (flags[:7], expanded, cleanup)

def build(log_alias=4, log_correction=1, log_label=3, alias_hold=14, label_hold=14, label_low=6, label_window=6, label_repair_hold=14, alias_low=2, alias_window=7, alias_repair_hold=14, padding='high', partition=0):
    config = dict(locals())
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs[n] for n in ('i', 'sigma', 'x'))
    alias, records, values = alias_decode(b, idx, log_alias, log_correction, alias_hold)
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    flags, label, close = label_decode(b, sel, log_label, label_hold, label_low, label_window, label_repair_hold, padding, partition)
    with b.phase('spin/control-products-and-close'):
        local_select(b, flags, label, x)
    close()
    with b.phase('alias/restore'):
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
        r.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    outcomes = measure_release(b, alias) + records
    with b.phase('recycle-alias/final-repair'):
        repair_records(b, idx, outcomes, values, alias_low, alias_window, alias_repair_hold)
    assert b.active_qubits == 72
    s = b.phase_summary()
    s.update(configuration=config, family='published_pau_shared_region_lookup', metadata_width=len(flag_data(log_label)[1]), flag_products=len(flag_data(log_label)[3]), tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'])
    return (b, s)

def emit(name, configuration):
    b, s = build(**configuration)
    out = HERE / 'results' / name
    out.mkdir(exist_ok=True)
    (out / 'resources.json').write_text(json.dumps(s, indent=2) + '\n')
    os.environ['UNCOMPUTE_OPS_PATH'] = str(out / 'circuit.ops')
    b.emit()
    return dict(key=name, toffoli=s['total_emitted_toffoli'], peak=s['peak_qubits'], tq=s['tq_cost'])
