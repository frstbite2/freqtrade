"""Point-in-time reads of the filing history, with amendments and duplicates resolved."""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models.insider import InsiderFiling, InsiderTransaction


def filings_as_of(session: Session, cik: int, as_of: datetime) -> list[InsiderFiling]:
    """Filings that were public at `as_of`. Later filings must never leak into the past."""
    return list(
        session.scalars(
            select(InsiderFiling)
            .where(InsiderFiling.issuer_cik == cik, InsiderFiling.accepted_at <= as_of)
            .options(selectinload(InsiderFiling.transactions))
            .order_by(InsiderFiling.accepted_at, InsiderFiling.accession)
        )
    )


def _lot(t: InsiderTransaction) -> tuple:
    """What an amendment must match to be read as a correction of a row."""
    title = " ".join((t.security_title or "").lower().split())
    return (
        t.table,
        title,
        t.transaction_date,
        t.code,
        t.acquired_disposed,
        t.ownership,
        t.nature_of_ownership,
    )


def owner_groups(filings: list[InsiderFiling]) -> dict[int, int]:
    """Map each filer CIK to the insider it counts as: people who ever file jointly are one.

    A fund and its chairman file together, sometimes with one named first and sometimes the
    other. Counting them separately would report one decision as a cluster of two insiders.
    """
    parent: dict[int, int] = {}

    def find(cik: int) -> int:
        while parent.setdefault(cik, cik) != cik:
            parent[cik] = parent[parent[cik]]
            cik = parent[cik]
        return cik

    for f in filings:
        for owner in f.owners or []:
            parent[find(owner["cik"])] = find(f.owner_cik)
    return {f.owner_cik: find(f.owner_cik) for f in filings}


def _amends(amendment: InsiderFiling, original: InsiderFiling) -> bool:
    if original.accepted_at >= amendment.accepted_at:
        return False
    if amendment.original_filed_date is not None:
        return original.filed_date == amendment.original_filed_date
    return original.period_of_report == amendment.period_of_report


def effective_transactions(filings: list[InsiderFiling]) -> list[InsiderTransaction]:
    """Transactions (not holdings) with each economic event counted once.

    1. An amendment replaces the rows of the filing it amends that describe the same lot.
       shortcut: an amendment that only *adds* a same-day, same-code lot also hides the original
       lot (undercount, never double count); fixing that needs the amendment's explanatory text.
    2. The same trade reported in several filings (joint owners filing separately) counts once,
       keeping the first public disclosure.
    """
    filings = sorted(filings, key=lambda f: (f.accepted_at, f.accession))
    groups = owner_groups(filings)
    by_owner: dict[int, list[InsiderFiling]] = defaultdict(list)
    for f in filings:
        by_owner[groups[f.owner_cik]].append(f)

    superseded: set[int] = set()
    for amendment in filings:
        if amendment.is_amendment:
            lots = {_lot(t) for t in amendment.transactions if not t.is_holding}
            for original in by_owner[groups[amendment.owner_cik]]:
                if _amends(amendment, original):
                    superseded.update(id(t) for t in original.transactions if _lot(t) in lots)

    first_seen: dict[tuple, str] = {}
    result = []
    for f in filings:
        for t in f.transactions:
            if t.is_holding or id(t) in superseded:
                continue
            trade = (*_lot(t)[:5], t.shares, t.price, t.shares_after)
            if first_seen.setdefault(trade, f.accession) == f.accession:
                result.append(t)
    return result
