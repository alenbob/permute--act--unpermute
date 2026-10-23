"""Measurement-phase repair with exact monomial-order optimization."""
from pau_banked import repair_plan
from tradeoff import ref
from exact_monomials import emit as monomials
from uncompute.gadgets import xor_outcomes

def repair_records(b, address, outcomes, values, low, log_window, hold):
    """Repair a lookup phase from classical records after its storage is freed.

    The lookup address must have been preserved, or coherently restored, since
    measurement. No intervening operation may mix its computational labels at
    the repair boundary. Classical records do not occupy logical qubits.
    """
    root, policy, payload, masks, _ = repair_plan(tuple(values), low, log_window, hold)
    k = 1 << log_window
    mid = address[low:low + log_window]
    u = b.qubits(k)
    b.x(u[0])
    for j in reversed(range(log_window)):
        for i in range(0, k, 2 << j):
            b.cswap(mid[j], u[i], u[i + (1 << j)])
    cache = {0: None}

    def parity(value):
        if value not in cache:
            cache[value] = xor_outcomes([o for j, o in enumerate(outcomes) if value >> j & 1])
        return cache[value]

    def leaf(lo, ctrl):

        def emit(q, mask):
            for j, v in enumerate(payload[lo]):
                outcome = parity(v[mask])
                if outcome is not None:
                    b.cz(q, u[j], cond=outcome)
        monomials(b, ctrl, address[:low], masks[lo], emit)
    ref()._policy_walk(b, root, policy, hold, lambda n: address[low + log_window + n.span.bit_length() - 2], leaf)
    for j in range(log_window):
        for i in range(0, k, 2 << j):
            v = u[i + (1 << j)]
            b.cx(v, u[i])
            b.and_release(v, mid[j], u[i])
    b.x(u[0])
    b.recycle(u[0])
