"""Account-token verification and the stateless per-user engine endpoints.

Tokens are signed here with a throwaway key and verified against an in-process
key set: this proves our verification logic, not the live Supabase project."""
import json
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app import auth_supabase
from app.auth_supabase import JWKSCache, RateLimiter, verify_token
from app.config import settings

USER = "3f0c1a52-8f0e-4c0a-9a53-0f6f4d1b2a11"
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



PLAN = {"asOfDate": "2026-11-15", "sessions": [], "priority": "balans", "availableDates": ["2026-11-16", "2026-11-17", "2026-11-19"],
        "planSessions": [{"label": "benen", "kind": "strength_lower", "workSets": 12, "key": True},
                         {"label": "tempo", "kind": "endurance", "minutes": 60, "relativeIntensity": 0.85}]}


def test_plan_endpoint_needs_a_session_and_returns_ranked_options(client, keys):
    assert client.post("/v3/engine/plan", json=PLAN).status_code == 401
    response = client.post("/v3/engine/plan", json=PLAN, headers=auth(keys()))
    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "exhaustive" and len(body["options"]) == 3
    assert body["basis"]["strength"] == "group_level_priors_only" and "not_validated_on_real_athletes" in body["limitations"]
    past = client.post("/v3/engine/plan", json={**PLAN, "availableDates": ["2026-11-15"]}, headers=auth(keys()))
    assert past.status_code == 422 and "after asOfDate" in past.json()["detail"]["message"]
    empty = client.post("/v3/engine/plan", json={**PLAN, "planSessions": [{"label": "x", "kind": "strength_lower"}]}, headers=auth(keys()))
    assert empty.status_code == 422


def test_oversized_and_malformed_bodies_are_refused_before_any_calculation(client, keys):
    from app import api_v3
    huge = b"{" + b" " * (api_v3.MAX_ENGINE_BODY + 10) + b"}"
    assert client.post("/v3/engine/evaluate", content=huge, headers={**auth(keys()), "Content-Type": "application/json"}).status_code == 413
    assert client.post("/v3/engine/evaluate", content=b"not json", headers=auth(keys())).status_code == 422
    impossible = client.post("/v3/engine/evaluate", json={"asOfDate": "2026-02-30"}, headers=auth(keys()))
    assert impossible.status_code == 422 and impossible.json()["detail"]["fields"] == ["asOfDate"]


def test_engine_calls_are_rate_limited_per_user(client, keys, monkeypatch):
    from app import api_v3
    monkeypatch.setattr(api_v3, "engine_limit", RateLimiter(limit=2, window_seconds=60))
    codes = [client.post("/v3/engine/evaluate", json={"asOfDate": "2026-11-12"}, headers=auth(keys())).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    other = keys(sub="9b0d7e10-1111-4222-8333-444455556666")
    assert client.post("/v3/engine/evaluate", json={"asOfDate": "2026-11-12"}, headers=auth(other)).status_code == 200


def test_cors_lets_the_pages_origin_send_the_authorization_header(client):
    origin = settings.cors_origins[0]
    response = client.options("/v3/engine/evaluate", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                                              "Access-Control-Request-Headers": "authorization,content-type"})
    assert response.status_code == 200 and "authorization" in response.headers["access-control-allow-headers"].lower()
    foreign = client.options("/v3/engine/evaluate", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
                                                             "Access-Control-Request-Headers": "authorization"})
    assert "access-control-allow-origin" not in foreign.headers


def test_request_built_by_the_webapp_is_accepted_and_its_context_is_used(client, keys):
    """The fixture is produced by the TypeScript client (webapp/tests/engine.test.tsx pins it)."""
    request = json.loads((FIXTURES / "client_request_v1.json").read_text())
    response = client.post("/v3/engine/evaluate", json=request, headers=auth(keys()))
    assert response.status_code == 200
    body = response.json()
    flag = next(f for f in body["concurrent"] if f["date"] == "2026-11-10")
    assert flag["code"] == "explosive_work_within_3h_of_endurance" and flag["gap_hours"] == 1.5 and flag["order"] == "endurance_first"
    assert flag["lower_body_strength_work"] is True
    squat = next(b for b in body["strength"] if b["exercise"] == "back_squat")
    assert squat["velocity"][0]["metric"] == "mean_concentric" and squat["velocity"][0]["device"] == "encoder-1"
    data = body["concurrent_model"]["data"]
    assert data["sessions_without_start_time"] == 1 and data["strength_sets_region_unknown"] == 0
    assert data["endurance_dose_sources"] == {"declared_intensity_assumed_scale": 1, "measured_power": 1}
    assert body["endurance"]["reference"]["source"] == "user_entered_threshold_not_cp"


def test_engine_api_is_reachable_in_the_hosted_production_layout_without_the_admin_key(keys, tmp_path, monkeypatch):
    from app.hosted import create_hosted_app
    (tmp_path / "index.html").write_text("<!doctype html><title>ct</title>")
    monkeypatch.setattr(settings, "require_api_key", True)
    with TestClient(create_hosted_app(tmp_path)) as hosted:
        assert hosted.get("/v3/engine/version").json()["accounts_configured"] is True
        assert hosted.post("/v3/engine/evaluate", json={"asOfDate": "2026-11-12"}, headers=auth(keys())).status_code == 200
        assert hosted.post("/v3/engine/evaluate", json={"asOfDate": "2026-11-12"}).status_code == 401
        assert hosted.get("/athletes").status_code in (401, 403)          # the research API stays behind the admin key


def test_planner_request_built_by_the_webapp_is_accepted_and_keeps_the_key_session_fresh(client, keys):
    """Fixture produced by the TypeScript client; webapp/tests/engine.test.tsx pins it."""
    request = json.loads((FIXTURES / "client_plan_request_v1.json").read_text())
    response = client.post("/v3/engine/plan", json=request, headers=auth(keys()))
    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "exhaustive" and body["arrangements_evaluated"] == 6 and body["priority"] == "balans"
    best = body["options"][0]["sessions"]
    assert sorted(s["label"] for s in best) == ["2026-11-11", "2026-11-12", "2026-11-14"]
    assert sorted(s["start"][:10] for s in best) == ["2026-11-11", "2026-11-12", "2026-11-14"]        # same days, another order at most
    legs = next(s for s in best if s["label"] == "2026-11-11")
    assert legs["key"] is True and legs["low_pct"] <= legs["expected_fatigue_effect_pct"] <= legs["high_pct"] <= 5
    # The session of 10 November (ride, then explosive work 1.5 h later) is history and still shapes the start state.
    assert body["data"]["sessions"] == 3 and body["difference_best_to_worst_pct"] is not None
