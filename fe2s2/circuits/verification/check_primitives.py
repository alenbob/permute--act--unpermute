#!/usr/bin/env python3
"""Exhaustive signed Kraus-branch checks of the one-AND fermionic swap."""
import itertools,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'shared'),str(ROOT/'upstream')]
from uncompute import Builder
from routing import fermionic_swap
from generate import normalized


def branch(ops,bits,outcome):
    q=dict(enumerate(bits));phase=0;records={};draws=0
    for op,a,cond in ops:
        if op=='CX':q[a[1]]=q.get(a[1],0)^q.get(a[0],0)
        elif op=='CCX':q[a[2]]=q.get(a[2],0)^(q.get(a[0],0)&q.get(a[1],0))
        elif op=='HMR':records[a[1]]=outcome;phase^=q.get(a[0],0)&outcome;q[a[0]]=0;draws+=1
        elif op=='R':assert q.get(a[0],0)==0
        elif op in ('Z','CZ','CCZ','NEG'):
            value=1
            for i in a:value&=q.get(i,0)
            phase^=value if cond is None else value&records[cond]
        else:raise ValueError(op)
    assert draws==1
    return q,phase


def check():
    cases=0;mutation_detected=False
    for n in range(2,7):
        for i in range(n):
            for j in range(i+1,n):
                b=Builder();c=b.qubit();x=b.qubits(n);fermionic_swap(b,c,x,i,j)
                assert b.phase_summary()['total_emitted_toffoli']==1
                ops=[normalized(op) for op in b.iter_expanded()]
                mutated=ops.copy();del mutated[next(k for k,(g,a,_) in enumerate(ops) if g=='CZ')]
                for bits in itertools.product((0,1),repeat=n+1):
                    wanted=list(bits);control=bits[0];a,bv=bits[i+1],bits[j+1]
                    expected=control*((a*bv)^((a^bv)*(sum(bits[i+2:j+1])%2)))
                    if control:wanted[i+1],wanted[j+1]=wanted[j+1],wanted[i+1]
                    for outcome in (0,1):
                        q,phase=branch(ops,bits,outcome)
                        assert [q[k] for k in range(n+1)]==wanted and phase==expected
                        assert all(v==0 for k,v in q.items() if k>n)
                        try:mq,mp=branch(mutated,bits,outcome);mutation_detected|=mp!=expected
                        except AssertionError:mutation_detected=True
                        cases+=1
    assert mutation_detected
    return dict(status='PASS',signed_basis_branches=cases,system_sizes=list(range(2,7)),
                both_measurement_outcomes=True,negative_mutation_detected=True,
                scope='For each transposition, both Kraus branches equal the signed fermionic swap times 1/sqrt(2), on every basis column. This establishes the coherent primitive channel, not the full query.')


if __name__=='__main__':print(json.dumps(check(),indent=2))
