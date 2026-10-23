"""Link every displayed point to its complete gate program."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json

HERE = Path(__file__).resolve().parent
CIRCUITS = HERE


def check_full_suite_reports():
    """Join the two supplementary upstream reports to the frozen source streams.

    This checks recorded evidence; it does not rerun the upstream suite.
    """
    manifest = json.loads((CIRCUITS / 'manifest.json').read_text())
    records = {p['id']: p for p in manifest['circuits']}
    expected = {'pau_single_q210_t5650': 18419194,
                'pau_single_q593_t3172': 18419191}
    paths = {p.stem: p for p in (CIRCUITS / 'full_suite').glob('*.json')}
    assert paths.keys() == expected.keys(), 'Supplementary report inventory'
    results = []
    for circuit_id, shots in expected.items():
        path = paths[circuit_id]
        report = json.loads(path.read_text())
        record = records[circuit_id]
        assert report['verdict'] == 'OK' and report['fail'] is None, circuit_id
        assert report['h_ops'] == record['original_gate_stream_sha256'], circuit_id
        for counter in ['wrong_output_shots', 'wrong_sign_shots', 'dirty_qubits', 'failed_shots']:
            assert report['counters'][counter] == 0, (circuit_id, counter)
        for field, key in [('toffoli', 'toffoli'), ('qubits', 'peak_total_qubits'),
                           ('tq_cost', 'toffoli_times_peak'), ('ops', 'operation_count'),
                           ('clifford', 'clifford')]:
            assert report['metrics'][field] == record[key], (circuit_id, field)
        assert report['metrics']['shots'] == shots, circuit_id
        results.append(dict(id=circuit_id, shots=shots,
                            report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            original_gate_stream_sha256=report['h_ops']))
    return dict(status='PASS', scope='Recorded full-suite report/hash linkage; no new full-suite run.',
                reports=results)


def check_data(recount=False):
    data = json.loads((HERE.parent / 'video/plot_data.json').read_text())
    path = CIRCUITS / 'manifest.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == data['circuit_manifest_sha256']
    manifest = json.loads(path.read_text())
    records = {p['id']: p for p in manifest['circuits']}
    spec = importlib.util.spec_from_file_location('gate_programs', CIRCUITS / 'circuits.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    points = [data['baseline'], *data['rows']]
    assert len({p['key'] for p in points}) == len(points) == 24
    result = []
    for point in points:
        record = records[point['key']]
        assert point['q'] * point['toffoli'] == point['tq']
        assert (record['peak_total_qubits'],record['toffoli'],record['toffoli_times_peak']) == (
            point['q'],point['toffoli'],point['tq'])
        assert (CIRCUITS / record['file']).is_file()
        if point == data['baseline']:
            assert record['id'].startswith('frame_released_')
        else:
            expected = {'Frame SELECT':'frame_paper_', 'Frame extension':'frame_extended_',
                        'PAU':'pau_single_'}[point['series']]
            assert record['id'].startswith(expected)
        row = dict(id=point['key'],toffoli=point['toffoli'],peak_total_qubits=point['q'],
                   toffoli_times_peak=point['tq'])
        if recount:
            counts = module.resources(record)
            assert all(counts[k] == row[k] for k in row)
            row['recounted'] = True
        result.append(row)
    assert data['best'] in data['rows']
    assert data['best']['tq'] == min(p['tq'] for p in data['rows'] if p['series']=='PAU')
    assert data['timing']['rectangle_start'] == data['best']['onset_seconds'] + .38
    assert all(p['q']<=data['domains']['leftX'][1] and p['toffoli']<=data['domains']['leftY'][1]
               for p in points)
    return dict(status='PASS',displayed_points=len(points),recounted=recount,points=result)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recount',action='store_true',help='Read every displayed gate program and recount resources.')
    args=parser.parse_args()
    print(json.dumps(dict(point_data=check_data(args.recount),
                          full_suite=check_full_suite_reports()),indent=2))
