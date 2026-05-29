"""
Main entry point for the PDD CLI.
"""

from __future__ import annotations

from typing import Any, Dict

from .core.cli import cli
from .commands import register_commands

# Re-export commonly used items for backward compatibility


# Internal defaults for package initialization
_DEFAULTS: Dict[str, Any] = {
    "PDD_STRENGTH_DEFAULT": 1.0,
    "PDD_TEMPERATURE_DEFAULT": 0.0,
    "PDD_TIME_DEFAULT": 0.25,
}


def _bootstrap_package_defaults() -> None:
    """Bootstrap package defaults before any other imports."""
    try:
        import pdd as pkg
    except ImportError:
        pkg = None  # type: ignore

    if pkg is None:
        return
    for key, value in _DEFAULTS.items():
        if not hasattr(pkg, key):
            setattr(pkg, key, value)


# Bootstrap and register commands
_bootstrap_package_defaults()
register_commands(cli)

if __name__ == "__main__":
    cli()
