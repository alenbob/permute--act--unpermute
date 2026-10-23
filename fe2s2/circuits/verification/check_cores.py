#!/usr/bin/env python3
"""All-row signed core tests and actual Qualtran decomposition reconciliation."""
import json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'interfaces'),str(ROOT/'shared'),str(ROOT/'upstream')]
import numpy as np
import cirq
import circuits
from uncompute import Builder,Simulator
from qualtran.bloqs.mcmt import And
from qualtran._infra.gate_with_registers import get_named_qubits
from qualtran_bloqs import SelectCore
import core_emitters
from pau_grouped import prepared
from phase_pau import common_data,source,scalar
from pau_spin import table as common_table
from frame_mask_space import table as frame_table


def native(kind):
    b=Builder();regs={name:b.qubits(n) for name,n in core_emitters.widths(kind).items()}
    core_emitters.emit(kind,b,regs);return b,regs


def from_qualtran(kind):
    bloq=SelectCore(kind);cb=bloq.decompose_bloq();ports=get_named_qubits(bloq.signature.lefts())
    circuit=cb.to_cirq_circuit(cirq_quregs=ports,qubit_manager=cirq.GreedyQubitManager(prefix='anc',maximize_reuse=True))
    b=Builder();regs={k:b.qubits(q.size) for k,q in ports.items()}
    mapping={q:w for k,qs in ports.items() for q,w in zip(qs.flatten(),regs[k])}
    def wire(q):
        if q not in mapping:mapping[q]=b.qubit()
        return mapping[q]
    primitives=0
    for op in circuit.all_operations():
        g=op.gate;qs=op.qubits;primitives+=1
        if isinstance(g,And):
            assert (g.cv1,g.cv2)==(1,1)
            a,c=map(wire,qs[:2])
            if g.uncompute:b.and_release(mapping.pop(qs[2]),a,c)
            else:
                if qs[2] in mapping:b.ccx(a,c,mapping[qs[2]])
                else:mapping[qs[2]]=b.and_compute(a,c)
        elif isinstance(g,cirq.GlobalPhaseGate):assert g.coefficient==-1;b.neg()
        else:
            functions={cirq.X:b.x,cirq.Z:b.z,cirq.CNOT:b.cx,cirq.CZ:b.cz,cirq.CCX:b.ccx,cirq.CCZ:b.ccz,cirq.SWAP:b.swap}
            assert g in functions,repr(g);functions[g](*(wire(q) for q in qs))
    return b,regs,len(cb.bloq_instances),primitives


def check():
    words,masks=circuits.reference_data();metadata=prepared()[4];flags=[sum(v<<j for j,v in enumerate(m[1])) for m in metadata]
    terms=common_table()[4];rng=random.Random(261003686);result=[]
    for kind,expected_tof in [('single',257),('two',274),('frame',158)]:
        n,regs=native(kind);q,qregs,nb,nops=from_qualtran(kind)
        assert n.phase_summary()['total_emitted_toffoli']==q.phase_summary()['total_emitted_toffoli']==expected_tof
        if kind=='single':labels=common_data(1,'high',0)[0];scalar_words=source('common_phase')[1]
        elif kind=='two':labels=core_emitters.two_data()[1][1];scalar_words=source('spin_split',True)[1]
        else:labels=frame_table()[1];scalar_words=None
        scalar_phases=[scalar(v,i,[(flags[i]>>k)&1 for k in range(7)],terms) for i,v in enumerate(scalar_words)] if scalar_words is not None else [0]*len(words)
        for start in range(0,len(words),1024):
            rows=list(range(start,min(start+1024,len(words))))*2
            states=[0]* (len(rows)//2)+[rng.getrandbits(40) for _ in rows[len(rows)//2:]]
            expected=[];phases=[]
            for i,x in zip(rows,states):
                m=masks[i];expected.append(x^(m&((1<<40)-1)))
                phases.append(((words[i]>>33)^(m>>80)^((x&(m>>40)&((1<<40)-1)).bit_count())^scalar_phases[i])&1)
            for builder,r in [(n,regs),(q,qregs)]:
                sim=Simulator(builder,batch=len(rows),seed=start+17,strict=True)
                values=dict(flags=[flags[i] for i in rows],label=[labels[i] for i in rows],system=states,index=rows)
                for k,ids in r.items():sim.write(ids,values[k])
                sim.run()
                for k,ids in r.items():assert sim.read(ids)==(expected if k=='system' else values[k]),(kind,k,start)
                sim.assert_clean(outputs=[j for reg in r.values() for j in reg],phase=sum(p<<j for j,p in enumerate(phases)))
        result.append(dict(kind=kind,status='PASS',toffoli=expected_tof,native_peak_qubits=n.peak_qubits,
            input_register_widths=core_emitters.widths(kind),qualtran_bloq_instances=nb,cirq_operations=nops,
            basis_inputs=2*len(words),measurement_cleanup='strict algebraic ledger on tested inputs'))
        print(json.dumps(result[-1]),flush=True)
    return dict(status='PASS',cores=result,
        scope='Every valid decoded row, zero and one random 40-bit input per row, for both native core and replay of actual Qualtran decomposition. Scalar phases factored into lookup are supplied separately. Not exhaustive over 2^40 system states or arbitrary invalid labels.')


if __name__=='__main__':
    report=check();(ROOT/'verification/core_checks.json').write_text(json.dumps(report,indent=2)+'\n')
