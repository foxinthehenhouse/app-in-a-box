"""Supabase JWT authentication.

Verifies the access token locally against the project's JWKS (asymmetric keys,
the Supabase default for new projects). If the project still signs with a legacy
HS256 secret or the JWKS is unreachable, it falls back to asking Supabase Auth
`/auth/v1/user`. Returns the caller as `CurrentUser`. Handlers MUST scope every
query by `user.id`. The backend uses the service key, which bypasses RLS, so the
filter in your query is the only thing standing between users' data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend import http as outbound
from backend.config import supabase_auth_apikey, supabase_url

logger = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url()}/auth/v1/.well-known/jwks.json", cache_keys=True)


def _verify_locally(token: str) -> CurrentUser | None:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        return None
    alg = header.get("alg")
    if alg not in ("ES256", "RS256") or not header.get("kid"):
        return None
    try:
        key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=[alg],
            audience="authenticated",
            issuer=f"{supabase_url()}/auth/v1",
            leeway=30,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.PyJWKClientConnectionError:
        return None  # JWKS unreachable: fall back to the Auth API
    except jwt.PyJWKClientError as exc:
        # JWKS answered but has no key for this `kid` (PyJWKClient already refetched once,
        # so a rotation is covered). Reject here: falling back to the Auth API would let
        # anyone turn random `kid`s into one outbound request each, before rate limits.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc
    if claims.get("role") != "authenticated":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return CurrentUser(id=str(claims["sub"]), email=claims.get("email"))


def _verify_remotely(token: str) -> CurrentUser:
    apikey = supabase_auth_apikey()
    if not apikey:
        # Nothing to call the Auth API with. 503, not 401: a 401 tells the client its
        # session is over and it signs the user out; this is our configuration, not
        # a verdict on the token. An empty apikey could only ever come back 401.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth not configured")
    try:
        resp = outbound.get(
            "supabase-auth",
            f"{supabase_url()}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": apikey},
            timeout=10,
        )
    except outbound.HTTPError as exc:  # unreachable, or the circuit is open
        logger.warning("Supabase auth unreachable: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth unavailable") from exc
    if resp.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    data = resp.json()
    return CurrentUser(id=str(data["id"]), email=data.get("email"))


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if not supabase_url():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Auth not configured")
    token = creds.credentials
    return _verify_locally(token) or _verify_remotely(token)
