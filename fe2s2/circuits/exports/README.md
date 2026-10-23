# Generated exports

To avoid storing several large copies of each circuit, exports are generated
in ignored `../output/`. The original readable streams remain checked in under
`../circuits/`.

From `circuits/`:

```sh
python generate.py pau_single_q210_t5650
python interfaces/openqasm.py pau_single_q210_t5650
```

The first command emits both readable and native binary streams plus allocation
events. The second emits standard OpenQASM 3. Use the same commands with any
ID under `configurations/`. Generation uses only the included Python code, pinned data and declared
dependencies.
