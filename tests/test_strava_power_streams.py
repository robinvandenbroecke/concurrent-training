from unittest.mock import Mock, patch

from app.integrations.secure_strava import StravaService


def test_fetch_power_stream_returns_timestamped_points():
    service = StravaService(db=None)
    service._sync_access_token = "token"
    response = Mock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "watts": {"data": [180, 0, 220]},
        "time": {"data": [0, 1, 2]},
    }
    with patch("app.integrations.secure_strava.httpx.get", return_value=response) as get:
        points = service._fetch_power_stream(123)
    assert points == [
        {"power": 180.0, "timestamp": 0},
        {"power": 220.0, "timestamp": 2},
    ]
    assert get.call_args.kwargs["params"]["keys"] == "watts,time"


def test_fetch_power_stream_falls_back_cleanly_without_token():
    service = StravaService(db=None)
    assert service._fetch_power_stream(123) is None
