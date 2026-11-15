"""Account-token verification, the stateless engine endpoint, activity files and
provider links. All provider traffic is SIMULATED with an in-process transport:
these tests prove our request/response handling, not that Garmin or Wahoo
accept the integration."""
import base64
import io
import json
import struct
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app import auth_supabase, models
from app.auth_supabase import JWKSCache, RateLimiter, verify_token
from app.config import settings
from app.integrations.providers import ProviderError, ProviderService
from app.science.activity_files import ActivityFileError, parse_activity_file

USER = "3f0c1a52-8f0e-4c0a-9a53-0f6f4d1b2a11"
OTHER = "9b0d7e10-1111-4222-8333-444455556666"
ISSUER = "https://example-project.supabase.co/auth/v1"
FIXTURES = Path(__file__).resolve().parents[1] / "webapp" / "tests" / "fixtures" / "contracts"


@pytest.fixture()
def keys(monkeypatch):
    private = ec.generate_private_key(ec.SECP256R1())
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    jwk.update({"kid": "test-key", "alg": "ES256", "use": "sig"})
    fetches = []
    cache = JWKSCache("unused", fetch=lambda url: fetches.append(url) or {"keys": [jwk]})
    monkeypatch.setattr(settings, "supabase_url", "https://example-project.supabase.co")
    monkeypatch.setattr(settings, "supabase_jwt_secret", "")
    monkeypatch.setattr(auth_supabase, "_cache", cache)

    def token(sub=USER, role="authenticated", exp=600, aud="authenticated", iss=ISSUER, kid="test-key", key=private, **extra):
        claims = {"sub": sub, "role": role, "aud": aud, "iss": iss, "exp": int(time.time()) + exp, **extra}
        return jwt.encode(claims, key, algorithm="ES256", headers={"kid": kid})
    token.fetches = fetches
    return token


@pytest.fixture()
def client(keys):
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── authentication ─────────────────────────────────────────────────────────

def test_valid_user_token_is_accepted_and_returns_the_subject(keys):
    assert verify_token(keys()) == USER


@pytest.mark.parametrize("change", [
    {"exp": -120}, {"aud": "other"}, {"iss": "https://evil.example/auth/v1"}, {"role": "anon"},
    {"role": "service_role"}, {"sub": "not-a-uuid"}, {"kid": "unknown"}, {"is_anonymous": True},
])
def test_wrong_expired_or_non_user_tokens_are_refused(keys, change):
    with pytest.raises((jwt.InvalidTokenError, ValueError)):
        verify_token(keys(**change))


