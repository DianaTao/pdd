"""Minimal dev-unit code used by the checkup gate demo."""


def refund(amount: float) -> float:
    """Return the refund amount unchanged (demo stub)."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    return amount
