# Permute–act–unpermute

Implementations and reproducibility material for the permute–act–unpermute
(PAU) framework of [Summer and Jamet, arXiv:2610.03686](https://arxiv.org/abs/2610.03686).
PAU separates the routing of a Hamiltonian term's support from its local action.

## Benchmarks

The [Fe₂S₂ benchmark](fe2s2/) applies PAU to a molecular Hamiltonian and
explores Toffoli–qubit tradeoffs with single- and multiple-family constructions.

- [Fe₂S₂ circuits and resource checks](fe2s2/circuits/)
- [Fe₂S₂ resource-plot video](fe2s2/video/)
- [Run the Fe₂S₂ reproduction](fe2s2/)

Each benchmark documents its problem instance, comparison methods, resource
conventions and verification scope. References and code/data credits accompany
the corresponding implementation.
