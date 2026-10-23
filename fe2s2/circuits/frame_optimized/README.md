# Frame SELECT with shared optimizations

In time order: sigma-adjoint, representative Pauli R, sigma. The representative is encoded as a compressed X/Z mask with the required sign polynomial.

Shares alias banks, lookup ordering, scratch tuning, retained comparator borrows and unary phase repair with PAU. The label payload and its cleanup are specific to Frame SELECT.

The full-query interface is 16 index bits, 16 coin bits and 40 system qubits.
Index and coin are restored; all workspace is cleaned. Abstract all-to-all
logical connectivity is assumed. No hardware-distance or error-correction
charge is included.

From the parent `circuits/` directory:

```sh
python generate.py frame_extended_q338_t4411
python verification/check_native.py frame_extended_q338_t4411
```

The matching JSON in `../configurations/` contains the exact choices. The
generated `<id>.json` gives the per-stage Toffoli counts and live peaks. Add
counts across stages; take the maximum of peaks, never their sum. The total
includes alias sampling and decoder costs, not only the system core.

See [verification](../verification/) for coverage and [attribution](../NOTICE.md)
for the PAU, Frame SELECT, benchmark-data and shared-method sources.
