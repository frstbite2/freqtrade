"""Recurring ingestion of SEC filings: Forms 3/4/5, Schedules 13D/13G and Form 13F.

Run the worker:   python -m backend.services.scheduler          (loops until stopped)
Run what is due:  python -m backend.services.scheduler --once   (suits cron; add --no-wait to
                  exit instead of waiting while another process ingests)
Force one job:    python -m backend.services.scheduler --once --force insider

Safe to run repeatedly and from several processes. A pass holds the SEC ingestion lock
(backend/database/locks.py) while it runs jobs, so no two processes ingest at once; the worker
skips a pass while another process holds it. Ingestion skips filings already stored. A run still
marked running when a process takes the lock belonged to a process that died, and is closed as
abandoned at once. Every run is recorded with per-target results, so a failure is visible.
"""

import argparse
import logging
import signal
import threading
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from backend.core.checks import need
from backend.core.config import Settings, get_settings
from backend.core.logging import redact, setup_logging
from backend.database.locks import IngestionLock, LockLost, add_wait_option, sec_ingestion
from backend.database.session import init_db, make_engine
from backend.models import record_audit
from backend.models.jobs import JobRun
from backend.services.beneficial_ownership import ingest as beneficial
from backend.services.edgar import EdgarClient, EdgarError
from backend.services.insider_intelligence import ingest as insider
from backend.services.institutional_analysis import ingest as institutional


logger = logging.getLogger(__name__)


def _since(days: int) -> date:
    return datetime.now(UTC).date() - timedelta(days=days)


# job name -> (settings field with its interval, targets, ingest one target)
def job_table(settings: Settings) -> dict[str, tuple[int, tuple, Callable]]:
    schedule, app = settings.app.ingestion, settings.app
    return {
        "insider": (
            schedule.insider_every_minutes,
            app.watchlist,
            lambda s, c, t: insider.ingest_issuer(s, c, t, _since(insider.DEFAULT_HISTORY_DAYS)),
        ),
        "beneficial": (
            schedule.beneficial_every_minutes,
            app.watchlist,
            lambda s, c, t: beneficial.ingest_issuer(
                s, c, t, _since(beneficial.DEFAULT_HISTORY_DAYS)
            ),
        ),
        "institutional": (
            schedule.institutional_every_minutes,
            app.tracked_managers,
            lambda s, c, t: institutional.ingest_manager(
                s, c, t, _since(institutional.DEFAULT_HISTORY_DAYS)
            ),
        ),
    }


def next_due(session: Session, settings: Settings, job: str) -> datetime | None:
    """When the job should next start. None: it has never finished a run, so it is due now."""
    last = session.scalar(
        select(JobRun)
        .where(JobRun.job == job, JobRun.active.is_(None))
        .order_by(JobRun.started_at.desc())
        .limit(1)
    )
    if last is None:
        return None
    schedule = settings.app.ingestion
    retry = last.status in ("failed", "interrupted")  # retried after retry_after_minutes
    wait = schedule.retry_after_minutes if retry else job_table(settings)[job][0]
    return last.started_at + timedelta(minutes=wait)


ABANDONED = "abandoned: its process ended without finishing (the SEC ingestion lock was free)"


def _acquire(session: Session, job: str, now: datetime) -> JobRun:
    """Start a run. The caller holds the SEC ingestion lock, so a run of this job still marked
    running belonged to a process that died: it is closed as abandoned first."""
    for left in session.scalars(select(JobRun).where(JobRun.job == job, JobRun.active.is_(True))):
        left.active, left.status, left.finished_at, left.error = None, "failed", now, ABANDONED
        logger.warning("job %s: closed the run started %s, abandoned", job, left.started_at)
    run = JobRun(job=job, active=True, started_at=now, status="running", detail={})
    session.add(run)
    session.commit()
    return run


def _engine(session: Session) -> Engine:
    bind = session.get_bind()
    return bind if isinstance(bind, Engine) else bind.engine


