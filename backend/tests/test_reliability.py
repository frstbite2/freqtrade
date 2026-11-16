"""Running unattended: the SEC ingestion lock, the combined SEC request rate, crash recovery,
ingestion health, run-history retention and production-mode API security.

Ingestion runs on the real SEC fixtures served offline. Lock tests use real child processes,
killed without warning where the test says so. Every test runs on SQLite; tests that take a
database also run on PostgreSQL when MIGRATION_TEST_DATABASE_URL names a throwaway database.
"""

import itertools
import os
import time
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from multiprocessing import get_context
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import sessionmaker

from backend.core.config import REPO_ROOT, load_settings
from backend.database.locks import IngestionLock, LockLost, sec_ingestion
from backend.database.session import Base, init_db, make_engine
from backend.main import create_app
from backend.models import AuditLog
from backend.models.jobs import JobRun
from backend.services import scheduler
from backend.services.edgar import EdgarClient
from backend.services.insider_intelligence import ingest as insider
from backend.tests.conftest import SINCE, TEST_USER_AGENT, edgar_handler


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
SPAWN = get_context("spawn")
PG = os.environ.get("MIGRATION_TEST_DATABASE_URL")


@pytest.fixture(params=["sqlite"] + (["postgresql"] if PG else []))
def db_url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path}/platform.sqlite"
        return
    engine = make_engine(PG)
    _wipe(engine, check=True)
    yield PG
    _wipe(engine, check=False)  # only this test's own rows are left
    engine.dispose()


def _wipe(engine, check):
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            if check and inspect(conn).has_table(table.name):
                # Before a test, a database these tests may empty holds no research data.
                assert (
                    table.name in ("audit_log", "job_run")
                    or not conn.execute(select(func.count()).select_from(table)).scalar()
                ), f"refusing to wipe {table.name}: it holds data"
        Base.metadata.drop_all(conn)
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def _settings(tmp_path, body="watchlist: [GME, NKE]\ntracked_managers: [1336528]\n"):
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "settings.yaml").write_text(body)
    return load_settings(config)


def _client(cache, handler=edgar_handler, **kwargs):
    return EdgarClient(
        TEST_USER_AGENT, cache, max_attempts=1, transport=httpx.MockTransport(handler), **kwargs
    )


def _wait_for(path: Path, seconds=60):
    deadline = time.monotonic() + seconds
    while not path.exists():
        assert time.monotonic() < deadline, f"child never wrote {path}"
        time.sleep(0.05)


# --- child processes (top-level so a spawned interpreter can import them) ---


def hold_lock(url, ready):
    lock = IngestionLock(make_engine(url))
    assert lock.acquire(wait=False)
    Path(ready).write_text("held")
    time.sleep(600)


def run_insider_job_slowly(url, config_dir, cache, ready):
    """The worker, mid-run, until it is killed."""
    settings = load_settings(config_dir)
    engine = make_engine(url)
    init_db(engine)

    def slow(request):
        Path(ready).touch()
        time.sleep(0.3)
        return edgar_handler(request)

    with sessionmaker(engine)() as session:
        scheduler.run_job(
            session, settings, "insider", lambda: _client(cache, slow, min_interval=0)
        )


def ingest_logging_requests(url, cache, ticker, log, use_lock):
    """One process ingesting one ticker at SEC's real pace, logging when each request leaves."""
    engine = make_engine(url)  # the parent created the tables

    def logged(request):
        with Path(log).open("a") as f:
            f.write(f"{time.time()} {os.getpid()}\n")
        return edgar_handler(request)

    lock_options = {"require_lock": True} if use_lock else {}
    client = _client(cache, logged, **lock_options)  # default spacing: 8 requests a second
    with sec_ingestion(engine, wait=True) if use_lock else nullcontext():
        with sessionmaker(engine)() as session:
            insider.ingest_issuer(session, client, ticker, SINCE)
    client.close()


# --- the lock ---


