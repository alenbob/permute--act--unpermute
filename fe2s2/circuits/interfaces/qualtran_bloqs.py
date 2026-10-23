"""Decomposable Qualtran cores and a dynamic Cirq interface for full queries.

Native Toffoli totals come from generate.py/circuits.py. Qualtran's Clifford+T
conventions are a different ledger and must not be substituted into the plot.
"""
from dataclasses import dataclass
from functools import cached_property
from contextlib import nullcontext
from pathlib import Path
import sys
import numpy as np
import cirq
import sympy
from qualtran import Bloq, QBit, Register, Signature
from qualtran.bloqs.mcmt import And
from qualtran.cirq_interop import CirqGateAsBloq
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(Path(__file__).resolve().parent)]
import circuits
import core_emitters


class Emitter:
    """Translate the same core emitter into connected Qualtran soquets."""
    def __init__(self,bb,ports):
        self.bb=bb;self.wires={};self.next=0;self.regs={}
        for name,array in ports.items():
            self.regs[name]=[]
            for soq in array:
                self.wires[self.next]=soq;self.regs[name].append(self.next);self.next+=1
    def phase(self,*args):return nullcontext()
    def qubit(self):
        q=self.next;self.next+=1;self.wires[q]=self.bb.allocate(dtype=QBit());return q
    def qubits(self,n):return [self.qubit() for _ in range(n)]
    def recycle(self,q):self.bb.free(self.wires.pop(q))
    def gate(self,g,*qs):
        if not qs:self.bb.add(CirqGateAsBloq(g));return
        inp=self.wires[qs[0]] if len(qs)==1 else np.array([self.wires[q] for q in qs])
        out=self.bb.add(CirqGateAsBloq(g),q=inp)
        for q,s in zip(qs,[out] if len(qs)==1 else out):self.wires[q]=s
    def x(self,q):self.gate(cirq.X,q)
    def z(self,q):self.gate(cirq.Z,q)
    def neg(self):self.gate(cirq.GlobalPhaseGate(-1))
    def cx(self,a,b):self.gate(cirq.CNOT,a,b)
    def cz(self,a,b):self.gate(cirq.CZ,a,b)
    def ccx(self,a,b,c):self.gate(cirq.CCX,a,b,c)
    def ccz(self,a,b,c):self.gate(cirq.CCZ,a,b,c)
    def swap(self,a,b):self.gate(cirq.SWAP,a,b)
    def cswap(self,c,a,b):self.cx(b,a);self.ccx(c,a,b);self.cx(b,a)
    def and_compute(self,a,b):
        out=self.bb.add_d(And(),ctrl=np.array([self.wires[a],self.wires[b]]))
        self.wires[a],self.wires[b]=out['ctrl'];q=self.next;self.next+=1;self.wires[q]=out['target'];return q
    def and_release(self,q,a,b):
        out=self.bb.add_d(And().adjoint(),ctrl=np.array([self.wires[a],self.wires[b]]),target=self.wires.pop(q))
        self.wires[a],self.wires[b]=out['ctrl']
    def outputs(self):
        assert set(self.wires)=={q for reg in self.regs.values() for q in reg}
        return {name:np.array([self.wires[q] for q in ids]) for name,ids in self.regs.items()}


@dataclass(frozen=True)
class SelectCore(Bloq):
    """kind: single (257 Toffolis), two (274), or banked frame (158).

    PAU labels must belong to the declared decoded table; in particular the
    two-family action basis uses identities on those valid labels. This core
    does not include alias loading, label lookup or measurement-phase repair.
    """
    kind:str='single'
    @cached_property
    def signature(self):
        return Signature([Register(k,QBit(),shape=(n,)) for k,n in core_emitters.widths(self.kind).items()])
    def build_composite_bloq(self,bb,**soqs):
        emitter=Emitter(bb,soqs);core_emitters.emit(self.kind,emitter,emitter.regs);return emitter.outputs()


@dataclass(frozen=True)
class QueryInstrument:
    """The whole dynamic query as explicit Cirq operations, including records.

    This is intentionally not a unitary Bloq: Qualtran 0.7 cannot import
    arbitrary classical feed-forward into CompositeBloq. Use SelectCore for
    connected Qualtran decompositions, this instrument for dynamic Cirq,
    or the OpenQASM exporter. No cost-only opaque query bloq is substituted.
    """
    circuit_id:str
    def operations(self,qubits=None):
        point=circuits.entry(self.circuit_id)
        q=list(qubits) if qubits is not None else cirq.LineQubit.range(point['peak_total_qubits'])
        if len(q)!=point['peak_total_qubits']:raise ValueError('Wrong qubit footprint')
        records={};draw=0
        gates={'X':cirq.X,'Z':cirq.Z,'CX':cirq.CNOT,'CZ':cirq.CZ,'CCX':cirq.CCX,'CCZ':cirq.CCZ,'SWAP':cirq.SWAP}
        for op,args,oc in circuits.operations(circuits.program_path(point)):
            if op=='HMR':
                key=f'm{draw}';draw+=1
                yield cirq.H(q[args[0]]);yield cirq.measure(q[args[0]],key=key);yield cirq.reset(q[args[0]])
                records[args[1]]=frozenset([key]);continue
            if op=='OXOR':records[args[0]]=records.get(args[0],frozenset())^records.get(args[1],frozenset());continue
            if op=='R':yield cirq.reset(q[args[0]]);continue
            operation=cirq.global_phase_operation(-1) if op=='NEG' else gates[op].on(*(q[i] for i in args))
            if oc is not None:
                keys=records.get(oc,frozenset())
                if not keys:continue
                condition=cirq.SympyCondition(sympy.Eq(sympy.Mod(sum(sympy.Symbol(k) for k in sorted(keys)),2),1))
                operation=operation.with_classical_controls(condition)
            yield operation
