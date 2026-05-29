"""Shared pytest fixtures (copied into drift pytest overlay)."""

import pytest


@pytest.fixture
def fee() -> int:
    return 1
