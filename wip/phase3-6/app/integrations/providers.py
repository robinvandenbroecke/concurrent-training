"""Official Garmin and Wahoo cloud links for a signed-in user.

Only documented, permitted routes are used:

* Wahoo Cloud API - OAuth 2.0 authorization code with PKCE, scopes
  ``user_read workouts_read offline_data``; workouts are listed and each
  workout's FIT file is downloaded from the URL in its summary.
* Garmin Connect Developer Program (business "Starter" access) - OAuth 2.0
  with PKCE. Starter access delivers data by push to a registered webhook.
* Garmin Connect Personal API - a key the user creates for their OWN account;
  read-only pull of activities and original files. Garmin states it is not
  intended for commercial applications serving multiple end users, so this
  mode is an owner/self-hosting route, not a public multi-user integration.

No password login, scraping or unofficial endpoint is used. Tokens and keys are
stored only encrypted (Fernet) and are never returned to the client.
This module performs cloud activity sync only; it does not control a trainer.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Callable, List, Optional
from urllib.parse import urlencode

from cryptography.fernet import Fernet, InvalidToken
import httpx
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.science.activity_files import ActivityFileError, parse_activity_file

STATE_TTL = timedelta(minutes=10)
SYNC_BATCH = 5
FILE_HOSTS = {"wahoo": ("cdn.wahooligan.com", "wahooligan.com"), "garmin": ("apis.garmin.com",)}


class ProviderError(Exception):
    """Safe to show to the user; never contains a token or provider response body."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    authorize_url: str
    token_url: str
    scope: str
    client_id: Callable[[], str]
    client_secret: Callable[[], str]


OAUTH = {
    "wahoo": OAuthProvider("wahoo", "https://api.wahooligan.com/oauth/authorize", "https://api.wahooligan.com/oauth/token",
                           "user_read workouts_read offline_data",
                           lambda: settings.wahoo_client_id, lambda: settings.wahoo_client_secret),
    "garmin": OAuthProvider("garmin", "https://connect.garmin.com/oauth2Confirm",
                            "https://diauth.garmin.com/di-oauth2-service/oauth/token", "",
                            lambda: settings.garmin_client_id, lambda: settings.garmin_client_secret),
}
GARMIN_PERSONAL = "https://personal.connectapi.garmin.com"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


