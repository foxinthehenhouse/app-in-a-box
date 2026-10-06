"""Supabase JWT verification (backend/auth.py): the one gate in front of every route.

Real ES256 tokens signed with a throwaway key, verified through the real code path; only
the JWKS fetch and the Auth API call are faked. Each rejection case is a token a
careless verifier would accept.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend import auth

URL = "https://proj.supabase.co"
KEY = ec.generate_private_key(ec.SECP256R1())


class _Jwks:
    def __init__(self, fail: bool = False, unknown_kid: bool = False) -> None:
        self.fail = fail
        self.unknown_kid = unknown_kid

    def get_signing_key_from_jwt(self, _token: str) -> Any:
        if self.fail:
            raise jwt.PyJWKClientConnectionError("unreachable")
        if self.unknown_kid:
            raise jwt.PyJWKClientError('Unable to find a signing key that matches: "zz"')
        return type("K", (), {"key": KEY.public_key()})()


@pytest.fixture(autouse=True)
def _supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setattr(auth, "_jwks_client", lambda: _Jwks())


def _token(alg: str = "ES256", **overrides: Any) -> str:
    claims = {
        "sub": "user-1",
        "email": "a@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "iss": f"{URL}/auth/v1",
        "exp": int(time.time()) + 600,
        **overrides,
    }
    claims = {k: v for k, v in claims.items() if v is not None}
    if alg == "HS256":
        return jwt.encode(claims, "legacy-secret-at-least-32-bytes-long!!", algorithm="HS256")
    return jwt.encode(claims, KEY, algorithm="ES256", headers={"kid": "k1"})


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_valid_token_verifies_locally() -> None:
    user = auth.get_current_user(_creds(_token()))
    assert user == auth.CurrentUser(id="user-1", email="a@example.com")


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "anon"},
        {"iss": "https://evil.example.com/auth/v1"},
        {"exp": int(time.time()) - 3600},
        {"role": "anon"},
        {"sub": None},
    ],
    ids=["wrong-audience", "wrong-issuer", "expired", "anon-role", "no-subject"],
)
def test_bad_claims_are_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_creds(_token(**overrides)))
    assert exc.value.status_code == 401


def test_token_signed_by_another_key_is_rejected() -> None:
    other = ec.generate_private_key(ec.SECP256R1())
    forged = jwt.encode(
        {"sub": "x", "role": "authenticated", "aud": "authenticated", "iss": f"{URL}/auth/v1",
         "exp": int(time.time()) + 600},
        other, algorithm="ES256", headers={"kid": "k1"},
    )  # fmt: skip
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_creds(forged))
    assert exc.value.status_code == 401


def _fake_get(status: int, body: dict[str, Any] | None = None, error: bool = False):
    def get(*_a: Any, **_k: Any) -> Any:
        if error:
            raise httpx.ConnectError("down")
        return type("R", (), {"status_code": status, "json": lambda self: body or {}})()

    return get


def test_legacy_hs256_falls_back_to_the_auth_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.outbound, "get", _fake_get(200, {"id": "user-2", "email": None}))
    assert auth.get_current_user(_creds(_token("HS256"))).id == "user-2"


def test_jwks_unreachable_falls_back_to_the_auth_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "_jwks_client", lambda: _Jwks(fail=True))
    monkeypatch.setattr(auth.outbound, "get", _fake_get(200, {"id": "user-3"}))
    assert auth.get_current_user(_creds(_token())).id == "user-3"


def test_unknown_kid_is_401_without_calling_the_auth_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "_jwks_client", lambda: _Jwks(unknown_kid=True))

    def must_not_call(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("an unknown kid must not trigger a remote Auth API call")

    monkeypatch.setattr(auth.outbound, "get", must_not_call)
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_creds(_token()))
    assert exc.value.status_code == 401


def test_auth_api_rejection_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.outbound, "get", _fake_get(401))
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_creds(_token("HS256")))
    assert exc.value.status_code == 401


def test_auth_api_down_is_503_not_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.outbound, "get", _fake_get(0, error=True))
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_creds(_token("HS256")))
    assert exc.value.status_code == 503


@pytest.mark.parametrize(
    "var", ["SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"]
)
def test_remote_verify_sends_a_real_apikey_under_each_key_config(
    monkeypatch: pytest.MonkeyPatch, var: str
) -> None:
    """Whichever project key the deploy has, /auth/v1/user gets a non-empty `apikey`.

    FEATURE_CONFIG accepts SUPABASE_SECRET_KEY alone, and the rotation runbook recommends
    it, but the fallback path used to read only ANON/SERVICE_ROLE: with SECRET_KEY alone it
    sent `apikey: ""`, Supabase answered 401, and every JWKS blip signed every user out.
    """
    monkeypatch.delenv("SUPABASE_ANON_KEY")
    monkeypatch.setenv(var, f"key-from-{var}")
    monkeypatch.setattr(auth, "_jwks_client", lambda: _Jwks(fail=True))
    seen: list[dict[str, str]] = []

    def get(*_a: Any, **kw: Any) -> Any:
        seen.append(kw["headers"])
        return type("R", (), {"status_code": 200, "json": lambda self: {"id": "user-9"}})()

    monkeypatch.setattr(auth.outbound, "get", get)
    assert auth.get_current_user(_creds(_token())).id == "user-9"
    assert seen[0]["apikey"] == f"key-from-{var}"


def test_jwks_blip_with_no_project_key_is_503_not_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid-looking token + JWKS down + nothing to call the Auth API with.

    503, not 401, on purpose: the client treats 401 as "this session is over" and signs
    the user out (and forgets the push token). Here the token may well be fine; what is
    missing is OUR configuration, and that is a server fault the client should retry,
    not a verdict on the session. 401 is reserved for a token Supabase has actually
    refused. No request is made with an empty apikey: it could only come back 401.
    """
    monkeypatch.delenv("SUPABASE_ANON_KEY")
    monkeypatch.setattr(auth, "_jwks_client", lambda: _Jwks(fail=True))

    def must_not_call(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("must not call the Auth API with an empty apikey")

    monkeypatch.setattr(auth.outbound, "get", must_not_call)
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_creds(_token()))
    assert exc.value.status_code == 503


def test_garbage_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.outbound, "get", _fake_get(401))
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_creds("not-a-jwt"))
    assert exc.value.status_code == 401


def test_missing_credentials_is_401() -> None:
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(None)
    assert exc.value.status_code == 401


def test_auth_not_configured_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_URL")
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_creds(_token()))
    assert exc.value.status_code == 503
