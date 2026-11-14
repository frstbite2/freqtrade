"""Scheduled ingestion: what is due, locking, failure isolation and reporting.

Ingestion itself runs on the real SEC fixtures; schedules and clocks are set by the tests.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from backend.core.config import load_settings
from backend.main import create_app
from backend.models import AuditLog
from backend.models.beneficial import BeneficialFiling
from backend.models.insider import InsiderFiling
from backend.models.institutional import InstitutionalFiling
from backend.models.jobs import JobRun
from backend.services import scheduler
from backend.services.edgar import EdgarClient, EdgarNotConfigured
from backend.tests.conftest import TEST_USER_AGENT, edgar_handler


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
PERSHING = 1336528


def settings_with(tmp_path, body: str):
    (tmp_path / "settings.yaml").write_text(body)
    return load_settings(tmp_path)


@pytest.fixture
def settings(tmp_path):
    return settings_with(tmp_path, f"watchlist: [GME, NKE]\ntracked_managers: [{PERSHING}]\n")


@pytest.fixture
def factory(tmp_path):
    def make(handler=edgar_handler):
        return lambda: EdgarClient(
            TEST_USER_AGENT, tmp_path / "cache", min_interval=0, max_attempts=1,
            transport=httpx.MockTransport(handler),
        )  # fmt: skip

    return make


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_first_pass_runs_every_job_and_stores_filings(db_session, settings, factory):
    runs = scheduler.run_due(db_session, settings, factory(), now=NOW)
    assert [(r.job, r.status, r.active) for r in runs] == [
        ("insider", "succeeded", None),
        ("beneficial", "succeeded", None),
        ("institutional", "succeeded", None),
    ]
    assert count(db_session, InsiderFiling) > 0 and count(db_session, BeneficialFiling) == 14
    assert count(db_session, InstitutionalFiling) == 6  # the 2022 filing predates the window
    insider = runs[0]
    assert set(insider.detail) == {"GME", "NKE"} and insider.error is None
    assert insider.detail["NKE"]["stored"] == insider.detail["NKE"]["listed"] > 0
    assert insider.finished_at is not None
    audits = db_session.scalars(select(AuditLog).where(AuditLog.action == "job.run")).all()
    assert [(a.detail["job"], a.detail["status"]) for a in audits] == [
        ("insider", "succeeded"), ("beneficial", "succeeded"), ("institutional", "succeeded"),
    ]  # fmt: skip


def test_jobs_run_again_only_when_their_interval_has_passed(db_session, settings, factory):
    scheduler.run_due(db_session, settings, factory(), now=NOW)
    stored = count(db_session, InsiderFiling)
    assert scheduler.run_due(db_session, settings, factory(), now=NOW + timedelta(minutes=59)) == []
    later = scheduler.run_due(db_session, settings, factory(), now=NOW + timedelta(minutes=61))
    assert [r.job for r in later] == ["insider"]  # hourly; the others are not due yet
    assert later[0].detail["NKE"]["stored"] == 0 and count(db_session, InsiderFiling) == stored
    day = scheduler.run_due(db_session, settings, factory(), now=NOW + timedelta(days=1, minutes=1))
    assert [r.job for r in day] == ["insider", "beneficial", "institutional"]
    assert count(db_session, JobRun) == 7 and count(db_session, InsiderFiling) == stored


def test_a_job_already_running_is_not_started_twice(db_session, settings, factory, tmp_path):
    db_session.add(JobRun(job="insider", active=True, started_at=NOW, status="running", detail={}))
    db_session.commit()
    assert (
        scheduler.run_job(db_session, settings, "insider", factory(), NOW + timedelta(minutes=5))
        is None
    )
    assert count(db_session, InsiderFiling) == 0
    # A second connection sees the same lock: the database enforces it, not this process.
    with sessionmaker(db_session.get_bind())() as other:
        assert (
            scheduler.run_job(other, settings, "insider", factory(), NOW + timedelta(minutes=6))
            is None
        )
    # Other jobs are not blocked by it.
    assert (
        scheduler.run_job(db_session, settings, "beneficial", factory(), NOW).status == "succeeded"
    )


def test_abandoned_run_is_taken_over_after_the_stale_limit(db_session, settings, factory):
    db_session.add(JobRun(job="insider", active=True, started_at=NOW, status="running", detail={}))
    db_session.commit()
    run = scheduler.run_job(
        db_session, settings, "insider", factory(), NOW + timedelta(minutes=181)
    )
    assert run.status == "succeeded"
    old = db_session.scalars(select(JobRun).order_by(JobRun.id)).first()
    assert (old.status, old.active) == ("failed", None) and "abandoned" in old.error


def test_one_bad_target_does_not_stop_the_others(db_session, tmp_path, factory):
    settings = settings_with(tmp_path, "watchlist: [GME, NOSUCH, NKE]\n")
    run = scheduler.run_job(db_session, settings, "beneficial", factory(), NOW)
    assert run.status == "partial" and run.error == "problems with: NOSUCH"
    assert "not in SEC's company list" in run.detail["NOSUCH"]["error"]
    assert run.detail["GME"]["stored"] == 5 and run.detail["NKE"]["stored"] == 9
    # A partial run still counts as done; the bad target is retried at the normal interval.
    assert scheduler.next_due(db_session, settings, "beneficial") == NOW + timedelta(minutes=360)


def test_failed_filings_make_the_run_partial_and_are_retried(db_session, tmp_path, factory):
    settings = settings_with(tmp_path, "watchlist: [GME]\n")
    down = {"on": True}

    def handler(request):
        if down["on"] and "000092189526002474" in str(request.url):
            return httpx.Response(200, content=b"<html>Request Rate Threshold Exceeded</html>")
        return edgar_handler(request)

    run = scheduler.run_job(db_session, settings, "beneficial", factory(handler), NOW)
    assert run.status == "partial" and list(run.detail["GME"]["failed"]) == ["0000921895-26-002474"]
    assert count(db_session, BeneficialFiling) == 4
    down["on"] = False
    again = scheduler.run_job(
        db_session, settings, "beneficial", factory(handler), NOW + timedelta(hours=7)
    )
    assert (again.status, again.detail["GME"]["stored"], again.detail["GME"]["failed"]) == (
        "succeeded",
        1,
        {},
    )


def test_total_failure_is_recorded_and_retried_sooner(db_session, settings, factory):
    def unconfigured():
        raise EdgarNotConfigured("SEC_USER_AGENT must be set to a name and contact email")

    run = scheduler.run_job(db_session, settings, "insider", unconfigured, NOW)
    assert (run.status, run.active, run.detail) == ("failed", None, {})
    assert "EdgarNotConfigured: SEC_USER_AGENT" in run.error
    assert scheduler.next_due(db_session, settings, "insider") == NOW + timedelta(minutes=15)
    assert (
        scheduler.run_due(db_session, settings, factory(), now=NOW + timedelta(minutes=14)) != []
    )  # others
    retry = scheduler.run_due(db_session, settings, factory(), now=NOW + timedelta(minutes=16))
    assert [(r.job, r.status) for r in retry] == [("insider", "succeeded")]


def test_sec_outage_fails_the_run_and_stores_nothing(db_session, settings, factory):
    down = factory(lambda request: httpx.Response(503))
    outage = scheduler.run_job(db_session, settings, "beneficial", down, NOW)
    assert outage.status == "failed" and set(outage.detail) == {"GME", "NKE"}
    assert "failed after 1 attempts" in outage.detail["GME"]["error"]
    assert count(db_session, BeneficialFiling) == 0
    recovered = scheduler.run_job(
        db_session, settings, "beneficial", factory(), NOW + timedelta(minutes=16)
    )
    assert recovered.status == "succeeded" and count(db_session, BeneficialFiling) == 14


def test_disabled_schedule_runs_nothing_unless_forced(db_session, tmp_path, factory):
    settings = settings_with(tmp_path, "watchlist: [GME]\ningestion:\n  enabled: false\n")
    assert scheduler.run_due(db_session, settings, factory(), now=NOW) == []
    forced = scheduler.run_due(db_session, settings, factory(), force="beneficial", now=NOW)
    assert [(r.job, r.status) for r in forced] == [("beneficial", "succeeded")]


def test_schedule_settings_are_validated(tmp_path):
    from pydantic import ValidationError

    for bad in ("ingestion:\n  insider_every_minutes: 0\n", "ingestion:\n  every: 5\n"):
        with pytest.raises(ValidationError):
            settings_with(tmp_path, bad)
    defaults = load_settings(tmp_path / "missing").app.ingestion
    assert (defaults.insider_every_minutes, defaults.institutional_every_minutes) == (60, 1440)


def test_api_reports_runs_failures_and_what_is_due(tmp_path, monkeypatch, factory):
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.sqlite")
    (tmp_path / "settings.yaml").write_text("watchlist: [GME, NOSUCH]\n")
    app = create_app(load_settings(tmp_path))
    auth = {"Authorization": "Bearer test-token"}
    with TestClient(app) as client:
        fresh = client.get("/api/v1/jobs", headers=auth).json()
        assert fresh["enabled"] is True and fresh["recent_runs"] == []
        assert fresh["jobs"]["insider"] == {
            "every_minutes": 60,
            "targets": 2,
            "last_run": None,
            "next_due": "now",
        }
        with app.state.sessions() as session:
            scheduler.run_job(session, app.state.settings, "beneficial", factory(), NOW)
        body = client.get("/api/v1/jobs", headers=auth).json()
        last = body["jobs"]["beneficial"]["last_run"]
        assert (last["status"], last["error"]) == ("partial", "problems with: NOSUCH")
        assert body["jobs"]["beneficial"]["next_due"] == (NOW + timedelta(minutes=360)).isoformat()
        assert (
            len(body["recent_runs"]) == 1
            and body["recent_runs"][0]["targets"]["GME"]["stored"] == 5
        )
        assert client.get("/api/v1/jobs").status_code == 401
        assert client.get("/api/v1/jobs", params={"history": 999}, headers=auth).status_code == 422
