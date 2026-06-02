import os
import json
import time
import base64
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from pdd.core.cloud import CloudConfig
from pdd import get_jwt_token
from pdd import auth_service

def create_mock_jwt(audience, email="test@example.com"):
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().strip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "aud": audience, 
        "email": email,
        "exp": time.time() + 1000
    }).encode()).decode().strip("=")
    return f"{header}.{payload}.signature"

@pytest.fixture
def clean_env():
    """Reset PDD_ENV and related variables."""
    vars_to_clear = ["PDD_ENV", "PDD_JWT_EXPECTED_AUD", "PDD_CLOUD_URL", "STAGING_PROJECT_ID"]
    old_values = {v: os.environ.get(v) for v in vars_to_clear}
    for v in vars_to_clear:
        if v in os.environ:
            del os.environ[v]
    yield
    for v, val in old_values.items():
        if val is not None:
            os.environ[v] = val
        elif v in os.environ:
            del os.environ[v]

@pytest.fixture
def mock_jwt_cache_file(tmp_path):
    cache_file = tmp_path / "jwt_cache"
    # Patch both locations since they might have been imported separately
    with patch("pdd.auth_service.JWT_CACHE_FILE", cache_file), \
         patch("pdd.get_jwt_token.JWT_CACHE_FILE", cache_file):
        yield cache_file

def test_cloud_config_to_auth_integration(clean_env, mock_jwt_cache_file):
    """
    E2E Test: CloudConfig.get_jwt_token should trigger audience validation in auth_service
    and invalidate cache if environment mismatches.
    """
    # 1. Setup: PDD_ENV=prod, but cache has a staging token
    os.environ["PDD_ENV"] = "prod"
    staging_aud = "prompt-driven-development-stg"
    jwt = create_mock_jwt(staging_aud)
    
    cache_data = {
        "id_token": jwt,
        "expires_at": time.time() + 1000
    }
    mock_jwt_cache_file.write_text(json.dumps(cache_data))
    
    # 2. Execution: Call high-level CloudConfig method
    # Use patch to avoid actual network calls if cache fails
    with patch("pdd.core.cloud.device_flow_get_token") as mock_device_flow:
        mock_device_flow.return_value = "new-token"
        
        # We expect it to find mismatch, clear cache, and return None (since we don't mock the whole device flow success here, 
        # but the important part is it doesn't return the cached staging token)
        token = CloudConfig.get_jwt_token(verbose=True)
        
        # 3. Verification
        # It should NOT return the staging token
        assert token != jwt
        # The cache file should have been unlinked/cleared
        assert not mock_jwt_cache_file.exists()

def test_shared_auth_consistency(clean_env, mock_jwt_cache_file):
    """
    Integration Test: Both get_jwt_token and auth_service should agree on token validity.
    """
    os.environ["PDD_ENV"] = "staging"
    staging_aud = "prompt-driven-development-stg"
    jwt = create_mock_jwt(staging_aud)
    
    cache_data = {
        "id_token": jwt,
        "expires_at": time.time() + 1000
    }
    mock_jwt_cache_file.write_text(json.dumps(cache_data))
    
    # Both should see it as valid
    assert get_jwt_token._get_cached_jwt() == jwt
    assert auth_service.get_cached_jwt() == jwt
    
    # Change env to prod
    os.environ["PDD_ENV"] = "prod"
    
    # Both should now see it as invalid
    # Note: _get_cached_jwt in get_jwt_token.py unlinks the file on mismatch
    assert get_jwt_token._get_cached_jwt() is None
    assert not mock_jwt_cache_file.exists()
    assert auth_service.get_cached_jwt() is None

def test_audience_propagation_from_cloud_url(clean_env, mock_jwt_cache_file):
    """
    Integration Test: PDD_CLOUD_URL should propagate through CloudConfig.ensure_default_env
    to the JWT audience check.
    """
    # Set staging cloud URL
    os.environ["PDD_CLOUD_URL"] = "https://us-central1-prompt-driven-development-stg.cloudfunctions.net"
    
    # Staging token in cache
    staging_aud = "prompt-driven-development-stg"
    jwt = create_mock_jwt(staging_aud)
    cache_data = {"id_token": jwt, "expires_at": time.time() + 1000}
    mock_jwt_cache_file.write_text(json.dumps(cache_data))
    
    # CloudConfig.get_jwt_token() calls ensure_default_env() which sets PDD_ENV=staging
    token = CloudConfig.get_jwt_token()
    assert token == jwt
    
    # Now set prod cloud URL
    os.environ["PDD_CLOUD_URL"] = "https://us-central1-prompt-driven-development.cloudfunctions.net"
    # Clear PDD_ENV so ensure_default_env() re-evaluates
    del os.environ["PDD_ENV"]
    
    # This should now invalidate the staging token
    token = CloudConfig.get_jwt_token()
    assert token is None or token != jwt
    assert not mock_jwt_cache_file.exists()

@pytest.mark.asyncio
async def test_server_auth_route_integration(clean_env, mock_jwt_cache_file):
    """
    Integration Test: Server auth status route should use the unified audience check.
    """
    from pdd.server.routes.auth import get_auth_status
    
    # Setup: Prod environment with staging token
    os.environ["PDD_ENV"] = "prod"
    staging_aud = "prompt-driven-development-stg"
    jwt = create_mock_jwt(staging_aud)
    cache_data = {"id_token": jwt, "expires_at": time.time() + 1000}
    mock_jwt_cache_file.write_text(json.dumps(cache_data))
    
    # Call the route handler directly (it's an async function)
    status = await get_auth_status()
    
    # It should report as NOT authenticated because the audience mismatched
    assert status.authenticated is False
    assert status.cached is False
    assert not mock_jwt_cache_file.exists()
