# Permute–act–unpermute

Code and reproducibility material for the permute–act–unpermute (PAU) framework:

**[Efficient Block Encoding of Structured Hamiltonians by Separating Where and What](https://arxiv.org/abs/2610.03686)**

Alessandro Summer and François Jamet

[Read on arXiv](https://arxiv.org/abs/2610.03686) · [Paper PDF](https://arxiv.org/pdf/2610.03686)

PAU separates **where** a Hamiltonian term acts from **what** it applies:
route the selected sites to a fixed target register, apply the local operator,
then undo the routing. Operators with the same support geometry share the
permutation network.

[![Figure 1: selected sites are routed to a fixed target, acted on locally, and returned.](assets/figure1.png)](https://arxiv.org/abs/2610.03686)

*Figure 1. Permute–act–unpermute block encoding. The support address controls
the permutation; the operator label controls the local action. Preparation
supplies their joint amplitudes.*

## Benchmarks

The [Fe₂S₂ benchmark](fe2s2/) applies PAU to a molecular Hamiltonian and
explores Toffoli–qubit tradeoffs with single- and multiple-family constructions.

- [Fe₂S₂ circuits and resource checks](fe2s2/circuits/)
- [Fe₂S₂ resource-plot video](fe2s2/video/)
- [Run the Fe₂S₂ reproduction](fe2s2/)

Each benchmark documents its problem instance, comparison methods, resource
conventions and verification scope. References and code/data credits accompany
the corresponding implementation.

## Citation

```bibtex
@misc{summer2026pau,
  title         = {Efficient Block Encoding of Structured Hamiltonians by Separating Where and What},
  author        = {Summer, Alessandro and Jamet, Fran{\c{c}}ois},
  year          = {2026},
  eprint        = {2610.03686},
  archivePrefix = {arXiv},
  primaryClass  = {quant-ph},
  url           = {https://arxiv.org/abs/2610.03686}
}
```
