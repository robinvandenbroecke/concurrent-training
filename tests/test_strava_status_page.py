"""
Tests for Strava status page HTML rendering
"""
import pytest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient


class TestStravaStatusPage:
    """Test HTML status page rendering"""
    
    def test_status_page_disconnected(self, client, db_session):
        """Disconnected page renders connect button"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            response = client.get("/integrations/strava?athlete_id=1")
            
            assert response.status_code == 200
            content = response.text
            
            # Should show disconnected state
            assert "Not Connected" in content or "❌" in content
            assert "Connect with Strava" in content or "Connect" in content
            
            # Should have link to login endpoint
            assert "/integrations/strava/login" in content
    
    def test_status_page_connected(self, client, db_session, sample_athlete):
        """Connected page renders sync/disconnect info"""
        from app.integrations.strava import StravaService
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Create connection first
            service = StravaService(db_session)
            token_response = {
                "access_token": "test_access",
                "refresh_token": "test_refresh",
                "expires_at": 9999999999,
                "athlete": {"id": 12345, "firstname": "Test", "lastname": "User"}
            }
            service.create_or_update_connection(
                athlete_id=sample_athlete.id,
                token_response=token_response
            )
            
            response = client.get(f"/integrations/strava?athlete_id={sample_athlete.id}")
            
            assert response.status_code == 200
            content = response.text
            
            # Should show connected state
            assert "Connected" in content or "✅" in content
            assert "Test User" in content
            
            # Should have sync and disconnect buttons
            assert "Sync Last 30 Days" in content or "sync" in content.lower()
            assert "Disconnect" in content
            
            # Should have forms for POST actions
            assert "method=\"post\"" in content
    
    def test_status_page_not_configured(self, client, db_session):
        """Status page shows error when OAuth not configured"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = ""
            mock_settings.strava_client_secret = ""
            
            response = client.get("/integrations/strava?athlete_id=1")
            
            assert response.status_code == 200
            content = response.text
            
            assert "not configured" in content.lower() or "STRAVA_CLIENT_ID" in content
    
    def test_login_redirect(self, client, db_session):
        """Login endpoint redirects to Strava authorize URL"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            mock_settings.strava_redirect_uri = "http://localhost:8000/callback"
            mock_settings.strava_scopes = "read,activity:read_all"
            mock_settings.admin_api_key = "test_key"
            
            response = client.get("/integrations/strava/login?athlete_id=42", follow_redirects=False)
            
            assert response.status_code == 307  # Redirect
            location = response.headers["location"]
            
            assert "https://www.strava.com/oauth/authorize" in location
            assert "client_id=test_client_id" in location
            assert "state=42%3A" in location  # URL encoded state
    
    def test_login_not_configured(self, client, db_session):
        """Login returns error when OAuth not configured"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = ""
            mock_settings.strava_client_secret = ""
            
            response = client.get("/integrations/strava/login?athlete_id=1")
            
            assert response.status_code == 503
            assert "not configured" in response.json()["detail"].lower()
    
    def test_sync_endpoint(self, client, db_session, sample_athlete):
        """Sync endpoint returns summary JSON"""
        from app.integrations.strava import StravaService
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Mock sync_activities at the service level
            with patch.object(StravaService, "sync_activities") as mock_sync:
                mock_sync.return_value = {
                    "imported": 5,
                    "skipped": 2,
                    "errors": [],
                    "total_fetched": 7,
                    "synced_at": "2024-01-15T12:00:00"
                }
                
                # Create connection first so the service thinks we're connected
                service = StravaService(db_session)
                token_response = {
                    "access_token": "test_access",
                    "refresh_token": "test_refresh",
                    "expires_at": 9999999999,
                    "athlete": {"id": 12345}
                }
                service.create_or_update_connection(
                    athlete_id=sample_athlete.id,
                    token_response=token_response
                )
                
                response = client.post(f"/integrations/strava/sync?athlete_id={sample_athlete.id}&days_back=30")
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["status"] == "success"
                assert data["imported"] == 5
                assert data["skipped"] == 2
    
    def test_disconnect_endpoint(self, client, db_session, sample_athlete):
        """Disconnect endpoint removes connection"""
        from app.integrations.strava import StravaService
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Create connection
            service = StravaService(db_session)
            token_response = {
                "access_token": "test_access",
                "refresh_token": "test_refresh",
                "expires_at": 9999999999,
                "athlete": {"id": 12345}
            }
            service.create_or_update_connection(
                athlete_id=sample_athlete.id,
                token_response=token_response
            )
            
            # Disconnect
            response = client.post(f"/integrations/strava/disconnect?athlete_id={sample_athlete.id}")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "disconnected"
            assert data["athlete_id"] == sample_athlete.id
            
            # Verify connection is inactive
            connection = service.get_connection(sample_athlete.id)
            assert connection.is_active is False
    
    def test_disconnect_not_connected(self, client, db_session, sample_athlete):
        """Disconnect when not connected returns 404"""
        response = client.post(f"/integrations/strava/disconnect?athlete_id={sample_athlete.id}")
        
        assert response.status_code == 404
        # Check that the error message mentions connection not found
        detail = response.json()["detail"].lower()
        assert "no strava connection" in detail or "not found" in detail
