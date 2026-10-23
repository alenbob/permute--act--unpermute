"""Small-space PAU: recycle scratch for cleanup and share alias corrections.

Frozen earlier circuits are reused as components, never edited. All quantum
system action is the same 349-Toffoli published-method PAU core.
"""
import argparse
import gc
import hashlib
import json
import os
from common import HERE
from tradeoff import ref, monomials, repair as alias_repair
from plane_bank import data as alias_data, decode_alias, load
from pau_wide import combine, correction_data
from pau_banked import table, adaptive_data, xor_shared_flags, erase_label, residual_phase, repair_plan
from pau_grouped import inplace_decode, prepared
from pau_orbit import local_select
from uncompute import Builder
from uncompute.gadgets import declare_registers, erase_register, xor_outcomes

def measure_release(b, register):
    outcomes = [b.hmr(q) for q in register]
    for q in reversed(register):
        b.recycle(q)
    return outcomes

def repair_records(b, address, outcomes, values, low, log_window, hold):
    """Repair a lookup phase from classical records after its storage is freed.

    The lookup address must have been preserved, or coherently restored, since
    measurement. No intervening operation may mix its computational labels at
    the repair boundary. Classical records do not occupy logical qubits.
    """
    root, policy, payload, masks, _ = repair_plan(tuple(values), low, log_window, hold)
    k = 1 << log_window
    mid = address[low:low + log_window]
    u = b.qubits(k)
    b.x(u[0])
    for j in reversed(range(log_window)):
        for i in range(0, k, 2 << j):
            b.cswap(mid[j], u[i], u[i + (1 << j)])
    cache = {0: None}

    def parity(value):
        if value not in cache:
            cache[value] = xor_outcomes([o for j, o in enumerate(outcomes) if value >> j & 1])
        return cache[value]

    def leaf(lo, ctrl):

        def emit(q, mask):
            for j, v in enumerate(payload[lo]):
                outcome = parity(v[mask])
                if outcome is not None:
                    b.cz(q, u[j], cond=outcome)
        monomials(b, ctrl, address[:low], masks[lo], emit)
    ref()._policy_walk(b, root, policy, hold, lambda n: address[low + log_window + n.span.bit_length() - 2], leaf)
    for j in range(log_window):
        for i in range(0, k, 2 << j):
            v = u[i + (1 << j)]
            b.cx(v, u[i])
            b.and_release(v, mid[j], u[i])
    b.x(u[0])
    b.recycle(u[0])

def decode_shared(b, idx, log_alias, hold, base_window, correction_window, correction_low, correction_hold, defer):
    words, _ = alias_data(2, log_alias)
    bank = b.qubits(32 * (1 << log_alias))
    alias = bank[:32]
    with b.phase('tq-alias/base-lookup'):
        load(b, idx[2 + log_alias:], words, bank, hold)
    with b.phase('tq-alias/base-combine'):
        combine(b, idx[2:2 + log_alias], bank, 32)
    deferred = []
    components = []
    if defer:
        with b.phase('tq-alias/base-measure'):
            deferred.extend(measure_release(b, bank[32:]))
        components.append((len(bank) - 32, tuple((words[i >> 2 + log_alias] >> 32 for i in range(ref().L)))))
    else:
        with b.phase('tq-alias/base-erase'):
            erase_register(b, bank[32:], idx[2 + log_alias:], len(words), [v >> 32 for v in words], base_window, range(len(words)), 'tq-alias/base-disposable', free=True, phase='tq-alias/base-repair')
    _, encoded, basis, constant, words = correction_data(0)
    compressed = b.qubits(len(basis))
    with b.phase('tq-alias/correction-lookup'):
        load(b, idx[2:], words, compressed, hold)
    expanded, close = inplace_decode(b, compressed, basis, constant, 96)
    with b.phase('tq-alias/correction-apply'):
        both = b.and_compute(idx[0], idx[1])
        for j, ctrl in enumerate((idx[0], idx[1], both)):
            for a, t in zip(expanded[32 * j:32 * (j + 1)], alias):
                b.ccx(ctrl, a, t)
        b.and_release(both, idx[0], idx[1])
    close()
    full = tuple((encoded[i >> 2] for i in range(ref().L)))
    if defer:
        with b.phase('tq-alias/correction-measure'):
            deferred.extend(measure_release(b, compressed))
        components.append((len(compressed), full))
    else:
        with b.phase('tq-alias/correction-erase'):
            erase_label(b, idx, compressed, correction_low, correction_window, hold=correction_hold, values=full)
    values = list(ref().DATA)
    offset = 32
    for width, component in components:
        for i, v in enumerate(component):
            values[i] |= v << offset
        offset += width
    return (alias, deferred, tuple(values))

