"""
Strava API integration service

Handles OAuth flow, token management, and activity syncing.
"""
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services.engine_orchestrator import EngineOrchestrator
from app.types import EnduranceSport

logger = logging.getLogger(__name__)


class StravaError(Exception):
    """Base Strava API error"""
    pass


class StravaAuthError(StravaError):
    """Authentication/authorization error"""
    pass


class StravaRateLimitError(StravaError):
    """Rate limit hit"""
    pass


class StravaService:
    """Service for Strava API integration"""
    
    BASE_URL = "https://www.strava.com/api/v3"
    AUTH_URL = "https://www.strava.com/oauth/authorize"
    TOKEN_URL = "https://www.strava.com/oauth/token"
    
    def __init__(self, db: Session):
        self.db = db
        self.client_id = settings.strava_client_id
        self.client_secret = settings.strava_client_secret
        self.redirect_uri = settings.strava_redirect_uri
        self.scopes = settings.strava_scopes
    
    def is_configured(self) -> bool:
        """Check if Strava OAuth is properly configured"""
        return bool(self.client_id and self.client_secret)
    
    def build_authorize_url(self, athlete_id: int, state: Optional[str] = None) -> str:
        """
        Build Strava OAuth authorization URL
        
        Args:
            athlete_id: Internal athlete ID
            state: Optional state token for CSRF protection
        
        Returns:
            Full authorization URL
        """
        if not self.is_configured():
            raise StravaAuthError("Strava OAuth not configured")
        
        # Generate state token if not provided
        if state is None:
            state = self._generate_state_token(athlete_id)
        
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": self.scopes,
            "state": state
        }
        
        return f"{self.AUTH_URL}?{urlencode(params)}"
    
    def exchange_code_for_token(self, code: str) -> Dict:
        """
        Exchange authorization code for access/refresh tokens
        
        Args:
            code: Authorization code from callback
        
        Returns:
            Token response dict with access_token, refresh_token, expires_at, athlete
        """
        if not self.is_configured():
            raise StravaAuthError("Strava OAuth not configured")
        
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code"
        }
        
        try:
            response = httpx.post(self.TOKEN_URL, data=payload, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise StravaAuthError(f"Invalid authorization code: {e.response.text}")
            raise StravaError(f"Token exchange failed: {e.response.text}")
        except httpx.RequestError as e:
            raise StravaError(f"Network error during token exchange: {e}")
    
    def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh access token using refresh token
        
        Args:
            refresh_token: Current refresh token
        
        Returns:
            New token response with updated tokens
        """
        if not self.is_configured():
            raise StravaAuthError("Strava OAuth not configured")
        
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        
        try:
            response = httpx.post(self.TOKEN_URL, data=payload, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise StravaAuthError(f"Invalid refresh token: {e.response.text}")
            raise StravaError(f"Token refresh failed: {e.response.text}")
        except httpx.RequestError as e:
            raise StravaError(f"Network error during token refresh: {e}")
    
    def get_connection(self, athlete_id: int) -> Optional[models.StravaConnection]:
        """Get Strava connection for athlete"""
        return self.db.query(models.StravaConnection).filter(
            models.StravaConnection.athlete_id == athlete_id
        ).first()
    
    def create_or_update_connection(
        self,
        athlete_id: int,
        token_response: Dict,
        accepted_scopes: Optional[str] = None
    ) -> models.StravaConnection:
        """
        Create or update Strava connection
        
        Args:
            athlete_id: Internal athlete ID
            token_response: OAuth token response
            accepted_scopes: Scopes accepted by user
        
        Returns:
            StravaConnection model
        """
        strava_athlete = token_response.get("athlete", {})
        strava_athlete_id = str(strava_athlete.get("id", ""))
        strava_athlete_name = f"{strava_athlete.get('firstname', '')} {strava_athlete.get('lastname', '')}".strip()
        
        # Check for existing connection
        connection = self.get_connection(athlete_id)
        
        if connection:
            # Update existing
            connection.strava_athlete_id = strava_athlete_id
            connection.strava_athlete_name = strava_athlete_name
            connection.access_token = token_response["access_token"]
            connection.refresh_token = token_response["refresh_token"]
            connection.expires_at = token_response["expires_at"]
            connection.accepted_scopes = accepted_scopes
            connection.is_active = True
            connection.last_sync_error = None
        else:
            # Create new
            connection = models.StravaConnection(
                athlete_id=athlete_id,
                strava_athlete_id=strava_athlete_id,
                strava_athlete_name=strava_athlete_name,
                access_token=token_response["access_token"],
                refresh_token=token_response["refresh_token"],
                expires_at=token_response["expires_at"],
                accepted_scopes=accepted_scopes,
                is_active=True
            )
            self.db.add(connection)
        
        self.db.commit()
        self.db.refresh(connection)
        return connection
    
    def ensure_valid_token(self, connection: models.StravaConnection) -> str:
        """
        Ensure connection has valid access token, refreshing if needed
        
        Args:
            connection: StravaConnection model
        
        Returns:
            Valid access token
        """
        # Check if token expires within 1 hour
        now = int(time.time())
        if connection.expires_at <= now + 3600:
            logger.info(f"Refreshing Strava token for athlete {connection.athlete_id}")
            try:
                token_response = self.refresh_access_token(connection.refresh_token)
                connection.access_token = token_response["access_token"]
                connection.refresh_token = token_response["refresh_token"]
                connection.expires_at = token_response["expires_at"]
                self.db.commit()
                logger.info(f"Token refreshed successfully")
            except StravaAuthError:
                # Token refresh failed - mark connection as inactive
                connection.is_active = False
                connection.last_sync_error = "Token refresh failed - reconnection required"
                self.db.commit()
                raise
        
        return connection.access_token
    
    def list_activities(
        self,
        access_token: str,
        after_timestamp: Optional[int] = None,
        before_timestamp: Optional[int] = None,
        page: int = 1,
        per_page: int = 100
    ) -> List[Dict]:
        """
        List activities from Strava API
        
        Args:
            access_token: Valid access token
            after_timestamp: Only activities after this Unix timestamp
            before_timestamp: Only activities before this Unix timestamp
            page: Page number
            per_page: Items per page (max 200)
        
        Returns:
            List of activity dicts
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"page": page, "per_page": per_page}
        
        if after_timestamp:
            params["after"] = after_timestamp
        if before_timestamp:
            params["before"] = before_timestamp
        
        try:
            response = httpx.get(
                f"{self.BASE_URL}/athlete/activities",
                headers=headers,
                params=params,
                timeout=30.0
            )
            
            if response.status_code == 429:
                raise StravaRateLimitError("Strava rate limit exceeded")
            
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise StravaAuthError("Invalid access token")
            raise StravaError(f"API error: {e.response.text}")
        except httpx.RequestError as e:
            raise StravaError(f"Network error: {e}")
    
    def sync_activities(
        self,
        athlete_id: int,
        days_back: int = 30,
        max_pages: int = 10
    ) -> Dict:
        """
        Sync Strava activities to EnduranceSession records
        
        Args:
            athlete_id: Internal athlete ID
            days_back: How many days to look back
            max_pages: Maximum pages to fetch (safety limit)
        
        Returns:
            Sync result summary dict
        """
        connection = self.get_connection(athlete_id)
        if not connection:
            raise StravaAuthError("No Strava connection found")
        
        if not connection.is_active:
            raise StravaAuthError("Strava connection is inactive")
        
        # Ensure valid token
        access_token = self.ensure_valid_token(connection)
        
        # Calculate sync window
        now = datetime.now()
        
        # Start from last_sync_at - 1 day (to catch any missed), or days_back
        if connection.last_sync_at:
            after_dt = connection.last_sync_at - timedelta(days=1)
        else:
            after_dt = now - timedelta(days=days_back)
        
        after_timestamp = int(after_dt.timestamp())
        before_timestamp = int(now.timestamp())
        
        logger.info(f"Syncing Strava activities for athlete {athlete_id} from {after_dt.isoformat()}")
        
        # Fetch all activities
        all_activities = []
        page = 1
        
        try:
            while page <= max_pages:
                activities = self.list_activities(
                    access_token=access_token,
                    after_timestamp=after_timestamp,
                    before_timestamp=before_timestamp,
                    page=page,
                    per_page=100
                )
                
                if not activities:
                    break
                
                all_activities.extend(activities)
                
                # Check for rate limit headers
                # Strava allows 100 requests per 15 minutes for read endpoints
                if len(activities) < 100:
                    break
                
                page += 1
        
        except StravaRateLimitError:
            # Continue with what we have
            logger.warning(f"Rate limit hit during sync for athlete {athlete_id}")
        
        # Import activities
        imported = 0
        skipped = 0
        errors = []
        
        orchestrator = EngineOrchestrator(self.db)
        
        for activity in all_activities:
            try:
                result = self._import_activity(athlete_id, activity, orchestrator)
                if result == "imported":
                    imported += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(f"Failed to import activity {activity.get('id')}: {e}")
                errors.append(f"Activity {activity.get('id')}: {str(e)}")
        
        # Update connection
        connection.last_sync_at = now
        if errors:
            connection.last_sync_error = f"{len(errors)} errors: {errors[0][:100]}"
        else:
            connection.last_sync_error = None
        
        self.db.commit()
        
        logger.info(f"Sync complete: {imported} imported, {skipped} skipped, {len(errors)} errors")
        
        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "total_fetched": len(all_activities),
            "synced_at": now.isoformat()
        }
    
    def _import_activity(
        self,
        athlete_id: int,
        activity: Dict,
        orchestrator: EngineOrchestrator
    ) -> str:
        """
        Import a single Strava activity as EnduranceSession
        
        Args:
            athlete_id: Internal athlete ID
            activity: Strava activity dict
            orchestrator: EngineOrchestrator instance
        
        Returns:
            "imported" or "skipped"
        """
        # Generate content hash for idempotency
        content_hash = self._generate_activity_hash(activity)
        
        # Check for existing session
        existing = self.db.query(models.EnduranceSession).filter(
            models.EnduranceSession.athlete_id == athlete_id,
            models.EnduranceSession.content_hash == content_hash
        ).first()
        
        if existing:
            return "skipped"
        
        # Map Strava sport type to our EnduranceSport
        strava_type = activity.get("type", "").lower()
        sport = self._map_strava_sport(strava_type)
        
        if not sport:
            # Skip unsupported activity types
            return "skipped"
        
        # Parse start time
        start_date_str = activity.get("start_date_local") or activity.get("start_date")
        if start_date_str:
            start_time = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
        else:
            # Fallback to current time (should not happen)
            start_time = datetime.utcnow()
        
        # Get duration (prefer moving_time over elapsed_time)
        duration_seconds = activity.get("moving_time") or activity.get("elapsed_time", 0)
        duration_minutes = duration_seconds / 60.0
        
        if duration_minutes <= 0:
            return "skipped"
        
        # Determine intensity type (simple heuristic)
        intensity_type = self._determine_intensity_type(activity)
        
        # Build raw_data with full activity payload
        raw_data = {
            "strava_activity_id": activity.get("id"),
            "strava_type": strava_type,
            "name": activity.get("name"),
            "distance": activity.get("distance"),
            "moving_time": activity.get("moving_time"),
            "elapsed_time": activity.get("elapsed_time"),
            "average_speed": activity.get("average_speed"),
            "max_speed": activity.get("max_speed"),
            "average_watts": activity.get("average_watts"),
            "max_watts": activity.get("max_watts"),
            "kilojoules": activity.get("kilojoules"),
            "average_heartrate": activity.get("average_heartrate"),
            "max_heartrate": activity.get("max_heartrate"),
            "elev_high": activity.get("elev_high"),
            "elev_low": activity.get("elev_low"),
            "total_elevation_gain": activity.get("total_elevation_gain"),
            "timezone": activity.get("timezone"),
            "gear_id": activity.get("gear_id"),
            "content_hash": content_hash
        }
        
        # Create endurance session via orchestrator
        session, day_state, _ = orchestrator.ingest_endurance_session(
            athlete_id=athlete_id,
            session_date=start_time.date(),
            sport=sport,
            duration_minutes=duration_minutes,
            intensity_type=intensity_type
        )
        
        # Update with Strava data
        session.content_hash = content_hash
        session.raw_data = raw_data
        
        self.db.commit()
        
        return "imported"
    
    def _map_strava_sport(self, strava_type: str) -> Optional[EnduranceSport]:
        """Map Strava activity type to EnduranceSport"""
        type_mapping = {
            "ride": EnduranceSport.CYCLING,
            "virtualride": EnduranceSport.CYCLING,
            "ebikeride": EnduranceSport.CYCLING,
            "run": EnduranceSport.RUNNING,
            "virtualrun": EnduranceSport.RUNNING,
            "swim": EnduranceSport.SWIMMING,
        }
        return type_mapping.get(strava_type.lower())
    
    def _determine_intensity_type(self, activity: Dict) -> str:
        """
        Determine intensity type from activity data
        
        Simple heuristic:
        - If name contains 'interval', 'hiit', 'workout' -> hiit
        - If average watts > 200 OR average speed is high for the sport -> hiit
        - Otherwise -> z2
        """
        name = activity.get("name", "").lower()
        
        # Check name for hints
        hiit_keywords = ["interval", "hiit", "workout", "sprint", "ftp", "test", "race"]
        if any(kw in name for kw in hiit_keywords):
            return "hiit"
        
        # Check power/effort for cycling
        avg_watts = activity.get("average_watts")
        if avg_watts and avg_watts > 200:
            return "hiit"
        
        # Default to z2 for steady state
        return "z2"
    
    def _generate_state_token(self, athlete_id: int) -> str:
        """Generate CSRF state token"""
        data = f"{athlete_id}:{time.time()}:{settings.admin_api_key}"
        return f"{athlete_id}:{hashlib.sha256(data.encode()).hexdigest()[:32]}"
    
    def _generate_activity_hash(self, activity: Dict) -> str:
        """Generate content hash for idempotency"""
        # Use activity ID + start time for uniqueness
        data = f"strava:{activity.get('id')}:{activity.get('start_date')}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    def disconnect(self, athlete_id: int) -> bool:
        """
        Disconnect Strava for athlete
        
        Args:
            athlete_id: Internal athlete ID
        
        Returns:
            True if disconnected, False if no connection existed
        """
        connection = self.get_connection(athlete_id)
        if not connection:
            return False
        
        # Mark as inactive rather than delete (for audit trail)
        connection.is_active = False
        connection.access_token = ""
        connection.refresh_token = ""
        self.db.commit()
        
        return True
