# Fe₂S₂ benchmark

This benchmark applies [Summer–Jamet PAU](https://arxiv.org/abs/2610.03686)
to the Li–Chan Fe₂S₂ Hamiltonian on 40 system qubits. PAU routes a selected
term's active modes to a four-mode target, applies its local Pauli action,
and reverses the routing. Single- and two-family implementations explore
the tradeoff between Toffoli count and peak logical qubits.

The [circuits](circuits/) folder contains 31 decomposed gate programs,
pinned reference data, a resource counter and a sampled simulator.
Frame SELECT, studied on the same instance by
[Gu et al.](https://arxiv.org/abs/2610.22367), supplies the comparison method.
This is a subsequent application of the PAU framework.

## Run the checks

With Python 3.10+ and no third-party dependencies, from this directory:

```sh
python verify.py
```

This verifies the packaged checksums, recounts every circuit, reconciles its
phase ledger, checks the point data and report hashes, and tests 256 sampled
input/measurement trajectories per circuit. Expect a few minutes of runtime.
Use `--shots` and `--seed` to change sampling; `--report /path/report.json`
saves a new report. See [circuit verification](circuits/README.md#verification)
for the recorded full-suite results and the limits of these checks.

## Resource boundary

Each program implements one pinned 41,052-term **alias–SELECT–unlookup** query:
16 address bits, 16 coin bits and 40 system qubits, plus live workspace.
Resources are **CCX + CCZ Toffoli equivalents** and peak total logical qubits.
Their product is a resource metric, not depth or physical runtime.
Uniform preparation, reflection, QPE and an additional external control are
excluded.

The best-product single-family PAU in this snapshot uses **5,650 Toffolis ×
210 qubits = 1,186,500**. The released Frame SELECT reference uses
14,978 × 126 = 1,887,228. These are tested implementations, not a proof of
global optimality. This release contains frozen gate programs; it does not
rerun the optimization search or derive the molecular integrals.

## Acknowledgments and comparison

We thank Li and Chan for the Hamiltonian integral data and Gu et al. for
Frame SELECT and the reused benchmark code and tables. Both optimized methods
receive applicable decoder, alias, lookup, comparator, workspace and cleanup
optimizations, retuned for their interfaces and space budgets. The comparison
covers each SELECT architecture **with its data loading and cleanup**. Shared
machinery is credited equally wherever used. The released reference and
paper-method points retain their narrower optimization scope.

[NOTICE.md](circuits/NOTICE.md) records specific reuse, method references and
licenses. [references.bib](references.bib) provides the citations in BibTeX.
Code is covered by the repository's Apache-2.0 license.
