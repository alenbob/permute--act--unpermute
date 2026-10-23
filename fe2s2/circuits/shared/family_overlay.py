"""Overlay inactive family addresses without changing any selected action.

An inactive sandwich has P=I, so its address is a semantic don't-care.
Copying the active branch's address into every inactive branch makes matching
address columns identical, allowing affine QROM compression to share them.
All physical sandwiches and all measurement repair remain in the circuit.
"""
from contextlib import contextmanager
from functools import lru_cache
from copy import deepcopy
import hashlib
import family_pau as original
from common import HERE
_layout = original.layout

@lru_cache(None)
def layout(scheme='three', shared_pair=False, padding='high', partition=0):
    spec = deepcopy(_layout(scheme, shared_pair, padding, partition))
    values = [list(v) for v in spec['values']]
    metadata = original.prepared()[4]
    for row, (base, _, _) in enumerate(metadata):
        fam = original.family(base)
        chosen = next((j for j, branch in enumerate(spec['branches']) if fam in branch['members']))
        width = spec['branches'][chosen]['address_width']
        address = values[chosen + 1][row] & (1 << width) - 1
        for j, branch in enumerate(spec['branches']):
            if j != chosen:
                assert values[j + 1][row] == 0
                values[j + 1][row] = address & (1 << branch['address_width']) - 1
    spec['values'] = tuple((tuple(v) for v in values))
    return spec

@contextmanager
def use_overlay():
    old = original.layout
    original.data.cache_clear()
    original.layout = layout
    try:
        yield
    finally:
        original.data.cache_clear()
        original.layout = old

def build(alias_configuration, selector_configuration):
    with use_overlay():
        b, regs, summary = original.build(alias_configuration, selector_configuration)
    summary['family'] = 'multiple_family_pau_overlaid_addresses'
    return (b, regs, summary)