def labels(b, sel, log_label, hold, retain, early_window, root_window, repair_low, repair_hold, joint_flags, defer):
    rank = len(table()[2])
    words, _ = adaptive_data(log_label)
    flags = b.qubits(7)
    controls = b.qubits(log_label)
    with b.phase('tq-pau/flags'):
        xor_shared_flags(b, sel, flags + controls, log_label)
    bank = b.qubits(rank * (1 << log_label))
    root = bank[:rank]
    with b.phase('tq-pau/label-lookup'):
        load(b, sel, words, bank, hold)
    with b.phase('tq-pau/label-combine'):
        combine(b, controls, bank, rank)
    deferred = []
    if not retain and log_label:
        if defer:
            with b.phase('tq-pau/label-early-measure'):
                deferred = measure_release(b, bank[rank:])
        else:
            with b.phase('tq-pau/label-early-repair'):
                erase_label(b, sel, bank[rank:], repair_low, early_window, hold=repair_hold, values=tuple((v >> rank for v in words)))

    def close():
        joint_bank = retain or defer
        values = tuple((v | word >> rank << rank for v, word in zip(table()[1], words))) if joint_bank else table()[1]
        outcomes = measure_release(b, bank if retain else root) + deferred
        if joint_flags:
            sizes = adaptive_data(log_label)[1]
            flag_values = [sum((v << j for j, v in enumerate(meta[1]))) | (i >> sizes[i] & (1 << log_label) - 1) << 7 for i, meta in enumerate(prepared()[4])]
            values = tuple((v | f << len(outcomes) for v, f in zip(values, flag_values)))
            outcomes += measure_release(b, flags + controls)
        else:
            with b.phase('tq-pau/flags-close'):
                xor_shared_flags(b, sel, flags + controls, log_label)
            for q in reversed(flags + controls):
                b.recycle(q)
        with b.phase('tq-pau/label-final-repair'):
            repair_records(b, sel, outcomes, values, repair_low, root_window, repair_hold)
    return (root, flags, close)

def build(log_alias=2, alias_hold=9, base_window=32, shared=True, defer_alias=True, correction_window=6, correction_low=2, correction_hold=12, log_label=1, label_hold=12, retain_labels=False, joint_flags=True, defer_labels=True, early_window=5, root_window=6, label_low=6, label_repair_hold=12, final_window=7, final_low=2, final_hold=12):
    config = dict(locals())
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs[n] for n in ('i', 'sigma', 'x'))
    if shared:
        alias, deferred, alias_values = decode_shared(b, idx, log_alias, alias_hold, base_window, correction_window, correction_low, correction_hold, defer_alias)
    else:
        alias = decode_alias(b, idx, 2, log_alias, alias_hold, base_window)
        deferred = []
        alias_values = tuple(r.DATA)
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    compressed, flags, close_bank = labels(b, sel, log_label, label_hold, retain_labels, early_window, root_window, label_low, label_repair_hold, joint_flags, defer_labels)
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
    outcomes = measure_release(b, alias) + deferred
    with b.phase('tq-alias/final-repair'):
        repair_records(b, idx, outcomes, alias_values, final_low, final_window, final_hold)
    assert b.active_qubits == 72
    s = b.phase_summary()
    s.update(family='published_pau_small_space', configuration=config, tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'])
    return (b, s)

def emit(name, configuration):
    b, s = build(**configuration)
    out = HERE / 'results' / name
    out.mkdir(exist_ok=True)
    (out / 'resources.json').write_text(json.dumps(s, indent=2) + '\n')
    os.environ['UNCOMPUTE_OPS_PATH'] = str(out / 'circuit.ops')
    b.emit()
    return dict(name=name, toffoli=s['total_emitted_toffoli'], peak=s['peak_qubits'], tq=s['tq_cost'])