def run_job(
    session: Session,
    settings: Settings,
    job: str,
    client_factory: Callable[[], EdgarClient],
    now: datetime | None = None,
    stop: threading.Event | None = None,
    lock: IngestionLock | None = None,
) -> JobRun | None:
    """Run one job for all its targets. Returns the finished run, or None if another process
    holds the SEC ingestion lock.

    `lock` is the caller's, already held; without one, this takes the lock itself or skips.
    When `stop` is set (the worker was asked to shut down), or the lock's database connection is
    lost, the run ends after the current target and is recorded as interrupted with the targets
    it did not reach, so it is retried soon.
    """
    own = lock is None
    if own:
        lock = IngestionLock(_engine(session))
        if not lock.acquire(wait=False):
            logger.info("job %s: another process is ingesting from SEC; skipped", job)
            return None
    try:
        return _run_job(
            session, settings, job, client_factory, now or datetime.now(UTC), stop, need(lock)
        )
    finally:
        if own:
            need(lock).release()


def _run_job(
    session: Session,
    settings: Settings,
    job: str,
    client_factory: Callable[[], EdgarClient],
    now: datetime,
    stop: threading.Event | None,
    lock: IngestionLock,
) -> JobRun:
    _, targets, ingest = job_table(settings)[job]
    run = _acquire(session, job, now)
    results: dict[str, dict] = {}
    error = None
    skipped: list[str] = []
    why = ""
    try:
        client = client_factory()
        try:
            for i, target in enumerate(targets):
                if stop is not None and stop.is_set():
                    skipped, why = [str(t) for t in targets[i:]], "interrupted by shutdown"
                    break
                try:
                    lock.check()
                except LockLost:
                    skipped = [str(t) for t in targets[i:]]
                    why = "lost the SEC ingestion lock (database connection ended)"
                    logger.error("job %s: %s; stopping", job, why)
                    break
                # One bad target must not stop the rest, whatever goes wrong with it.
                try:
                    report = ingest(session, client, target)
                    results[str(target)] = _summary(report)
                except (EdgarError, ValueError) as exc:  # expected: SEC, network, bad data
                    session.rollback()
                    results[str(target)] = {"error": redact(str(exc))}
                    logger.warning("job %s: %s failed: %s", job, target, exc)
                except Exception as exc:  # unexpected: a bug; keep the traceback in the log
                    session.rollback()
                    results[str(target)] = {"error": redact(f"{type(exc).__name__}: {exc}")}
                    logger.exception("job %s: %s failed unexpectedly", job, target)
        finally:
            client.close()
    except Exception as exc:
        session.rollback()
        error = redact(f"{type(exc).__name__}: {exc}")
        logger.exception("job %s failed", job)

    problems = [t for t, r in results.items() if r.get("error") or r.get("failed")]
    all_failed = bool(results) and all("error" in r for r in results.values())
    if error:
        status = "failed"
    elif skipped:
        status, error = "interrupted", f"{why} before: {', '.join(skipped)}"
    elif all_failed:
        status = "failed"
    else:
        status = "partial" if problems else "succeeded"
    if error is None and problems:
        error = f"problems with: {', '.join(problems)}"
    run = need(session.get(JobRun, run.id), "job run")
    run.active, run.status, run.finished_at = None, status, datetime.now(UTC)
    run.detail, run.error = results, error
    record_audit(
        session,
        "scheduler",
        "job.run",
        job=job,
        status=status,
        targets=len(targets),
        problems=problems,
    )
    logger.info(
        "job %s: %s (%d targets, %d with problems)", job, status, len(targets), len(problems)
    )
    return run


def _summary(report: object) -> dict:
    data = asdict(report) if is_dataclass(report) and not isinstance(report, type) else {}
    keep = ("listed", "stored", "already_stored", "reclassified", "failed")
    return {k: data[k] for k in keep if k in data}


