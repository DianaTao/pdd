"""Tests for refund_payment (local import + conftest fixture)."""

from refund_demo.refund_payment import refund_payment


def test_refund_payment_uses_helper() -> None:
    assert refund_payment(5) == 6


def test_refund_payment_respects_fee(fee: int) -> None:
    assert refund_payment(3) == 3 + fee
