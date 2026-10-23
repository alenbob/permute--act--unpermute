#!/usr/bin/env python3
"""Replay upstream binary parsing and strict measurement cleanup on basis inputs."""
import argparse,json,lzma,random
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'upstream')]
import circuits
from generate import normalized
from uncompute import Simulator
from uncompute.evalcore.compact_reader import _CompactVM


def check(point,path,shots=256,seed=20261023,all_rows=False):
    words,masks=circuits.reference_data();rng=random.Random(seed)
    count=2*len(words) if all_rows else shots
    # All-row mode has two comparator-boundary cases and random system states
    # per row, NOT all 2^40 states or all coin values.
    values=[];expected=[]
    for j in range(count):
        i=j//2 if all_rows else rng.randrange(len(words));keep=words[i]&65535
        coin=(max(0,keep-1),keep)[j%2] if all_rows else (0,65535,max(0,keep-1),keep,min(65535,keep+1),rng.randrange(65536))[j%6]
        x=rng.getrandbits(40);sel=i if coin<keep else (words[i]>>16)&65535;m=masks[sel]
        phase=((words[sel]>>33)^(m>>80)^((x&(m>>40)&((1<<40)-1)).bit_count()))&1
        values.append((i,coin,x));expected.append((i,coin,x^(m&((1<<40)-1)),phase))
    regs=circuits.registers(circuits.program_path(point));boundary=[q for reg in regs for q in reg]
    for start in range(0,count,2048):
        batch=values[start:start+2048];want=expected[start:start+2048]
        sim=Simulator(batch=len(batch),seed=seed+start,strict=True)
        for k,reg in enumerate(regs):sim.write(reg,[v[k] for v in batch])
        expected_ops=circuits.operations(circuits.program_path(point));checked=0
        class Sink:
            def apply(self,ops,validate=False):
                nonlocal checked
                for op in ops:
                    assert normalized(op)==next(expected_ops),checked;checked+=1
                sim.apply(ops,validate=validate)
        with lzma.open(path,'rb') as f:
            assert f.read(8)==b'OPSTRM01';vm=_CompactVM(f,[],Sink());vm.run();vm.flush()
        assert next(expected_ops,None) is None and checked==point['operation_count']
        assert vm.num_qubits==point['peak_total_qubits']
        for k,reg in enumerate(regs):assert sim.read(reg)==[v[k] for v in want]
        sim.assert_clean(outputs=boundary,phase=sum(v[3]<<j for j,v in enumerate(want)))
        assert sim.stats.toffoli==len(batch)*point['toffoli']
    return dict(id=point['id'],status='PASS',basis_inputs=count,seed=seed,
                native_parser_operation_equality=True,strict_measurement_ledger=True,
                scope='Both measurement outcomes algebraically on each tested basis input; input sampling does not prove all coherent input states.',
                all_rows=all_rows)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('id');p.add_argument('--shots',type=int,default=256);p.add_argument('--all-rows',action='store_true');p.add_argument('--ops',type=Path);p.add_argument('--report',type=Path)
    a=p.parse_args();result=check(circuits.entry(a.id),a.ops or ROOT/'output'/(a.id+'.ops.xz'),a.shots,all_rows=a.all_rows)
    if a.report:a.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
