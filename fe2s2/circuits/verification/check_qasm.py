#!/usr/bin/env python3
"""Parse exported statements with the official AST and compare every operation.

This is deliberately a restricted reader of the emitted dialect, not a
compiler for arbitrary OpenQASM. Unsupported constructs fail closed.
"""
import argparse
import hashlib
import itertools
import json
import lzma
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'interfaces')]
import circuits
import openqasm as exporter
import openqasm3
from openqasm3 import ast as a


def idx(node,name):
    if isinstance(node,a.IndexedIdentifier):
        assert node.name.name==name and len(node.indices)==1
        values=node.indices[0]
    elif isinstance(node,a.IndexExpression):
        assert node.collection.name==name;values=node.index
    else:raise ValueError(type(node))
    assert len(values)==1 and isinstance(values[0],a.IntegerLiteral)
    return values[0].value


def gate(n,condition=None):
    if isinstance(n,a.QuantumPhase):
        assert not n.modifiers and not n.qubits and isinstance(n.argument,a.Identifier) and n.argument.name=='pi'
        return 'NEG',(),condition
    assert isinstance(n,a.QuantumGate) and not n.arguments and n.duration is None
    name=n.name.name.upper();args=tuple(idx(q,'q') for q in n.qubits)
    if n.modifiers:
        assert name=='Z' and len(n.modifiers)==1 and n.modifiers[0].modifier.name=='ctrl' and n.modifiers[0].argument.value==2
        name='CCZ'
    assert name in {'X','Z','CX','CZ','CCX','CCZ','SWAP'}
    assert condition is None or name in {'Z','CZ','NEG'}
    return name,args,condition


def decode(nodes):
    it=iter(nodes)
    for n in it:
        if isinstance(n,a.QuantumGate) and n.name.name=='h':
            assert not n.modifiers and len(n.qubits)==1 and not n.arguments
            q=idx(n.qubits[0],'q');m=next(it);r=next(it)
            assert isinstance(m,a.QuantumMeasurementStatement) and idx(m.measure.qubit,'q')==q
            assert isinstance(r,a.QuantumReset) and idx(r.qubits,'q')==q
            yield 'HMR',(q,idx(m.target,'m')),None
        elif isinstance(n,a.QuantumReset):yield 'R',(idx(n.qubits,'q'),),None
        elif isinstance(n,a.ClassicalAssignment):
            assert n.op.name=='=' and isinstance(n.rvalue,a.BinaryExpression) and n.rvalue.op.name=='^'
            t=idx(n.lvalue,'m');assert idx(n.rvalue.lhs,'m')==t
            yield 'OXOR',(t,idx(n.rvalue.rhs,'m')),None
        elif isinstance(n,a.BranchingStatement):
            c=n.condition;assert isinstance(c,a.BinaryExpression) and c.op.name=='==' and c.rhs.value==1
            assert not n.else_block and len(n.if_block)==1
            yield gate(n.if_block[0],idx(c.lhs,'m'))
        else:yield gate(n)


def check(point,path,chunk_size=256):
    expected=circuits.operations(circuits.program_path(point));count=0
    opener=lzma.open if path.suffix=='.xz' else open
    with opener(path,'rt') as f:
        lines=iter(f);head=[]
        while len(head)<4:
            line=next(lines)
            if not line.startswith('//'):head.append(line)
        ast=openqasm3.parse(''.join(head));q,bit=ast.statements[1:]
        assert q.size.value==point['peak_total_qubits'] and q.qubit.name=='q'
        assert bit.identifier.name=='m' and bit.init_expression.value==0
        while True:
            chunk=list(itertools.islice(lines,chunk_size))
            if not chunk:break
            tree=openqasm3.parse('OPENQASM 3.0;\n'+''.join(chunk))
            for got in decode(tree.statements):
                want=next(expected);assert got==want,(count,got,want);count+=1
    assert next(expected,None) is None
    assert count==point['operation_count']
    return dict(id=point['id'],status='PASS',operations=count,
                parser_version=openqasm3.__version__,export_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                scope='All statements parsed in complete-instruction chunks; exact gate/outcome sequence equality. No full-state simulation.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('id');p.add_argument('--file',type=Path);p.add_argument('--report',type=Path)
    args=p.parse_args();point=circuits.entry(args.id);path=args.file or ROOT/'output'/(args.id+'.qasm.xz')
    if args.file is None:exporter.export(point,path)
    result=check(point,path)
    if args.report:args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
