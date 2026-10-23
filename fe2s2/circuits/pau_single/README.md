# Single-family PAU

In time order: permutation Pi, local Pauli action, inverse Pi. The route composes mode-permutation generators and pair routers, gathering active modes on four target sites.

Fermionic transpositions include Jordan–Wigner phases and use one temporary
AND opening. The current composed schedule has 123 forward transpositions.
Scalar sign terms are folded into label lookup; the phase-factored system
core used by the example below costs 257 Toffoli equivalents. The full query
also pays for alias, decoding and cleanup. Earlier point configurations retain
their own core choices and are reproduced without changing their gate streams.

The full-query interface is 16 index bits, 16 coin bits and 40 system qubits.
Index and coin are restored; all workspace is cleaned. Abstract all-to-all
logical connectivity is assumed. No hardware-distance or error-correction
charge is included.

From the parent `circuits/` directory:

```sh
python generate.py pau_single_q210_t5650
python verification/check_native.py pau_single_q210_t5650
```

The matching JSON in `../configurations/` contains the exact choices. The
generated `<id>.json` gives the per-stage Toffoli counts and live peaks. Add
counts across stages; take the maximum of peaks, never their sum. The total
includes alias sampling and decoder costs, not only the system core.

See [verification](../verification/) for coverage and [attribution](../NOTICE.md)
for the PAU, Frame SELECT, benchmark-data and shared-method sources.