def run_due(
    session: Session,
    settings: Settings,
    client_factory: Callable[[], EdgarClient],
    force: str | None = None,
    now: datetime | None = None,
    stop: threading.Event | None = None,
    wait: bool = False,
    lock: IngestionLock | None = None,
) -> list[JobRun]:
    """Run every job that is due (or the forced one), holding the SEC ingestion lock for the
    pass: the caller's `lock`, already held, or one taken here. Without `wait`, a pass that has
    to take the lock is skipped if another process holds it. Does nothing when ingestion is
    disabled. Afterwards, prunes old run history (`prune_run_history`)."""
    if not settings.app.ingestion.enabled and not force:
        return []
    now = now or datetime.now(UTC)
    due = [
        job
        for job in job_table(settings)
        if job == force
        or (force is None and ((d := next_due(session, settings, job)) is None or d <= now))
    ]
    if not due:
        return []
    own = lock is None
    if lock is None:
        lock = IngestionLock(_engine(session))
        told = "another process is ingesting from SEC; waiting for it to finish"
        if not lock.acquire(wait=wait, stop=stop, on_wait=lambda: logger.info(told)):
            logger.info("another process is ingesting from SEC; this pass is skipped")
            return []
    runs = []
    try:
        for job in due:
            if stop is not None and stop.is_set():
                break
            run = run_job(session, settings, job, client_factory, now, stop, lock)
            if run is not None:
                runs.append(run)
        prune_run_history(session, settings, now)
    finally:
        if own:
            lock.release()
    return runs


def prune_run_history(session: Session, settings: Settings, now: datetime) -> int:
    """Delete old scheduler run records; returns how many.

    Eligible: rows of `job_run` (a run's per-target counts and error text) that finished more
    than `run_history_days` ago, except each job's latest run (it decides when the job is next
    due), latest success and latest failure (shown by the health check). Running rows are never
    touched. Nothing else is ever deleted: not `audit_log`, which keeps a summary of every run
    indefinitely, and no filing, holding, transaction, owner, issuer, manager or price record.
    """
    cutoff = now - timedelta(days=settings.app.ingestion.run_history_days)
    keep = set()
    for job in job_table(settings):
        for condition in (
            JobRun.active.is_(None),
            JobRun.status == "succeeded",
            JobRun.status == "failed",
        ):
            latest = _latest(session, job, condition)
            if latest is not None:
                keep.add(latest.id)
    old = select(JobRun.id).where(JobRun.active.is_(None), JobRun.finished_at < cutoff)
    ids = [i for i in session.scalars(old) if i not in keep]
    if not ids:
        return 0
    session.execute(delete(JobRun).where(JobRun.id.in_(ids)))
    record_audit(  # commits the deletion with it
        session, "scheduler", "job.prune", removed=len(ids), finished_before=cutoff.isoformat()
    )
    logger.info("pruned %d run records that finished before %s", len(ids), cutoff)
    return len(ids)


def _latest(session: Session, job: str, *conditions) -> JobRun | None:
    return session.scalar(
        select(JobRun)
        .where(JobRun.job == job, *conditions)
        .order_by(JobRun.started_at.desc(), JobRun.id.desc())
        .limit(1)
    )


# A job not started this long after it was due means the worker is down or stuck.
OVERDUE_GRACE = timedelta(minutes=30)


