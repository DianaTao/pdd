import pytest
from pdd.server.models import ServerConfig

def test_server_config_defaults_regression():
    """Verify ServerConfig can be instantiated with defaults (fixing mypy issues)."""
    config = ServerConfig()
    assert config.host == "127.0.0.1"
    assert config.port == 9876
