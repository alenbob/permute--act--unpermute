# Circuit interfaces

The authoritative implementation is Python plus the pinned native builder.
Each point has one recipe; the formats below expose the same operations.

| Interface | Supported scope |
|---|---|
| Readable `.gates.xz` | Complete flat dynamic query; standard-library reader |
| Native `.ops.xz` | Complete query for the unchanged upstream evaluator |
| OpenQASM 3 | Complete dynamic query, including measurement, XOR, feed-forward and global phase |
| Qualtran `SelectCore` | Actual connected decompositions of single PAU, two-family PAU and banked Frame cores |
| Cirq `QueryInstrument` | Explicit dynamic operations for every complete query |

## Qualtran

```python
import sys
sys.path.insert(0, 'interfaces')
from qualtran_bloqs import SelectCore, QueryInstrument
core = SelectCore('two')       # also 'single' and 'frame'
composite = core.decompose_bloq()
print(composite.bloq_counts())
# Iterate rather than materialize a large whole-query diagram:
operations = QueryInstrument('pau_two_q215_t5627').operations()
```

The cores reuse the scientific emitters and expose flags, decoded labels and
the 40 system wires as explicit ports. They decompose to gates and temporary
AND/AND-adjoint bloqs, with no cost-only placeholder. The two-family action
identities require valid decoded labels. Scalar phases factored into lookup
are outside the PAU core boundary. Tests restore those phases when comparing
the signed Hamiltonian action.

The single PAU interface takes 29 expanded label bits, after affine decoding
of the 28 stored coordinates shown in the overview diagram. The two-family
interface takes 28 compressed coordinates and includes its affine projections.
Frame SELECT takes the 86-bit representative payload. Core-only space figures
refer to these explicit boundaries; compare complete queries for the common
resource boundary used in the video.

Qualtran 0.7 does not import arbitrary dynamic classical feed-forward into
`CompositeBloq`. `QueryInstrument` therefore supplies a Cirq operation stream;
it is not presented as a unitary Qualtran query. Its measurement keys are
versioned, so outcome reuse and XOR retain their meaning. The three system
cores do have connected Qualtran decompositions.

Qualtran's usual Clifford+T cost model is distinct from the benchmark's native
CCX+CCZ convention. Recount with `circuits.py` or `generate.py` for comparison
with the video. Do not replace the native count with a generic T count.

## OpenQASM

`openqasm.py` uses standard OpenQASM 3.0 with `stdgates.inc`. HMR becomes
H/measure/reset, CCZ becomes `ctrl(2) @ z`, NEG becomes `gphase(pi)`, and
conditional Z/CZ/NEG and outcome XOR remain explicit. The exported qubit array
has the recorded wire footprint; boundary register IDs are in the frozen
program header. Insert input preparation after the declarations when running
the standalone file.

A standard reset can discard garbage; it cannot express the native requirement
that an R wire is already zero. Run the native cleanliness checks as well.
The official-parser checker reads every emitted instruction and compares its
AST-derived operations with the frozen stream. Parser acceptance alone does
not prove semantic correctness or backend execution.

[Qualtran protocols](https://qualtran.readthedocs.io/en/latest/Protocols.html) ·
[OpenQASM measurement/reset semantics](https://openqasm.com/versions/3.0/language/insts.html).