class ProviderService:
    def __init__(self, db: Session, client: Optional[httpx.Client] = None):
        key = settings.provider_token_encryption_key.strip()
        self._fernet = Fernet(key.encode()) if key else None
        self.db = db
        self.http = client or httpx.Client(timeout=15.0, follow_redirects=False)

    # ── secrets ────────────────────────────────────────────────────────────
    def _protect(self, value: str) -> str:
        if not self._fernet:
            raise ProviderError("Provider links are not configured on this server", 503)
        return self._fernet.encrypt(value.encode()).decode()

    def _reveal(self, value: Optional[str]) -> str:
        if not self._fernet or not value:
            raise ProviderError("Provider link must be renewed", 409)
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            raise ProviderError("Provider link must be renewed", 409) from None

    def _redirect_uri(self, provider: str) -> str:
        return f"{settings.provider_redirect_base.rstrip('/')}/v3/providers/{provider}/callback"

    def available(self, provider: str) -> dict:
        oauth = provider in OAUTH and bool(OAUTH[provider].client_id() and self._fernet and settings.provider_redirect_base)
        return {"oauth": oauth, "personal_key": provider == "garmin" and bool(self._fernet)}

    def _connection(self, user_id: str, provider: str) -> Optional[models.ProviderConnection]:
        return self.db.query(models.ProviderConnection).filter_by(user_id=user_id, provider=provider).first()

    def status(self, user_id: str, provider: str) -> dict:
        if provider not in OAUTH:
            raise ProviderError("Unknown provider", 404)
        row = self._connection(user_id, provider)
        linked = bool(row and row.status == "connected")
        return {"provider": provider, "available": self.available(provider), "connected": linked,
                "mode": row.mode if linked else None, "needs_renewal": bool(row and row.status == "error"),
                "last_error": row.last_error if row else None, "synced_until": row.cursor if linked else None,
                "sync_requested": bool(row and row.sync_requested)}

    # ── OAuth 2.0 with PKCE ────────────────────────────────────────────────
    def start(self, user_id: str, provider: str) -> str:
        if not self.available(provider)["oauth"]:
            raise ProviderError("This provider is not enabled on this server", 503)
        config = OAUTH[provider]
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.db.query(models.ProviderOAuthState).filter(models.ProviderOAuthState.expires_at < _now()).delete()
        self.db.add(models.ProviderOAuthState(state_hash=hashlib.sha256(state.encode()).hexdigest(), user_id=user_id,
                                              provider=provider, verifier_enc=self._protect(verifier), expires_at=_now() + STATE_TTL))
        self.db.commit()
        query = {"client_id": config.client_id(), "redirect_uri": self._redirect_uri(provider), "response_type": "code",
                 "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
        if config.scope:
            query["scope"] = config.scope
        return f"{config.authorize_url}?{urlencode(query)}"

    def finish(self, provider: str, code: str, state: str) -> str:
        """Complete the redirect. The state row identifies the user; it works exactly once."""
        row = self.db.get(models.ProviderOAuthState, hashlib.sha256(state.encode()).hexdigest())
        if row is None or row.provider != provider or _aware(row.expires_at) < _now():
            raise ProviderError("This link request has expired; start again from the app")
        user_id, verifier = row.user_id, self._reveal(row.verifier_enc)
        self.db.delete(row)
        self.db.commit()
        config = OAUTH[provider]
        tokens = self._token_request(config, {"grant_type": "authorization_code", "code": code,
                                              "redirect_uri": self._redirect_uri(provider), "code_verifier": verifier})
        connection = self._connection(user_id, provider) or models.ProviderConnection(user_id=user_id, provider=provider)
        connection.mode, connection.status, connection.last_error = "oauth", "connected", None
        self._store_tokens(connection, tokens)
        connection.provider_user_id = self._provider_user(provider, tokens["access_token"])
        connection.sync_requested = True
        self.db.add(connection)
        self.db.commit()
        return user_id

    def _token_request(self, config: OAuthProvider, form: dict) -> dict:
        try:
            response = self.http.post(config.token_url, data={**form, "client_id": config.client_id(),
                                                              "client_secret": config.client_secret()})
        except httpx.HTTPError:
            raise ProviderError("The provider could not be reached; try again later", 502) from None
        if response.status_code != 200:
            raise ProviderError("The provider refused the authorization", 409)
        body = response.json()
        if not isinstance(body, dict) or not body.get("access_token"):
            raise ProviderError("The provider returned an unexpected answer", 502)
        return body

    def _store_tokens(self, connection: models.ProviderConnection, tokens: dict) -> None:
        connection.access_token_enc = self._protect(tokens["access_token"])
        if tokens.get("refresh_token"):
            connection.refresh_token_enc = self._protect(tokens["refresh_token"])
        lifetime = float(tokens.get("expires_in") or 3600)
        connection.expires_at = _now() + timedelta(seconds=max(60.0, lifetime - 60.0))
        connection.scopes = str(tokens.get("scope") or "")[:255] or connection.scopes

    def _provider_user(self, provider: str, access_token: str) -> Optional[str]:
        url = "https://api.wahooligan.com/v1/user" if provider == "wahoo" else "https://apis.garmin.com/wellness-api/rest/user/id"
        body = self._get_json(url, access_token)
        value = body.get("id") or body.get("userId")
        return str(value)[:128] if value is not None else None

    def _get_json(self, url: str, access_token: str, params: Optional[dict] = None) -> dict:
        try:
            response = self.http.get(url, params=params, headers={"Authorization": f"Bearer {access_token}"})
        except httpx.HTTPError:
            raise ProviderError("The provider could not be reached; try again later", 502) from None
        if response.status_code == 401:
            raise ProviderError("Provider link must be renewed", 409)
        if response.status_code == 429:
            raise ProviderError("The provider's rate limit was reached; try again later", 429)
        if response.status_code != 200:
            raise ProviderError("The provider returned an error", 502)
        body = response.json()
        return body if isinstance(body, dict) else {"items": body}

    def _access_token(self, connection: models.ProviderConnection) -> str:
        if connection.status != "connected":
            raise ProviderError("Provider link must be renewed", 409)
        if connection.expires_at and _aware(connection.expires_at) > _now():
            return self._reveal(connection.access_token_enc)
        try:
            if connection.mode == "personal_key":
                tokens = self._garmin_personal_token(self._reveal(connection.refresh_token_enc))
            else:
                tokens = self._token_request(OAUTH[connection.provider], {
                    "grant_type": "refresh_token", "refresh_token": self._reveal(connection.refresh_token_enc)})
        except ProviderError as error:
            if error.status == 409:   # revoked or expired at the provider: require an explicit new link
                connection.status, connection.last_error = "error", "authorization_expired_or_revoked"
                self.db.commit()
            raise
        self._store_tokens(connection, tokens)
        self.db.commit()
        return tokens["access_token"]

    # ── Garmin Personal API (the user's own key) ───────────────────────────
    def _garmin_personal_token(self, api_key: str) -> dict:
        try:
            response = self.http.post(f"{GARMIN_PERSONAL}/personalapitoken-service/personal-api/personal-api-key/token",
                                      headers={"Authorization": f"ApiKey {api_key}"})
        except httpx.HTTPError:
            raise ProviderError("Garmin could not be reached; try again later", 502) from None
        if response.status_code in {401, 403}:
            raise ProviderError("Garmin did not accept this Personal API key (wrong, deleted or expired)", 409)
        if response.status_code != 200:
            raise ProviderError("Garmin returned an error", 502)
        body = response.json()
        token = body.get("access_token") or body.get("accessToken") if isinstance(body, dict) else None
        if not token:
            raise ProviderError("Garmin returned an unexpected answer", 502)
        return {"access_token": token, "expires_in": body.get("expires_in") or body.get("expiresIn") or 86400}

    def link_garmin_personal(self, user_id: str, api_key: str) -> None:
        api_key = api_key.strip()
        if not 16 <= len(api_key) <= 512:
            raise ProviderError("That does not look like a Garmin Personal API key")
        tokens = self._garmin_personal_token(api_key)        # verifies the key before anything is stored
        connection = self._connection(user_id, "garmin") or models.ProviderConnection(user_id=user_id, provider="garmin")
        connection.mode, connection.status, connection.last_error = "personal_key", "connected", None
        connection.refresh_token_enc = self._protect(api_key)
        self._store_tokens(connection, tokens)
        connection.sync_requested = True
        self.db.add(connection)
        self.db.commit()

    # ── revoke ─────────────────────────────────────────────────────────────
    def disconnect(self, user_id: str, provider: str) -> dict:
        connection = self._connection(user_id, provider)
        if connection is None:
            return {"removed": False, "revoked_at_provider": False}
        revoked = False
        if connection.mode == "oauth" and connection.status == "connected":
            url = "https://api.wahooligan.com/v1/permissions" if provider == "wahoo" else "https://apis.garmin.com/wellness-api/rest/user/registration"
            try:
                token = self._access_token(connection)
                revoked = self.http.delete(url, headers={"Authorization": f"Bearer {token}"}).status_code in {200, 204}
            except (ProviderError, httpx.HTTPError):
                revoked = False
        # Local tokens are always deleted, even when the provider could not be reached.
        self.db.delete(connection)
        self.db.commit()
        return {"removed": True, "revoked_at_provider": revoked,
                "manual_step": None if revoked else "revoke_in_provider_account_settings"}

    # ── incremental pull ───────────────────────────────────────────────────
    def _download(self, provider: str, url: str, access_token: Optional[str]) -> bytes:
        host = httpx.URL(url).host or ""
        if httpx.URL(url).scheme != "https" or not any(host == h or host.endswith("." + h) for h in FILE_HOSTS[provider]):
            raise ProviderError("The provider returned an unexpected file location", 502)
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        try:
            response = self.http.get(url, headers=headers)
        except httpx.HTTPError:
            raise ProviderError("The activity file could not be downloaded", 502) from None
        if response.status_code != 200:
            raise ProviderError("The activity file could not be downloaded", 502)
        return response.content

    def _candidates(self, connection: models.ProviderConnection, token: str) -> List[dict]:
        """Oldest-first list of activities newer than the acknowledged cursor."""
        cursor = connection.cursor or ""
        found: List[dict] = []
        if connection.provider == "wahoo":
            for page in range(1, 6):
                body = self._get_json("https://api.wahooligan.com/v1/workouts", token, {"page": page, "per_page": 30})
                items = body.get("workouts") or []
                found += [{"id": str(w["id"]), "start": str(w.get("starts") or "")} for w in items if w.get("id") is not None]
                if len(items) < 30 or (items and str(items[-1].get("starts") or "") <= cursor):
                    break
        elif connection.mode == "personal_key":
            params = {"start": 0, "limit": 50}
            if cursor:
                params["startDate"] = cursor[:10]
            body = self._get_json(f"{GARMIN_PERSONAL}/activitylist-service/activities/search/activities", token, params)
            items = body.get("items") or body.get("activities") or []
            found = [{"id": str(a["activityId"]), "start": str(a.get("startTimeGMT") or a.get("beginTimestamp") or "")}
                     for a in items if isinstance(a, dict) and a.get("activityId") is not None]
        else:
            raise ProviderError("Garmin business access delivers activities by push; none are waiting", 409)
        return sorted((c for c in found if c["start"] > cursor), key=lambda c: c["start"])

    def sync(self, user_id: str, provider: str) -> dict:
        """Return up to SYNC_BATCH parsed activities. Nothing is marked done until ``acknowledge``."""
        connection = self._connection(user_id, provider)
        if connection is None:
            raise ProviderError("This provider is not linked", 404)
        token = self._access_token(connection)
        candidates = self._candidates(connection, token)
        activities, skipped = [], []
        for item in candidates[:SYNC_BATCH]:
            try:
                if provider == "wahoo":
                    detail = self._get_json(f"https://api.wahooligan.com/v1/workouts/{item['id']}", token)
                    url = ((detail.get("workout_summary") or {}).get("file") or {}).get("url")
                    if not url:
                        skipped.append({"external_id": item["id"], "reason": "no_file_yet"})
                        continue
                    data = self._download("wahoo", url, None)
                else:
                    data = self._personal_file(item["id"], token)
                parsed = parse_activity_file(data)
            except ActivityFileError as error:
                skipped.append({"external_id": item["id"], "reason": str(error)})
                continue
            parsed["provenance"] = {"provider": provider, "external_id": item["id"], "route": connection.mode}
            activities.append({"external_id": item["id"], "listed_start": item["start"], "activity": parsed})
        batch = candidates[:SYNC_BATCH]
        connection.sync_requested = len(candidates) > SYNC_BATCH
        self.db.commit()
        return {"activities": activities, "skipped": skipped, "more": len(candidates) > SYNC_BATCH,
                "ack_cursor": batch[-1]["start"] if batch else None}

    def _personal_file(self, activity_id: str, token: str) -> bytes:
        try:
            response = self.http.get(f"{GARMIN_PERSONAL}/download-service/files/activity/{activity_id}",
                                     headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError:
            raise ProviderError("The activity file could not be downloaded", 502) from None
        if response.status_code != 200:
            raise ProviderError("The activity file could not be downloaded", 502)
        return response.content

    def acknowledge(self, user_id: str, provider: str, cursor: str) -> None:
        """Called after the client has durably stored the batch. The cursor only moves forward."""
        connection = self._connection(user_id, provider)
        if connection is None:
            raise ProviderError("This provider is not linked", 404)
        if len(cursor) > 64:
            raise ProviderError("Invalid cursor")
        if cursor > (connection.cursor or ""):
            connection.cursor = cursor
            self.db.commit()

    # ── provider → server notifications ────────────────────────────────────
    def notify(self, provider: str, provider_user_id: str) -> bool:
        """A verified webhook only raises a flag; data are always pulled over the authenticated API."""
        rows = self.db.query(models.ProviderConnection).filter_by(provider=provider, provider_user_id=str(provider_user_id)[:128]).all()
        for row in rows:
            row.sync_requested = True
        self.db.commit()
        return bool(rows)
