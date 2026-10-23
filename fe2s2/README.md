# Fe₂S₂ reproduction

This snapshot contains the complete gate programs behind **all 24 points in
the video**, the pinned alias/Pauli reference data, a resource counter and
sampled simulator, and a standalone renderer with its data, fonts and logos.
Seven additional two-family PAU programs from the wider figure are also included.

| Directory | Contents |
|---|---|
| [circuits](circuits/) | 31 decomposed gate programs, reference data, point manifest, reader and checks |
| [video](video/) | Renderer, numerical point mapping, dependencies, assets and reference outputs |

## Check the circuits and plotted values

Python 3.10+ is sufficient; these checks use only the standard library.
From this directory:

```sh
python verify.py
```

This recounts every circuit's CCX/CCZ operations and occupied qubit range,
reconciles its phase ledger, checks all video-point mappings, and tests 256
sampled input/measurement trajectories per circuit. It also verifies the
packaged files against `SHA256SUMS`. Expect a few minutes of runtime.
Use `--shots` and `--seed` to change the sampled tests; `--report /path/report.json`
saves a new report outside the frozen snapshot.

`release_checks.json` records the fresh release run. The earlier circuit-export
checks remain in `circuits/checks.json` and `circuits/conversion_checks.json`.
Sampled checks are not an exhaustive semantic certificate. The occupied-wire
range agrees with the recorded peak-live space, but the exported gate streams
do not independently reconstruct allocation/free events or prove minimal space.

## Render the video

See [video/README.md](video/README.md) for the complete commands. The renderer
uses the local files only. Python 3.11 with the pinned plotting dependencies
reproduces the final figure and GIF. MP4 additionally needs Swift/AVFoundation
on macOS or FFmpeg with `libx264` on other platforms.

## What is measured

One pinned 41,052-term **alias–SELECT–unlookup** query, with 16 address bits,
16 coin bits and 40 system qubits. The count is CCX + CCZ Toffoli equivalents;
measurement-conditioned Clifford corrections are included in the gate programs.
Space includes the system qubits. Their product is a resource metric, not
circuit depth, physical runtime or an integrated spacetime volume.

Uniform preparation, reflection, QPE and an additional external control are
excluded. Both experimental methods receive applicable shared alias, decoder,
comparator, workspace and cleanup improvements. The gain over the released
reference includes those improvements as well as the choice of SELECT architecture.

The yellow rectangle represents 5,650 × 210 = **1,186,500**; the released
salmon rectangle represents 14,978 × 126 = **1,887,228**. These are benchmark
results, not a global optimality claim. The package reproduces this frozen
circuit and video snapshot; it does not rerun the optimization search or
derive the molecular integrals from first principles.

## Acknowledgments and comparison

Both optimized implementations use the same Fe₂S₂ Hamiltonian and benchmark,
and both receive the applicable decoder, alias-sampling, lookup, comparator,
workspace and cleanup optimizations, retuned for their respective interfaces
and space budgets. The PAU points implement Summer–Jamet PAU; the optimized
Frame SELECT points implement the architecture of Gu et al. Their resource
difference therefore compares these two SELECT architectures together with
their associated data-loading and cleanup requirements. Shared implementation
machinery is credited equally for both wherever it is used.

We acknowledge Summer and Jamet for the PAU framework; Gu, Kemeny, Yelin and
Lukin for Frame SELECT, the released benchmark, and the reused preprocessing
and implementation machinery; and Li and Chan for the Hamiltonian integral
data. The shared alias-sampling, lookup and measurement-based cleanup methods
retain the references listed in [NOTICE.md](circuits/NOTICE.md). The Fe₂S₂ PAU
implementations are subsequent applications of the PAU framework.

The released Frame SELECT reference and paper-method points retain their
original optimization scope. Comparisons against them also include the
additional implementation improvements applied to the experimental series.

Code is covered by the repository's Apache-2.0 license;
Rubik retains its bundled SIL Open Font License. The third-party logos retain
their owners' rights and identify the compared methods.
