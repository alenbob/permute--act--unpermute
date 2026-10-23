"""One-Toffoli action reduction on the even-flip Fe2S2 label domain.

Every Hamiltonian term has even X/Y parity, which fermionic routing preserves.
For f0^f1^f2^f3=0, C sum(fj*xj) = C sum_{j<3} fj*(xj^x3).
Three CCZ gates therefore replace four. Routing, decoding and signs are intact.
The restriction is part of the contract: arbitrary odd-parity labels differ.
"""
from contextlib import contextmanager
from pau_composed import local_select as original

def local_select(b, flags, label, x):

    class ActionBuilder:
        seen = 0

        def __getattr__(self, name):
            return getattr(b, name)

        def ccz(self, a, c, target):
            assert a == flags[1] and c == label[21 + self.seen] and (target == x[self.seen])
            self.seen += 1
            if self.seen == 4:
                for j in range(3):
                    b.cx(x[3], x[j])
                    b.ccz(flags[1], label[21 + j], x[j])
                    b.cx(x[3], x[j])
    proxy = ActionBuilder()
    original(proxy, flags, label, x)
    assert proxy.seen == 4

@contextmanager
def use_core():
    """Local experiment hook; restore the existing emitter even after failure."""
    import composed_query
    old = composed_query.local_select
    composed_query.local_select = local_select
    try:
        yield
    finally:
        composed_query.local_select = old
