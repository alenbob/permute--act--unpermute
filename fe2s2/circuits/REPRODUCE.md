# Reproduce a point

Use Python 3.11 in a virtual environment. The basic frozen-stream checker
needs no packages. Rebuilding needs NumPy; the upstream CLI also needs Click.
The optional interface checks have their own dependency list.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-build.txt
python generate.py pau_single_q210_t5650
python verification/check_native.py pau_single_q210_t5650
```

Run these commands from `fe2s2/circuits`. Substitute any of the 31 IDs in
`configurations/`. `generate.py` writes into ignored `output/`:

- `<id>.gates.xz`: readable program, checked byte for byte after decompression
  against the original program's SHA-256.
- `<id>.ops.xz`: upstream `OPSTRM01` binary stream.
- `<id>.liveness.json.xz`: allocation/free events and replayed peak.
- `<id>.json`: phase costs, source hashes and configuration hash.

The generator reconstructs the circuit from the table and configuration; it
does not read the frozen gate program. The expected hash is an assertion, not
an input to synthesis. Changing a configuration requires a new circuit ID,
new expected values and validation before it becomes a published point.

## Native evaluator

The included upstream source is pinned to commit
`64b5a13aa249f1360846657392e6c66817b26d0f`. Run its unchanged grader on a
regenerated stream:

```sh
python upstream/tools/eval.py chemistry-fe2s2 \
  --ops output/pau_single_q210_t5650.ops.xz --jobs 2 --out output/full-grader
```

This runs the full upstream schedule (about 18.4 million probes) and can take
substantial time. The Python interpreter is sufficient. An optional C compiler
can accelerate it: from `upstream/`, run `make kernel PYTHON=/path/to/python`.
The checked-in release reports distinguish fresh sampled tests from historical
full-suite results.

## Interfaces

```sh
python -m pip install -r requirements-interfaces.txt
python interfaces/openqasm.py pau_single_q210_t5650
python verification/check_qasm.py pau_single_q210_t5650
python verification/check_cores.py
```

The OpenQASM file is compressed text. Decompress with `xz -dc` or Python's
`lzma` module. It contains standard gates, X-basis demolition expressed as
H/measure/reset, classical XOR and conditional phase corrections.

The published video and point data remain in `../video/`; all gate/resource
values are unchanged. This package reproduces and checks the circuits behind
the video. It does not include the animation renderer.
