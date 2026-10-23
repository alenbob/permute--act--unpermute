# Fe₂S₂ circuits

Single- and two-family PAU implementations for the 40-qubit Fe₂S₂ benchmark,
with Frame SELECT comparison circuits: **31 decomposed programs**, including
alias sampling, SELECT, measurement feed-forward and cleanup.

## Quick start

From this directory, with Python 3.10+ and no extra packages:

```sh
python circuits.py list
python circuits.py check
python circuits.py smoke pau_single_q210_t5650 --shots 256 --seed 42
```

`check` verifies hashes, resource counts and phase ledgers; `smoke` tests
sampled outputs, signs and clean ancillas. To inspect a complete program:

```sh
python circuits.py emit pau_single_q210_t5650 > pau_single.gates
```

[FORMAT.md](FORMAT.md) defines the gates. The video and its point data are in
[`../video/`](../video/).

## Rebuild a circuit

Use Python 3.11 and the pinned dependencies:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-build.txt
python generate.py pau_single_q210_t5650
python verification/check_native.py pau_single_q210_t5650
```

Substitute any ID in [configurations/](configurations/). The generator builds
from the table and configuration, then checks exact agreement with the frozen
gate sequence. It writes four files to ignored `output/`:

- `.gates.xz`: readable gate program.
- `.ops.xz`: native binary program for the evaluator.
- `.liveness.json.xz`: allocation/free trace and replayed peak.
- `.json`: per-stage costs and source/configuration hashes.

The scientific emitters are in [shared/](shared/). Configurations capture the
chosen tradeoff points; the optimization-search history is not included.

## Implementations

| Circuit ID prefix | Construction |
|---|---|
| `pau_single` | One common four-mode action core, with composed mode permutations and pair routers |
| `pau_two` | Mixed-spin/small-support and same-spin families, sharing routing and controls |
| `frame_released` | Released Frame SELECT reference |
| `frame_paper` | The same SELECT with its existing unlookup window and workspace retuned |
| `frame_extended` | Frame SELECT with shared alias, decoder and cleanup optimizations |

PAU executes **permute → local action → unpermute**. Frame SELECT executes
**σ† → representative Pauli R → σ**. In two-family PAU, both conditional
sandwiches execute coherently and their full costs are counted.

## Qualtran, Cirq and OpenQASM

```sh
python -m pip install -r requirements-interfaces.txt
python interfaces/openqasm.py pau_single_q210_t5650
python verification/check_qasm.py pau_single_q210_t5650
python verification/check_cores.py
```

The [interfaces guide](interfaces/) shows how to use the three decomposable
Qualtran SELECT cores and complete dynamic Cirq queries. OpenQASM 3 exports
include measurement, classical XOR and feed-forward; decompress `.qasm.xz`
with `xz -dc`. Qualtran cores and complete queries have different boundaries,
specified in that guide.

## Circuit contract and resources

```text
|i>_16 |coin>_16 |x>_40
  -> (-1)^phase |i>_16 |coin>_16 |x XOR flip(selected)>_40

selected = i if coin < keep[i] else alternate[i]
phase = coefficient_sign[selected] XOR half_Y_parity[selected]
        XOR parity(x AND Z_or_Y_mask[selected])
```

Valid rows are `0 <= i < 41052`, with all 40-bit system inputs in both parity
sectors. The instance has 30 electrons in 20 spatial orbitals, a coefficient
threshold of `1e-4`, no identity term, and 16-bit alias precision. The address
and coin are restored and all workspace is cleaned.

Resources count **CCX + CCZ Toffoli equivalents** and peak total logical
qubits, including the 40 system qubits. Measurement-conditioned Clifford
corrections remain Clifford. Allocation traces check the live peak; stage
counts add, stage peaks do not. Abstract all-to-all connectivity is assumed.
Uniform preparation, reflection, QPE and an additional external control are
outside this alias–SELECT–unlookup boundary. The Toffoli–qubit product is not
depth or physical runtime.

## Verification

The [release report](verification/release_verification.json) records exact
regeneration of all 31 circuits, 256 native strict-ledger basis inputs per
query, two system inputs for every term row of each Qualtran core, and parser
and operation checks of three complete OpenQASM exports. The
[verification guide](verification/) gives the commands and precise coverage.
Finite input tests are not exhaustive quantum-state verification.

These two programs also have recorded full-suite runs, with zero failures:

| Circuit | Tested inputs | Report |
|---|---:|---|
| `pau_single_q210_t5650` | 18,419,194 | [JSON](full_suite/pau_single_q210_t5650.json) |
| `pau_single_q593_t3172` | 18,419,191 | [JSON](full_suite/pau_single_q593_t3172.json) |

Those are historical runs linked to the exact source-stream hashes. To run
the full evaluator on a regenerated circuit (about 18.4 million probes):

```sh
python upstream/tools/eval.py chemistry-fe2s2 \
  --ops output/pau_single_q210_t5650.ops.xz --jobs 2 --out output/full-grader
```

An optional C kernel accelerates this: run `make kernel PYTHON=/path/to/python`
from `upstream/`. The package-wide check is `python ../verify.py`.

## References and credits

PAU follows [Summer–Jamet](https://arxiv.org/abs/2610.03686); the Hamiltonian
data are from [Li–Chan](https://github.com/zhendongli2008/Active-space-model-for-Iron-Sulfur-Clusters).
The Frame SELECT comparison and reused benchmark code/data come from
[Gu et al.](https://arxiv.org/abs/2610.22367) and
[uncompute](https://github.com/andigu/uncompute/tree/64b5a13aa249f1360846657392e6c66817b26d0f).
Reuse includes term/frame and sign tables, alias data and lookup/comparator/
cleanup machinery. These support both optimized architectures; the added
emitters, adapters and checks implement the extensions in this release.

[references.bib](../references.bib) also credits the alias-sampling, lookup and
temporary-AND methods. Code is Apache-2.0; the [repository license](../../LICENSE)
and [vendored license](upstream/LICENSE) are retained.
