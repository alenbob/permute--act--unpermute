"""Compute an independent basis of the two families' action-mask products.

The affine identities are derived from every valid decoded action label.
Only independent e*m products require temporary ANDs; dependent outputs use
X/CNOT projections. Complementary-family masks are m XOR (e*m).
"""
from functools import lru_cache
from contextlib import contextmanager
import compact_families as cf

@lru_cache(None)
def model(scheme, shared, padding, partition):
    spec = cf.pooled_layout(scheme, shared, padding, partition)
    assert scheme == 'spin_split' and len(spec['branches']) == 2
    branch = spec['branches'][0]
    a, w = (branch['address_width'], branch['target_width'])
    mask = (1 << 2 * w) - 1
    rows = sorted({(v >> spec['enable_offset'] & 3, word >> a & mask) for v, word in zip(spec['values'][0], spec['values'][1])})
    assert all((e in (1, 2) for e, m in rows))
    inputs = [(1 << len(rows)) - 1, sum(((e & 1) << j for j, (e, m) in enumerate(rows)))]
    inputs += [sum(((m >> k & 1) << j for j, (e, m) in enumerate(rows))) for k in range(2 * w)]
    pivots = {}

    def reduce(v):
        code = 0
        while v:
            p = v.bit_length() - 1
            if p not in pivots:
                break
            row, c = pivots[p]
            v ^= row
            code ^= c
        return (v, code)
    for k, v in enumerate(inputs):
        rest, code = reduce(v)
        if rest:
            pivots[rest.bit_length() - 1] = (rest, code ^ 1 << k)
    products = []
    expressions = []
    for k in range(2 * w):
        value = inputs[1] & inputs[2 + k]
        rest, code = reduce(value)
        if rest:
            index = len(inputs) + len(products)
            products.append(k)
            pivots[rest.bit_length() - 1] = (rest, code ^ 1 << index)
            code = 1 << index
        expressions.append(code)
    columns = inputs + [inputs[1] & inputs[2 + k] for k in products]
    for k, expr in enumerate(expressions):
        value = 0
        for j, col in enumerate(columns):
            if expr >> j & 1:
                value ^= col
        assert value == inputs[1] & inputs[2 + k]
    return dict(products=products, expressions=expressions, width=w, unique_labels=len(rows), input_columns=len(inputs))

@contextmanager
def use(config):
    assert config.get('pooled_actions')
    plan = model(config['scheme'], config['shared_pair'], config['padding'], config['partition'])
    old = cf.enabled_action
    state = {}
    calls = 0

    def action(b, flags, label, x, branch, enable):
        nonlocal calls
        a, w = (branch['address_width'], branch['target_width'])
        fields = label[a:a + 2 * w]
        if calls == 0:
            products = [b.and_compute(enable, fields[k]) for k in plan['products']]
            state.update(enable=enable, fields=fields, products=products)
        else:
            assert calls == 1 and fields == state['fields']
        wires = [None, state['enable']] + fields + state['products']
        expressions = []
        for j, expr in enumerate(plan['expressions']):
            if calls:
                expr ^= 1 << 2 + j
            parity = set()
            for k, q in enumerate(wires[1:], 1):
                if expr >> k & 1:
                    if q in parity:
                        parity.remove(q)
                    else:
                        parity.add(q)
            expressions.append((tuple(sorted(parity)), expr & 1))
        local = {}
        for terms, constant in expressions:
            key = (terms, constant)
            if key in local:
                continue
            borrowed = len(terms) == 1 and (not constant)
            q = terms[0] if borrowed else b.qubit()
            local[key] = (q, borrowed)
            if not borrowed:
                if constant:
                    b.x(q)
                for p in terms:
                    b.cx(p, q)
        projected = [local[key][0] for key in expressions]
        cf.branch_action(b, flags, label[:a] + projected + label[a + 2 * w:], x, branch)
        for (terms, constant), (q, borrowed) in reversed(list(local.items())):
            if not borrowed:
                for p in reversed(terms):
                    b.cx(p, q)
                if constant:
                    b.x(q)
                b.recycle(q)
        if calls:
            for k, p in reversed(list(zip(plan['products'], state['products']))):
                b.and_release(p, state['enable'], fields[k])
            state.clear()
        calls += 1
    cf.enabled_action = action
    try:
        yield
    finally:
        cf.enabled_action = old
        assert calls == 2 and (not state)
