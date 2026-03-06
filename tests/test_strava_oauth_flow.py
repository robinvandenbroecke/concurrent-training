"""
Tests for Strava OAuth flow
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from app.integrations.strava import StravaService, StravaError, StravaAuthError, StravaRateLimitError


class TestStravaOAuthFlow:
    """Test OAuth authentication flow"""
    
    def test_build_authorize_url(self, db_session):
        """Login endpoint generates correct authorization URL with expected params"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            mock_settings.strava_redirect_uri = "http://localhost:8000/callback"
            mock_settings.strava_scopes = "read,activity:read_all"
            mock_settings.admin_api_key = "test_key"
            
            service = StravaService(db_session)
            url = service.build_authorize_url(athlete_id=42)
            
            assert "https://www.strava.com/oauth/authorize" in url
            assert "client_id=test_client_id" in url
            assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fcallback" in url
            assert "response_type=code" in url
            assert "approval_prompt=auto" in url
            assert "scope=read%2Cactivity%3Aread_all" in url
            assert "state=42%3A" in url  # State starts with athlete_id
    
    def test_build_authorize_url_not_configured(self, db_session):
        """Building URL when not configured raises error"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = ""
            mock_settings.strava_client_secret = ""
            
            service = StravaService(db_session)
            with pytest.raises(StravaAuthError, match="not configured"):
                service.build_authorize_url(athlete_id=42)
    
    @patch("app.integrations.strava.httpx.post")
    def test_exchange_code_for_token(self, mock_post, db_session):
        """Callback exchanges code and returns tokens"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Mock response
            mock_response = Mock()
            mock_response.json.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_at": 1234567890,
                "athlete": {"id": 12345, "firstname": "John", "lastname": "Doe"}
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            service = StravaService(db_session)
            result = service.exchange_code_for_token("test_code")
            
            assert result["access_token"] == "test_access_token"
            assert result["refresh_token"] == "test_refresh_token"
            assert result["expires_at"] == 1234567890
            assert result["athlete"]["id"] == 12345
            
            # Verify call
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "https://www.strava.com/oauth/token"
            assert call_args[1]["data"]["code"] == "test_code"
    
    @patch("app.integrations.strava.httpx.post")
    def test_exchange_code_invalid_code(self, mock_post, db_session):
        """Invalid authorization code raises auth error"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Mock 401 response
            from httpx import HTTPStatusError, Response
            mock_response = Mock(spec=Response)
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_post.return_value = mock_response
            mock_post.side_effect = HTTPStatusError(
                "401 Unauthorized",
                request=Mock(),
                response=mock_response
            )
            
            service = StravaService(db_session)
            with pytest.raises(StravaAuthError, match="Invalid authorization"):
                service.exchange_code_for_token("invalid_code")


class TestStravaTokenRefresh:
    """Test token refresh functionality"""
    
    @patch("app.integrations.strava.httpx.post")
    def test_refresh_access_token(self, mock_post, db_session):
        """Refresh path updates refresh_token and access_token"""
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Mock response with new tokens
            mock_response = Mock()
            mock_response.json.return_value = {
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",  # Strava may rotate refresh tokens
                "expires_at": 9999999999
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            service = StravaService(db_session)
            result = service.refresh_access_token("old_refresh_token")
            
            assert result["access_token"] == "new_access_token"
            assert result["refresh_token"] == "new_refresh_token"
            
            # Verify grant_type
            call_args = mock_post.call_args
            assert call_args[1]["data"]["grant_type"] == "refresh_token"
            assert call_args[1]["data"]["refresh_token"] == "old_refresh_token"
    
    def test_ensure_valid_token_not_expired(self, db_session):
        """Token not near expiry - no refresh needed"""
        import time
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            service = StravaService(db_session)
            
            # Create mock connection with far-future expiry
            mock_connection = Mock()
            mock_connection.expires_at = int(time.time()) + 7200  # 2 hours from now
            mock_connection.access_token = "valid_token"
            
            token = service.ensure_valid_token(mock_connection)
            
            assert token == "valid_token"
            # DB commit should not be called (no refresh)
            mock_connection.assert_not_called
    
    @patch("app.integrations.strava.httpx.post")
    def test_ensure_valid_token_expired(self, mock_post, db_session):
        """Token near expiry - refresh triggered"""
        import time
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            mock_settings.strava_client_secret = "test_secret"
            
            # Mock refresh response
            mock_response = Mock()
            mock_response.json.return_value = {
                "access_token": "refreshed_token",
                "refresh_token": "new_refresh_token",
                "expires_at": int(time.time()) + 21600
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            service = StravaService(db_session)
            
            # Create mock connection with near-expiry
            mock_connection = Mock()
            mock_connection.expires_at = int(time.time()) + 1800  # 30 min from now
            mock_connection.refresh_token = "old_refresh_token"
            mock_connection.access_token = "old_token"
            
            token = service.ensure_valid_token(mock_connection)
            
            assert token == "refreshed_token"
            mock_post.assert_called_once()


class TestStravaConnectionCRUD:
    """Test connection creation and management"""
    
    def test_create_connection(self, db_session, sample_athlete):
        """Create new Strava connection"""
        from app import models
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            
            service = StravaService(db_session)
            
            token_response = {
                "access_token": "access123",
                "refresh_token": "refresh456",
                "expires_at": 1234567890,
                "athlete": {"id": 99999, "firstname": "Jane", "lastname": "Smith"}
            }
            
            connection = service.create_or_update_connection(
                athlete_id=sample_athlete.id,
                token_response=token_response,
                accepted_scopes="read,activity:read_all"
            )
            
            assert connection.athlete_id == sample_athlete.id
            assert connection.strava_athlete_id == "99999"
            assert connection.strava_athlete_name == "Jane Smith"
            assert connection.access_token == "access123"
            assert connection.refresh_token == "refresh456"
            assert connection.accepted_scopes == "read,activity:read_all"
            assert connection.is_active is True
    
    def test_update_existing_connection(self, db_session, sample_athlete):
        """Update existing connection with new tokens"""
        from app import models
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            
            service = StravaService(db_session)
            
            # Create initial connection
            token_response = {
                "access_token": "old_access",
                "refresh_token": "old_refresh",
                "expires_at": 1000000000,
                "athlete": {"id": 11111, "firstname": "Old", "lastname": "Name"}
            }
            
            service.create_or_update_connection(
                athlete_id=sample_athlete.id,
                token_response=token_response
            )
            
            # Update with new tokens
            new_token_response = {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_at": 2000000000,
                "athlete": {"id": 22222, "firstname": "New", "lastname": "Name"}
            }
            
            connection = service.create_or_update_connection(
                athlete_id=sample_athlete.id,
                token_response=new_token_response
            )
            
            assert connection.access_token == "new_access"
            assert connection.strava_athlete_id == "22222"
            
            # Should still be only one connection
            count = db_session.query(models.StravaConnection).filter(
                models.StravaConnection.athlete_id == sample_athlete.id
            ).count()
            assert count == 1
    
    def test_disconnect(self, db_session, sample_athlete):
        """Disconnect removes tokens and marks inactive"""
        from app import models
        
        with patch("app.integrations.strava.settings") as mock_settings:
            mock_settings.strava_client_id = "test_client_id"
            
            service = StravaService(db_session)
            
            # Create connection
            token_response = {
                "access_token": "access123",
                "refresh_token": "refresh456",
                "expires_at": 1234567890,
                "athlete": {"id": 99999}
            }
            
            service.create_or_update_connection(
                athlete_id=sample_athlete.id,
                token_response=token_response
            )
            
            # Disconnect
            result = service.disconnect(sample_athlete.id)
            
            assert result is True
            
            connection = service.get_connection(sample_athlete.id)
            assert connection.is_active is False
            assert connection.access_token == ""
            assert connection.refresh_token == ""
    
    def test_disconnect_not_connected(self, db_session, sample_athlete):
        """Disconnect when not connected returns False"""
        service = StravaService(db_session)
        
        result = service.disconnect(sample_athlete.id)
        assert result is False
