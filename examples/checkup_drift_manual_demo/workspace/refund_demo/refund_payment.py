"""Baseline refund_payment module for manual drift verification."""

from refund_demo.helper import adjust


def refund_payment(amount: int) -> int:
    """Return the input amount adjusted by the local helper."""
    return adjust(amount)
