# Pinned upstream subset

Files here are copied from andigu/uncompute at commit
`64b5a13aa249f1360846657392e6c66817b26d0f`, under its Apache-2.0 license.
The subset includes the builder, normative binary parser, simulator, evaluator,
Fe2S2 contract, table derivation, grader, data and original Frame implementation.
It is not a fork of the full benchmark suite.

Use `tools/eval.py chemistry-fe2s2 --ops ../output/<id>.ops.xz` from this
directory to evaluate a generated stream. The grader and its schedule remain
unchanged. `reference.py --skip-derive` checks upstream table construction;
full FCIDUMP derivation additionally needs the versions listed in its header.
The independent public checks in `../verification/` do not need those chemistry
packages. An optional C kernel is built with `make kernel PYTHON=/path/to/python`.
