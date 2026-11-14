"""Point-in-time views of Schedule 13D/13G history: each filing, and each holder's latest one.

Limits that every consumer must keep in view:
- A filing states ownership as of its event date and became public at `accepted_at`. It is not
  the holder's position today; 13G holders in particular may update only quarterly or yearly.
- Percentages are the filer's own figures. Persons on one filing usually report the same shares
  (a fund, its adviser, its owner), so they are never added together.
- Filings before December 2024 are free-form: they are listed, but their numbers are unknown.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models.beneficial import BeneficialFiling, BeneficialOwner


DISCLAIMER = (
    "Delayed public disclosures (Schedules 13D and 13G), as of each filing's event date; not "
    "current holdings. 13D filers may seek to influence the company; 13G filers state they are "
    "passive. Filings before December 2024 are listed without their figures."
)
MEANING = {
    "13D": "active: the holder has, or may have, the purpose of influencing or controlling "
    "the issuer",
    "13G": "passive: the holder states it does not seek to influence or control the issuer",
}


def filings_as_of(session: Session, cik: int, as_of: datetime) -> list[BeneficialFiling]:
    """Filings that were public at `as_of`, oldest first."""
    return list(
        session.scalars(
            select(BeneficialFiling)
            .where(BeneficialFiling.issuer_cik == cik, BeneficialFiling.accepted_at <= as_of)
            .options(selectinload(BeneficialFiling.persons))
            .order_by(BeneficialFiling.accepted_at, BeneficialFiling.accession)
        )
    )


def lead_person(filing: BeneficialFiling) -> BeneficialOwner | None:
    """The reporting person with the largest stake, which stands for the filing as a whole."""
    stated = [p for p in filing.persons if p.percent is not None or p.shares is not None]
    return max(
        stated, key=lambda p: (p.percent or Decimal(0), p.shares or Decimal(0)), default=None
    )


def holder_key(filing: BeneficialFiling) -> str:
    """Identifies the holder across filings: the largest reporting person's name, normalised.

    The account a filing is submitted under varies (the holder, a fund vehicle, a law firm), and
    free-form filings carry no person data, so the name is the only thread that runs through.
    """
    lead = lead_person(filing)
    name = lead.name if lead and lead.name else filing.filer_name or str(filing.filer_cik)
    return "".join(ch for ch in name.upper() if ch.isalnum() or ch == " ").strip()


def describe(filings: list[BeneficialFiling]) -> list[dict]:
    """Every filing with its change from the same holder's previous structured filing."""
    previous: dict[str, BeneficialFiling] = {}
    out = []
    for f in filings:
        lead = lead_person(f)
        row = {
            "accession": f.accession,
            "form": f.form,
            "schedule": f.schedule,
            "schedule_meaning": MEANING[f.schedule],
            "is_amendment": f.is_amendment,
            "amendment_number": f.amendment_number,
            "structured": f.structured,
            "holder": (lead.name if lead and lead.name else f.filer_name),
            "holder_key": holder_key(f),
            "filed_by_cik": f.filer_cik,
            "event_date": f.event_date.isoformat() if f.event_date else None,
            "filed_date": f.filed_date.isoformat(),
            "accepted_at": f.accepted_at.isoformat(),
            "security": f.security_title,
            "cusip": f.cusip,
            "shares": None if lead is None or lead.shares is None else str(lead.shares),
            "percent": None if lead is None or lead.percent is None else str(lead.percent),
            # None: not stated or not parsed. False: the holder reports having dropped below 5%.
            "above_5_percent": None if lead is None or lead.percent is None else lead.percent >= 5,
            "reporting_persons": [
                {
                    "name": p.name,
                    "type": p.person_type,
                    "shares": None if p.shares is None else str(p.shares),
                    "percent": None if p.percent is None else str(p.percent),
                }
                for p in f.persons
            ],
            "rule": f.rule,
            "purpose": f.purpose,
            "issues": f.issues,
            "filing_url": f.url,
            "change": None,
        }
        key = holder_key(f)
        if f.structured:
            if key in previous:
                row["change"] = _change(previous[key], f)
            previous[key] = f
        out.append(row)
    return out


def _change(before: BeneficialFiling, after: BeneficialFiling) -> dict:
    old, new = lead_person(before), lead_person(after)
    shares = percent = None
    if old and new and old.shares is not None and new.shares is not None:
        shares = new.shares - old.shares
    if old and new and old.percent is not None and new.percent is not None:
        percent = new.percent - old.percent
    notes = []
    if before.schedule != after.schedule:
        notes.append(f"switched from Schedule {before.schedule} to Schedule {after.schedule}")
    if shares == 0 and percent:
        notes.append("same share count: the percentage moved because the share class changed size")
    # Shares up or down by half or more while the stake barely moves is not trading.
    if (
        old
        and new
        and shares
        and percent is not None
        and old.shares
        and old.percent
        and new.shares is not None
        and abs(new.shares / old.shares - 1) > Decimal("0.5")
        and abs(percent) < old.percent / 5
    ):
        notes.append(
            "share count changed far more than the percentage: likely a stock split or a "
            "change of share class; compare the percentages, not the shares"
        )
    if new and new.percent is not None and new.percent < 5:
        notes.append("now below 5%: the holder need not file further updates")
    return {
        "since_accession": before.accession,
        "since_filed_date": before.filed_date.isoformat(),
        "shares": None if shares is None else str(shares),
        "percent_points": None if percent is None else str(percent),
        "notes": notes,
    }


def holders(filings: list[BeneficialFiling]) -> list[dict]:
    """Each holder's latest filing, largest disclosed stake first.

    A holder known only from free-form filings is listed with unknown figures rather than left out.
    """
    latest: dict[str, dict] = {}
    for row in describe(filings):
        current = latest.get(row["holder_key"])
        # A structured filing is never replaced by an older-style one: its figures are known.
        if current is None or row["structured"] or not current["structured"]:
            latest[row["holder_key"]] = row
    return sorted(
        latest.values(),
        key=lambda r: (r["percent"] is None, -Decimal(r["percent"] or 0), r["holder"] or ""),
    )
