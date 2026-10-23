# Attribution and provenance

The original Fe₂S₂ benchmark implementation, task data and circuit-model
infrastructure are from **Andi Gu, Alek H. Kemeny, Susanne F. Yelin and Mikhail
D. Lukin**, *Discovering state-of-the-art quantum circuits with large language
models*, arXiv:2610.22367, and https://github.com/andigu/uncompute, pinned at
commit `64b5a13aa249f1360846657392e6c66817b26d0f`. That upstream code is released
under Apache License 2.0; its license is reproduced without changes in
`LICENSES/Apache-2.0.txt`.

The gate programs are modified, normalized text exports. The reference frame
program follows the released implementation; the paper-method programs retune
its permitted workspace/window parameters. The optimized Frame SELECT and PAU
programs include subsequent implementation changes. The portable reader,
counter and smoke runner were written for this export. Their verification
scope is documented in the accompanying README files.

**Scientific contributions and reuse**

- Summer and Jamet, https://arxiv.org/abs/2610.03686: the general
  permute–act–unpermute architecture, support routing and local target action.
- Gu et al.: Frame SELECT; the benchmark term ordering, frame partition,
  representatives, sign/gauge data, frame permutations, alias table and reused
  lookup-walk/comparator/repair machinery. These contributions are also used
  in the PAU implementations where applicable.
- Li and Chan: the iron–sulfur active-space integral data, from
  https://github.com/zhendongli2008/Active-space-model-for-Iron-Sulfur-Clusters.
- Babbush et al., https://arxiv.org/abs/1805.03662: coherent alias-sampling
  methods. Berry et al., https://arxiv.org/abs/1902.02134: space–time tradeoffs
  in quantum data lookup. Gidney, https://arxiv.org/abs/1709.06648: temporary
  logical ANDs and measurement-based cleanup.
- The operation semantics follow the benchmark's kickmix model, attributed
  upstream to Babbush et al., https://arxiv.org/abs/2603.28846.

The additional Fe₂S₂ work composes PAU permutations, encodes local actions,
splits support/action families and tunes the shared alias/decoder/comparator/
cleanup toolkit for both architectures. These application results postdate
the original PAU paper. See the [acknowledgments and comparison](../README.md#acknowledgments-and-comparison)
for the shared optimization treatment and the scope of the architectural
comparison.
