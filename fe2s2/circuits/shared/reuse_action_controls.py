"""Share action-mask products between complementary two-family enables.

The selected payload has one common local Pauli mask. Compute e*m once;
the other family's mask is m XOR (e*m). All temporary products are erased
after the second local action, before any input label is measured.
"""
from contextlib import contextmanager
import compact_families as cf

@contextmanager
def use(config):
    assert config['scheme'] == 'spin_split' and config.get('pooled_actions')
    spec = cf.pooled_layout(config['scheme'], config['shared_pair'], config['padding'], config['partition'])
    assert len(spec['branches']) == 2
    off = spec['enable_offset']
    assert all((v >> off & 3 in (1, 2) for v in spec['values'][0]))
    old = cf.enabled_action
    state = {}
    calls = 0

    def action(b, flags, label, x, branch, enable):
        nonlocal calls
        a, w = (branch['address_width'], branch['target_width'])
        fields = label[a:a + 2 * w]
        if calls == 0:
            cache = {q: q if q == enable else b.and_compute(enable, q) for q in dict.fromkeys(fields)}
            state.update(enable=enable, cache=cache)
            projected = [cache[q] for q in fields]
            cf.branch_action(b, flags, label[:a] + projected + label[a + 2 * w:], x, branch)
        else:
            assert calls == 1 and set(fields) == set(state['cache'])
            first = state['enable']
            cache = state['cache']
            zero = None
            if first in cache:
                zero = b.qubit()
            for q, p in cache.items():
                if q != first:
                    b.cx(q, p)
            projected = [zero if q == first else cache[q] for q in fields]
            cf.branch_action(b, flags, label[:a] + projected + label[a + 2 * w:], x, branch)
            for q, p in reversed(list(cache.items())):
                if q != first:
                    b.cx(q, p)
                    b.and_release(p, first, q)
            if zero is not None:
                b.recycle(zero)
            state.clear()
        calls += 1
    cf.enabled_action = action
    try:
        yield
    finally:
        cf.enabled_action = old
        assert calls == 2 and (not state)
