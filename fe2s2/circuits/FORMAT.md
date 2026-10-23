# Readable gate-program format, version 1

Each `.gates.xz` file is an XZ-compressed ASCII program. Decompress with an XZ
utility or `python circuits.py emit CIRCUIT_ID`. Lines run in circuit time
order. There are no macro gates, omitted blocks, loops or implicit lookups.

```text
FE2S2-GATES 1
REGISTER index 0 1 ... 15
REGISTER coin 16 17 ... 31
REGISTER system 32 33 ... 71
... gate lines ...
END number_of_gate_lines
```

The ellipses above illustrate the layout; actual files list every wire and
every gate explicitly. Register bits are little-endian: the first listed wire
is the least significant bit. Other qubits start in zero and must finish in
zero. Measurement outcome registers are classical, start at zero, and are not
included in logical-qubit counts. Qubit IDs and outcome IDs are separate spaces.

| Line | Meaning | Toffoli equivalents |
|---|---|---:|
| `X t` | Pauli X on qubit t | 0 |
| `Z t` | Pauli Z on qubit t | 0 |
| `NEG` | Multiply the state by −1 | 0 |
| `CX c t` | Controlled X | 0 |
| `CZ c t` | Controlled Z | 0 |
| `SWAP a b` | Exchange two qubits | 0 |
| `CCX a b t` | Toffoli | 1 |
| `CCZ a b t` | Three-qubit controlled phase | 1 |
| `R q` | Reset/release a qubit already known to be zero; tests reject a dirty reset | 0 |
| `HMR q o` | Measure q in the X basis, store the result in outcome o, then reset q to zero | 0 |
| `OXOR dst src` | Classical `outcome[dst] ^= outcome[src]` | 0 |

`Z`, `CZ` and `NEG` may end with `@o`, meaning apply the phase only when the
stored measurement outcome o equals one. For example, `CZ 5 8 @12` is a
measurement-conditioned Clifford correction, not a three-qubit CCZ. Conditions
do not discount the static operation count.

CX, CZ, SWAP, R and HMR contribute to the separate Clifford counter. X, Z and
NEG are treated as tracked Pauli/global phases in the benchmark's bookkeeping.
OXOR is classical bookkeeping. All program qubit operands of a gate are distinct.

For a basis-state trajectory, `HMR q o` draws a fresh random bit m, multiplies
the sign by `(-1)^(m * q)`, writes `outcome[o] = m` and sets q to zero. Later
conditional phase gates repair this measurement kickback. This is the public
benchmark's kickmix circuit semantics; it is not an approximation that drops
measurement phases. The smoke runner checks sampled measurement records; it
does not prove that every possible record is repaired.

Example of a computed temporary AND and its cleanup:

```text
CCX 0 1 72
HMR 72 0
CZ 0 1 @0
R 72
```

This sequence costs one Toffoli equivalent. An actual useful operation would
use qubit 72 between computation and measurement. The included gate programs
retain all such uses and corrections explicitly.

Programmatic access:

```python
import circuits

point = circuits.entry('pau_single_q210_t5650')
print(circuits.resources(point))
for name, operands, measurement_condition in circuits.operations(circuits.program_path(point)):
    # Translate each explicit gate to a preferred circuit framework.
    # Preserve HMR, outcome XOR and measurement-conditioned phases.
    pass
```

The text programs are normalized exports of pinned public-model operation
streams. `original_gate_stream_sha256` identifies the exact pre-export program;
`text_sha256` identifies its normalized readable expansion. Native segment
boundaries carry no circuit meaning and are not preserved. This format is not
OpenQASM and should not be passed directly to an OpenQASM parser.
