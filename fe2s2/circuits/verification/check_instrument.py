#!/usr/bin/env python3
"""Exercise actual Cirq measurement/XOR/feed-forward lowering on a small channel."""
import json,sys
from pathlib import Path
from unittest.mock import patch
import numpy as np
import cirq
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'interfaces')]
from qualtran_bloqs import QueryInstrument


def check():
    # Compute a*b, demolish twice and XOR the records; a single conditional CZ
    # must cancel both kicks. Also exercise a fresh XOR accumulator and NEG/Z.
    ops=[('CCX',(0,1,2),None),('HMR',(2,0),None),('R',(2,),None),
         ('CCX',(0,1,2),None),('HMR',(2,1),None),('OXOR',(2,0),None),
         ('OXOR',(2,1),None),('CZ',(0,1),2),('NEG',(),None),
         ('Z',(0,),None),('CX',(0,1),None),('SWAP',(0,1),None),
         ('CCZ',(0,1,2),None)]
    with patch('qualtran_bloqs.circuits.entry',return_value={'peak_total_qubits':3,'file':'fixture'}),patch('qualtran_bloqs.circuits.program_path',return_value='fixture'),patch('qualtran_bloqs.circuits.operations',return_value=iter(ops)):
        got=list(QueryInstrument('fixture').operations())
    q=cirq.LineQubit.range(3);actual=cirq.Circuit(o for o in got if o.qubits)
    expected=cirq.Circuit(cirq.global_phase_operation(-1),cirq.Z(q[0]),cirq.CNOT(q[0],q[1]),cirq.SWAP(q[0],q[1]))
    rng=np.random.default_rng(2601023)
    for _ in range(8):
        state=rng.normal(size=4)+1j*rng.normal(size=4);state/=np.linalg.norm(state)
        # q2 is the clean work bit in Cirq's big-endian state ordering.
        initial=np.zeros(8,dtype=complex);initial[::2]=state
        want=cirq.final_state_vector(expected,initial_state=initial,qubit_order=q)
        out=cirq.DensityMatrixSimulator(dtype=np.complex128).simulate(actual,initial_state=initial,qubit_order=q).final_density_matrix
        assert np.allclose(out,np.outer(want,want.conj()),atol=1e-12)
    phases=[o for o in got if isinstance(o.gate,cirq.GlobalPhaseGate)]
    assert len(phases)==1 and phases[0].gate.coefficient==-1
    return dict(status='PASS',coherent_inputs=8,explicit_global_phase_preserved=True,
      scope='Small channel test of actual QueryInstrument lowering, including fresh outcome XOR, measurement and conditional CZ. Whole 40-qubit queries are not densely simulated.')


if __name__=='__main__':print(json.dumps(check(),indent=2))
