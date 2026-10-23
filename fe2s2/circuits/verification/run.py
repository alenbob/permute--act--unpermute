#!/usr/bin/env python3
"""Run independent reference/primitive checks and optional full reproduction."""
import argparse,hashlib,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import circuits
from check_reference import check as reference
from check_primitives import check as primitives


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rebuild',action='store_true',help='Regenerate every configured point and check its native binary stream.')
    p.add_argument('--interfaces',action='store_true',help='Check all three Qualtran cores and three representative full OpenQASM exports.')
    p.add_argument('--report',type=Path,default=ROOT/'output/verification.json')
    a=p.parse_args();result=dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),reference=reference(),primitives=primitives(),rebuilds=[],native=[],qasm=[])
    def run(script,*args):subprocess.run([sys.executable,str(ROOT/script),*args],check=True)
    if a.rebuild:
        for point in circuits.manifest()['circuits']:
            name=point['id'];run('generate.py',name)
            result['rebuilds'].append(json.loads((ROOT/'output'/(name+'.json')).read_text()))
            path=ROOT/'output'/(name+'.native-check.json');run('verification/check_native.py',name,'--report',str(path));result['native'].append(json.loads(path.read_text()))
    if a.interfaces:
        from check_instrument import check as instrument
        result['instrument']=instrument()
        run('verification/check_cores.py');result['cores']=json.loads((ROOT/'verification/core_checks.json').read_text())
        for name in ('pau_single_q210_t5650','pau_two_q215_t5627','frame_extended_q338_t4411'):
            path=ROOT/'output'/(name+'.qasm-check.json');run('verification/check_qasm.py',name,'--report',str(path));result['qasm'].append(json.loads(path.read_text()))
    result['source_sha256']={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for folder in ('shared','interfaces','verification','configurations','upstream') for path in sorted((ROOT/folder).rglob('*')) if path.is_file() and path.suffix in ('.py','.c','.json') and '__pycache__' not in path.parts and path.name not in ('release_verification.json','core_checks.json')}
    result['source_sha256']['generate.py']=hashlib.sha256((ROOT/'generate.py').read_bytes()).hexdigest()
    result['status']='PASS';a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',rebuilds=len(result['rebuilds']),native=len(result['native']),qasm=len(result['qasm']))))


if __name__=='__main__':main()
