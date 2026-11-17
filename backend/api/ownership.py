"""Beneficial ownership (Schedules 13D/13G) endpoints. Read-only over the ingested history."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.routes import require_token
from backend.models.beneficial import BeneficialIssuer
from backend.services.beneficial_ownership.history import (
    DISCLAIMER,
    describe,
    filings_as_of,
    holders,
)


router = APIRouter(prefix="/api/v1/ownership", dependencies=[Depends(require_token)])

Ticker = Annotated[str, Path(pattern=r"^[A-Za-z0-9.\-]{1,16}$")]
AsOf = Annotated[datetime | None, Query(description="Point in time (ISO 8601 with UTC offset).")]
Schedule = Annotated[Literal["13D", "13G"] | None, Query(description="Only this schedule.")]


def _load(session: Session, ticker: str, as_of: datetime | None):
    issuer = session.scalar(
        select(BeneficialIssuer).where(BeneficialIssuer.ticker == ticker.upper())
    )
    if issuer is None:
        raise HTTPException(
            404,
            f"No 13D/13G history has been ingested for {ticker.upper()}. "
            "This means the data is unavailable, not that nobody holds more than 5%.",
        )
    if as_of is None:
        as_of = datetime.now(UTC)
    elif as_of.tzinfo is None:
        raise HTTPException(422, "as_of must include a UTC offset, e.g. 2026-01-31T00:00:00Z")
    filings = filings_as_of(session, issuer.cik, as_of.astimezone(UTC))
    meta = {
        "ticker": issuer.ticker,
        "cik": issuer.cik,
        "issuer": issuer.name,
        "history_since": issuer.history_since.isoformat(),
        "last_ingested_at": issuer.last_ingested_at.isoformat(),
        "missing_filings": issuer.failed_filings,
        "disclaimer": DISCLAIMER,
    }
    return filings, meta


@router.get("/{ticker}/holders")
def holders_endpoint(
    request: Request, ticker: Ticker, as_of: AsOf = None, schedule: Schedule = None
) -> dict:
    """Each filer's most recent disclosure of a stake above 5%, with the change it reported.

    With `schedule`, only holders whose latest filing is of that schedule."""
    with request.app.state.sessions() as session:
        filings, meta = _load(session, ticker, as_of)
        return meta | {"holders": holders(filings, schedule)}


@router.get("/{ticker}/filings")
def filings_endpoint(
    request: Request,
    ticker: Ticker,
    as_of: AsOf = None,
    schedule: Schedule = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict:
    """The full history of 13D/13G filings, newest first."""
    with request.app.state.sessions() as session:
        filings, meta = _load(session, ticker, as_of)
        rows = describe(filings, schedule)[::-1]
        return meta | {"total": len(rows), "filings": rows[:limit]}
