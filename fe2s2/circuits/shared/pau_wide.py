"""Larger-workspace PAU variants with shared alias-correction lookup.

All system action is the existing published-method four-site PAU core.
The optional frame comparator gets the identical new alias decoder.
Frozen earlier implementations and certificates are left unchanged.
"""
import argparse
import gc
import hashlib
import json
import os
from functools import lru_cache
from common import HERE
from tradeoff import ref, anf, repair as alias_repair
from circuit import compress, blocked_lookup
from plane_bank import data as alias_data, load
from pau_grouped import inplace_decode
from pau_banked import table, decode_adaptive, residual_phase, erase_label, adaptive_data, xor_shared_flags
from pau_orbit import local_select
from uncompute import Builder
from uncompute.gadgets import declare_registers, erase_register

def combine(b, bits, bank, width):
    """XOR nonconstant ANF words into word zero with shared AND prefixes."""

    def go(mask, ctrl, start):
        for a, t in zip(bank[width * mask:width * (mask + 1)], bank[:width]):
            b.ccx(ctrl, a, t)
        for j in range(start, len(bits)):
            q = b.and_compute(ctrl, bits[j])
            go(mask | 1 << j, q, j + 1)
            b.and_release(q, ctrl, bits[j])
    for j, ctrl in enumerate(bits):
        go(1 << j, ctrl, j + 1)

@lru_cache(None)
def correction_data(log_bank):
    rest = alias_data(2, 1)[1]
    native = tuple((sum((v << 32 * j for j, v in enumerate(p))) for p in zip(*rest)))
    encoded, basis, constant = compress(native)
    rank = len(basis)
    words = tuple((sum((v << rank * j for j, v in enumerate(p))) for p in anf(tuple(encoded), log_bank)))
    return (native, tuple(encoded), tuple(basis), constant, words)

def shared_alias(b, idx, log_alias, log_correction, hold=14, repair_low=4, repair_window=5, retain=False):
    words, _ = alias_data(2, log_alias)
    k = 1 << log_alias
    bank = b.qubits(32 * k)
    alias = bank[:32]
    with b.phase('wide-alias/base-lookup'):
        load(b, idx[2 + log_alias:], words, bank, hold)
    with b.phase('wide-alias/base-combine'):
        combine(b, idx[2:2 + log_alias], bank, 32)
    deferred = []
    components = []
    if retain:
        deferred.extend(bank[32:])
        components.append((len(bank) - 32, tuple((words[i >> 2 + log_alias] >> 32 for i in range(ref().L)))))
    else:
        with b.phase('wide-alias/base-erase'):
            erase_register(b, bank[32:], idx[2 + log_alias:], len(words), [v >> 32 for v in words], 32, range(len(words)), 'wide-alias/base-disposable', free=True, phase='wide-alias/base-repair')
    native, encoded, basis, constant, words = correction_data(log_correction)
    rank = len(basis)
    k = 1 << log_correction
    bank = b.qubits(rank * k)
    compressed = bank[:rank]
    with b.phase('wide-alias/correction-lookup'):
        load(b, idx[2 + log_correction:], words, bank, hold)
    with b.phase('wide-alias/correction-combine'):
        combine(b, idx[2:2 + log_correction], bank, rank)
    if log_correction and (not retain):
        with b.phase('wide-alias/correction-bank-erase'):
            full = tuple((words[i >> 2 + log_correction] >> rank for i in range(ref().L)))
            erase_label(b, idx, bank[rank:], repair_low, repair_window, values=full)
    with b.phase('wide-alias/correction-affine'):
        expanded, close = inplace_decode(b, compressed, basis, constant, 96)
    with b.phase('wide-alias/correction-apply'):
        both = b.and_compute(idx[0], idx[1])
        for j, ctrl in enumerate((idx[0], idx[1], both)):
            for a, t in zip(expanded[32 * j:32 * (j + 1)], alias):
                b.ccx(ctrl, a, t)
        b.and_release(both, idx[0], idx[1])
    close()
    if retain:
        deferred.extend(bank)
        components.append((len(bank), tuple((encoded[i >> 2] | words[i >> 2 + log_correction] >> rank << rank for i in range(ref().L)))))

        def close_alias():
            values = list(ref().DATA)
            offset = 32
            for width, vs in components:
                for i, v in enumerate(vs):
                    values[i] |= v << offset
                offset += width
            with b.phase('wide-alias/joint-repair'):
                erase_label(b, idx, alias + deferred, 2, 7, hold=40, values=tuple(values))
    else:
        with b.phase('wide-alias/correction-root-erase'):
            full = tuple((encoded[i >> 2] for i in range(ref().L)))
            erase_label(b, idx, compressed, repair_low, repair_window, values=full)

        def close_alias():
            outcomes = [b.hmr(q) for q in alias]
            for q in reversed(alias):
                b.recycle(q)
            alias_repair(b, idx, outcomes, 2, 7, 40)
    return (alias, close_alias)

