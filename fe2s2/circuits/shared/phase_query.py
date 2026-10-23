"""Complete query with phase-factored PAUs and retained comparator carries."""
import hashlib
from common import HERE
from composed_query import alias_decode
from phase_pau import select
from retained_compare import open_compare
from pau_tq import measure_release
from refined_repair import repair_records
from uncompute import Builder
from uncompute.gadgets import declare_registers
from family_pau import hashes

def build(alias_configuration, selector_configuration, retained_borrows=0):
    b = Builder()
    regs = declare_registers(b, [('i', 16), ('sigma', 16), ('x', 40)])
    idx, sigma, x = (regs[n] for n in ('i', 'sigma', 'x'))
    c = cfg = alias_configuration
    if 'base_slices' in c:
        from segmented_alias import alias_decode as segmented
        alias, records, values = segmented(b, idx, c['base_slices'], c['log_correction'], c['lookup_plan']['correction'])
    else:
        alias, records, values = alias_decode(b, idx, c['alias_mode'], c['log_alias'], c['log_correction'], c['alias_hold'], c.get('lookup_plan'))
    keep, sel = (alias[:16], alias[16:])
    with b.phase('alias/retained-compare-select'):
        flag, close_compare = open_compare(b, sigma, keep, retained_borrows)
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
    select(b, sel, x, **selector_configuration)
    with b.phase('alias/retained-restore'):
        for a, c in zip(idx, sel):
            b.cswap(flag, a, c)
        close_compare()
    outcomes = measure_release(b, alias) + records
    with b.phase('current-alias/final-repair'):
        repair_records(b, idx, outcomes, values, cfg['alias_low'], cfg['alias_window'], cfg['alias_repair_hold'])
    assert b.active_qubits == 72
    s = b.phase_summary()
    s.update(configuration=dict(alias=alias_configuration, selector=selector_configuration, retained_borrows=retained_borrows), family='phase_polynomial_' + selector_configuration['scheme'], tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'])
    return (b, regs, s)
