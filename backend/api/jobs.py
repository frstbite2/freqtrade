"""Scheduled-ingestion status: what ran, what failed, what is due."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from backend.api.routes import require_token
from backend.models.jobs import JobRun
from backend.services.scheduler import job_table, next_due


router = APIRouter(prefix="/api/v1/jobs", dependencies=[Depends(require_token)])


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
