"""PAU with independently sized decoder banks and deferred classical repairs.

Temporary bank words are measured immediately after combination. Their
classical records are repaired jointly at the preserved-address boundary.
The published-method 349-Toffoli PAU system action is reused unchanged.
"""
import argparse
import gc
import hashlib
import json
import os
from common import HERE
from plane_bank import data, load
from tradeoff import ref
from pau_wide import combine, correction_data
from pau_tq import measure_release, repair_records, labels
from pau_banked import table, residual_phase
from pau_grouped import inplace_decode
from pau_orbit import local_select
from uncompute import Builder
from uncompute.gadgets import declare_registers

def alias_decode(b, idx, log_alias, log_correction, hold):
    words, _ = data(2, log_alias)
    bank = b.qubits(32 * (1 << log_alias))
    alias = bank[:32]
    with b.phase('recycle-alias/base-lookup'):
        load(b, idx[2 + log_alias:], words, bank, hold)
    with b.phase('recycle-alias/base-combine'):
        combine(b, idx[2:2 + log_alias], bank, 32)
    with b.phase('recycle-alias/base-measure'):
        records = measure_release(b, bank[32:])
    components = [(len(bank) - 32, tuple((words[i >> 2 + log_alias] >> 32 for i in range(ref().L))))]
    _, encoded, basis, constant, words = correction_data(log_correction)
    rank = len(basis)
    bank = b.qubits(rank * (1 << log_correction))
    root = bank[:rank]
    with b.phase('recycle-alias/correction-lookup'):
        load(b, idx[2 + log_correction:], words, bank, hold)
    with b.phase('recycle-alias/correction-combine'):
        combine(b, idx[2:2 + log_correction], bank, rank)
    expanded, close = inplace_decode(b, root, basis, constant, 96)
    with b.phase('recycle-alias/correction-apply'):
        both = b.and_compute(idx[0], idx[1])
        for j, ctrl in enumerate((idx[0], idx[1], both)):
            for a, t in zip(expanded[32 * j:32 * (j + 1)], alias):
                b.ccx(ctrl, a, t)
        b.and_release(both, idx[0], idx[1])
    close()
    with b.phase('recycle-alias/correction-measure'):
        records += measure_release(b, bank)
    components.append((len(bank), tuple((encoded[i >> 2] | words[i >> 2 + log_correction] >> rank << rank for i in range(ref().L)))))
    values = list(ref().DATA)
    offset = 32
    for width, component in components:
        for i, v in enumerate(component):
            values[i] |= v << offset
        offset += width
    return (alias, records, tuple(values))

def build(log_alias=4, log_correction=1, log_label=3, alias_hold=14, label_hold=14, label_low=6, label_window=6, label_repair_hold=14, alias_low=2, alias_window=7, alias_repair_hold=14):
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
    compressed, flags, close_bank = labels(b, sel, log_label, label_hold, False, 5, label_window, label_low, label_repair_hold, True, True)
    _, _, basis, constant, terms = table()
    label, close = inplace_decode(b, compressed, basis, constant, 36 + len(terms))
    with b.phase('pau/residual-phase'):
        residual_phase(b, sel, label)
    with b.phase('pau/control-products-and-close'):
        local_select(b, flags, label[:36], x)
    close()
    close_bank()
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
    s.update(configuration=config, family='published_pau_recycled_banks', tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'])
    return (b, s)

def emit(name, configuration):
    b, s = build(**configuration)
    out = HERE / 'results' / name
    out.mkdir(exist_ok=True)
    (out / 'resources.json').write_text(json.dumps(s, indent=2) + '\n')
    os.environ['UNCOMPUTE_OPS_PATH'] = str(out / 'circuit.ops')
    b.emit()
    return dict(key=name, toffoli=s['total_emitted_toffoli'], peak=s['peak_qubits'], tq=s['tq_cost'])
