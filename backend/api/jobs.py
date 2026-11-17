"""Scheduled-ingestion status: what ran, what failed, what is due."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select

from backend.api.routes import require_token
from backend.database.locks import IngestionLock
from backend.database.session import db_ok
from backend.models.jobs import JobRun
from backend.services.scheduler import ingestion_health, job_table, next_due


router = APIRouter(prefix="/api/v1/jobs", dependencies=[Depends(require_token)])
health_router = APIRouter(prefix="/api/v1/health", dependencies=[Depends(require_token)])


def _run(run: JobRun) -> dict:
    return {
        "job": run.job,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error": run.error,
        "targets": run.detail,
    }


@router.get("")
def jobs(request: Request, history: Annotated[int, Query(ge=0, le=200)] = 20) -> dict:
    settings = request.app.state.settings
    with request.app.state.sessions() as session:
        status = {}
        for name, (every, targets, _) in job_table(settings).items():
            last = session.scalar(
                select(JobRun).where(JobRun.job == name).order_by(JobRun.started_at.desc()).limit(1)
            )
            due = next_due(session, settings, name)
            status[name] = {
                "every_minutes": every,
                "targets": len(targets),
                "last_run": _run(last) if last else None,  # None: never run, so no data yet
                "next_due": due.isoformat() if due else "now",
            }
        recent = session.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(history))
        return {
            "enabled": settings.app.ingestion.enabled,
            "jobs": status,
            "recent_runs": [_run(r) for r in recent],
        }


@health_router.get("/ingestion")
def ingestion(request: Request, response: Response) -> dict:
    """Ingestion health for monitoring: 503 when the database is unreachable, a job's last run
    failed or a job is overdue; 200 otherwise ("healthy", "degraded" or "disabled")."""
    settings, engine = request.app.state.settings, request.app.state.engine
    now = request.app.state.clock()
    if not db_ok(engine):
        response.status_code = 503
        return {
            "status": "unhealthy",
            "database": "unreachable",
            "checked_at": now.isoformat(),
            "problems": ["database unreachable"],
        }
    with request.app.state.sessions() as session:
        body = ingestion_health(session, settings, now)
    body["database"] = "ok"
    body["ingesting_now"] = IngestionLock.holder_exists(engine)  # None: not readable on SQLite
    if body["status"] == "unhealthy":
        response.status_code = 503
    return body
