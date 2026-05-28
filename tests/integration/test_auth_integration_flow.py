import os
import json
import time
from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from pdd.auth_service import verify_auth, JWT_CACHE_FILE

@pytest.mark.asyncio
async def test_verify_auth_integration_with_cached_token(tmp_path):
    """
    Test verify_auth when a valid token is cached.
    """
    # Set up a fake JWT cache file
    fake_token = "header.payload.signature"
    # Create a fake payload with an expiration time in the future
    # payload is usually base64 encoded JSON
    import base64
    payload = {
        "email": "test@example.com",
        "exp": time.time() + 3600
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    fake_token = f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{payload_b64}.signature"
    
    # We need to mock JWT_CACHE_FILE path in auth_service
    with patch("pdd.auth_service.JWT_CACHE_FILE", tmp_path / "jwt_cache"):
        # Write fake token to cache
        cache_data = {
            "id_token": fake_token,
            "expires_at": time.time() + 3600
        }
        with open(tmp_path / "jwt_cache", "w") as f:
            json.dump(cache_data, f)
            
        result = await verify_auth()
        
        assert result["valid"] is True
        assert result["username"] == "test@example.com"
        assert result["needs_reauth"] is False

@pytest.mark.asyncio
async def test_verify_auth_integration_refresh_flow(tmp_path):
    """
    Test verify_auth when JWT is expired but refresh token exists.
    """
    with patch("pdd.auth_service.JWT_CACHE_FILE", tmp_path / "jwt_cache"):
        # 1. Mock expired JWT or no JWT
        # (already handled if file doesn't exist)
        
        # 2. Mock refresh token exists
        with patch("pdd.auth_service.get_refresh_token", return_value="fake_refresh_token"):
            
            # 3. Mock FirebaseAuthenticator._refresh_firebase_token
            new_id_token = "new.id.token"
            mock_auth = AsyncMock()
            mock_auth._refresh_firebase_token.return_value = new_id_token
            
            with patch("pdd.get_jwt_token.FirebaseAuthenticator", return_value=mock_auth):
                with patch("os.environ.get", return_value="fake_api_key"):
                    # Mock _cache_jwt to actually write to our tmp_path
                    def mock_cache(token):
                        with open(tmp_path / "jwt_cache", "w") as f:
                            json.dump({"id_token": token, "expires_at": time.time() + 3600}, f)
                    
                    with patch("pdd.get_jwt_token._cache_jwt", side_effect=mock_cache):
                        result = await verify_auth()
                        
                        assert result["valid"] is True
                        assert result["needs_reauth"] is False
                        mock_auth._refresh_firebase_token.assert_called_once_with("fake_refresh_token")
                        assert (tmp_path / "jwt_cache").exists()

@pytest.mark.asyncio
async def test_verify_auth_integration_no_credentials():
    """
    Test verify_auth when no credentials exist.
    """
    with patch("pdd.auth_service.JWT_CACHE_FILE", Path("/non/existent/path")):
        with patch("pdd.auth_service.get_refresh_token", return_value=None):
            result = await verify_auth()
            
            assert result["valid"] is False
            assert result["needs_reauth"] is True
            assert "No authentication credentials found" in result["error"]

from pathlib import Path