def test_a_second_process_cannot_take_the_lock_and_a_killed_holder_frees_it(db_url, tmp_path):
    ready = tmp_path / "ready"
    holder = SPAWN.Process(target=hold_lock, args=(db_url, str(ready)))
    holder.start()
    try:
        _wait_for(ready)
        mine = IngestionLock(make_engine(db_url))
        assert mine.acquire(wait=False) is False
        holder.kill()  # SIGKILL: no cleanup code runs in the holder
        holder.join()
        deadline = time.monotonic() + 10
        while not mine.acquire(wait=False):
            assert time.monotonic() < deadline, "the lock was not freed when its holder died"
            time.sleep(0.05)
        mine.release()
    finally:
        holder.kill()


def test_waiting_for_the_lock_proceeds_once_it_is_free(db_url, tmp_path):
    ready = tmp_path / "ready"
    holder = SPAWN.Process(target=hold_lock, args=(db_url, str(ready)))
    holder.start()
    try:
        _wait_for(ready)
        told = []
        lock = IngestionLock(make_engine(db_url))
        killer = SPAWN.Process(target=_kill_after, args=(holder.pid, 1.0))
        killer.start()
        started = time.monotonic()
        assert lock.acquire(wait=True, on_wait=lambda: told.append(1), poll=0.1)
        assert time.monotonic() - started >= 0.9 and told == [1]  # waited, and said so once
        lock.release()
        killer.join()
    finally:
        holder.kill()


def _kill_after(pid, seconds):
    import signal

    time.sleep(seconds)
    os.kill(pid, signal.SIGTERM)


def test_no_wait_command_line_option_exits_instead_of_waiting(db_url, tmp_path):
    ready = tmp_path / "ready"
    holder = SPAWN.Process(target=hold_lock, args=(db_url, str(ready)))
    holder.start()
    try:
        _wait_for(ready)
        with pytest.raises(SystemExit, match="another process is ingesting from SEC"):
            with sec_ingestion(make_engine(db_url), wait=False):
                pass
    finally:
        holder.kill()


COMMANDS = [
    ["backend.services.insider_intelligence.ingest", "NKE"],
    ["backend.services.beneficial_ownership.ingest", "GME"],
    ["backend.services.institutional_analysis.ingest", "1336528"],
    ["backend.services.insider_intelligence.verify", "unused.zip"],
    ["backend.services.institutional_analysis.verify", "unused.zip"],
    ["backend.services.scheduler", "--once", "--force", "insider"],
]


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: "-".join(c[0].split(".")[-2:]))
def test_every_sec_command_takes_the_lock_and_honours_no_wait(command, tmp_path):
    """Each real command, run as its own process while another process holds the lock, exits at
    once with --no-wait. None of them reaches SEC: the lock comes before any request."""
    import subprocess
    import sys

    url = f"sqlite:///{tmp_path}/platform.sqlite"
    ready = tmp_path / "ready"
    holder = SPAWN.Process(target=hold_lock, args=(url, str(ready)))
    holder.start()
    try:
        _wait_for(ready)
        env = os.environ | {
            "DATABASE_URL": url,
            "SEC_USER_AGENT": TEST_USER_AGENT,
            "CONFIG_DIR": str(_settings(tmp_path) and tmp_path / "config"),
        }
        result = subprocess.run(
            [sys.executable, "-m", *command, "--no-wait"],
            check=False, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
        )  # fmt: skip
        out = result.stdout + result.stderr
        assert result.returncode != 0, out
        assert "another process is ingesting from SEC" in out, out
    finally:
        holder.kill()


@pytest.mark.skipif(not PG, reason="needs MIGRATION_TEST_DATABASE_URL (PostgreSQL)")
def test_a_lost_database_connection_is_detected():
    engine = make_engine(PG)
    lock = IngestionLock(engine)
    assert lock.acquire(wait=False)
    lock.check()  # fine while connected
    with engine.connect() as admin:  # the database drops the lock's connection
        admin.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_locks "
                "WHERE locktype = 'advisory' AND objid = :key AND pid <> pg_backend_pid()"
            ),
            {"key": IngestionLock.KEY},
        )
    with pytest.raises(LockLost):
        lock.check()
    lock.release()
    successor = IngestionLock(engine)
    assert successor.acquire(wait=False)  # and someone else may now take it
    successor.release()


