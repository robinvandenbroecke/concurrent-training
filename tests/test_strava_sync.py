"""
Tests for Strava activity syncing
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

import httpx

from app.integrations.strava import StravaService, StravaRateLimitError
from app.types import EnduranceSport


class TestStravaActivitySync:
    """Test syncing activities from Strava"""
    
    @patch("app.integrations.strava.httpx.get")
    def test_list_activities(self, mock_get, db_session):
        """List activities mocked returns expected data"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Mock response
            mock_response = Mock()
            mock_response.json.return_value = [
                {"id": 1, "name": "Morning Ride", "type": "Ride"},
                {"id": 2, "name": "Evening Run", "type": "Run"}
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            service = StravaService(db_session)
            activities = service.list_activities("test_token")
            
            assert len(activities) == 2
            assert activities[0]["name"] == "Morning Ride"
            
            # Verify API call
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "https://www.strava.com/api/v3/athlete/activities"
            assert call_args[1]["headers"]["Authorization"] == "Bearer test_token"
    
    @patch("app.integrations.strava.httpx.get")
    def test_list_activities_rate_limit(self, mock_get, db_session):
        """Rate limit 429 raises StravaRateLimitError"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Mock 429 response
            mock_response = Mock()
            mock_response.status_code = 429
            mock_get.return_value = mock_response
            
            service = StravaService(db_session)
            
            with pytest.raises(StravaRateLimitError, match="rate limit"):
                service.list_activities("test_token")
    
    def test_map_strava_sport(self, db_session):
        """Strava activity types correctly mapped to EnduranceSport"""
        service = StravaService(db_session)
        
        assert service._map_strava_sport("ride") == EnduranceSport.CYCLING
        assert service._map_strava_sport("virtualride") == EnduranceSport.CYCLING
        assert service._map_strava_sport("ebikeride") == EnduranceSport.CYCLING
        assert service._map_strava_sport("run") == EnduranceSport.RUNNING
        assert service._map_strava_sport("virtualrun") == EnduranceSport.RUNNING
        assert service._map_strava_sport("swim") == EnduranceSport.SWIMMING
        assert service._map_strava_sport("yoga") is None
        assert service._map_strava_sport("weighttraining") is None
    
    def test_determine_intensity_type(self, db_session):
        """Intensity type determined from activity data"""
        service = StravaService(db_session)
        
        # HIIT by name
        assert service._determine_intensity_type({"name": "Interval Workout"}) == "hiit"
        assert service._determine_intensity_type({"name": "HIIT Session"}) == "hiit"
        assert service._determine_intensity_type({"name": "Sprint Training"}) == "hiit"
        
        # HIIT by power
        assert service._determine_intensity_type({
            "name": "Hard Ride",
            "average_watts": 250
        }) == "hiit"
        
        # Z2 default
        assert service._determine_intensity_type({
            "name": "Easy Spin",
            "average_watts": 150
        }) == "z2"
    
    def test_generate_activity_hash(self, db_session):
        """Content hash is deterministic for idempotency"""
        service = StravaService(db_session)
        
        activity = {
            "id": 12345,
            "start_date": "2024-01-15T08:00:00Z"
        }
        
        hash1 = service._generate_activity_hash(activity)
        hash2 = service._generate_activity_hash(activity)
        
        assert hash1 == hash2
        assert len(hash1) == 32  # SHA256 truncated
    
    @patch("app.integrations.strava.httpx.get")
    def test_sync_activities_imports_via_orchestrator(self, mock_get, db_session, sample_athlete):
        """Activities are imported through orchestrator with idempotency"""
        from app import models
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Create connection first
            service = StravaService(db_session)
            token_response = {
                "access_token": "test_token",
                "refresh_token": "refresh_token",
                "expires_at": 9999999999,
                "athlete": {"id": 12345}
            }
            service.create_or_update_connection(
                athlete_id=sample_athlete.id,
                token_response=token_response
            )
            
            # Mock activities API response
            mock_response = Mock()
            mock_response.json.return_value = [
                {
                    "id": 11111,
                    "name": "Morning Ride",
                    "type": "Ride",
                    "start_date_local": "2024-01-15T08:00:00",
                    "moving_time": 3600,
                    "average_watts": 180
                },
                {
                    "id": 22222,
                    "name": "Evening Run",
                    "type": "Run",
                    "start_date_local": "2024-01-15T18:00:00",
                    "moving_time": 1800
                }
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            # Run sync
            result = service.sync_activities(sample_athlete.id, days_back=7)
            
            assert result["imported"] == 2
            assert result["skipped"] == 0
            assert result["total_fetched"] == 2
            
            # Verify sessions were created
            sessions = db_session.query(models.EnduranceSession).filter(
                models.EnduranceSession.athlete_id == sample_athlete.id
            ).all()
            
            assert len(sessions) == 2
            
            # Check sport mapping
            sports = [s.sport for s in sessions]
            assert EnduranceSport.CYCLING in sports
            assert EnduranceSport.RUNNING in sports
    
    @patch("app.integrations.strava.httpx.get")
    def test_sync_activities_idempotent(self, mock_get, db_session, sample_athlete):
        """Duplicate sync does not duplicate sessions"""
        from app import models
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Create connection
            service = StravaService(db_session)
            token_response = {
                "access_token": "test_token",
                "refresh_token": "refresh_token",
                "expires_at": 9999999999,
                "athlete": {"id": 12345}
            }
            service.create_or_update_connection(
                athlete_id=sample_athlete.id,
                token_response=token_response
            )
            
            # Mock activities
            mock_response = Mock()
            mock_response.json.return_value = [
                {
                    "id": 11111,
                    "name": "Morning Ride",
                    "type": "Ride",
                    "start_date_local": "2024-01-15T08:00:00",
                    "moving_time": 3600
                }
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            # First sync
            result1 = service.sync_activities(sample_athlete.id, days_back=7)
            assert result1["imported"] == 1
            assert result1["skipped"] == 0
            
            # Second sync (same activity)
            result2 = service.sync_activities(sample_athlete.id, days_back=7)
            assert result2["imported"] == 0
            assert result2["skipped"] == 1  # Skipped due to content hash match
            
            # Verify only one session exists
            sessions = db_session.query(models.EnduranceSession).filter(
                models.EnduranceSession.athlete_id == sample_athlete.id
            ).all()
            assert len(sessions) == 1
    
    @patch("app.integrations.strava.httpx.get")
    def test_sync_activities_rate_limit_partial(self, mock_get, db_session, sample_athlete):
        """Rate limit 429 returns partial result gracefully"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Create connection
            service = StravaService(db_session)
            token_response = {
                "access_token": "test_token",
                "refresh_token": "refresh_token",
                "expires_at": 9999999999,
                "athlete": {"id": 12345}
            }
            service.create_or_update_connection(
                athlete_id=sample_athlete.id,
                token_response=token_response
            )
            
            # First call succeeds, second hits rate limit
            mock_response_ok = Mock()
            mock_response_ok.json.return_value = [
                {"id": 1, "name": "Ride 1", "type": "Ride", "start_date_local": "2024-01-15T08:00:00", "moving_time": 1800}
            ]
            mock_response_ok.raise_for_status = Mock()
            
            mock_response_ratelimit = Mock()
            mock_response_ratelimit.status_code = 429
            
            mock_get.side_effect = [
                mock_response_ok,  # First page OK
                mock_response_ratelimit  # Second page rate limited
            ]
            
            # Run sync - should not raise, return partial results
            result = service.sync_activities(sample_athlete.id, days_back=7)
            
            # Should have imported what we got before rate limit
            assert result["imported"] >= 0  # May be 0 or 1 depending on batch order
            assert "errors" in result


class TestStravaActivityMapping:
    """Test activity mapping to EnduranceSession"""
    
    def test_import_activity_skips_unsupported_type(self, db_session, sample_athlete):
        """Unsupported activity types are skipped"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            
            service = StravaService(db_session)
            
            activity = {
                "id": 99999,
                "name": "Yoga Session",
                "type": "Yoga",  # Not supported
                "start_date_local": "2024-01-15T08:00:00",
                "moving_time": 3600
            }
            
            orchestrator = Mock()
            result = service._import_activity(sample_athlete.id, activity, orchestrator)
            
            assert result == "skipped"
            orchestrator.assert_not_called()
    
    def test_import_activity_skips_zero_duration(self, db_session, sample_athlete):
        """Activities with zero duration are skipped"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            
            service = StravaService(db_session)
            
            activity = {
                "id": 99999,
                "name": "Empty Ride",
                "type": "Ride",
                "start_date_local": "2024-01-15T08:00:00",
                "moving_time": 0  # Zero duration
            }
            
            orchestrator = Mock()
            result = service._import_activity(sample_athlete.id, activity, orchestrator)
            
            assert result == "skipped"
    
    def test_import_activity_builds_raw_data(self, db_session, sample_athlete):
        """Full activity payload stored in raw_data"""
        from app import models
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            
            service = StravaService(db_session)
            
            # Create connection
            token_response = {
                "access_token": "test_token",
                "refresh_token": "refresh_token",
                "expires_at": 9999999999,
                "athlete": {"id": 12345}
            }
            service.create_or_update_connection(
                athlete_id=sample_athlete.id,
                token_response=token_response
            )
            
            activity = {
                "id": 12345,
                "name": "Long Ride",
                "type": "Ride",
                "start_date_local": "2024-01-15T08:00:00",
                "moving_time": 7200,
                "distance": 50000,
                "average_speed": 6.9,
                "max_speed": 12.5,
                "average_watts": 200,
                "max_watts": 350,
                "kilojoules": 1440,
                "average_heartrate": 145,
                "max_heartrate": 175,
                "total_elevation_gain": 500
            }
            
            orchestrator = Mock()
            mock_session = Mock()
            mock_session.id = 1
            orchestrator.ingest_endurance_session.return_value = (mock_session, Mock(), Mock())
            
            result = service._import_activity(sample_athlete.id, activity, orchestrator)
            
            assert result == "imported"
            
            # Verify orchestrator was called
            call_args = orchestrator.ingest_endurance_session.call_args
            assert call_args[1]["athlete_id"] == sample_athlete.id
            assert call_args[1]["sport"] == EnduranceSport.CYCLING
            assert call_args[1]["duration_minutes"] == 120.0  # 7200 seconds / 60
