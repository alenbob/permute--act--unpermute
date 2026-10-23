"""PAU decoder experiments: shared inactive addresses and direct scalar phase.

The scalar sign is a polynomial in the preserved row-address bits. A lookup
leaf applies CZs to precomputed monomials rather than loading sign coefficient
qubits. Polynomial coefficients remain part of the lookup's equality key.
This is an exact phase oracle, not deletion or measurement of a needed sign.
"""
from contextlib import contextmanager
from functools import lru_cache
from copy import deepcopy
import hashlib
import family_pau as fp
from family_overlay import layout as overlay_layout
from pau_spin import table as common_table
from pau_grouped import inplace_decode, prepared
from pau_decode import flag_data, flag_map
from pau_wide import combine
from pau_tq import measure_release
from refined_repair import repair_records
from permuted_lookup import tree
from uncompute.gadgets import xor_word
from tradeoff import ref, anf
from circuit import compress
from common import HERE
_select, _layout, _load, _gauge = (fp.select, fp.layout, fp.load, fp.gauge)

def scalar(word, row, flags, terms):
    a, c, d = flags[2:5]
    phase = word >> 29 & 1 ^ word >> 30 & 1 & (c ^ d)
    phase ^= word >> 31 & 1 & (a & c ^ a & d ^ c & d)
    phase ^= word >> 32 & 1 & flags[1]
    for j, term in enumerate(terms):
        if word >> 33 + j & 1:
            phase ^= all((row >> bit & 1 for bit in term))
    return phase

@lru_cache(None)
def source(scheme, shared_pair=False, padding='high', partition=0, overlay=True):
    """Return the payload and scalar coefficients before bank conversion."""
    if scheme == 'common_phase':
        words = common_table(padding, partition)[0]
        return (None, words)
    from family_layouts import SCHEMES, layout as extended_layout
    method = extended_layout if scheme in SCHEMES else overlay_layout if overlay else _layout
    spec = deepcopy(method(scheme, shared_pair, padding, partition))
    words = []
    for row, glob in enumerate(spec['values'][0]):
        sign = 0
        for branch, values in zip(spec['branches'], spec['values'][1:]):
            sign ^= values[row] >> branch['address_width'] + 2 * branch['target_width'] & 1
        words.append(sign << 29 | (glob >> 1 & 1023) << 30)
    return (spec, tuple(words))

@lru_cache(None)
def stripped_layout(scheme='three', shared_pair=False, padding='high', partition=0):
    spec, _ = source(scheme, shared_pair, padding, partition)
    spec = deepcopy(spec)
    values = [tuple((v & ~(1023 << 1) for v in spec['values'][0]))]
    for branch, component in zip(spec['branches'], spec['values'][1:]):
        mask = (1 << branch['address_width'] + 2 * branch['target_width']) - 1
        values.append(tuple((v & mask for v in component)))
    spec['values'] = tuple(values)
    return spec

@lru_cache(None)
def phase_polynomials(scheme, shared_pair, padding, partition, log_bank):
    _, scalar_words = source(scheme, shared_pair, padding, partition)
    terms = common_table(padding, partition)[4]
    polynomials = [0] * ref().L
    for gens, lo, hi in ref().REGIONS:
        n = len(gens)
        span = 1 << n
        size = span << log_bank
        for first in range(lo & ~(size - 1), hi, size):
            valid = max(first, lo)
            truth = []
            for j in range(size):
                row = first + j
                word = scalar_words[row if lo <= row < hi else valid]
                flags = [0] * 7
                for bit, generator in enumerate(gens):
                    flags[generator] = j >> bit & 1
                truth.append(scalar(word, row, flags, terms))
            coefficients = anf(tuple(truth), n + log_bank)[0]
            polynomial = sum((v << mask for mask, v in enumerate(coefficients)))
            for row in range(max(first, lo), min(first + size, hi)):
                polynomials[row] = polynomial
    return tuple(polynomials)

def set_bits(word):
    while word:
        bit = word & -word
        yield (bit.bit_length() - 1)
        word ^= bit

def phase_lookup(b, address, values, target, hold, order, polynomials):
    """Native walker with a payload XOR and a diagonal phase at each leaf."""
    width = len(target)
    keys = tuple((v | p << width for v, p in zip(values, polynomials)))
    root, words = tree(keys, tuple(order))
    masks = sorted({m for p in polynomials for m in set_bits(p)}, key=lambda m: (m.bit_count(), m))
    products = {1 << j: q for j, q in enumerate(address)}
    trail = []

    def product(mask):
        if mask in products:
            return products[mask]
        split = next(((a, mask ^ a) for a in sorted(products) if a & mask == a and a != mask and (mask ^ a in products)), None)
        if split is None:
            bit = mask & -mask
            split = (mask ^ bit, bit)
        a, c = (product(m) for m in split)
        q = b.and_compute(a, c)
        products[mask] = q
        trail.append((q, a, c))
        return q
    for mask in masks:
        if mask:
            product(mask)

    def leaf(number, control):
        word = words[number]
        xor_word(b, control, word & (1 << width) - 1, target)
        for mask in set_bits(word >> width):
            if not mask:
                if control is not None:
                    b.z(control)
                else:
                    b.neg()
            elif control is None:
                b.z(products[mask])
            else:
                b.cz(control, products[mask])
    if root.kind == 'leaf':
        leaf(root.lo, None)
    else:
        cost, policy = ref()._walk_policy(root, hold)
        assert cost < ref()._INF
        ref()._policy_walk(b, root, policy, hold, lambda node: address[order[len(order) - node.span.bit_length() + 1]], leaf)
    for q, a, c in reversed(trail):
        b.and_release(q, a, c)

