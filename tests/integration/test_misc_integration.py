import pdd
from pdd.server.app import ServerConfig

def test_init_exports_integration():
    """
    Test that pdd package exports the expected members.
    """
    assert hasattr(pdd, "extract_step_report")
    assert callable(pdd.extract_step_report)

def test_server_config_defaults_integration():
    """
    Test that ServerConfig can be instantiated with defaults, verifying the mypy fix.
    """
    config = ServerConfig()
    assert config.host == "127.0.0.1"
    assert config.port == 9876
    assert config.allow_remote is False
    assert config.log_level == "info"