def test_token_signed_by_another_key_or_with_alg_none_or_hs256_is_refused(keys):
    with pytest.raises(jwt.InvalidTokenError):
        verify_token(keys(key=ec.generate_private_key(ec.SECP256R1())))
    unsigned = jwt.encode({"sub": USER, "role": "authenticated", "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 60}, None, algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        verify_token(unsigned)
    # No shared secret configured: an HS256 token (e.g. signed with a public value) is never accepted.
    forged = jwt.encode({"sub": USER, "role": "authenticated", "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 60}, "x" * 40, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        verify_token(forged)


def test_unknown_key_ids_cannot_force_unbounded_jwks_fetches(keys):
    for _ in range(5):
        with pytest.raises(jwt.InvalidTokenError):
            verify_token(keys(kid="rotating-attack"))
    assert len(keys.fetches) == 1


def test_rate_limiter_is_per_user_and_recovers():
    limiter = RateLimiter(limit=2, window_seconds=10)
    limiter.check("a", now=0); limiter.check("a", now=1); limiter.check("b", now=1)
    with pytest.raises(Exception):
        limiter.check("a", now=2)
    limiter.check("a", now=11.5)


def test_engine_endpoint_requires_a_user_session_and_never_the_admin_key(client, keys):
    request = json.loads((FIXTURES / "engine_v1_request.json").read_text())
    assert client.post("/v3/engine/evaluate", json=request).status_code == 401
    assert client.post("/v3/engine/evaluate", json=request, headers={"X-API-Key": settings.admin_api_key}).status_code == 401
    assert client.post("/v3/engine/evaluate", json=request, headers=auth(keys(role="anon"))).status_code == 401
    response = client.post("/v3/engine/evaluate", json=request, headers=auth(keys()))
    assert response.status_code == 200
    assert response.json() == json.loads((FIXTURES / "engine_v1_response.json").read_text())


def test_engine_endpoint_reports_fields_not_data_and_checks_the_contract_version(client, keys):
    bad = {"asOfDate": "2026-11-12", "sessions": [{"id": "x", "date": "2026-11-12", "type": "kracht",
           "exercises": [{"sets": [{"setNum": 1, "weight": 100, "completedReps": 1, "velocities": [7.77]}]}]}]}
    response = client.post("/v3/engine/evaluate", json=bad, headers=auth(keys()))
    assert response.status_code == 422 and "7.77" not in response.text
    assert any("velocities" in field for field in response.json()["detail"]["fields"])
    future = client.post("/v3/engine/evaluate", json={"contractVersion": "99", "asOfDate": "2026-11-12"}, headers=auth(keys()))
    assert future.status_code == 409 and future.json()["detail"]["supported"] == "1"


def test_engine_is_unavailable_rather_than_open_when_accounts_are_not_configured(client, keys, monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    assert client.post("/v3/engine/evaluate", json={"asOfDate": "2026-11-12"}, headers=auth(keys())).status_code == 503
    assert client.get("/v3/engine/version").json()["accounts_configured"] is False


# ── activity files (synthetic fixtures built here; not recordings from a real device) ──

def _crc(data: bytes) -> int:
    table = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401, 0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]
    crc = 0
    for byte in data:
        for nibble in (byte & 0xF, byte >> 4):
            tmp = table[crc & 0xF]
            crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ table[nibble]
    return crc


def make_fit(records, sport=2):
    """Minimal FIT activity: file_id, sport and record messages (public FIT profile numbers)."""
    epoch = datetime(1989, 12, 31, tzinfo=timezone.utc)
    body = b""
    body += bytes([0x40, 0, 0]) + struct.pack("<H", 0) + bytes([2, 0, 1, 0x00, 1, 2, 0x84]) + bytes([0x00, 4]) + struct.pack("<H", 32)
    body += bytes([0x41, 0, 0]) + struct.pack("<H", 12) + bytes([1, 0, 1, 0x00]) + bytes([0x01, sport])
    body += bytes([0x42, 0, 0]) + struct.pack("<H", 20) + bytes([4, 253, 4, 0x86, 7, 2, 0x84, 3, 1, 0x02, 4, 1, 0x02])
    for when, power, hr, cadence in records:
        body += bytes([0x02]) + struct.pack("<IHBB", int((when - epoch).total_seconds()),
                                            0xFFFF if power is None else power, 0xFF if hr is None else hr, 0xFF if cadence is None else cadence)
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(body), b".FIT")
    header += struct.pack("<H", _crc(header))
    return header + body + struct.pack("<H", _crc(header + body))


START = datetime(2026, 11, 10, 15, 30, tzinfo=timezone.utc)


def test_fit_file_keeps_units_gaps_and_zero_power():
    records = [(START + timedelta(seconds=s), p, 140, 90) for s, p in ((0, 200), (1, 0), (2, None), (5, 250))]
    parsed = parse_activity_file(make_fit(records))
    assert parsed["format"] == "fit" and parsed["sport"] == "cycling" and parsed["elapsed_seconds"] == 5
    assert parsed["start_time"] == "2026-11-10T15:30:00Z" and parsed["device"]["manufacturer"] == "wahoo_fitness"
    power = parsed["channels"]["power"]
    assert power["unit"] == "W" and power["values"] == [200, 0, None, None, None, 250]     # coasting is 0, a gap is null
    assert power["samples"] == 3 and power["missing_seconds"] == 3 and power["mean_recorded"] == 150.0
    assert parsed["channels"]["heart_rate"]["values"][2] == 140


def test_fit_without_power_reports_no_power_channel_and_corrupt_files_are_refused():
    parsed = parse_activity_file(make_fit([(START, None, 120, None), (START + timedelta(seconds=3), None, 125, None)], sport=1))
    assert parsed["sport"] == "running" and "power" not in parsed["channels"] and "cadence" not in parsed["channels"]
    damaged = bytearray(make_fit([(START, 100, 100, 80), (START + timedelta(seconds=1), 100, 100, 80)]))
    damaged[30] ^= 0xFF
    for bad in (bytes(damaged), b"", b"hello world this is not an activity", make_fit([(START, 1, 1, 1)])):
        with pytest.raises(ActivityFileError):
            parse_activity_file(bad)


def test_tcx_and_gpx_are_parsed_without_entity_expansion_or_invented_power():
    tcx = b"""<?xml version="1.0"?><TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
      xmlns:x="http://www.garmin.com/xmlschemas/ActivityExtension/v2"><Activities><Activity Sport="Biking"><Lap><Track>
      <Trackpoint><Time>2026-11-10T15:30:00Z</Time><HeartRateBpm><Value>130</Value></HeartRateBpm><Cadence>88</Cadence>
        <Extensions><x:TPX><x:Watts>210</x:Watts></x:TPX></Extensions></Trackpoint>
      <Trackpoint><Time>2026-11-10T15:30:02Z</Time><Extensions><x:TPX><x:Watts>0</x:Watts></x:TPX></Extensions></Trackpoint>
      </Track></Lap></Activity></Activities></TrainingCenterDatabase>"""
    parsed = parse_activity_file(tcx)
    assert parsed["format"] == "tcx" and parsed["sport"] == "cycling" and parsed["channels"]["power"]["values"] == [210, None, 0]
    gpx = b"""<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><type>running</type><trkseg>
      <trkpt lat="51" lon="4"><time>2026-11-10T15:30:00+01:00</time></trkpt>
      <trkpt lat="51" lon="4"><time>2026-11-10T15:30:04+01:00</time></trkpt></trkseg></trk></gpx>"""
    plain = parse_activity_file(gpx)
    assert plain["start_time"] == "2026-11-10T14:30:00Z" and plain["channels"] == {}      # speed is not turned into power
    bomb = b"""<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]><gpx><trk><type>&b;</type></trk></gpx>"""
    with pytest.raises(ActivityFileError):
        parse_activity_file(bomb)


def test_import_endpoint_parses_for_the_signed_in_user_and_stores_nothing(client, keys):
    fit = make_fit([(START + timedelta(seconds=s), 180, 130, 85) for s in range(4)])
    assert client.post("/v3/import/activity-file", content=fit).status_code == 401
    response = client.post("/v3/import/activity-file", content=fit, headers=auth(keys()))
    assert response.status_code == 200 and response.json()["provenance"]["provider"] == "file"
    assert client.post("/v3/import/activity-file", content=b"nope", headers=auth(keys())).status_code == 422


# ── provider links (simulated provider) ────────────────────────────────────

class FakeWahoo:
    def __init__(self):
        self.refreshes, self.revoked, self.seen_verifier, self.fail_refresh = 0, False, None, False
        self.workouts = [{"id": 11, "starts": "2026-11-01T08:00:00.000Z"}, {"id": 12, "starts": "2026-11-05T08:00:00.000Z"},
                         {"id": 13, "starts": "2026-11-08T08:00:00.000Z"}]
        self.fit = make_fit([(START + timedelta(seconds=s), 200, 130, 85) for s in range(3)])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "cdn.wahooligan.com":
            assert "authorization" not in request.headers
            return httpx.Response(200, content=self.fit)
        if path == "/oauth/token":
            form = dict(item.split("=") for item in request.content.decode().split("&"))
            if form["grant_type"] == "authorization_code":
                self.seen_verifier = form["code_verifier"]
                return httpx.Response(200, json={"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 7200})
            self.refreshes += 1
            if self.fail_refresh:
                return httpx.Response(401, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": f"access-{self.refreshes + 1}", "refresh_token": "refresh-2", "expires_in": 7200})
        assert request.headers["authorization"].startswith("Bearer access-")
        if path == "/v1/user":
            return httpx.Response(200, json={"id": 777})
        if path == "/v1/workouts":
            return httpx.Response(200, json={"workouts": self.workouts})
        if path.startswith("/v1/workouts/"):
            return httpx.Response(200, json={"id": int(path.rsplit("/", 1)[1]), "workout_summary": {"file": {"url": "https://cdn.wahooligan.com/x.fit"}}})
        if path == "/v1/permissions" and request.method == "DELETE":
            self.revoked = True
            return httpx.Response(204)
        return httpx.Response(404)


@pytest.fixture()
def provider_env(monkeypatch):
    from app.database import Base, SessionLocal, engine
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "provider_token_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "wahoo_client_id", "client")
    monkeypatch.setattr(settings, "wahoo_client_secret", "secret")
    monkeypatch.setattr(settings, "provider_redirect_base", "https://api.example.test")
    db = SessionLocal()
    for table in (models.ProviderConnection, models.ProviderOAuthState):
        db.query(table).delete()
    db.commit()
    fake = FakeWahoo()
    yield ProviderService(db, httpx.Client(transport=httpx.MockTransport(fake))), fake, db
    db.close()


def link(service):
    url = httpx.URL(service.start(USER, "wahoo"))
    return url.params["state"], url


def test_oauth_link_uses_pkce_single_use_state_and_encrypted_storage(provider_env):
    service, fake, db = provider_env
    state, url = link(service)
    assert url.host == "api.wahooligan.com" and url.params["code_challenge_method"] == "S256"
    assert url.params["scope"] == "user_read workouts_read offline_data"
    assert url.params["redirect_uri"] == "https://api.example.test/v3/providers/wahoo/callback"
    assert service.finish("wahoo", "code", state) == USER
    challenge = base64.urlsafe_b64encode(__import__("hashlib").sha256(fake.seen_verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == url.params["code_challenge"]
    row = db.query(models.ProviderConnection).one()
    assert row.user_id == USER and row.provider_user_id == "777"
    assert "access-1" not in row.access_token_enc and "refresh-1" not in row.refresh_token_enc
    with pytest.raises(ProviderError):                       # replay of the same redirect
        service.finish("wahoo", "code", state)
    with pytest.raises(ProviderError):                       # a state nobody issued
        service.finish("wahoo", "code", "forged-state")
    status = service.status(USER, "wahoo")
    assert status["connected"] and "access" not in json.dumps(status)
    assert service.status(OTHER, "wahoo")["connected"] is False


def test_incremental_sync_is_idempotent_until_acknowledged_and_never_repeats_after(provider_env):
    service, fake, _ = provider_env
    service.finish("wahoo", "code", link(service)[0])
    first = service.sync(USER, "wahoo")
    assert [a["external_id"] for a in first["activities"]] == ["11", "12", "13"]
    assert first["activities"][0]["activity"]["provenance"] == {"provider": "wahoo", "external_id": "11", "route": "oauth"}
    assert service.sync(USER, "wahoo")["activities"][0]["external_id"] == "11"      # not acknowledged: same batch again
    service.acknowledge(USER, "wahoo", first["ack_cursor"])
    assert service.sync(USER, "wahoo") == {"activities": [], "skipped": [], "more": False, "ack_cursor": None}
    service.acknowledge(USER, "wahoo", "2026-01-01T00:00:00Z")                      # a cursor never moves backwards
    assert service.sync(USER, "wahoo")["activities"] == []
    fake.workouts.append({"id": 14, "starts": "2026-11-12T08:00:00.000Z"})
    assert [a["external_id"] for a in service.sync(USER, "wahoo")["activities"]] == ["14"]
    with pytest.raises(ProviderError):
        service.sync(OTHER, "wahoo")                                                # another user has no link


def test_expired_token_is_refreshed_and_a_revoked_link_asks_for_renewal(provider_env):
    service, fake, db = provider_env
    service.finish("wahoo", "code", link(service)[0])
    row = db.query(models.ProviderConnection).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    service.sync(USER, "wahoo")
    assert fake.refreshes == 1
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    fake.fail_refresh = True
    with pytest.raises(ProviderError) as error:
        service.sync(USER, "wahoo")
    assert error.value.status == 409 and service.status(USER, "wahoo")["needs_renewal"] is True
    assert "access" not in str(error.value) and "invalid_grant" not in str(error.value)


def test_disconnect_revokes_at_the_provider_and_always_deletes_local_tokens(provider_env):
    service, fake, db = provider_env
    service.finish("wahoo", "code", link(service)[0])
    assert service.disconnect(USER, "wahoo") == {"removed": True, "revoked_at_provider": True, "manual_step": None}
    assert fake.revoked and db.query(models.ProviderConnection).count() == 0
    assert service.disconnect(USER, "wahoo")["removed"] is False


def test_file_downloads_are_restricted_to_the_providers_own_hosts(provider_env):
    service, _, _ = provider_env
    for url in ("http://cdn.wahooligan.com/a.fit", "https://evil.example/a.fit", "https://cdn.wahooligan.com.evil.example/a.fit"):
        with pytest.raises(ProviderError):
            service._download("wahoo", url, None)


def test_garmin_personal_key_is_verified_stored_encrypted_and_pulled_as_zip(provider_env):
    service, _, db = provider_env
    fit = make_fit([(START + timedelta(seconds=s), 150, 120, 80) for s in range(3)])
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("123_ACTIVITY.fit", fit)
    calls = []

    def garmin(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.headers.get("authorization", "")))
        assert request.url.host == "personal.connectapi.garmin.com"
        if request.url.path.endswith("/personal-api-key/token"):
            ok = request.headers["authorization"] == "ApiKey my-personal-key-0000000000"
            return httpx.Response(200, json={"access_token": "garmin-token", "expires_in": 86400}) if ok else httpx.Response(401)
        if request.url.path.endswith("/activities/search/activities"):
            return httpx.Response(200, json=[{"activityId": 123, "startTimeGMT": "2026-11-10 15:30:00"}])
        return httpx.Response(200, content=archive.getvalue())
    service.http = httpx.Client(transport=httpx.MockTransport(garmin))
    with pytest.raises(ProviderError):
        service.link_garmin_personal(USER, "wrong-key-000000000000000")
    assert db.query(models.ProviderConnection).count() == 0          # a refused key is not stored
    service.link_garmin_personal(USER, "my-personal-key-0000000000")
    row = db.query(models.ProviderConnection).one()
    assert row.mode == "personal_key" and "my-personal-key" not in row.refresh_token_enc
    result = service.sync(USER, "garmin")
    assert result["activities"][0]["activity"]["channels"]["power"]["values"] == [150, 150, 150]
    assert result["activities"][0]["activity"]["provenance"]["route"] == "personal_key"
    assert all(auth_header.startswith(("ApiKey ", "Bearer garmin-token")) for _, _, auth_header in calls)


def test_provider_endpoints_are_per_user_and_unconfigured_providers_say_so(client, keys, provider_env, monkeypatch):
    assert client.get("/v3/providers/wahoo/status").status_code == 401
    assert client.get("/v3/providers/strava/status", headers=auth(keys())).status_code == 404
    status = client.get("/v3/providers/garmin/status", headers=auth(keys())).json()
    assert status["connected"] is False and status["available"] == {"oauth": False, "personal_key": True}
    assert client.post("/v3/providers/garmin/connect", headers=auth(keys())).status_code == 503
    callback = client.get("/v3/providers/wahoo/callback?code=x&state=forged", follow_redirects=False)
    assert callback.status_code == 303 and callback.headers["location"].endswith("provider=wahoo&link=failed")
    assert client.post("/v3/providers/wahoo/webhook", json={"webhook_token": "x"}).status_code == 503
    monkeypatch.setattr(settings, "wahoo_webhook_token", "shared-webhook-token")
    assert client.post("/v3/providers/wahoo/webhook", json={"webhook_token": "wrong", "user": {"id": 777}}).status_code == 403
    assert client.post("/v3/providers/wahoo/webhook", json={"webhook_token": "shared-webhook-token", "user": {"id": 777}}).status_code == 200


def test_power_summary_is_exact_for_the_load_formula_and_mean_maximal_skips_gaps():
    watts = [300] * 60 + [None] * 5 + [100] * 120
    records = [(START + timedelta(seconds=i), w, None, None) for i, w in enumerate(watts) if w is not None]
    summary = parse_activity_file(make_fit(records))["power_summary"]
    assert summary["recorded_seconds"] == 180 and summary["missing_seconds"] == 5
    assert summary["sum_squares_w2s"] == 60 * 300 ** 2 + 120 * 100 ** 2
    assert summary["mean_maximal_w"]["60"] == 300.0 and summary["mean_maximal_w"]["5"] == 300.0
    assert "180" not in summary["mean_maximal_w"]                      # no 3-minute window without a gap
    from app.science.contract import EngineRequest
    from app.science.service import evaluate
    stream = {"sport": "cycling", "durationMinutes": 3, "intensityType": "easy", "power": {"sampleSeconds": 1, "watts": watts}}
    compact = {"sport": "cycling", "durationMinutes": 3, "intensityType": "easy",
               "powerSummary": {"recordedSeconds": 180, "missingSeconds": 5, "meanW": summary["mean_w"], "sumSquaresW2s": summary["sum_squares_w2s"]}}
    loads = [evaluate(EngineRequest.model_validate({"asOfDate": "2026-11-10", "endurance": {"thresholdPowerW": 250}, "sessions": [
        {"id": "a", "date": "2026-11-10", "type": "duur", "durationMinutes": 3, "enduranceResult": result}]}))["load"]["daily"][0]["endurance"][0]
        for result in (stream, compact)]
    assert loads[0] == loads[1] and loads[0]["missing_samples"] == 5