@lru_cache(None)
def common_data(log_bank, padding, partition):
    native = tuple((v & (1 << 29) - 1 for v in common_table(padding, partition)[0]))
    encoded, basis, constant = compress(native)
    rank = len(basis)
    words = [0] * ref().L
    k = 1 << log_bank
    for gens, lo, hi in ref().REGIONS:
        span = 1 << len(gens)
        for first in range(lo & ~(k * span - 1), hi, k * span):
            valid = max(first, lo)
            group = [encoded[first + j * span] if lo <= first + j * span < hi else encoded[valid] for j in range(k)]
            coefficients = anf(tuple(group), log_bank)[0]
            packed = sum((v << rank * j for j, v in enumerate(coefficients)))
            for row in range(max(first, lo), min(first + k * span, hi)):
                words[row] = packed
    return (native, tuple(encoded), tuple(basis), constant, tuple(words))

def phase_free_core(b, flags, label, x):
    """Same 123-swap PAU network, with scalar phases handled in the lookup."""
    from pau_composed import local_select

    class Core:
        skip = False
        action_ccz = 0

        def __getattr__(self, name):
            if self.skip and name in ('cx', 'cz', 'and_release'):
                return lambda *args: None
            return getattr(b, name)

        def cz(self, a, c):
            if a in dummy:
                self.skip = True
                if a == dummy[3]:
                    self.skip = False
                return
            if not self.skip:
                b.cz(a, c)

        def and_compute(self, a, c):
            if self.skip:
                return -1000
            return b.and_compute(a, c)

        def z(self, q):
            if q not in dummy:
                b.z(q)

        def ccz(self, a, c, q):
            assert a == flags[1]
            self.action_ccz += 1
            if self.action_ccz == 4:
                for j in range(3):
                    b.cx(x[3], x[j])
                    b.ccz(flags[1], label[21 + j], x[j])
                    b.cx(x[3], x[j])
    dummy = (-1001, -1002, -1003, -1004)
    proxy = Core()
    local_select(proxy, flags, list(label) + list(dummy), x)
    assert proxy.action_ccz == 4 and (not proxy.skip)

def common_select(b, sel, system, log_label=1, label_hold=14, label_low=6, label_window=6, label_repair_hold=8, padding='high', partition=0, order=None, lookup_plans=None, repair=True, **unused):
    native, encoded, basis, constant, words = common_data(log_label, padding, partition)
    rank = len(basis)
    width = rank << log_label
    meta_values, meta_basis, meta_constant, factors, flag_values = flag_data(log_label)
    bank = b.qubits(width)
    meta = b.qubits(len(meta_basis))
    combined = tuple((w | m << width for w, m in zip(words, meta_values)))
    plan = (lookup_plans or {}).get('0', dict(order=order or list(reversed(range(16))), hold=label_hold))
    with b.phase('phase-label/lookup'):
        phase_lookup(b, sel, combined, bank + meta, plan['hold'], plan['order'], phase_polynomials('common_phase', False, padding, partition, log_label))
    flags = b.qubits(7 + log_label)
    with b.phase('phase-label/flags'):
        flag_map(b, sel, meta, flags, meta_basis, meta_constant, factors)
    meta_records = measure_release(b, meta)
    with b.phase('phase-label/combine'):
        combine(b, flags[7:], bank, rank)
    spare = measure_release(b, bank[rank:])
    label, close = inplace_decode(b, bank[:rank], basis, constant, 29)
    with b.phase('phase-pau/core'):
        phase_free_core(b, flags[:7], label, system)
    close()
    records = measure_release(b, bank[:rank]) + spare + meta_records + measure_release(b, flags)
    values = tuple((v | w >> rank << rank | m << width | f << width + len(meta_basis) for v, w, m, f in zip(encoded, words, meta_values, flag_values)))
    if repair:
        with b.phase('phase-label/repair'):
            repair_records(b, sel, records, values, label_low, label_window, label_repair_hold)
    return values

def select(b, sel, x, scheme='three', shared_pair=False, padding='high', partition=0, log_label=1, **options):
    if scheme == 'common_phase':
        return common_select(b, sel, x, log_label=log_label, padding=padding, partition=partition, **options)
    polys = phase_polynomials(scheme, shared_pair, padding, partition, log_label)
    calls = 0

    def load(b, addr, values, target, hold, order):
        nonlocal calls
        calls += 1
        if calls == 1:
            phase_lookup(b, addr, values, target, hold, order, polys)
        else:
            _load(b, addr, values, target, hold, order)
    old_layout, old_load, old_gauge = (fp.layout, fp.load, fp.gauge)
    fp.data.cache_clear()
    fp.layout = stripped_layout
    fp.load = load
    fp.gauge = lambda *args: None
    try:
        return _select(b, sel, x, scheme=scheme, shared_pair=shared_pair, padding=padding, partition=partition, log_label=log_label, **options)
    finally:
        fp.data.cache_clear()
        fp.layout, fp.load, fp.gauge = (old_layout, old_load, old_gauge)

def build(alias_configuration, selector_configuration):
    old = fp.select
    fp.select = select
    try:
        b, regs, summary = fp.build(alias_configuration, selector_configuration)
    finally:
        fp.select = old
    summary['family'] = 'phase_polynomial_' + selector_configuration['scheme']
    return (b, regs, summary)
