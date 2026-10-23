#!/usr/bin/env python3
"""Collect completed checks, rejecting missing evidence or changed generator inputs.

This assembles existing reports; it does not rerun their semantic tests. Use
run.py --rebuild --interfaces to produce the inputs in output/ first.
"""
import argparse
import hashlib
import importlib.metadata
import json
import lzma
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import circuits

REPRESENTATIVES = ('pau_single_q210_t5650', 'pau_two_q215_t5627',
                   'frame_extended_q338_t4411')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_pass(path):
    report = json.loads(path.read_text())
    assert report['status'] == 'PASS', str(path)
    return report


def collect():
    checks = load_pass(ROOT / 'output/verification.json')
    for key in ('reference', 'primitives', 'instrument'):
        assert checks[key]['status'] == 'PASS', key
    points = circuits.manifest()['circuits']
    rebuilt, native, qasm = [], [], []
    validated_sources = {}
    for point in points:
        name = point['id']
        result = load_pass(ROOT / 'output' / (name + '.json'))
        assert result['id'] == name
        for key in ('toffoli', 'peak_total_qubits', 'text_sha256'):
            assert result[key] == point[key], (name, key)
        assert result['final_live_qubits'] == 72
        assert result['configuration_sha256'] == digest(ROOT / 'configurations' / (name + '.json'))
        for path, expected in result['source_sha256'].items():
            if path not in validated_sources:
                validated_sources[path] = digest(ROOT / path)
            assert validated_sources[path] == expected, ('Changed input', name, path)
        artifacts = {}
        for suffix in ('.gates.xz', '.ops.xz', '.liveness.json.xz'):
            artifacts[suffix] = digest(ROOT / 'output' / (name + suffix))
        with lzma.open(ROOT / 'output' / (name + '.gates.xz'), 'rb') as f:
            h = hashlib.sha256()
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        assert h.hexdigest() == result['text_sha256']
        result = {k: v for k, v in result.items() if k != 'source_sha256'}
        result['generated_artifact_sha256'] = artifacts
        rebuilt.append(result)
        test = load_pass(ROOT / 'output' / (name + '.native-check.json'))
        assert test['id'] == name and test['basis_inputs'] >= 256
        assert test['native_parser_operation_equality'] and test['strict_measurement_ledger']
        native.append(test)
    cores = load_pass(ROOT / 'verification/core_checks.json')
    assert {c['kind'] for c in cores['cores']} == {'single', 'two', 'frame'}
    assert all(c['status'] == 'PASS' and c['basis_inputs'] == 82104 for c in cores['cores'])
    for name in REPRESENTATIVES:
        test = load_pass(ROOT / 'output' / (name + '.qasm-check.json'))
        assert test['id'] == name
        assert test['operations'] == circuits.entry(name)['operation_count']
        assert test['export_sha256'] == digest(ROOT / 'output' / (name + '.qasm.xz'))
        qasm.append(test)
    source_hashes = dict(validated_sources)
    for folder in ('interfaces', 'verification', 'configurations'):
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.json') and path.name != 'release_verification.json':
                source_hashes[str(path.relative_to(ROOT))] = digest(path)
    for name in ('manifest.json', 'circuits.py', 'data/reference.json.xz',
                 'requirements-build.txt', 'requirements-interfaces.txt'):
        source_hashes[name] = digest(ROOT / name)
    versions = {'python': platform.python_version()}
    for name in ('numpy', 'click', 'qualtran', 'cirq-core', 'sympy', 'attrs', 'openqasm3', 'antlr4-python3-runtime'):
        versions[name] = importlib.metadata.version(name)
    return dict(
        status='PASS', assembled_at_utc=datetime.now(timezone.utc).isoformat(),
        evidence_origin='Completed checks collected from output/. Collection rechecks generator source/configuration and artifact hashes, not the semantic tests themselves.',
        scope='Fresh exact regeneration and allocation replay for all 31 points; 256 native strict-ledger basis inputs per query; every valid row with two system inputs for each core and its Qualtran decomposition; three complete QASM parser/operation checks. No full-state simulation of a complete query, new FCIDUMP derivation, global-optimality proof, or new full upstream grader run.',
        environment=versions, reference=checks['reference'], primitives=checks['primitives'],
        instrument=checks['instrument'], rebuilds=rebuilt, native=native, cores=cores,
        qasm=qasm, source_sha256=dict(sorted(source_hashes.items())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'verification/release_verification.json')
    args = parser.parse_args()
    report = collect()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], circuits=len(report['rebuilds']),
                          cores=len(report['cores']['cores']), qasm=len(report['qasm']))))
