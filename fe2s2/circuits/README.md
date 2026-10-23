# Fe₂S₂ circuits

**31 fully decomposed gate programs** for the 40-qubit Fe₂S₂ benchmark:
single- and two-family PAU, plus Frame SELECT comparisons. Each includes
alias sampling, SELECT, measurement feed-forward and cleanup.
The compressed plain-text programs are frozen exports; high-level generators
and optimization-search history are not included.

## Run

Python 3.10+; standard library only. From this directory:

```sh
python circuits.py list
python circuits.py check
python circuits.py smoke --shots 64
```

For one circuit:

```sh
python circuits.py emit pau_single_q210_t5650 > pau_single.gates
python circuits.py check pau_single_q210_t5650
python circuits.py smoke pau_single_q210_t5650 --shots 256 --seed 42
```

`check` verifies program hashes, counts gates and occupied qubits, and
reconciles the phase ledger. `smoke` tests sampled alias decisions, system
outputs, signs and clean ancillas with sampled measurement records.
`emit` prints the complete program; [FORMAT.md](FORMAT.md) defines its gates.

| Circuit ID prefix | Construction |
|---|---|
| `pau_single` | PAU with one common four-mode action core |
| `pau_two` | PAU with two support/action families |
| `frame_released` | Released Frame SELECT reference |
| `frame_paper` | Frame SELECT tuned within the paper's methods |
| `frame_extended` | Optimized Frame SELECT |

## Circuit contract

```text
|i>_16 |coin>_16 |x>_40
  -> (-1)^phase |i>_16 |coin>_16 |x XOR flip(selected)>_40

selected = i if coin < keep[i] else alternate[i]
phase = coefficient_sign[selected] XOR half_Y_parity[selected]
        XOR parity(x AND Z_or_Y_mask[selected])
```

Valid rows are `0 <= i < 41052`; the contract covers all 40-bit system inputs
in both parity sectors. The Li–Chan instance has 30 electrons in 20 spatial
orbitals, with `|coefficient| >= 1e-4` truncation, the identity term removed
and 16-bit alias precision. Reference hashes pin the table, signs and normalization.

The circuit loads alias data, selects a term, decodes its controls, applies
the system operation, then restores the address and cleans the workspace.
PAU uses **permute → local action → unpermute**; Frame SELECT uses
**σ† → representative Pauli R → σ**. Two-family PAU splits the routed action
into separate support cases with the same external contract.

Resources use CCX + CCZ Toffoli equivalents and total peak qubits, including
the 40-qubit system. Measurement-conditioned Clifford corrections remain
Clifford. The exported occupied-wire range matches the emitter's recorded
peak, but allocation/free events are not retained, so this does not independently
prove a minimal lifetime schedule. Phase costs may aggregate repeated visits;
phase peaks cannot be added. See the [resource boundary](../README.md#resource-boundary).

## Verification

The following exact source streams passed the full upstream test suite:

| PAU circuit | Tested shots | Report |
|---|---:|---|
| `pau_single_q210_t5650` | 18,419,194 | [JSON](full_suite/pau_single_q210_t5650.json) |
| `pau_single_q593_t3172` | 18,419,191 | [JSON](full_suite/pau_single_q593_t3172.json) |

Both reports have zero wrong-output, wrong-sign, dirty-qubit and failed-shot
counters. Their `h_ops` hashes match the manifest's `original_gate_stream_sha256`;
`conversion_checks.json` records operation-by-operation preservation in this
text format. These are existing full-suite runs, not new runs during packaging.
Other circuits retain their recorded full/subset scope; optimized rows have
82,104 all-row comparator-boundary checks and up to 65,536 native probes.

`manifest.json` and `checks.json` retain the original export's evidence and
style fields. The supplementary reports above extend that historical record.
`../release_checks.json` records the current package recount and sampled checks.
Finite tests do not certify every quantum input or measurement outcome.

`circuits.py` is the reader, counter and simulator; `data/reference.json.xz`
holds the alias words and Pauli masks. The [benchmark overview](../README.md)
sets the comparison scope; [NOTICE.md](NOTICE.md) records code/data attribution.
