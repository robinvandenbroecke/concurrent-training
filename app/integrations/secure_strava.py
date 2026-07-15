"""Hardened Strava integration.

Adds signed OAuth state verification, optional token encryption at rest, and
power-aware activity ingestion through the canonical day rebuild path.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import hmac
import logging
import time
from typing import Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
import httpx
from sqlalchemy.exc import IntegrityError

from app import models
from app.config import settings
from app.domain.endurance_engine import compute_endurance_load
from app.integrations.strava import (
    StravaAuthError,
    StravaError,
    StravaRateLimitError,
    StravaService as BaseStravaService,
)
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)


class StravaService(BaseStravaService):
    def __init__(self, db):
        super().__init__(db)
        key = settings.strava_token_encryption_key.strip()
        self._fernet = Fernet(key.encode()) if key else None
        self._sync_access_token: Optional[str] = None

    def _protect(self, token: str) -> str:
        if not self._fernet:
            return token
        return "enc:" + self._fernet.encrypt(token.encode()).decode()

    def _unprotect(self, token: str) -> str:
        if not token.startswith("enc:"):
            return token
        if not self._fernet:
            raise StravaAuthError("Encrypted Strava token cannot be read without STRAVA_TOKEN_ENCRYPTION_KEY")
        try:
            return self._fernet.decrypt(token[4:].encode()).decode()
        except InvalidToken as exc:
            raise StravaAuthError("Stored Strava token is invalid") from exc

    def _generate_state_token(self, athlete_id: int) -> str:
        timestamp = int(time.time())
        payload = f"{athlete_id}:{timestamp}"
        signature = hmac.new(
            settings.admin_api_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        return f"{payload}:{signature}"

    def verify_state_token(self, state: str) -> int:
        try:
            athlete_text, timestamp_text, signature = state.split(":", 2)
            athlete_id = int(athlete_text)
            timestamp = int(timestamp_text)
        except (ValueError, TypeError) as exc:
            raise StravaAuthError("Invalid OAuth state") from exc
        if abs(int(time.time()) - timestamp) > settings.strava_state_ttl_seconds:
            raise StravaAuthError("OAuth state expired")
        payload = f"{athlete_id}:{timestamp}"
        expected = hmac.new(
            settings.admin_api_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise StravaAuthError("OAuth state signature mismatch")
        return athlete_id

    def create_or_update_connection(
        self, athlete_id: int, token_response: Dict, accepted_scopes: Optional[str] = None
    ) -> models.StravaConnection:
        athlete = token_response.get("athlete", {})
        connection = self.get_connection(athlete_id)
        values = {
            "strava_athlete_id": str(athlete.get("id", "")),
            "strava_athlete_name": f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip(),
            "access_token": self._protect(token_response["access_token"]),
            "refresh_token": self._protect(token_response["refresh_token"]),
            "expires_at": token_response["expires_at"],
            "accepted_scopes": accepted_scopes,
            "is_active": True,
            "last_sync_error": None,
        }
        if connection is None:
            connection = models.StravaConnection(athlete_id=athlete_id, **values)
            self.db.add(connection)
        else:
            for key, value in values.items():
                setattr(connection, key, value)
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def ensure_valid_token(self, connection: models.StravaConnection) -> str:
        access_token = self._unprotect(connection.access_token)
        if connection.expires_at <= int(time.time()) + 3600:
            try:
                response = self.refresh_access_token(self._unprotect(connection.refresh_token))
            except StravaAuthError:
                connection.is_active = False
                connection.last_sync_error = "Token refresh failed - reconnection required"
                self.db.commit()
                raise
            connection.access_token = self._protect(response["access_token"])
            connection.refresh_token = self._protect(response["refresh_token"])
            connection.expires_at = response["expires_at"]
            self.db.commit()
            access_token = response["access_token"]
        return access_token

    def sync_activities(self, athlete_id: int, days_back: int = 30, max_pages: int = 10) -> Dict:
        """Expose the valid token to per-activity stream imports for this sync only."""
        connection = self.get_connection(athlete_id)
        if not connection or not connection.is_active:
            raise StravaAuthError("No active Strava connection found")
        self._sync_access_token = self.ensure_valid_token(connection)
        try:
            return super().sync_activities(athlete_id, days_back=days_back, max_pages=max_pages)
        finally:
            self._sync_access_token = None

    def _fetch_power_stream(self, activity_id: object) -> Optional[List[Dict]]:
        """Fetch second-level watts when Strava exposes a power stream."""
        if not activity_id or not self._sync_access_token:
            return None
        try:
            response = httpx.get(
                f"{self.BASE_URL}/activities/{activity_id}/streams",
                headers={"Authorization": f"Bearer {self._sync_access_token}"},
                params={"keys": "watts,time", "key_by_type": "true"},
                timeout=30.0,
            )
            if response.status_code == 429:
                logger.warning("Strava stream rate limit reached for activity %s", activity_id)
                return None
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.info("No usable power stream for activity %s: %s", activity_id, exc)
            return None

        watts = payload.get("watts", {}).get("data", []) if isinstance(payload, dict) else []
        times = payload.get("time", {}).get("data", []) if isinstance(payload, dict) else []
        if not watts:
            return None
        points: List[Dict] = []
        for index, value in enumerate(watts):
            try:
                power = float(value)
            except (TypeError, ValueError):
                continue
            if power <= 0:
                continue
            timestamp = times[index] if index < len(times) else index
            points.append({"power": power, "timestamp": timestamp})
        return points or None

    def _threshold_power(self, athlete_id: int, sport: str) -> Optional[float]:
        row = self.db.query(models.SystemParameters).filter(
            models.SystemParameters.athlete_id == athlete_id
        ).first()
        params = row.params if row and isinstance(row.params, dict) else {}
        try:
            value = params.get("endurance", {}).get(sport, {}).get("threshold_power_w")
            return float(value) if value and float(value) > 0 else None
        except (TypeError, ValueError):
            return None

    def _import_activity(self, athlete_id: int, activity: Dict, orchestrator) -> str:
        content_hash = self._generate_activity_hash(activity)
        existing = self.db.query(models.EnduranceSession).filter(
            models.EnduranceSession.athlete_id == athlete_id,
            models.EnduranceSession.content_hash == content_hash,
        ).first()
        if existing:
            return "skipped"

        sport = self._map_strava_sport(str(activity.get("type", "")).lower())
        if not sport:
            return "skipped"
        start_text = activity.get("start_date") or activity.get("start_date_local")
        if not start_text:
            return "skipped"
        start_time = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
        duration_minutes = float(activity.get("moving_time") or activity.get("elapsed_time") or 0) / 60.0
        if duration_minutes <= 0:
            return "skipped"

        power_data = None
        if sport.value in {"cycling", "running"} and (
            activity.get("device_watts") or activity.get("average_watts")
        ):
            power_data = self._fetch_power_stream(activity.get("id"))

        declared = self._determine_intensity_type(activity)
        threshold = self._threshold_power(athlete_id, sport.value)
        load = compute_endurance_load(
            sport=sport.value,
            duration_minutes=duration_minutes,
            declared_intensity=declared,
            power_data=power_data,
            average_power_w=activity.get("average_watts"),
            normalized_power_w=activity.get("weighted_average_watts") or activity.get("average_watts"),
            threshold_power_w=threshold,
        )
        session = models.EnduranceSession(
            athlete_id=athlete_id,
            sport=sport,
            start_time=start_time,
            duration_minutes=duration_minutes,
            intensity_type=load.intensity_type,
            content_hash=content_hash,
            u_E_Z2=load.u_z2,
            u_E_HIIT=load.u_hiit,
            raw_data={
                "source": "strava",
                "external_id": str(activity.get("id")),
                "signal_source": load.signal_source,
                "power_data": power_data,
                "power_stream_points": len(power_data or []),
                "average_power_w": load.average_power_w,
                "normalized_power_w": load.normalized_power_w,
                "threshold_power_w": load.threshold_power_w,
                "intensity_factor": load.intensity_factor,
                "average_heartrate": activity.get("average_heartrate"),
                "max_heartrate": activity.get("max_heartrate"),
                "distance": activity.get("distance"),
                "total_elevation_gain": activity.get("total_elevation_gain"),
                "activity": activity,
            },
        )
        self.db.add(session)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            return "skipped"
        SessionService(self.db)._rebuild_day(athlete_id, start_time.date())
        self.db.commit()
        return "imported"

    def disconnect(self, athlete_id: int) -> bool:
        connection = self.get_connection(athlete_id)
        if not connection:
            return False
        connection.is_active = False
        connection.access_token = ""
        connection.refresh_token = ""
        self.db.commit()
        return True


__all__ = ["StravaService", "StravaError", "StravaAuthError", "StravaRateLimitError"]