def retained_labels(b, sel, log_label, hold):
    rank = len(table()[2])
    words, _ = adaptive_data(log_label)
    flags = b.qubits(7)
    controls = b.qubits(log_label)
    with b.phase('pau/retained-flags'):
        xor_shared_flags(b, sel, flags + controls, log_label)
    bank = b.qubits(rank * (1 << log_label))
    root = bank[:rank]
    with b.phase('pau/retained-lookup'):
        load(b, sel, words, bank, hold)
    with b.phase('pau/retained-combine'):
        combine(b, controls, bank, rank)

    def close():
        with b.phase('pau/retained-flags-close'):
            xor_shared_flags(b, sel, flags + controls, log_label)
        for q in reversed(flags + controls):
            b.recycle(q)
        values = tuple((value | word >> rank << rank for value, word in zip(table()[1], words)))
        with b.phase('pau/retained-joint-repair'):
            erase_label(b, sel, bank, 4, 6, values=values)
    return (root, flags, close)

def build(log_alias=4, log_correction=1, log_label=3, hold=14, alias_mode='shared', alias_k=32, family='pau', retain_labels=False):
    r = ref()
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs[n] for n in ('i', 'sigma', 'x'))
    if alias_mode in ('shared', 'retained'):
        alias, close_alias = shared_alias(b, idx, log_alias, log_correction, hold, retain=alias_mode == 'retained')
    elif alias_mode == 'blocked':
        alias, close_alias = blocked_lookup(b, idx, tuple(r.DATA), 32, alias_k, 'alias', 'full')
    else:
        raise ValueError(alias_mode)
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/compare-select'):
        flag = b.qubit()
        r.compare_into(b, sigma, keep, flag)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    if family == 'frame':
        r.select_pauli(b, sel, x)
    elif family == 'pau':
        if retain_labels:
            compressed, flags, close_bank = retained_labels(b, sel, log_label, hold)
        else:
            compressed, flags, close_bank = decode_adaptive(b, sel, log_label, hold, 4, 5, True)
        _, _, basis, constant, terms = table()
        label, close = inplace_decode(b, compressed, basis, constant, 36 + len(terms))
        with b.phase('pau/residual-phase'):
            residual_phase(b, sel, label)
        with b.phase('pau/control-products-and-close'):
            local_select(b, flags, label[:36], x)
        close()
        close_bank()
        if not retain_labels:
            with b.phase('pau/orbit-label-erase'):
                erase_label(b, sel, compressed, 4, 5)
    else:
        raise ValueError(family)
    with b.phase('alias/restore'):
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
        r.compare_into(b, sigma, keep, flag)
        b.recycle(flag)
    close_alias()
    assert b.active_qubits == 72
    s = b.phase_summary()
    s.update(family='published_pau_wide' if family == 'pau' else 'frame_select_wide_alias', configuration=dict(log_alias=log_alias, log_correction=log_correction, log_label=log_label, hold=hold, alias_mode=alias_mode, alias_k=alias_k, family=family, retain_labels=retain_labels), tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'], repair_configuration=dict(joint_alias_low=2, joint_alias_log_window=7, joint_label_low=4, joint_label_log_window=6))
    return (b, s)

def emit(name, configuration):
    b, s = build(**configuration)
    out = HERE / 'results' / name
    out.mkdir(exist_ok=True)
    (out / 'resources.json').write_text(json.dumps(s, indent=2) + '\n')
    os.environ['UNCOMPUTE_OPS_PATH'] = str(out / 'circuit.ops')
    b.emit()
    result = dict(name=name, toffoli=s['total_emitted_toffoli'], peak=s['peak_qubits'], tq=s['tq_cost'])
    print(json.dumps(result), flush=True)
    return result
