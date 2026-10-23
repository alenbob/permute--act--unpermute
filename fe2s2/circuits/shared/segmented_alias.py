"""Alias base lookup with separately sized banks for disjoint output slices.

Each slice is combined coherently before its spare words are measured. Only
ancillas are measured; phase repairs wait until the original index is restored.
The 32 output bits and the original low-two-bit correction are unchanged.
"""
from functools import lru_cache
from common import HERE
from plane_bank import data
from tradeoff import ref
from pau_wide import combine, correction_data
from pau_tq import measure_release
from pau_grouped import inplace_decode
from permuted_lookup import load

@lru_cache(None)
def slice_words(offset, width, log_bank):
    assert 0 <= offset < 32 and 1 <= width <= 32 - offset
    words, _ = data(2, log_bank)
    mask = (1 << width) - 1
    return tuple((sum(((word >> 32 * j + offset & mask) << width * j for j in range(1 << log_bank))) for word in words))

def alias_decode(b, idx, slices, log_correction, correction_plan):
    outputs = {}
    records = []
    components = []
    for number, part in enumerate(slices):
        offset, width, log = (part[n] for n in ('offset', 'width', 'log_bank'))
        assert not set(range(offset, offset + width)) & set(outputs)
        words = slice_words(offset, width, log)
        bank = b.qubits(width * (1 << log))
        with b.phase(f'segmented-alias/base-{number}-lookup'):
            load(b, idx[2 + log:], words, bank, part['hold'], part['order'])
        with b.phase(f'segmented-alias/base-{number}-combine'):
            combine(b, idx[2:2 + log], bank, width)
        with b.phase(f'segmented-alias/base-{number}-measure'):
            records += measure_release(b, bank[width:])
        outputs.update(zip(range(offset, offset + width), bank[:width]))
        components.append((len(bank) - width, tuple((words[i >> 2 + log] >> width for i in range(ref().L)))))
    assert set(outputs) == set(range(32))
    alias = [outputs[j] for j in range(32)]
    _, encoded, basis, constant, words = correction_data(log_correction)
    rank = len(basis)
    bank = b.qubits(rank * (1 << log_correction))
    root = bank[:rank]
    with b.phase('recycle-alias/correction-lookup'):
        load(b, idx[2 + log_correction:], words, bank, correction_plan['hold'], correction_plan['order'])
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
