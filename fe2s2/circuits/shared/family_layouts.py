"""Alternative PAU partitions chosen around their actual routing geometry."""
from functools import lru_cache
import family_pau as fp
from pau_grouped import prepared
from pau_spin import table
from tradeoff import ref
SCHEMES = {'flip_split': (('at_most_two_flips', (0, 1, 2, 3, 4), 'two_flip'), ('four_flips', (5, 6), 'four')), 'spin_split': (('mixed_or_small', (0, 1, 2, 3, 5), 'four_mixed'), ('same_spin', (4, 6), 'four_same')), 'spin_three': (('at_most_two_flips', (0, 1, 2, 3, 4), 'two_flip'), ('four_mixed', (5,), 'four_mixed'), ('four_same', (6,), 'four_same'))}

@lru_cache(None)
def layout(scheme, shared_pair=False, padding='high', partition=0):
    definitions = SCHEMES[scheme]
    metadata = prepared()[4]
    old = table()[0]
    branches = []
    for name, members, kind in definitions:
        recipe = fp.stages(kind, shared_pair)
        address = sum(map(fp.stage_width, recipe))
        width = 3 if kind == 'two_flip' else 4
        branches.append(dict(name=name, members=members, kind=kind, shared=shared_pair, address_width=address, target_width=width, width=address + 2 * width + 1))
    values = [[] for _ in range(1 + len(branches))]
    census = [0] * 7
    cache = {}
    norms = {}
    for row, (base, _, _) in enumerate(metadata):
        fam = fp.family(base)
        census[fam] += 1
        chosen = next((j for j, b in enumerate(branches) if fam in b['members']))
        branch = branches[chosen]
        f, z = ref()._fz(base)
        active = fp.support(f, z)
        normalize = int(branch['kind'] == 'two_flip' and bool(f & sum((1 << i for i in fp.ODD))))
        if branch['kind'] == 'two_flip' and (not f) and all((i % 2 for i in active)):
            normalize = 1
        if shared_pair and fam in (2, 3, 4):
            normalize = int(bool(f & sum((1 << i for i in fp.ODD))))
        norms[base] = normalize
        key = (base, chosen)
        if key not in cache:
            cache[key] = fp.route_branch(base, branch['kind'], normalize, shared_pair, partition, padding)
        native, _, _, first_word = cache[key]
        global_word = normalize | (old[row] >> 30 & 1023) << 1
        if shared_pair:
            global_word |= first_word << 11
        values[0].append(global_word)
        address = native & (1 << branch['address_width']) - 1
        for j, b in enumerate(branches):
            values[j + 1].append(native if j == chosen else address & (1 << b['address_width']) - 1)
    for branch, words in zip(branches, values[1:]):
        a, w = (branch['address_width'], branch['target_width'])
        columns = {}
        for j in range(w):
            column = tuple((v >> a + j & 1 for v in words))
            if any(column):
                columns.setdefault(column, []).append(j)
        branch['flip_groups'] = list(columns.values())
    return dict(branches=branches, widths=[11 + (10 if shared_pair else 0)] + [b['width'] for b in branches], values=tuple((tuple(v) for v in values)), census=census, terms=table()[4], normalization=norms, route_cache=cache)
