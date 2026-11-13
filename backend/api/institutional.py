"""Institutional (Form 13F) endpoints. Read-only over the ingested filing history."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import func, select

from backend.api.routes import require_token
from backend.models.institutional import (
    InstitutionalFiling,
    InstitutionalHolding,
    InstitutionalManager,
)
from backend.services.institutional_analysis.holdings import previous_quarter
from backend.services.institutional_analysis.scoring import (
    DISCLAIMER,
    change_dict,
    latest_period,
    quarter_changes,
    score_security,
)


router = APIRouter(prefix="/api/v1/institutional", dependencies=[Depends(require_token)])

Cusip = Annotated[str, Path(pattern=r"^[0-9A-Za-z]{9}$")]
AsOf = Annotated[datetime | None, Query(description="Point in time (ISO 8601 with UTC offset).")]
UNAVAILABLE = (
    "No 13F filings have been ingested for that moment. "
    "This means the data is unavailable, not that there was no institutional activity."
)


def _as_of(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        raise HTTPException(422, "as_of must include a UTC offset, e.g. 2026-01-31T00:00:00Z")
    return value.astimezone(UTC)


@router.get("/securities/{cusip}")
def security(request: Request, cusip: Cusip, as_of: AsOf = None) -> dict:
    """Which tracked managers disclosed holding a security, and how that changed."""
    with request.app.state.sessions() as session:
        result = score_security(session, cusip.upper(), _as_of(as_of))
    if result is None:
        raise HTTPException(404, UNAVAILABLE)
    return result


@router.get("/search")
def search(request: Request, name: Annotated[str, Query(min_length=2, max_length=60)]) -> dict:
    """Find a security's CUSIP by the issuer name managers report (13F has no tickers)."""
    with request.app.state.sessions() as session:
        rows = session.execute(
            select(
                InstitutionalHolding.cusip,
                InstitutionalHolding.title_of_class,
                func.max(InstitutionalHolding.issuer_name),
                func.count(),
            )
            .where(InstitutionalHolding.issuer_name.ilike(f"%{name}%", escape="\\"))
            .group_by(InstitutionalHolding.cusip, InstitutionalHolding.title_of_class)
            .order_by(func.count().desc())
            .limit(25)
        ).all()
    return {
        "matches": [
            {"cusip": cusip, "title_of_class": cls, "issuer_name": issuer, "rows": n}
            for cusip, cls, issuer, n in rows
        ]
    }


@router.get("/managers")
def managers(request: Request) -> dict:
    with request.app.state.sessions() as session:
        latest = dict(
            session.execute(
                select(
                    InstitutionalFiling.manager_cik, func.max(InstitutionalFiling.period)
                ).group_by(InstitutionalFiling.manager_cik)
            ).all()
        )
        return {
            "managers": [
                {
                    "cik": m.cik,
                    "name": m.name,
                    "history_since": m.history_since.isoformat(),
                    "last_ingested_at": m.last_ingested_at.isoformat(),
                    "latest_period": latest[m.cik].isoformat() if m.cik in latest else None,
                    "missing_filings": m.failed_filings,
                }
                for m in session.scalars(
                    select(InstitutionalManager).order_by(InstitutionalManager.name)
                )
            ],
            "disclaimer": DISCLAIMER,
        }


@router.get("/managers/{cik}/changes")
def manager_changes(
    request: Request,
    cik: Annotated[int, Path(ge=1)],
    as_of: AsOf = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> dict:
    """One manager's position changes between its two latest comparable quarters."""
    moment = _as_of(as_of)
    with request.app.state.sessions() as session:
        manager = session.get(InstitutionalManager, cik)
        period = latest_period(session, moment)
        if manager is None or period is None:
            raise HTTPException(404, UNAVAILABLE)
        by_manager, reports, skipped = quarter_changes(session, period, moment)
        if cik not in by_manager:
            raise HTTPException(404, f"{manager.name} has no comparable reports ({skipped[cik]}).")
        rows = sorted(by_manager[cik], key=lambda c: -max(c.value, 0))
        current = reports[cik][1]
        return {
            "institution": manager.name,
            "manager_cik": cik,
            "period": period.isoformat(),
            "previous_period": previous_quarter(period).isoformat(),
            "disclosed_at": current.disclosed_at.isoformat(),
            "filings": current.filings,
            "confidential_positions_omitted": current.confidential_omitted,
            "option_rows_not_shown": current.option_rows,
            "total": len(rows),
            "changes": [change_dict(c) for c in rows[:limit]],
            "disclaimer": DISCLAIMER,
        }