def test_real_sec_requests_need_the_lock(tmp_path):
    def must_not_be_called(request):
        raise AssertionError("a request was sent without the lock")

    client = _client(tmp_path, must_not_be_called, require_lock=True)
    with pytest.raises(RuntimeError, match="SEC ingestion lock"):
        client.get("https://www.sec.gov/files/company_tickers.json", max_age=0)
    client.close()


def test_sqlite_lock_is_a_file_next_to_the_database(tmp_path):
    lock = IngestionLock(make_engine(f"sqlite:///{tmp_path}/data/platform.sqlite"))
    assert lock.acquire(wait=False)
    assert (tmp_path / "data" / "platform.sqlite.ingest-lock").exists()
    lock.release()


# --- the combined SEC request rate ---


def _request_times(log: Path) -> list[tuple[float, str]]:
    rows = [line.split() for line in log.read_text().splitlines()]
    return sorted((float(t), pid) for t, pid in rows)


def _busiest_second(times: list[float]) -> int:
    return max(sum(1 for u in times if t <= u < t + 1) for t in times)


def _run_two_processes(db_url, tmp_path, use_lock) -> list[tuple[float, str]]:
    init_db(make_engine(db_url))
    log = tmp_path / "requests.log"
    procs = [
        SPAWN.Process(
            target=ingest_logging_requests,
            args=(db_url, str(tmp_path / f"cache-{t}"), t, str(log), use_lock),
        )
        for t in ("NKE", "INTC")
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
        assert p.exitcode == 0
    return _request_times(log)


def test_without_the_lock_two_processes_exceed_secs_limit(tmp_path):
    """The problem the lock solves, measured: each process alone keeps to 8 a second."""
    times = _run_two_processes(f"sqlite:///{tmp_path}/p.sqlite", tmp_path, use_lock=False)
    assert _busiest_second([t for t, _ in times]) > 10


def test_with_the_lock_the_combined_rate_stays_within_secs_limit(db_url, tmp_path):
    times = _run_two_processes(db_url, tmp_path, use_lock=True)
    assert len(times) >= 20
    assert _busiest_second([t for t, _ in times]) <= 9  # 8 a second, 9 at a window's edges
    order = [pid for _, pid in times]
    switches = sum(1 for a, b in itertools.pairwise(order) if a != b)
    assert switches == 1  # one process finished before the other sent anything


# --- the scheduler ---


def test_worker_skips_its_pass_while_another_process_ingests(db_url, tmp_path):
    settings = _settings(tmp_path)
    ready = tmp_path / "ready"
    holder = SPAWN.Process(target=hold_lock, args=(db_url, str(ready)))
    holder.start()
    try:
        _wait_for(ready)
        engine = make_engine(db_url)
        init_db(engine)
        with sessionmaker(engine)() as session:
            assert scheduler.run_due(session, settings, lambda: _client(tmp_path), now=NOW) == []
            assert session.scalar(select(func.count()).select_from(JobRun)) == 0
    finally:
        holder.kill()


def test_a_run_left_by_a_killed_worker_is_closed_at_once_and_redone(db_url, tmp_path):
    settings = _settings(tmp_path)
    ready = tmp_path / "ready"
    worker = SPAWN.Process(
        target=run_insider_job_slowly,
        args=(db_url, str(tmp_path / "config"), str(tmp_path / "cache-1"), str(ready)),
    )
    worker.start()
    _wait_for(ready)
    worker.kill()  # out of memory, kill -9, host restart: no chance to record anything
    worker.join()
    engine = make_engine(db_url)
    with sessionmaker(engine)() as session:
        (left,) = session.scalars(select(JobRun)).all()
        assert (left.job, left.status, left.active) == ("insider", "running", True)
        one_minute_later = left.started_at + timedelta(minutes=1)
        runs = scheduler.run_due(
            session, settings, lambda: _client(tmp_path / "cache-2"), now=one_minute_later
        )
        assert ("insider", "succeeded") in [(r.job, r.status) for r in runs]
        session.refresh(left)
        assert (left.status, left.active) == ("failed", None)
        assert left.error.startswith("abandoned: its process ended")


def test_a_lost_lock_stops_the_run_between_targets(db_url, tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    engine = make_engine(db_url)
    init_db(engine)
    real = scheduler.beneficial.ingest_issuer

    def then_connection_lost(*args):
        report = real(*args)
        monkeypatch.setattr(IngestionLock, "check", _lost)
        return report

    monkeypatch.setattr(scheduler.beneficial, "ingest_issuer", then_connection_lost)
    with sessionmaker(engine)() as session:
        run = scheduler.run_job(session, settings, "beneficial", lambda: _client(tmp_path), NOW)
        assert (run.status, run.active, set(run.detail)) == ("interrupted", None, {"GME"})
        assert run.error == "lost the SEC ingestion lock (database connection ended) before: NKE"
        assert scheduler.next_due(session, settings, "beneficial") == NOW + timedelta(minutes=15)


def _lost(self):
    raise LockLost("connection ended")


# --- ingestion health ---

AUTH = {"Authorization": "Bearer " + "h" * 40}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "h" * 40)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.sqlite")
    monkeypatch.delenv("APP_ENV", raising=False)
    (tmp_path / "settings.yaml").write_text("watchlist: [GME]\ntracked_managers: [1336528]\n")
    app = create_app(load_settings(tmp_path))
    with TestClient(app) as client:
        yield app, client


def _run(session, job, status, started, finished=True, error=None):
    session.add(
        JobRun(
            job=job,
            active=None if finished else True,
            started_at=started,
            finished_at=started + timedelta(minutes=2) if finished else None,
            status=status,
            detail={},
            error=error,
        )
    )
    session.commit()


def _health(app, client, now):
    app.state.clock = lambda: now
    return client.get("/api/v1/health/ingestion", headers=AUTH)


def _all_succeeded(session, at):
    for job in ("insider", "beneficial", "institutional"):
        _run(session, job, "succeeded", at)


def test_health_is_ok_when_every_job_has_run_on_time(api):
    app, client = api
    with app.state.sessions() as s:
        _all_succeeded(s, NOW)
    response = _health(app, client, NOW + timedelta(minutes=30))
    body = response.json()
    assert (response.status_code, body["status"], body["database"]) == (200, "healthy", "ok")
    insider_job = body["jobs"]["insider"]
    assert insider_job["last_success"]["started_at"] == NOW.isoformat()
    assert (insider_job["last_failure"], insider_job["running"], insider_job["overdue"]) == (
        None,
        None,
        False,
    )
    assert body["scheduler"] == "healthy"


def test_health_is_unhealthy_when_a_job_failed(api):
    app, client = api
    with app.state.sessions() as s:
        _all_succeeded(s, NOW)
        _run(s, "beneficial", "failed", NOW + timedelta(minutes=5), error="SEC answered 503")
    response = _health(app, client, NOW + timedelta(minutes=10))
    body = response.json()
    assert (response.status_code, body["status"]) == (503, "unhealthy")
    assert body["jobs"]["beneficial"]["last_failure"]["error"] == "SEC answered 503"
    assert body["problems"] == ["beneficial: last run failed"]


def test_health_reports_an_interrupted_run_and_a_running_one(api):
    app, client = api
    with app.state.sessions() as s:
        _all_succeeded(s, NOW)
        _run(s, "beneficial", "interrupted", NOW + timedelta(minutes=5), error="interrupted")
        _run(s, "insider", "running", NOW + timedelta(minutes=8), finished=False)
    response = _health(app, client, NOW + timedelta(minutes=10))
    body = response.json()
    assert (response.status_code, body["status"]) == (200, "degraded")
    assert body["jobs"]["beneficial"]["interrupted"] is True
    assert (
        body["jobs"]["insider"]["running"]["started_at"] == (NOW + timedelta(minutes=8)).isoformat()
    )
    assert body["problems"] == ["beneficial: last run was interrupted; retry is due"]


def test_health_is_unhealthy_when_a_job_is_overdue(api):
    app, client = api
    with app.state.sessions() as s:
        _all_succeeded(s, NOW)
    # insider runs hourly: due at 13:00, overdue after the 30-minute grace period.
    response = _health(app, client, NOW + timedelta(minutes=95))
    body = response.json()
    assert (response.status_code, body["status"], body["scheduler"]) == (
        503,
        "unhealthy",
        "stalled",
    )
    assert body["jobs"]["insider"]["overdue"] is True
    assert body["problems"] == ["insider: overdue since 2026-11-14T13:30:00+00:00"]


def test_health_before_any_run_and_with_the_database_down(api, monkeypatch):
    app, client = api
    fresh = _health(app, client, NOW)  # due now, not overdue; worth a look, not an alarm
    assert (fresh.status_code, fresh.json()["status"]) == (200, "degraded")
    assert "insider: has never run" in fresh.json()["problems"]
    monkeypatch.setattr("backend.api.jobs.db_ok", lambda engine: False)
    down = _health(app, client, NOW)
    assert (down.status_code, down.json()["status"], down.json()["database"]) == (
        503,
        "unhealthy",
        "unreachable",
    )


def test_health_needs_the_token(api):
    _, client = api
    assert client.get("/api/v1/health/ingestion").status_code == 401


# --- run-history retention ---


def test_retention_removes_only_old_run_history(db_url, tmp_path):
    settings = _settings(tmp_path)
    engine = make_engine(db_url)
    init_db(engine)
    research = [t for t in Base.metadata.sorted_tables if t.name not in ("job_run", "audit_log")]
    with sessionmaker(engine)() as session:
        scheduler.run_due(session, settings, lambda: _client(tmp_path), now=NOW)  # real filings
        before = {t.name: session.scalar(select(func.count()).select_from(t)) for t in research}
        assert sum(before.values()) > 0
        audits = session.scalar(select(func.count()).select_from(AuditLog))
        old = NOW - timedelta(days=200)
        for days in (190, 180, 170):
            _run(session, "insider", "succeeded", old + timedelta(days=200 - days))
        _run(session, "insider", "failed", old - timedelta(days=5))
        _run(session, "beneficial", "partial", old)
        _run(session, "institutional", "running", old, finished=False)  # never touched

        later = NOW + timedelta(days=100)
        removed = scheduler.prune_run_history(session, settings, later)

        # Kept: every job's latest run, latest success and latest failure, and running rows.
        kept = {
            (r.job, r.status, r.started_at.date().isoformat())
            for r in session.scalars(select(JobRun))
        }
        assert removed == 4
        assert kept == {
            ("insider", "succeeded", NOW.date().isoformat()),
            ("insider", "failed", (old - timedelta(days=5)).date().isoformat()),
            ("beneficial", "succeeded", NOW.date().isoformat()),
            ("institutional", "succeeded", NOW.date().isoformat()),
            ("institutional", "running", old.date().isoformat()),
        }
        after = {t.name: session.scalar(select(func.count()).select_from(t)) for t in research}
        assert after == before  # no filing, holding, transaction or price row is ever deleted
        pruned = session.scalars(select(AuditLog).where(AuditLog.action == "job.prune")).one()
        assert pruned.detail["removed"] == 4
        assert session.scalar(select(func.count()).select_from(AuditLog)) == audits + 1


def test_retention_period_is_validated(tmp_path):
    from pydantic import ValidationError

    assert _settings(tmp_path, "").app.ingestion.run_history_days == 90
    with pytest.raises(ValidationError):
        _settings(tmp_path, "ingestion:\n  run_history_days: 3\n")
    with pytest.raises(ValidationError):  # removed: the lock replaced the age limit
        _settings(tmp_path, "ingestion:\n  stale_after_minutes: 180\n")


# --- production-mode API security ---


def _app(tmp_path, monkeypatch, env, token):
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/{env}.sqlite")
    if token is None:
        monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    else:
        monkeypatch.setenv("API_AUTH_TOKEN", token)
    return create_app(load_settings(tmp_path))


@pytest.mark.parametrize(
    ("env", "token", "problem"),
    [
        ("production", None, "API_AUTH_TOKEN must be set"),
        ("production", "change-me", "placeholder"),
        ("production", "Change-Me", "placeholder"),
        ("production", "short-but-not-a-placeholder", "at least 32 characters"),
        ("production", "a" * 40, "too simple"),
        ("test", "change-me", "placeholder"),
        ("test", "", "API_AUTH_TOKEN must be set"),
    ],
)
def test_weak_tokens_stop_the_api_outside_development(tmp_path, monkeypatch, env, token, problem):
    with pytest.raises(RuntimeError, match=problem) as error:
        _app(tmp_path, monkeypatch, env, token)
    if token:
        assert token not in str(error.value)  # never echo the token


def test_strong_token_starts_production_without_api_docs(tmp_path, monkeypatch):
    token = "Xk3-v9Qe" * 5
    app = _app(tmp_path, monkeypatch, "production", token)
    with TestClient(app) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
        status = client.get("/api/v1/status", headers={"Authorization": f"Bearer {token}"})
        assert status.status_code == 200 and token not in status.text


def test_development_keeps_api_docs_and_short_tokens(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, "development", "dev")
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_credentials_never_reach_api_responses(tmp_path, monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "pg-secret-value-1234")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "alpaca-secret-value-5678")
    token = "Tok-" + "r7Lp" * 9
    app = _app(tmp_path, monkeypatch, "development", token)
    error = (
        "OperationalError: connection to postgresql://trader:pg-secret-value-1234@db:5432/x "
        "failed; key alpaca-secret-value-5678"
    )

    def broken_factory():
        raise RuntimeError(error)

    with TestClient(app) as client:
        with app.state.sessions() as s:
            scheduler.run_job(s, app.state.settings, "insider", broken_factory, NOW)
        auth = {"Authorization": f"Bearer {token}"}
        bodies = [
            client.get(path, headers=auth).text
            for path in ("/api/v1/status", "/api/v1/config", "/api/v1/jobs", "/health")
        ]
        bodies.append(client.get("/api/v1/health/ingestion", headers=auth).text)
    for secret in ("pg-secret-value-1234", "alpaca-secret-value-5678", token):
        assert not any(secret in body for body in bodies), secret
    assert any("trader:***@db" in body for body in bodies)  # the error is kept, redacted


def test_compose_keeps_the_api_on_localhost_and_the_database_private():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.platform.yml").read_text())
    services = compose["services"]
    assert services["api"]["ports"] == ["127.0.0.1:8000:8000"]
    assert "ports" not in services["db"] and "ports" not in services["worker"]
    db_command = " ".join(services["db"]["command"])
    for setting in ("tcp_keepalives_idle=30", "tcp_keepalives_interval=10"):
        assert setting in db_command


def test_postgres_connections_use_tcp_keepalives(monkeypatch):
    engine = make_engine("postgresql+psycopg://user:pw@localhost:5/db")
    sent = {}

    def capture(*args, **kwargs):
        sent.update(kwargs)
        raise ConnectionRefusedError("captured; no server needed")

    monkeypatch.setattr(engine.dialect.loaded_dbapi, "connect", capture)
    with pytest.raises(Exception, match="captured"):
        engine.connect()
    assert (sent["keepalives"], sent["keepalives_idle"], sent["keepalives_count"]) == (1, 30, 3)
