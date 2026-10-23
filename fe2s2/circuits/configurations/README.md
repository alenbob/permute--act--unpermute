# Point configurations

Each JSON file is a self-contained recipe for one frozen circuit ID.

- `engine`: paper-only Frame builder or the shared composition builder.
- `alias`: ANF bank widths, compressed-correction choices, optional word
  segmentation and address/hold plans.
- `selector`: scientific emitter and decoded-payload/core parameters. `family`
  uses the phase-factored PAU family interface; `legacy` uses the banked or
  released representative interface retained by that point.
- `lookup_holds`: phase-specific scratch budgets; absent entries use the
  corresponding alias or selector plan.
- `retained_borrows`: upper comparator borrows kept live across SELECT.
- `select_repair`, `alias_repair`: low-bit planes, unary window and repair hold.
  `null` selects the original repair implementation for that component.
- `cost_tree`: use the frozen, classically checked correction truth-table tree.
- `expected`: frozen gate-sequence hash, native Toffoli count, peak total space
  and operation count. These are checked outputs, not synthesis inputs.

`generate.py` is the supported entry point. It builds from these fields and
pinned input data without loading the frozen gate program or a previous
optimization-search catalog. The configurations document chosen finite-search
points; they do not claim global optimality. The frozen correction-tree input
is in `shared/data/` and its entries are checked before emission.
