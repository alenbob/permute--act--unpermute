"""Native PAU queries with shared router products and sparse adaptive lookups."""
import hashlib
from common import HERE
import composed_query as cq
import phase_query as pq
import compact_families as cf
import phase_pau as pp
from reuse_family_core import reuse
import sparse_payload_lookup as sp

def select(b, sel, x, reuse_router=True, **config):
    if config['scheme'] == 'frame_extension':
        from multiframe import use_multiframe
        c = config['frame_configuration']
        with use_multiframe():
            return cq.select(b, sel, x, 'frame', c['select_mode'], c['flag_mode'], c['log_label'], c['label_hold'], c['label_low'], c['label_window'], c['label_repair_hold'], c['padding'], c['partition'], lookup_plan=c.get('lookup_plan'))
    if config['scheme'] == 'common_phase':
        return pp.select(b, sel, x, **config)
    if not reuse_router:
        return cf.select(b, sel, x, **config)
    with reuse(b):
        return cf.select(b, sel, x, **config)

def build(alias_configuration, selector_configuration, retained_borrows=0):
    old_lookup = cq.lookup
    old_select = pq.select

    def lookup(b, addr, values, target, hold, plan, part):
        chosen = (plan or {}).get(part, {})
        if not chosen.get('sparse_payload'):
            return old_lookup(b, addr, values, target, hold, plan, part)
        sp.load(b, addr, values, target, chosen.get('hold', hold), chosen['order'], chosen.get('kind', 'fixed'), chosen.get('exact', 6), chosen.get('tie', 'priority'))
    cq.lookup = lookup
    pq.select = select
    try:
        b, regs, s = pq.build(alias_configuration, selector_configuration, retained_borrows)
    finally:
        cq.lookup = old_lookup
        pq.select = old_select
    s['family'] = 'reuse_' + selector_configuration['scheme']
    return (b, regs, s)
