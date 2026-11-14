"""Recurring ingestion of SEC filings: Forms 3/4/5, Schedules 13D/13G and Form 13F.

Run the worker:   python -m backend.services.scheduler          (loops until stopped)
Run what is due:  python -m backend.services.scheduler --once   (suits cron)
Force one job:    python -m backend.services.scheduler --once --force insider

Safe to run repeatedly and from several processes: ingestion skips filings already stored, and
a job that is already running is never started a second time (see models/jobs.py). Every run is
recorded with per-target results, so a failure is visible rather than silent.
"""

import argparse
import logging
import signal
import threading
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.core.checks import need
from backend.core.config import Settings, get_settings
from backend.core.logging import setup_logging
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
    wait = schedule.retry_after_minutes if last.status == "failed" else job_table(settings)[job][0]
    return last.started_at + timedelta(minutes=wait)


def _acquire(session: Session, settings: Settings, job: str, now: datetime) -> JobRun | None:
    """Start a run, or return None if one is already in progress."""
    for _ in range(2):
        run = JobRun(job=job, active=True, started_at=now, status="running", detail={})
        session.add(run)
        try:
            session.commit()
            return run
        except IntegrityError:
            session.rollback()
        running = session.scalar(select(JobRun).where(JobRun.job == job, JobRun.active.is_(True)))
        stale = now - timedelta(minutes=settings.app.ingestion.stale_after_minutes)
        if running is None or running.started_at > stale:
            return None
        # The process that owned it died without finishing: close it and take over.
        running.active, running.status, running.finished_at = None, "failed", now
        running.error = "abandoned: still marked running after the stale limit"
        session.commit()
        logger.warning("job %s: took over an abandoned run started %s", job, running.started_at)
    return None


def run_job(
    session: Session,
    settings: Settings,
    job: str,
    client_factory: Callable[[], EdgarClient],
    now: datetime | None = None,
) -> JobRun | None:
    """Run one job for all its targets. Returns the finished run, or None if already running."""
    _, targets, ingest = job_table(settings)[job]
    run = _acquire(session, settings, job, now or datetime.now(UTC))
    if run is None:
        logger.info("job %s: already running elsewhere, skipped", job)
        return None
    results: dict[str, dict] = {}
    error = None
    try:
        client = client_factory()
        try:
            for target in targets:
                try:
                    report = ingest(session, client, target)
                    results[str(target)] = _summary(report)
                except (EdgarError, ValueError) as exc:  # one bad target must not stop the rest
                    session.rollback()
                    results[str(target)] = {"error": str(exc)}
                    logger.warning("job %s: %s failed: %s", job, target, exc)
        finally:
            client.close()
    except Exception as exc:
        session.rollback()
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("job %s failed", job)

    problems = [t for t, r in results.items() if r.get("error") or r.get("failed")]
    all_failed = bool(targets) and all("error" in r for r in results.values())
    status = "failed" if error or all_failed else "partial" if problems else "succeeded"
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
) -> list[JobRun]:
    """Run every job that is due (or the forced one). Does nothing when ingestion is disabled."""
    if not settings.app.ingestion.enabled and not force:
        return []
    now = now or datetime.now(UTC)
    runs = []
    for job in job_table(settings):
        due = next_due(session, settings, job)
        if job == force or (force is None and (due is None or due <= now)):
            run = run_job(session, settings, job, client_factory, now)
            if run is not None:
                runs.append(run)
    return runs


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--once", action="store_true", help="run what is due, then exit")
    args.add_argument("--force", choices=["insider", "beneficial", "institutional"])
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
        signal.signal(sig, lambda *_: stop.set())  # finish the current job, then exit
    if not settings.app.ingestion.enabled and not opts.force:
        logger.warning("ingestion is disabled in settings; nothing will run")
    while not stop.is_set():
        with sessions() as session:
            run_due(session, settings, client, opts.force)
        if opts.once:
            break
        stop.wait(settings.app.ingestion.poll_seconds)
    engine.dispose()
    logger.info("scheduler stopped")


if __name__ == "__main__":
    main()
