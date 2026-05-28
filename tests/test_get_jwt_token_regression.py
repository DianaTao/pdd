import pytest
from pdd import get_jwt_token
from pdd.get_jwt_token import (
    verify_github_oauth,
    create_signed_jwt,
    verify_signed_jwt,
    extract_bearer_token,
    verify_firebase_token,
    AuthError
)

def test_get_jwt_token_exports_regression():
    """Verify that all expected functions are exported in get_jwt_token.py."""
    assert callable(verify_github_oauth)
    assert callable(create_signed_jwt)
    assert callable(verify_signed_jwt)
    assert callable(extract_bearer_token)
    assert callable(verify_firebase_token)

def test_verify_firebase_token_return_type_regression():
    """Verify verify_firebase_token returns a dict as required by architecture.json."""
    # Create a dummy JWT (header.payload.signature)
    # Payload is {"sub": "user123"} -> eyJzdWIiOiAidXNlcjEyMyJ9
    dummy_token = "header.eyJzdWIiOiAidXNlcjEyMyJ9.signature"
    
    result = verify_firebase_token(dummy_token)
    assert isinstance(result, dict)
    assert result["sub"] == "user123"

def test_verify_firebase_token_empty_regression():
    """Verify verify_firebase_token raises AuthError on empty token."""
    with pytest.raises(AuthError, match="No token provided"):
        verify_firebase_token("")
