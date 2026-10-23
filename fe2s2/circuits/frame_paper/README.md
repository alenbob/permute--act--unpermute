# Frame SELECT: paper-only tuning

The same released SELECT, with the existing measurement-unlookup window and hold budget retuned.

Only techniques present in the paper and release are used. The forward alias lookup and SELECT are unchanged; the existing window address slice is parameterized.

The full-query interface is 16 index bits, 16 coin bits and 40 system qubits.
Index and coin are restored; all workspace is cleaned. Abstract all-to-all
logical connectivity is assumed. No hardware-distance or error-correction
charge is included.

From the parent `circuits/` directory:

```sh
python generate.py frame_paper_q145_t14479
python verification/check_native.py frame_paper_q145_t14479
```

The matching JSON in `../configurations/` contains the exact choices. The
generated `<id>.json` gives the per-stage Toffoli counts and live peaks. Add
counts across stages; take the maximum of peaks, never their sum. The total
includes alias sampling and decoder costs, not only the system core.

See [verification](../verification/) for coverage and [attribution](../NOTICE.md)
for the PAU, Frame SELECT, benchmark-data and shared-method sources.