def ingestion_health(session: Session, settings: Settings, now: datetime) -> dict:
    """Last success, last failure, running, interrupted and overdue state of every job.

    `status` is "unhealthy" when a job's last run failed or a job is overdue, "degraded" when a
    run was partial or interrupted, or a job has never run, "disabled" when ingestion is off, and
    otherwise "healthy". Alerting can be built on this (or on the endpoint that serves it).
    """
    enabled = settings.app.ingestion.enabled
    jobs, severe, mild = {}, [], []
    for name, (every, targets, _) in job_table(settings).items():
        running = _latest(session, name, JobRun.active.is_(True))
        last = _latest(session, name, JobRun.active.is_(None))
        success = _latest(session, name, JobRun.status == "succeeded")
        failure = _latest(session, name, JobRun.status == "failed")
        due = next_due(session, settings, name)
        overdue = bool(enabled and running is None and due and now > due + OVERDUE_GRACE)
        jobs[name] = {
            "every_minutes": every,
            "targets": len(targets),
            "last_run": _times(last) | {"status": last.status} if last else None,
            "last_success": _times(success) if success else None,
            "last_failure": _times(failure) | {"error": failure.error} if failure else None,
            "running": {"started_at": running.started_at.isoformat()} if running else None,
            "interrupted": bool(last and last.status == "interrupted"),
            "next_due": due.isoformat() if due else "now",
            "overdue": overdue,
        }
        if not enabled:
            continue
        if last is None and running is None:
            mild.append(f"{name}: has never run")
        elif last is not None and last.status == "failed":
            severe.append(f"{name}: last run failed")
        elif last is not None and last.status == "partial":
            mild.append(f"{name}: last run had problems: {last.error}")
        elif last is not None and last.status == "interrupted":
            mild.append(f"{name}: last run was interrupted; retry is due")
        if overdue:
            severe.append(f"{name}: overdue since {(need(due) + OVERDUE_GRACE).isoformat()}")
    stalled = any(j["overdue"] for j in jobs.values())
    status = (
        "disabled" if not enabled else "unhealthy" if severe else "degraded" if mild else "healthy"
    )
    return {
        "status": status,
        "scheduler": "disabled" if not enabled else "stalled" if stalled else "healthy",
        "checked_at": now.isoformat(),
        "jobs": jobs,
        "problems": severe + mild,
    }


def _times(run: JobRun) -> dict:
    return {
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def serve(
    sessions: sessionmaker,
    settings: Settings,
    client_factory: Callable[[], EdgarClient],
    stop: threading.Event,
    once: bool = False,
    force: str | None = None,
    lock: IngestionLock | None = None,
) -> None:
    """Run due jobs every `poll_seconds` until `stop` is set. A failing pass (the database
    restarting, say) is logged and retried at the next poll instead of ending the worker.
    The looping worker takes the SEC ingestion lock per pass and skips a pass while another
    process holds it; `lock` (used with --once) is one the caller already holds."""
    while not stop.is_set():
        try:
            with sessions() as session:
                run_due(session, settings, client_factory, force, stop=stop, lock=lock)
        except Exception:
            logger.exception("scheduler pass failed; retrying at the next poll")
        if once:
            break
        stop.wait(settings.app.ingestion.poll_seconds)


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--once", action="store_true", help="run what is due, then exit")
    args.add_argument("--force", choices=["insider", "beneficial", "institutional"])
    add_wait_option(args)  # with --once; the looping worker never waits, it tries next poll
    opts = args.parse_args()
    settings = get_settings()
    setup_logging(settings.app.log_level, settings.app.log_json)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    engine = make_engine(settings.app.database_url)
    init_db(engine)
    sessions = sessionmaker(engine)

    def client() -> EdgarClient:
        return EdgarClient(settings.app.sec_user_agent, settings.app.edgar_cache_dir)

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())  # finish the current target, then exit
    if not settings.app.ingestion.enabled and not opts.force:
        logger.warning("ingestion is disabled in settings; nothing will run")
    if opts.once:  # like the other SEC commands: wait for the lock, or exit with --no-wait
        with sec_ingestion(engine, wait=not opts.no_wait) as lock:
            serve(sessions, settings, client, stop, once=True, force=opts.force, lock=lock)
    else:
        serve(sessions, settings, client, stop, force=opts.force)
    engine.dispose()
    logger.info("scheduler stopped")


if __name__ == "__main__":
    main()
