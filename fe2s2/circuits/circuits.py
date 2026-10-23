#!/usr/bin/env python3
"""Read, count and smoke-test the frozen Fe2S2 Figure 1(a) gate programs.

Python 3.10+; standard library only. See README.md for the resource boundary
and FORMAT.md for gate semantics. This is a gate-level release, not a search
reproducer. No project installation or network access is required.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import lzma
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parent
ARITY = dict(X=1, Z=1, NEG=0, CX=2, CZ=2, SWAP=2, CCX=3,
             CCZ=3, R=1, HMR=2, OXOR=2)
Q_ARITY = ARITY | dict(HMR=1, OXOR=0)
CLIFFORD = {'CX', 'CZ', 'SWAP', 'R', 'HMR'}


def manifest():
    return json.loads((ROOT / 'manifest.json').read_text())


def entry(name):
    return next(p for p in manifest()['circuits'] if p['id'] == name)


def program_path(point):
    return ROOT / point['file']


def registers(path):
    with lzma.open(path, 'rt', encoding='ascii') as stream:
        if stream.readline().strip() != 'FE2S2-GATES 1':
            raise ValueError('Unsupported gate-program version')
        result = []
        for name, width in [('index', 16), ('coin', 16), ('system', 40)]:
            fields = stream.readline().split()
            if fields[:2] != ['REGISTER', name] or len(fields) != width + 2:
                raise ValueError(f'Invalid {name} register')
            result.append(tuple(map(int, fields[2:])))
        ids = [q for reg in result for q in reg]
        if len(set(ids)) != 72 or min(ids) < 0:
            raise ValueError('Invalid or overlapping boundary registers')
        return result


def operations(path):
    """Yield (gate_name, operand_tuple, optional_outcome_id), in time order.

    Qubit operands precede outcome operands. HMR(q, o) writes an outcome;
    OXOR(o_target, o_source) acts only on outcomes. See FORMAT.md.
    Exhaust this iterator to check the END operation count.
    """
    with lzma.open(path, 'rt', encoding='ascii') as stream:
        for _ in range(4):
            next(stream)
        count = 0
        for line in stream:
            fields = line.split()
            if not fields:
                raise ValueError('Empty program line')
            if fields[0] == 'END':
                if fields != ['END', str(count)] or stream.read():
                    raise ValueError('Invalid END count or trailing content')
                return
            op = fields.pop(0)
            if op not in ARITY:
                raise ValueError(f'Unknown operation {op}')
            outcome = None
            if fields and fields[-1].startswith('@'):
                outcome = int(fields.pop()[1:])
                if op not in {'Z', 'CZ', 'NEG'} or outcome < 0:
                    raise ValueError('Invalid measurement-outcome condition')
            args = tuple(map(int, fields))
            if len(args) != ARITY[op] or any(v < 0 for v in args):
                raise ValueError(f'Invalid operands: {op} {args}')
            qargs = args[:Q_ARITY[op]]
            if len(qargs) != len(set(qargs)):
                raise ValueError('Aliased qubit operands')
            if op == 'OXOR' and args[0] == args[1]:
                raise ValueError('Aliased outcome operands')
            count += 1
            yield op, args, outcome
        raise ValueError('Missing END')


def digest(path, decompressed=False):
    h = hashlib.sha256()
    opener = lzma.open if decompressed else open
    with opener(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def resources(point):
    """Recount gates and occupied wire range, independently of saved totals.

    The original allocator reuses qubit IDs. Its pinned peak-live count is
    checked against this executable wire footprint; the gate stream alone
    does not reconstruct allocation/free events or prove minimal liveness.
    """
    path = program_path(point)
    if digest(path) != point['file_sha256']:
        raise ValueError('Compressed program hash mismatch')
    if digest(path, True) != point['text_sha256']:
        raise ValueError('Expanded text hash mismatch')
    regs = registers(path)
    largest = max(q for reg in regs for q in reg)
    counts = Counter()
    for op, args, _ in operations(path):
        counts[op] += 1
        if Q_ARITY[op]:
            largest = max(largest, *args[:Q_ARITY[op]])
    toffoli = counts['CCX'] + counts['CCZ']
    peak = largest + 1
    result = dict(id=point['id'], toffoli=toffoli, peak_total_qubits=peak,
                  toffoli_times_peak=toffoli * peak,
                  clifford=sum(counts[k] for k in CLIFFORD),
                  operation_count=sum(counts.values()), gate_counts=dict(counts))
    for key in ('toffoli', 'peak_total_qubits', 'toffoli_times_peak',
                'clifford', 'operation_count'):
        if result[key] != point[key]:
            raise ValueError(f'{point["id"]}: {key} mismatch')
    phases = point['phases']
    if sum(p['toffoli'] for p in phases) != toffoli:
        raise ValueError('Phase Toffoli ledger mismatch')
    if sum(p['clifford'] for p in phases) != result['clifford']:
        raise ValueError('Phase Clifford ledger mismatch')
    if max(p['peak'] for p in phases) != peak:
        raise ValueError('Phase peak ledger mismatch')
    return result


def reference_data():
    data = manifest()['reference_data']
    path = ROOT / data['file']
    if digest(path) != data['file_sha256']:
        raise ValueError('Reference data hash mismatch')
    with lzma.open(path, 'rt') as stream:
        words, masks = json.load(stream)
    if len(words) != 41052 or len(masks) != 41052:
        raise ValueError('Wrong table length')
    for values, width, pin in [(words, 8, data['words_sha256']),
                               (masks, 16, data['masks_sha256'])]:
        if hashlib.sha256(b''.join(v.to_bytes(width, 'little') for v in values)).hexdigest() != pin:
            raise ValueError('Reference table digest mismatch')
    return words, masks


def smoke(point, shots=64, seed=20261023):
    """Bit-parallel basis-state tests with random measurement outcomes.

    Checks exact outputs, global sign, clean resets and final workspace on
    these sampled inputs. This is not an exhaustive or symbolic certificate.
    """
    if shots < 1:
        raise ValueError('shots must be positive')
    words, masks = reference_data()
    rng = random.Random(seed)
    full = (1 << shots) - 1
    inputs, expected = [], []
    for lane in range(shots):
        i = (0, 41051)[lane] if lane < 2 else rng.randrange(41052)
        keep = words[i] & 65535
        coin = (0, 65535, max(0, keep - 1), keep,
                min(65535, keep + 1), rng.randrange(65536))[lane % 6]
        x = (0, (1 << 40) - 1, (1 << 30) - 1,
             rng.getrandbits(40))[lane % 4]
        selected = i if coin < keep else (words[i] >> 16) & 65535
        mask = masks[selected]
        flips, zy = mask & ((1 << 40) - 1), (mask >> 40) & ((1 << 40) - 1)
        phase = ((words[selected] >> 33) & 1) ^ ((mask >> 80) & 1) ^ ((x & zy).bit_count() & 1)
        inputs.append((i, coin, x))
        expected.append((i, coin, x ^ flips, phase))
    path = program_path(point)
    regs = registers(path)
    q = [0] * point['peak_total_qubits']
    outcomes = defaultdict(int)
    phase = 0
    for register, ids in enumerate(regs):
        for bit, wire in enumerate(ids):
            q[wire] = sum(((values[register] >> bit) & 1) << lane
                          for lane, values in enumerate(inputs))
    for number, (op, a, oc) in enumerate(operations(path)):
        if op == 'X': q[a[0]] ^= full
        elif op == 'CX': q[a[1]] ^= q[a[0]]
        elif op == 'CCX': q[a[2]] ^= q[a[0]] & q[a[1]]
        elif op in {'NEG', 'Z', 'CZ', 'CCZ'}:
            value = full
            for wire in a: value &= q[wire]
            if oc is not None: value &= outcomes[oc]
            phase ^= value
        elif op == 'SWAP': q[a[0]], q[a[1]] = q[a[1]], q[a[0]]
        elif op == 'HMR':
            outcomes[a[1]] = rng.getrandbits(shots)
            phase ^= q[a[0]] & outcomes[a[1]]
            q[a[0]] = 0
        elif op == 'R':
            if q[a[0]]: raise ValueError(f'Dirty reset at operation {number}')
        elif op == 'OXOR': outcomes[a[0]] ^= outcomes[a[1]]
        else: raise ValueError(f'Unsupported gate {op}')
    boundary = {wire for reg in regs for wire in reg}
    if any(value for wire, value in enumerate(q) if wire not in boundary):
        raise ValueError('Dirty final workspace')
    for lane, want in enumerate(expected):
        got = tuple(sum(((q[wire] >> lane) & 1) << bit
                        for bit, wire in enumerate(ids)) for ids in regs)
        got += ((phase >> lane) & 1,)
        if got != want:
            raise ValueError(f'Output/sign mismatch in lane {lane}: {got} != {want}')
    return dict(id=point['id'], shots=shots, seed=seed, status='PASS',
                scope='Sampled basis inputs and measurement records; not a full certificate.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['list', 'check', 'smoke', 'show', 'emit'])
    parser.add_argument('circuit', nargs='?', default='all')
    parser.add_argument('--shots', type=int, default=64)
    parser.add_argument('--seed', type=int, default=20261023)
    parser.add_argument('--limit', type=int, default=60)
    args = parser.parse_args()
    points = manifest()['circuits'] if args.circuit == 'all' else [entry(args.circuit)]
    if args.action in {'show', 'emit'} and len(points) != 1:
        parser.error('Choose one circuit for show/emit')
    for point in points:
        if args.action == 'list':
            print(f"{point['id']:38} {point['toffoli']:6} Toffoli  "
                  f"{point['peak_total_qubits']:4} qubits  product {point['toffoli_times_peak']:,}")
        elif args.action == 'check':
            print(json.dumps(resources(point)), flush=True)
        elif args.action == 'smoke':
            resources(point)
            print(json.dumps(smoke(point, args.shots, args.seed)), flush=True)
        else:
            with lzma.open(program_path(point), 'rt') as stream:
                for n, line in enumerate(stream):
                    if args.action == 'show' and n >= args.limit: break
                    sys.stdout.write(line)


if __name__ == '__main__':
    main()
