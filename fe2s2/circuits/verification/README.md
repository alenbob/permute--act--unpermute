# Verification scope

From `circuits/`, run:

```sh
python verification/run.py
python verification/run.py --rebuild --interfaces
python verification/summarize.py
```

The first command checks every stored coefficient/Pauli/alias mass and the
fermionic-swap primitive. The second also rebuilds all 31 points, checks their
native streams, checks the three Qualtran core decompositions and parses three
representative complete OpenQASM exports. It requires the optional interface
dependencies and can take tens of minutes. The default report goes to ignored
`output/`. Keep failures visible; a partial run is not a full-release PASS.
The final command assembles the completed reports and rechecks their generator
input and artifact hashes. It does not rerun semantic tests. It requires a
completed run with both `--rebuild` and `--interfaces`; the source-linked
release summary is written to `release_verification.json`.

| Check | What it establishes | What it does not establish |
|---|---|---|
| `check_reference.py` | Every stored Pauli mask and coefficient sign; exact integer alias masses and largest-remainder weights | A new derivation of the molecular integrals |
| `generate.py` | Exact regenerated gate sequence; Toffoli counts; allocation-event replay and final live ports | Global optimality of the circuit or memory schedule |
| `check_native.py` | Independent upstream binary parsing; exact operation equality; sampled signed query action and strict measurement cleanup | Exhaustive coverage of all address/coin/system inputs |
| `check_primitives.py` | Both measurement branches of the fermionic swap, every basis column for sizes 2–6; negative mutation detected | Correctness of every large query by itself |
| `check_cores.py` | Native and actual Qualtran decompositions agree with signed reference actions on every valid decoded row, with two system inputs per row | All 2^40 system states, invalid labels, or alias loading |
| `check_instrument.py` | Small coherent channel tests of actual Cirq lowering, with XOR and feed-forward | A dense simulation of a full query |
| `check_qasm.py` | Official parser acceptance and exact AST-to-native operation equality, including outcome IDs, XOR and phase | Execution on every QASM backend or a dense simulation |

`check_native.py <id> --all-rows` optionally checks two comparator-boundary
cases for all 41,052 rows against the complete query. Its default tests 256
structured/random basis inputs. In both modes the upstream strict ledger
checks both values of each measurement outcome algebraically **on those tested
inputs**. This does not remove input-coverage limits.

The independent reference checker uses compensated floating-point summation
for the coefficient normalization; this matches the pinned table across
Python versions. Alias probabilities themselves are compared as exact integers.

The reports include the source/configuration hashes needed to identify the
checked revision. `release_verification.json` records the new release run;
`core_checks.json` records the expanded core tests. Existing `../checks.json`,
`../conversion_checks.json` and `../manifest.json` retain their historical
scope and hashes. Full upstream grader results recorded there are not described
as fresh full-suite runs. The unchanged full grader is available under
`../upstream/tools/eval.py`.

The verification boundary remains alias–SELECT–unlookup. These reports are
not a certificate for uniform preparation, reflection, controlled block
encoding, QPE, or physical fault-tolerant runtime.
