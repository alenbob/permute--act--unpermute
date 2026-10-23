# Shared scientific emitters

These modules implement the same table-driven circuits used by the frozen
programs. The supported entry point is `../generate.py`; it resolves all
configuration choices explicitly. The optimization-search drivers and historical
experiment catalogs are not part of this release. Legacy low-level helper
entry points are retained for source context; they are not separate public CLIs.

| Stage | Main modules |
|---|---|
| Pinned task and reference frames | `common.py`, upstream `discovered/circuit.py` |
| Alias ANF banks, compressed corrections and segmented words | `composed_query.py`, `pau_recycle.py`, `segmented_alias.py`, `pau_wide.py` |
| Address order, adaptive and sparse walks | `permuted_lookup.py`, `adaptive_lookup.py`, `sparse_payload_lookup.py`, `cost_query.py` |
| Comparator borrows retained across SELECT | `retained_compare.py` |
| Single PAU mode geometry and local action | `pau_permutation_core.py`, `pau_composed.py`, `phase_pau.py`, `routing.py` |
| Two PAUs with shared controls and affine label views | `family_pau.py`, `compact_families.py`, `reuse_family_core.py`, `basis_action_controls.py` |
| Frame representative and conjugation | `frame_mask_space.py`, `multiframe.py` |
| Measurement-phase cleanup | `unary_repair.py`, `refined_repair.py`, `exact_monomials.py` |

Both optimized architectures use the applicable shared alias, lookup,
comparator and cleanup machinery. Greater bank width reduces repeated
lookups but increases live space. Wider unary repair windows reduce phase-walk
costs at a space cost. Retaining comparator borrows saves recomputation while
those wires remain live through SELECT. Point configurations tune these
choices jointly because phase peaks overlap differently.

The release adaptation removes experiment drivers and historical bookkeeping,
resolves prior configurations into standalone JSON, and retains scientific
emission functions. Exact regenerated operation hashes check that these
packaging changes preserve the frozen programs. Original upstream files under
`../upstream/` retain their license and source text. See `../NOTICE.md`.
