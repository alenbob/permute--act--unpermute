"""Branch-dependent label lookup with the exact scalar-phase payload retained."""
from contextlib import contextmanager, ExitStack
import hashlib
from common import HERE
import reuse_query as rq
import phase_pau as pp
import sparse_payload_lookup as sp
from uncompute.gadgets import xor_word

def phase_lookup(b, address, values, target, hold, order, polynomials, plan):
    width = len(target)
    keys = tuple((v | p << width for v, p in zip(values, polynomials)))
    root, words = sp.tree(keys, tuple(plan.get('order', order)), plan.get('kind', 'adaptive'), plan.get('exact', 6), plan.get('tie', 'priority'))
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
    for mask in sorted({m for p in polynomials for m in pp.set_bits(p)}, key=lambda m: (m.bit_count(), m)):
        if mask:
            product(mask)

    def leaf(number, control):
        word = words[number]
        xor_word(b, control, word & (1 << width) - 1, target)
        for mask in pp.set_bits(word >> width):
            if not mask:
                if control is None:
                    b.neg()
                else:
                    b.z(control)
            elif control is None:
                b.z(products[mask])
            else:
                b.cz(control, products[mask])
    hold = plan.get('hold', hold)
    if root.kind == 'leaf':
        leaf(root.lo, None)
    elif root.kind != 'empty':
        cost, policy = sp._walk_policy(root, hold)
        assert cost < sp._INF
        sp._policy_walk(b, root, policy, hold, lambda n: address[n.bit], leaf)
    for q, a, c in reversed(trail):
        b.and_release(q, a, c)

@contextmanager
def phase_decoder(plan):
    old = pp.phase_lookup
    pp.phase_lookup = lambda b, addr, values, target, hold, order, polys: phase_lookup(b, addr, values, target, hold, order, polys, plan)
    try:
        yield
    finally:
        pp.phase_lookup = old

@contextmanager
def options(config):
    c = dict(config)
    plan = c.pop('phase_tree', None)
    actions = c.pop('reuse_actions', False)
    basis = c.pop('action_basis', False)
    with ExitStack() as stack:
        if plan is not None:
            stack.enter_context(phase_decoder(plan))
        if basis:
            from basis_action_controls import use
            stack.enter_context(use(c))
        elif actions:
            from reuse_action_controls import use
            stack.enter_context(use(c))
        yield c

def select(b, sel, x, **config):
    with options(config) as c:
        return rq.select(b, sel, x, **c)

def build(alias_configuration, selector_configuration, retained_borrows=0):
    with options(selector_configuration) as c:
        b, regs, s = rq.build(alias_configuration, c, retained_borrows)
    s['configuration']['selector'] = selector_configuration
    s['family'] = 'branch_' + selector_configuration['scheme']
    return (b, regs, s)
