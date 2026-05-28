"""Deterministic fixture module for contract-aware test generation."""


def calculate_refund(
    charge_amount: int | float,
    requested_refund: int | float,
) -> int | float:
    """Return an approved refund amount or reject contract violations."""
    if requested_refund < 0:
        raise ValueError("requested refund must be non-negative")
    if requested_refund > charge_amount:
        raise ValueError("requested refund cannot exceed charge amount")
    return requested_refund
