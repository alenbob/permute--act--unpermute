"""Recount the frozen circuits and test sampled inputs against the alias/Pauli table.

Standard-library Python 3.10+ only. The report distinguishes resource checks
from sampled semantic checks; these tests are not an exhaustive certificate.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json

ROOT=Path(__file__).resolve().parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shots',type=int,default=256)
    parser.add_argument('--seed',type=int,default=20261023)
    parser.add_argument('--report',type=Path,help='Optional JSON output; defaults to printing the summary only.')
    args=parser.parse_args()
    assert args.shots>0
    checksums=ROOT/'SHA256SUMS'
    checked_files=0
    if checksums.exists():
        for line in checksums.read_text().splitlines():
            digest,name=line.split('  ',1)
            path=ROOT/name
            assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
            checked_files+=1
    circuits=load('frozen_circuits',ROOT/'circuits/circuits.py')
    link=load('point_link',ROOT/'circuits/check_data.py')
    point_map=link.check_data()
    full_suite=link.check_full_suite_reports()
    results=[]
    for point in circuits.manifest()['circuits']:
        counts=circuits.resources(point)
        semantic=circuits.smoke(point,args.shots,args.seed)
        results.append(dict(resources=counts,smoke=semantic))
        print(f"PASS {point['id']}: {counts['toffoli']} Toffoli, {counts['peak_total_qubits']} qubits; {args.shots} sampled inputs",flush=True)
    summary=dict(status='PASS',circuit_count=len(results),plotted_point_count=point_map['displayed_points'],
        sampled_inputs_per_circuit=args.shots,seed=args.seed,
        scope='Exact gate hashes and resource recounts, phase-ledger checks, point-data and recorded full-suite report linkage, and sampled basis-state/measurement-record checks. Not an exhaustive semantic certificate or a proof of minimal space.',
        checked_release_files=checked_files,
        recorded_full_suite=full_suite,
        circuit_manifest_sha256=hashlib.sha256((ROOT/'circuits/manifest.json').read_bytes()).hexdigest(),
        checker_sha256=hashlib.sha256((ROOT/'circuits/circuits.py').read_bytes()).hexdigest(),
        data_checker_sha256=hashlib.sha256((ROOT/'circuits/check_data.py').read_bytes()).hexdigest(),
        plot_data_sha256=hashlib.sha256((ROOT/'video/plot_data.json').read_bytes()).hexdigest(),results=results)
    if args.report:
        args.report.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))


if __name__=='__main__':
    main()
