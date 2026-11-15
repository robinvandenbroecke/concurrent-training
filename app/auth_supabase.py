"""Verify the caller's own Supabase session token.

The web/Android client sends the access token it already holds
(``Authorization: Bearer``). No admin key, service-role key or provider secret
ever reaches the browser. Asymmetric project signing keys are verified against
the project's public JWKS; the legacy shared HS256 secret is supported only
when ``SUPABASE_JWT_SECRET`` is configured on the server.
Reference: https://supabase.com/docs/guides/auth/jwts
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Callable, Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from app.config import settings

ASYMMETRIC = ["ES256", "RS256", "EdDSA"]
bearer = HTTPBearer(auto_error=False)


class JWKSCache:
    """Small thread-safe JWKS cache with a bounded refetch rate."""

    def __init__(self, url: str, fetch: Optional[Callable[[str], dict]] = None, ttl: float = 600.0, min_refetch: float = 30.0):
        self.url, self.ttl, self.min_refetch = url, ttl, min_refetch
        self._fetch = fetch or (lambda u: httpx.get(u, timeout=5.0).raise_for_status().json())
        self._keys: dict = {}
        self._loaded = 0.0
        self._lock = threading.Lock()

    def key(self, kid: str):
        with self._lock:
            now = time.monotonic()
            stale = now - self._loaded > self.ttl
            if (stale or kid not in self._keys) and now - self._loaded > (0 if not self._keys else self.min_refetch):
                document = self._fetch(self.url)
                self._keys = {k["kid"]: jwt.PyJWK(k) for k in document.get("keys", []) if k.get("kid")}
                self._loaded = now
            return self._keys.get(kid)


_cache: Optional[JWKSCache] = None


def _jwks() -> JWKSCache:
    global _cache
    if _cache is None:
        _cache = JWKSCache(f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")
    return _cache


def verify_token(token: str, *, jwks: Optional[JWKSCache] = None) -> str:
    """Return the authenticated user's UUID or raise ``jwt.InvalidTokenError``."""
    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    options = {"require": ["exp", "sub", "iss", "aud"]}
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg")
    if algorithm in ASYMMETRIC:
        key = (jwks or _jwks()).key(header.get("kid", ""))
        if key is None:
            raise jwt.InvalidTokenError("Unknown signing key")
        claims = jwt.decode(token, key.key, algorithms=[algorithm], audience=settings.supabase_jwt_audience,
                            issuer=issuer, options=options, leeway=10)
    elif algorithm == "HS256" and settings.supabase_jwt_secret:
        claims = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"],
                            audience=settings.supabase_jwt_audience, issuer=issuer, options=options, leeway=10)
    else:
        raise jwt.InvalidTokenError("Unsupported token algorithm")
    if claims.get("role") != "authenticated" or claims.get("is_anonymous"):
        raise jwt.InvalidTokenError("Not an authenticated user session")
    return str(uuid.UUID(claims["sub"]))


async def current_user(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> str:
    if not settings.supabase_url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Account verification is not configured on this server")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    try:
        return await run_in_threadpool(verify_token, credentials.credentials)
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session", headers={"WWW-Authenticate": "Bearer"}) from None
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Signing keys are temporarily unavailable") from None


class RateLimiter:
    """Per-user sliding window; protects the single free instance, not a security boundary."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit, self.window = limit, window_seconds
        self._hits: dict = {}
        self._lock = threading.Lock()

    def check(self, user: str, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = [t for t in self._hits.get(user, []) if now - t < self.window]
            if len(hits) >= self.limit:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests; try again shortly")
            hits.append(now)
            self._hits[user] = hits
            if len(self._hits) > 5000:
                self._hits = {u: h for u, h in self._hits.items() if h and now - h[-1] < self.window}
