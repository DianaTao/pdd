from pdd.core.cloud import CLOUD_ENDPOINTS

def test_cloud_endpoints_submit_command_regression():
    """Verify submitCommand is present in CLOUD_ENDPOINTS."""
    assert "submitCommand" in CLOUD_ENDPOINTS
    assert CLOUD_ENDPOINTS["submitCommand"] == "/submitCommand"
