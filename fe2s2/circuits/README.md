# Fe₂S₂ circuits

PAU implementations for the 40-qubit Fe₂S₂ Hamiltonian, with a common
four-mode action core or two support/action families. The programs cover
different workspace budgets and include Frame SELECT comparison circuits.
See the [benchmark overview](../README.md) for the methods and references.

This package contains **31 exact, fully decomposed gate programs**: all 24
points in the video, including the released reference, plus seven two-family
PAU comparisons from the wider figure. It is a frozen gate-level
release: the programs already contain the data lookups, alias decision,
SELECT, measurement feed-forward and cleanup. They are not resource formulas
or black-box circuit placeholders.

The small `circuits.py` reader, resource counter and simulator need **Python
3.10 or newer, with no third-party packages and no network access**. The circuit
programs are compressed plain text; `emit` prints their complete readable code.
The high-level circuit generators and optimization-search history are not
included in this essential export.

## Run

From this directory, using your Python 3.10+ interpreter:

```sh
python circuits.py list
python circuits.py check
python circuits.py smoke --shots 64
```

Inspect or test one circuit:

```sh
python circuits.py show pau_single_q210_t5650 --limit 80
python circuits.py emit pau_single_q210_t5650 > pau_single.gates
python circuits.py check pau_single_q210_t5650
python circuits.py smoke pau_single_q210_t5650 --shots 256 --seed 42
```

`check` reads the actual gate program, verifies its hashes, counts CCX/CCZ,
counts Clifford operations, checks the occupied qubit range, and reconciles the
phase ledger. `smoke` additionally checks sampled alias boundary cases, system
outputs, global signs, clean resets and final ancillas with randomly sampled
measurement records. Checking all programs can take several minutes.

## Connect the code to the video

The current video contains **24 points including the released reference**.
All 24 have complete gate programs here. Seven extra two-family PAU programs
are included from the wider figure; they are not displayed in the current video.
The exact mapping is in [`../video/plot_data.json`](../video/plot_data.json).
Run `python ../video/check_data.py --recount` to check every video point against
the gates, independently of the displayed numbers.

| Video marker | ID prefix | Construction |
|---|---|---|
| Salmon cross | `frame_released` | Released Frame SELECT implementation |
| Salmon hollow circles | `frame_paper` | Frame SELECT using the paper's methods |
| Salmon filled diamonds | `frame_extended` | Frame SELECT with shared optimizations |
| Yellow hollow squares | `pau_single` | Summer–Jamet PAU with a common routed-action core |
| Not displayed | `pau_two` | Two-family PAU comparison circuits |

The yellow rectangle ends at `pau_single_q210_t5650`: 5,650 Toffolis × 210
total qubits = 1,186,500. The released salmon rectangle ends at
`frame_released_q126_t14978`: 14,978 × 126 = 1,887,228. These are complete
alias–SELECT–unlookup costs, not costs of the system-register core alone.

The frozen `manifest.json` retains its original blue/red figure style fields
and 31-point description so that existing evidence hashes remain valid.
Those historical color and marker fields do not describe the video's palette.
Circuit IDs, gate programs, resource counts and recorded test scopes are unchanged.

## What the circuits do

The boundary map is

```text
|i>_16 |coin>_16 |x>_40
  -> (-1)^phase |i>_16 |coin>_16 |x XOR flip(selected)>_40

selected = i if coin < keep[i] else alternate[i]
phase = coefficient_sign[selected] XOR half_Y_parity[selected]
        XOR parity(x AND Z_or_Y_mask[selected])
```

The row range is `0 <= i < 41052`; other row addresses are outside the
benchmark contract. The system input ranges over all 40-bit basis states,
including both parity sectors. The finite-precision alias table, signs and
normalization are pinned in the reference-data hashes. The Hamiltonian is the
Li–Chan (30-electron, 20-orbital) Fe₂S₂ instance after the benchmark's
`|coefficient| >= 1e-4` truncation, with the identity term removed and 16-bit
alias precision.

The common logical stages are:

1. Load/combine alias data, compare the coin and select a term address.
2. Decode the selected term into the architecture's control payload.
3. Apply the system operation. PAU executes **permute → local action →
   unpermute**, routing active modes to a fixed four-mode target. Frame SELECT
   executes **σ† → representative Pauli R → σ**. The two-family PAU uses
   separate support/action cases while preserving the same boundary map.
4. Erase the payload, restore the input address, uncompute the alias decision
   and repair all measurement-induced phases.

The phase ledger is a cost breakdown, not a gate-offset map: named phases may
be revisited and their counters aggregated. Phase peaks cannot be added.

## Resource convention and verification scope

The reported count is **CCX + CCZ Toffoli equivalents**, not a count of T gates.
Temporary logical AND computation costs one such gate; its measurement-based
uncomputation uses HMR and outcome-conditioned Clifford corrections. Clifford
counts are included separately. The calculation assumes the same abstract
connectivity and logical gate model for all programs; physical routing and
error correction are not added here.

Space includes the **40 system qubits**, 16 address qubits, 16 coin qubits and
live workspace. The original emitter reused qubit IDs; this export independently
checks that `max used qubit ID + 1` matches its recorded peak-live count. The
gate stream does not retain allocation/free events and does not independently
prove the minimal lifetime schedule. The product is Toffoli count × peak total
logical qubits, **not depth, elapsed time or integrated spacetime volume**.

Uniform state preparation, reflection, QPE and an additional external control
are outside this boundary. Both experimental methods use applicable shared
alias, lookup, comparator, workspace and cleanup optimizations, retuned for
their different interfaces. Improvements over the released cross therefore
include compilation improvements as well as the choice of SELECT architecture.

`recorded_validation` preserves the prior full-suite/subset distinction for
each exact source program. These historical tests were **not rerun in full**
when packaging. `checks.json` records the original export checks and smoke tests;
`../release_checks.json` records fresh checks for this public package. These
checks do not certify all inputs or all measurement outcomes. Neither the tests
nor the finite optimization search establishes a global optimum.

`conversion_checks.json` separately records an operation-by-operation comparison
against the original programs using the upstream reference parser. This checks
that the text export preserves the complete gate sequence and register mapping.

## Files and provenance

- `circuits.py`: portable reader, resource checker and sampled basis-state simulator.
- `circuits/*.gates.xz`: complete, decomposed circuit programs; see `FORMAT.md`.
- `manifest.json`: point mapping, hashes, phase resources and prior test scope.
- `data/reference.json.xz`: pinned alias words and Pauli-action masks.
- `checks.json`: original resource and smoke-test results for this export.
- `conversion_checks.json`: exact gate-sequence preservation checks.
- `NOTICE.md` and `LICENSES/Apache-2.0.txt`: scientific attribution and upstream licensing.

See the
[acknowledgments and comparison](../README.md#acknowledgments-and-comparison)
for the shared optimization treatment. [NOTICE.md](NOTICE.md) records the
method references, data sources, specific code reuse and pinned source revision.
