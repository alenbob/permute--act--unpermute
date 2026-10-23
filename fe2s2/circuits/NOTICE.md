# References and code/data attribution

The PAU circuits apply the permute–act–unpermute framework of
[Summer and Jamet, arXiv:2610.03686](https://arxiv.org/abs/2610.03686).
The Fe₂S₂ integral data originate with [Li and Chan](https://github.com/zhendongli2008/Active-space-model-for-Iron-Sulfur-Clusters).

## Reused implementation material

Frame SELECT and the shared benchmark implementation are from Andi Gu,
Alek H. Kemeny, Susanne F. Yelin and Mikhail D. Lukin,
[*Discovering state-of-the-art quantum circuits with large language models*,
arXiv:2610.22367](https://arxiv.org/abs/2610.22367), and
[andigu/uncompute](https://github.com/andigu/uncompute/tree/64b5a13aa249f1360846657392e6c66817b26d0f),
pinned at commit `64b5a13aa249f1360846657392e6c66817b26d0f`.
The paper's authors are affiliated with Harvard, Anthropic and QuEra;
the comparison-figure logos are not a complete list of author affiliations.
Reuse includes term ordering, frame partitions and representatives, sign/gauge
and permutation data, the alias table, and lookup-walk/comparator/repair
machinery, used by both implementations where applicable. The upstream code
is licensed under Apache 2.0; its license is retained unchanged in
[LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt).

The gate programs are modified, normalized text exports. The released Frame
SELECT program preserves the reference construction; the paper-method programs
retune its permitted parameters. The optimized Frame SELECT and PAU programs
include subsequent implementation changes. The portable reader, counter and
smoke runner were written for this export.

The release also includes modular scientific emitters, standalone point
configurations, format adapters and additional verification code. The vendored
builder, simulator, chemistry grader, tables and released reference under
`upstream/` retain their upstream source and license. Adapted benchmark
machinery in `shared/` is credited in its README. The generators reproduce
the frozen programs; the new interfaces do not change their resource counts.

## Shared method references

- [Babbush et al., arXiv:1805.03662](https://arxiv.org/abs/1805.03662): coherent alias sampling.
- [Berry et al., arXiv:1902.02134](https://arxiv.org/abs/1902.02134): quantum data lookup and its space–time tradeoffs.
- [Gidney, arXiv:1709.06648](https://arxiv.org/abs/1709.06648): temporary logical ANDs and measurement-based cleanup.
- [Babbush et al., arXiv:2603.28846](https://arxiv.org/abs/2603.28846): the kickmix circuit model used by the benchmark.

[BibTeX entries](../references.bib) are provided for these sources. Logos remain
the property of their owners; their inclusion does not imply endorsement.
