"""Pinned inputs and upstream circuit infrastructure for the Fe2S2 experiment."""
from pathlib import Path
import hashlib
import json
import lzma
import sys
HERE = Path(__file__).resolve().parent
VENDOR = HERE.parent / 'upstream'
TASK = VENDOR / 'tasks/chemistry-fe2s2'
COMMIT = '64b5a13aa249f1360846657392e6c66817b26d0f'
sys.path.insert(0, str(VENDOR))

def inputs():
    contract = json.loads((TASK / 'contract.json').read_text())
    table = json.loads(lzma.decompress((TASK / 'data/table.json.xz').read_bytes()))
    masks_blob = json.loads(lzma.decompress((TASK / 'data/masks.json.xz').read_bytes()))
    words = [int(t['word'], 16) for t in table['terms']]
    masks = [int(m, 16) for m in masks_blob['masks']]
    assert len(words) == len(masks) == contract['L'] == 41052
    for values, size, key in [(words, 8, 'data_sha256'), (masks, 16, 'masks_sha256')]:
        assert hashlib.sha256(b''.join((v.to_bytes(size, 'little') for v in values))).hexdigest() == contract[key]
    assert hashlib.sha256(lzma.decompress((TASK / 'data/fcidump.xz').read_bytes())).hexdigest() == contract['fcidump_sha256']
    assert str(table['lambda']) == contract['lambda']
    return (contract, table, words, masks)

def upstream():
    from uncompute.testing import load_module
    return load_module(TASK / 'circuits/discovered/circuit.py', 'fe2s2_discovered')
