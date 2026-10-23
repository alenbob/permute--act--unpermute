"""Use a frozen cost-aware alias-correction tree within complete PAU/Frame queries."""
from contextlib import contextmanager
from functools import lru_cache
import json, sys
from common import HERE
from adaptive_lookup import Node
from uncompute.gadgets import xor_word
import plane_bank, permuted_lookup, sparse_payload_lookup as sp

@lru_cache(None)
def frozen():
    data = json.loads((HERE / 'data/correction_tree.json').read_text())

    def decode(n):
        return Node(n['kind'], tuple((decode(c) for c in n['kids'])), n['lo'], n['span'], n['bit'])
    root = decode(data['root'])
    words = tuple(data['words'])
    values = tuple(data['values'])
    from pau_wide import correction_data
    assert values == correction_data(0)[-1]
    for index, value in enumerate(values):
        n = root
        while n.kind == 'two':
            n = n.kids[index >> n.bit & 1]
        assert n.kind in ('leaf', 'empty')
        assert (0 if n.kind == 'empty' else words[n.lo]) == value, (index, value)
    return (root, words, values)

@contextmanager
def correction_tree(enabled=True):
    saved = []
    if enabled:
        root, words, values = frozen()
        originals = (plane_bank.load, permuted_lookup.load, sp.load)
        for module in list(sys.modules.values()):
            if module is None:
                continue
            for name, old in list(vars(module).items()):
                if not any((old is f for f in originals)):
                    continue

                def load(b, address, payload, target, hold, *args, _old=old, **kw):
                    if len(address) == 14 and len(target) == 96 and (tuple(payload) == values) and ('correction-lookup' in b.current_phase):
                        cost, policy = sp._walk_policy(root, hold)
                        assert cost < sp._INF
                        return sp._policy_walk(b, root, policy, hold, lambda n: address[n.bit], lambda i, c: xor_word(b, c, words[i], target))
                    return _old(b, address, payload, target, hold, *args, **kw)
                saved.append((module, name, old))
                setattr(module, name, load)
    try:
        yield
    finally:
        for module, name, old in saved:
            setattr(module, name, old)
