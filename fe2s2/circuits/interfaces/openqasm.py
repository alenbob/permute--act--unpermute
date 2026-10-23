#!/usr/bin/env python3
"""Export the exact dynamic program as standard OpenQASM 3.0."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import circuits


def statement(op,args,condition):
    q=', '.join(f'q[{n}]' for n in args)
    if op=='HMR':
        a,m=args
        return f'h q[{a}]; m[{m}] = measure q[{a}]; reset q[{a}];'
    if op=='OXOR':return f'm[{args[0]}] = m[{args[0]}] ^ m[{args[1]}];'
    if op=='R':return f'reset {q};'
    if op=='NEG':s='gphase(pi);'
    elif op=='CCZ':s=f'ctrl(2) @ z {q};'
    else:s=f'{op.lower()} {q};'
    return s if condition is None else f'if (m[{condition}] == 1) {{ {s} }}'


def header(point):
    path=circuits.program_path(point);nout=0
    for op,args,cond in circuits.operations(path):
        ids=args if op=='OXOR' else args[1:] if op=='HMR' else ()
        nout=max(nout,max(ids,default=-1)+1,(cond+1) if cond is not None else 0)
    return ('OPENQASM 3.0;\ninclude "stdgates.inc";\n'
        f'qubit[{point["peak_total_qubits"]}] q;\nbit[{max(1,nout)}] m = "'+ '0'*max(1,nout)+'";\n')


def export(point,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    opener=lzma.open if path.suffix=='.xz' else open
    with opener(path,'wt') as f:
        f.write('// Alias-SELECT-unlookup. Boundary inputs are specified in manifest.json.\n')
        f.write('// R resets assert a zero state in the native verifier; QASM reset alone cannot enforce this.\n')
        f.write('// Insert input preparation after the declarations when executing this standalone program.\n')
        f.write(header(point))
        for op,args,cond in circuits.operations(circuits.program_path(point)):
            f.write(statement(op,args,cond)+'\n')
    return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('id');p.add_argument('--output',type=Path)
    a=p.parse_args();path=a.output or ROOT/'output'/(a.id+'.qasm.xz')
    export(circuits.entry(a.id),path);print(path)
