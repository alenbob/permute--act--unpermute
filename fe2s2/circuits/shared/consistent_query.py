"""Common current decoder machinery for PAU and experimental frame SELECT.

The paper-only comparator lives in frozen frame_paper.py. Here both families
receive the same alias/flag/bank/measurement techniques and parameter domain.
Small-space alternatives are explicit configuration choices, not old versions.
"""
import argparse
import gc
import hashlib
import json
import os
from functools import lru_cache
from common import HERE
from tradeoff import ref
from plane_bank import data, load, sparse_xor
from address_order import lookup as ordered_lookup
from pau_wide import combine
from pau_recycle import alias_decode as shared_alias
from pau_tq import measure_release, repair_records
from pau_decode import flag_data, flag_map
from pau_banked import xor_shared_flags
from pau_grouped import inplace_decode
from pau_spin import table as pau_table, bank_data as pau_bank, local_select
from frame_mask_space import table as frame_table, bank_data as frame_bank, act as frame_act
from uncompute import Builder
from uncompute.gadgets import declare_registers
SOURCES = ()
ORDER = (15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 2, 5, 4, 3, 1, 0)

def hashes():
    return {}

def alias_decode(b, idx, mode, log_alias, log_correction, hold):
    if mode == 'shared':
        return shared_alias(b, idx, log_alias, log_correction, hold)
    if mode == 'ordered':
        alias = b.qubits(32)
        ordered_lookup(b, idx, alias, ORDER)
        return (alias, [], tuple(ref().DATA))
    assert mode == 'sparse'
    words, rest = data(2, log_alias)
    bank = b.qubits(32 * (1 << log_alias))
    alias = bank[:32]
    with b.phase('sparse-alias/base-lookup'):
        load(b, idx[2 + log_alias:], words, bank, hold)
    with b.phase('sparse-alias/base-combine'):
        combine(b, idx[2:2 + log_alias], bank, 32)
    with b.phase('sparse-alias/base-measure'):
        records = measure_release(b, bank[32:])
    with b.phase('sparse-alias/corrections'):
        for mask, values in enumerate(rest, 1):
            bits = [idx[j] for j in range(2) if mask >> j & 1]
            ctrl = bits[0] if len(bits) == 1 else b.and_compute(*bits)
            sparse_xor(b, idx[2:], values, alias, ctrl)
            if len(bits) == 2:
                b.and_release(ctrl, *bits)
    values = tuple((v | words[i >> 2 + log_alias] >> 32 << 32 for i, v in enumerate(ref().DATA)))
    return (alias, records, values)

@lru_cache(None)
def label_data(family, log_label, padding, partition):
    if family == 'pau':
        native, encoded, basis, constant, terms = pau_table(padding, partition)
        words = pau_bank(log_label, padding, partition)[0]
    else:
        native, encoded, basis, constant, terms = frame_table()
        words = frame_bank(log_label)
    return (native, encoded, basis, constant, terms, words)

def residual_sign(b, sel, label, terms):
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
        b.cz(label[33 + j], product(term))
    for v, a, c in reversed(trail):
        b.and_release(v, a, c)

