from types import SimpleNamespace
from unittest.mock import Mock

import jwt

from app.config import settings
from app.core.auth import SupabaseTokenVerifier


def test_asymmetric_token_uses_auth_server_when_local_verification_fails(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setattr(jwt, "get_unverified_header", lambda _token: {"alg": "RS256"})
    monkeypatch.setattr(
        jwt,
        "decode",
        Mock(side_effect=jwt.InvalidTokenError("local verification failed")),
    )

    verifier = SupabaseTokenVerifier()
    verifier._jwks_client = Mock()
    verifier._jwks_client.get_signing_key_from_jwt.return_value = SimpleNamespace(key=object())
    remote_verify = Mock(return_value={"sub": "user-a", "email": "person@example.com"})
    monkeypatch.setattr(verifier, "_verify_with_auth_server", remote_verify)

    assert verifier.verify("access-token")["sub"] == "user-a"
    remote_verify.assert_called_once_with("access-token")
