# Two-family PAU

Two conditional support/action sandwiches share a prefix and router controls. One covers mixed-spin or smaller supports; the other covers the same-spin cases. Inactive actions are identity, so their routes cancel.

Both sandwiches execute coherently and are fully charged; costs are not probability-weighted. Affine label views, overlaid inactive addresses, shared pair-router products and an independent basis of action products reduce cost. The decoded core costs 274 Toffoli equivalents. These seven comparison programs are included but are not drawn in the current video.

The full-query interface is 16 index bits, 16 coin bits and 40 system qubits.
Index and coin are restored; all workspace is cleaned. Abstract all-to-all
logical connectivity is assumed. No hardware-distance or error-correction
charge is included.

From the parent `circuits/` directory:

```sh
python generate.py pau_two_q215_t5627
python verification/check_native.py pau_two_q215_t5627
```

The matching JSON in `../configurations/` contains the exact choices. The
generated `<id>.json` gives the per-stage Toffoli counts and live peaks. Add
counts across stages; take the maximum of peaks, never their sum. The total
includes alias sampling and decoder costs, not only the system core.

See [verification](../verification/) for coverage and [attribution](../NOTICE.md)
for the PAU, Frame SELECT, benchmark-data and shared-method sources.
