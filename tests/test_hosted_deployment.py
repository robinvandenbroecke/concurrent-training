from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.config import settings
from app.database import get_db
from app.hosted import create_hosted_app
from deployment.serve import deployment_config


def valid_environ():
    return {
        "APP_ENV": "production",
        "ADMIN_API_KEY": "host-test-key-that-is-long-enough-for-tests",
        "DATABASE_URL": "postgresql://owner:p%40ss%25word@db.example.test/postgres?sslmode=require",
    }


def test_hosted_configuration_preserves_password_and_forces_private_schema():
    environ = valid_environ()
    environ["DATABASE_URL"] += "&options=-csearch_path%3Dpublic"
    url, port = deployment_config(environ)
    assert port == 10000
    assert url.password == "p@ss%word"
    assert url.query["options"] == "-csearch_path=ct_backend -cstatement_timeout=3000"
    assert make_url(url.render_as_string(hide_password=False)) == url


@pytest.mark.parametrize("change", [
    {"DATABASE_URL": "sqlite:///ephemeral.db"},
    {"DATABASE_URL": ""},
    {"DATABASE_URL": "postgresql://owner:secret@db.example.test/postgres"},
    {"DATABASE_URL": "postgresql://owner:secret@db.example.test/postgres?sslmode=disable"},
    {"ADMIN_API_KEY": " " * 40},
    {"APP_ENV": "development"},
    {"PORT": "0"},
])
def test_hosted_startup_rejects_unsafe_configuration_without_disclosing_secrets(change):
    environ = valid_environ() | change
    with pytest.raises(ValueError) as error:
        deployment_config(environ)
    assert "p%40ss" not in str(error.value)
    assert "owner:secret" not in str(error.value)


def test_host_serves_frontend_but_keeps_backend_protected(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text('<html><script src="/concurrent-training/assets/app.js"></script></html>')
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text("window.hosted=true")
    monkeypatch.setattr(settings, "require_api_key", True)
    with TestClient(create_hosted_app(tmp_path)) as client:
        assert client.get("/", follow_redirects=False).headers["location"] == "/concurrent-training/"
        assert client.get("/concurrent-training/").status_code == 200
        assert client.get("/concurrent-training/assets/app.js").text == "window.hosted=true"
        assert client.get("/athletes").status_code == 401
        assert client.get("/concurrent-training/.env").status_code == 404
        assert client.get("/concurrent-training/../requirements.txt").status_code == 404


def test_readiness_requires_current_migrations_and_hides_database_errors(tmp_path):
    (tmp_path / "index.html").write_text("<html>CT</html>")
    app = create_hosted_app(tmp_path)
    db = Mock()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        db.execute.return_value.scalar.return_value = "006"
        assert client.get("/ready").json() == {"status": "ready", "database": "connected"}
        db.execute.return_value.scalar.return_value = "005"
        assert client.get("/ready").status_code == 503
        db.execute.side_effect = RuntimeError("postgresql://owner:private-password@db.invalid/postgres")
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "database": "unavailable"}
        assert "private-password" not in response.text


def test_missing_frontend_build_refuses_to_start(tmp_path):
    with pytest.raises(RuntimeError, match="Build webapp/dist"):
        create_hosted_app(tmp_path)