def select(b, sel, system, family, select_mode, flag_mode, log_label, label_hold, label_low, label_window, label_repair_hold, padding, partition, repair=True):
    if select_mode == 'released':
        assert family == 'frame'
        ref().select_pauli(b, sel, system)
        return (0, ())
    assert select_mode == 'banked'
    native, encoded, basis, constant, terms, words = label_data(family, log_label, padding, partition)
    rank = len(basis)
    bank_width = rank * (1 << log_label)
    meta_values, meta_basis, meta_constant, factors, flag_values = flag_data(log_label)
    meta_records = []
    meta_width = 0
    if flag_mode == 'separate':
        flags = b.qubits(7 + log_label)
        with b.phase('current-label/flags'):
            xor_shared_flags(b, sel, flags, log_label)
    bank = b.qubits(bank_width)
    root = bank[:rank]
    if flag_mode == 'shared':
        meta_width = len(meta_basis)
        meta = b.qubits(meta_width)
        combined = tuple((w | m << bank_width for w, m in zip(words, meta_values)))
        with b.phase('current-label/lookup'):
            load(b, sel, combined, bank + meta, label_hold)
        flags = b.qubits(7 + log_label)
        with b.phase('current-label/flags'):
            flag_map(b, sel, meta, flags, meta_basis, meta_constant, factors)
        with b.phase('current-label/metadata-measure'):
            meta_records = measure_release(b, meta)
    else:
        assert flag_mode == 'separate'
        with b.phase('current-label/lookup'):
            load(b, sel, words, bank, label_hold)
    with b.phase('current-label/combine'):
        combine(b, flags[7:], bank, rank)
    with b.phase('current-label/spare-measure'):
        spare = measure_release(b, bank[rank:])
    if family == 'pau':
        label, _ = inplace_decode(b, root, basis, constant, 40)
        with b.phase('current-label/residual-sign'):
            residual_sign(b, sel, label, terms)
        with b.phase('current-label/sign-measure'):
            sign_records = measure_release(b, label[33:])
        with b.phase('spin/control-products-and-close'):
            local_select(b, flags[:7], label[:33], system)
        root_records = measure_release(b, label[:33]) + sign_records
        root_width = 40
        root_values = native
    else:
        r = ref()
        with b.phase('current-frame/open'):
            for g in reversed(r.PRIORITY):
                r.conjugate_open(b, flags[g], system, g)
        with b.phase('current-frame/action'):
            frame_act(b, sel, root, system)
        with b.phase('current-frame/close'):
            for g in r.PRIORITY:
                r.conjugate_close(b, flags[g], system, g)
        root_records = measure_release(b, root)
        root_width = rank
        root_values = encoded
    records = root_records + spare + meta_records + measure_release(b, flags)
    meta_offset = root_width + bank_width - rank
    flag_offset = meta_offset + meta_width
    values = tuple((v | word >> rank << root_width | (m if meta_width else 0) << meta_offset | f << flag_offset for v, word, m, f in zip(root_values, words, meta_values, flag_values)))
    if not repair:
        return (len(records), values)
    with b.phase('current-label/joint-repair'):
        repair_records(b, sel, records, values, label_low, label_window, label_repair_hold)

def build(family='pau', alias_mode='shared', log_alias=4, log_correction=1, alias_hold=14, select_mode='banked', flag_mode='shared', log_label=3, label_hold=14, label_low=6, label_window=6, label_repair_hold=14, alias_low=2, alias_window=7, alias_repair_hold=14, padding='high', partition=0):
    config = dict(locals())
    assert family in ('pau', 'frame')
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, system = (regs[n] for n in ('i', 'sigma', 'x'))
    alias, records, values = alias_decode(b, idx, alias_mode, log_alias, log_correction, alias_hold)
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    select(b, sel, system, family, select_mode, flag_mode, log_label, label_hold, label_low, label_window, label_repair_hold, padding, partition)
    with b.phase('alias/restore'):
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
        r.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    outcomes = measure_release(b, alias) + records
    with b.phase('current-alias/final-repair'):
        repair_records(b, idx, outcomes, values, alias_low, alias_window, alias_repair_hold)
    assert b.active_qubits == 72
    summary = b.phase_summary()
    summary.update(configuration=config, family='current_' + family, tq_cost=summary['total_emitted_toffoli'] * summary['peak_qubits'])
    if family == 'pau':
        assert sum((p['toffoli'] for p in summary['phases'] if p['name'].startswith('spin/'))) == 269
    return (b, regs, summary)

def emit(key, configuration):
    b, regs, s = build(**configuration)
    out = HERE / 'results' / key
    out.mkdir(exist_ok=True)
    (out / 'resources.json').write_text(json.dumps(s, indent=2) + '\n')
    os.environ['UNCOMPUTE_OPS_PATH'] = str(out / 'circuit.ops')
    b.emit()
    return (b, regs, s)
