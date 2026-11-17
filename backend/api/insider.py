"""Insider intelligence endpoints. Read-only over the ingested filing history."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.routes import require_token
from backend.models.insider import InsiderIssuer
from backend.services.insider_intelligence.history import effective_transactions, filings_as_of
from backend.services.insider_intelligence.scoring import (
    DISCLAIMER,
    score_issuer,
    transaction_dict,
)


router = APIRouter(prefix="/api/v1/insider", dependencies=[Depends(require_token)])

Ticker = Annotated[str, Path(pattern=r"^[A-Za-z0-9.\-]{1,16}$")]
AsOf = Annotated[
    datetime | None,
    Query(description="Point in time (ISO 8601 with UTC offset). Default: now."),
]


def _issuer(session: Session, ticker: str) -> InsiderIssuer:
    issuer = session.scalar(select(InsiderIssuer).where(InsiderIssuer.ticker == ticker.upper()))
    if issuer is None:
        # Never ingested is "unavailable", which must not be read as "no insider activity".
        raise HTTPException(
            404,
            f"No insider filing history has been ingested for {ticker.upper()}. "
            "This means the data is unavailable, not that there was no activity.",
        )
    return issuer


def _as_of(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        raise HTTPException(422, "as_of must include a UTC offset, e.g. 2026-01-31T00:00:00Z")
    return value.astimezone(UTC)


@router.get("/{ticker}/score")
def score(request: Request, ticker: Ticker, as_of: AsOf = None) -> dict:
    with request.app.state.sessions() as session:
        return score_issuer(session, _issuer(session, ticker).cik, _as_of(as_of))


@router.get("/{ticker}/transactions")
def transactions(
    request: Request,
    ticker: Ticker,
    as_of: AsOf = None,
    signals_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict:
    """Disclosed transactions, newest first, each linked to its SEC filing."""
    with request.app.state.sessions() as session:
        issuer = _issuer(session, ticker)
        rows = effective_transactions(filings_as_of(session, issuer.cik, _as_of(as_of)))
        if signals_only:
            rows = [t for t in rows if t.signal]
        rows.sort(key=lambda t: (t.filing.accepted_at, t.accession, -t.row_index), reverse=True)
        return {
            "ticker": issuer.ticker,
            "cik": issuer.cik,
            "history_since": issuer.history_since.isoformat(),
            "last_ingested_at": issuer.last_ingested_at.isoformat(),
            "missing_filings": issuer.failed_filings,
            "total": len(rows),
            "transactions": [transaction_dict(t) for t in rows[:limit]],
            "disclaimer": DISCLAIMER,
        }
