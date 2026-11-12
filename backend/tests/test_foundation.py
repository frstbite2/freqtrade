import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.core.config import REPO_ROOT, RiskConfig, ScoringWeights, load_settings
from backend.core.logging import JsonFormatter, redact
from backend.main import create_app
from backend.models import AuditLog


TOKEN = "test-token-123"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "APP_ENV",
        "DATABASE_URL",
        "LOG_LEVEL",
        "SEC_USER_AGENT",
        "CONFIG_DIR",
        "POLYGON_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("API_AUTH_TOKEN", TOKEN)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.sqlite")
    app = create_app(load_settings())
    with TestClient(app) as c:
        yield c


# --- configuration ---


def test_repo_config_loads_with_spec_defaults():
    s = load_settings(REPO_ROOT / "config")
    assert s.app.trading_mode == "paper"
    assert (s.risk.risk_per_trade_pct, s.risk.max_daily_loss_pct) == (0.5, 2.0)
    assert (s.risk.max_open_positions, s.risk.max_portfolio_exposure_pct) == (5, 50.0)


def test_missing_config_dir_falls_back_to_defaults(tmp_path):
    s = load_settings(tmp_path)
    assert s.risk == RiskConfig() and s.app.trading_mode == "paper"


def test_live_trading_is_rejected(tmp_path):
    (tmp_path / "settings.yaml").write_text("trading_mode: live\n")
    with pytest.raises(ValidationError):
        load_settings(tmp_path)


def test_unknown_keys_rejected(tmp_path):
    (tmp_path / "settings.yaml").write_text("alpaca_api_key: abc\n")
    with pytest.raises(ValidationError):
        load_settings(tmp_path)


@pytest.mark.parametrize(
    "bad",
    [
        {"risk_per_trade_pct": 0},
        {"risk_per_trade_pct": 10},
        {"max_daily_loss_pct": 6, "max_weekly_loss_pct": 5},
        {"max_asset_exposure_pct": 60, "max_portfolio_exposure_pct": 50},
    ],
)
def test_risk_validation(bad):
    with pytest.raises(ValidationError):
        RiskConfig(**bad)


def test_weights_must_sum_to_one():
    with pytest.raises(ValidationError):
        ScoringWeights(technical=0.5)


def test_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SEC_USER_AGENT", "Example Research admin@example.com")
    s = load_settings(tmp_path)
    assert s.app.log_level == "DEBUG"
    assert s.configured_providers()["sec_edgar"] is True
    assert s.configured_providers()["polygon"] is False


# --- logging ---


def test_secrets_redacted_from_logs(monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "supersecretvalue")
    record = logging.LogRecord("x", logging.INFO, "", 0, "key=%s", ("supersecretvalue",), None)
    out = JsonFormatter().format(record)
    assert "supersecretvalue" not in out and json.loads(out)["msg"] == "key=***"
    assert redact("postgresql://user:pw123@db:5432/x") == "postgresql://user:***@db:5432/x"


# --- API + database ---


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "ok"}


def test_api_requires_token(client):
    assert client.get("/api/v1/status").status_code == 401
    assert (
        client.get("/api/v1/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
    )


def test_api_fails_closed_without_configured_token(client, monkeypatch):
    monkeypatch.delenv("API_AUTH_TOKEN")
    assert client.get("/api/v1/status", headers={"Authorization": "Bearer x"}).status_code == 503


def test_status_and_config_hide_secrets(client, monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "supersecretvalue")
    h = {"Authorization": f"Bearer {TOKEN}"}
    status = client.get("/api/v1/status", headers=h)
    cfg = client.get("/api/v1/config", headers=h)
    assert status.status_code == cfg.status_code == 200
    assert status.json()["trading_mode"] == "paper"
    assert status.json()["providers_configured"]["polygon"] is True
    assert cfg.json()["risk"]["risk_per_trade_pct"] == 0.5
    assert "supersecretvalue" not in status.text + cfg.text and TOKEN not in status.text + cfg.text


def test_startup_and_shutdown_are_audited(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/a.sqlite")
    app = create_app(load_settings())
    with TestClient(app):
        pass
    with Session(app.state.engine) as s:
        assert s.scalars(select(AuditLog.action).order_by(AuditLog.id)).all() == [
            "startup",
            "shutdown",
        ]


def test_health_reports_unreachable_database(client):
    client.app.state.engine = create_engine("sqlite:////nonexistent-dir/x.sqlite")
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["database"] == "unreachable"
