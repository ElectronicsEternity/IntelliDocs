from dataclasses import dataclass
import logging

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None = None


class SupabaseTokenVerifier:
    """Verify Supabase access tokens and return their trusted claims."""

    def __init__(self) -> None:
        self._jwks_client: PyJWKClient | None = None

    def verify(self, token: str) -> dict:
        if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
            raise RuntimeError("Supabase authentication is not configured.")

        algorithm = jwt.get_unverified_header(token).get("alg", "")
        if algorithm.startswith(("RS", "ES", "Ed")):
            try:
                if self._jwks_client is None:
                    jwks_url = (
                        f"{settings.SUPABASE_URL.rstrip('/')}"
                        "/auth/v1/.well-known/jwks.json"
                    )
                    self._jwks_client = PyJWKClient(jwks_url, cache_keys=True)
                signing_key = self._jwks_client.get_signing_key_from_jwt(token).key
                return jwt.decode(
                    token,
                    signing_key,
                    algorithms=[algorithm],
                    audience="authenticated",
                    issuer=f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
                )
            except (jwt.PyJWTError, PyJWKClientError) as exc:
                logger.info(
                    "Local Supabase JWT verification failed (%s); using Auth server fallback.",
                    type(exc).__name__,
                )
                return self._verify_with_auth_server(token)

        # Legacy HS256 projects do not expose their secret in JWKS. Ask the
        # Supabase Auth server to validate the token instead.
        return self._verify_with_auth_server(token)

    @staticmethod
    def _verify_with_auth_server(token: str) -> dict:
        response = httpx.get(
            f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user",
            headers={
                "apikey": settings.SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {token}",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        user = response.json()
        return {"sub": user.get("id"), "email": user.get("email")}


bearer_scheme = HTTPBearer(auto_error=False)
token_verifier = SupabaseTokenVerifier()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid Supabase access token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        claims = token_verifier.verify(credentials.credentials)
        user_id = claims.get("sub")
        if not user_id:
            raise ValueError("Token has no subject.")
        return AuthenticatedUser(id=str(user_id), email=claims.get("email"))
    except (ValueError, RuntimeError, jwt.PyJWTError, PyJWKClientError, httpx.HTTPError) as exc:
        logger.warning("Supabase access token rejected (%s).", type(exc).__name__)
        raise unauthorized from None
