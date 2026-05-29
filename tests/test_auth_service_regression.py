import pytest
from pdd.auth_service import verify_auth, get_jwt_cache_info
import inspect

@pytest.mark.asyncio
async def test_verify_auth_interface_regression():
    """Verify verify_auth is async and returns the expected dict structure."""
    assert inspect.iscoroutinefunction(verify_auth)
    
    # We don't need to actually run it with real credentials, 
    # just check that it returns a dict when it fails (no credentials).
    result = await verify_auth()
    assert isinstance(result, dict)
    assert "valid" in result
    assert "error" in result
    assert "needs_reauth" in result

def test_get_jwt_cache_info_interface_regression():
    """Verify get_jwt_cache_info returns a tuple (bool, Optional[float])."""
    result = get_jwt_cache_info()
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert result[1] is None or isinstance(result[1], (int, float))
