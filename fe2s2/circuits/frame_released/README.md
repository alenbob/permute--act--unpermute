# Released Frame SELECT

The unchanged seven-frame representative construction of Gu et al. The parameterized default reproduces its exact gate sequence.

The original repeated-subtree alias lookup, representative walk and joint measurement unlookup are retained.

The full-query interface is 16 index bits, 16 coin bits and 40 system qubits.
Index and coin are restored; all workspace is cleaned. Abstract all-to-all
logical connectivity is assumed. No hardware-distance or error-correction
charge is included.

From the parent `circuits/` directory:

```sh
python generate.py frame_released_q126_t14978
python verification/check_native.py frame_released_q126_t14978
```

The matching JSON in `../configurations/` contains the exact choices. The
generated `<id>.json` gives the per-stage Toffoli counts and live peaks. Add
counts across stages; take the maximum of peaks, never their sum. The total
includes alias sampling and decoder costs, not only the system core.

See [verification](../verification/) for coverage and [attribution](../NOTICE.md)
for the PAU, Frame SELECT, benchmark-data and shared-method sources.
