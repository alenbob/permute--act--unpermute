"""Retune only workspace and the released joint-MBU window of frame SELECT.

The vendor circuit is immutable. Its frame set, gauges, sign placement,
representative walk, repeated-subtree alias lookup and comparator are reused
verbatim. The only source adaptation makes the MBU address slice depend on
the already existing LOG_KW parameter. No forward ANF bank, address sifting,
retained-bank repair or PAU routine is imported.
"""
import gc
import hashlib
import inspect
import json
import os
from common import HERE, TASK, upstream

def configure(log_window=4, repair_hold=38, lookup_hold=22):
    r = upstream()
    r.H_LOOK = lookup_hold
    r._LK_ANDS, r._LK_POLICY = r._walk_policy(r._LK_ROOT, lookup_hold)
    r.LOG_KW = log_window
    r.KW = 1 << log_window
    r.FIX_WIN = 4 * r.KW
    r.N_FIX = -(-r.L // r.FIX_WIN)
    r.H_FIX = repair_hold
    r._PLANE_SETS = [r._plane_set(i) for i in range(r.N_FIX)]
    r._FX_ROOT = r._content_tree(0, 1 << r.A - 2 - log_window, r.N_FIX, None, None, lambda i: 2 if 3 in r._PLANE_SETS[i] else 1 if r._PLANE_SETS[i] else 0)
    r._FX_ANDS, r._FX_POLICY = r._walk_policy(r._FX_ROOT, repair_hold)
    source = inspect.getsource(r.b2_fixup)
    old = 'mid, hu = idx[2:6], idx[6:]'
    new = 'mid, hu = idx[2:2+LOG_KW], idx[2+LOG_KW:]'
    assert source.count(old) == 1
    exec(compile(source.replace(old, new), '<paper-window-parameter>', 'exec'), r.__dict__)
    return r

def build(log_window=4, repair_hold=38, lookup_hold=22):
    r = configure(log_window, repair_hold, lookup_hold)
    b, _ = r.build()
    s = b.phase_summary()
    assert b.active_qubits == 72
    stages = {p['name']: p['toffoli'] for p in s['phases']}
    assert sum((v for k, v in stages.items() if k.startswith('select-'))) == 3861
    assert stages['lookup'] == 10271
    s.update(configuration=dict(log_window=log_window, repair_hold=repair_hold, lookup_hold=lookup_hold), family='paper_frame_select', tq_cost=s['total_emitted_toffoli'] * s['peak_qubits'], method_scope='Paper SI IV and its released implementation; workspace/window parameters retuned here, all SELECT and forward lookup code unchanged.')
    return (b, s)
