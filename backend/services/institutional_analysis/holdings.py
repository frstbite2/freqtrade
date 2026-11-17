"""What a manager's 13F filings said it held at a quarter end, and how that changed.

Everything is point-in-time: only filings already public at `as_of` are used. Holdings are a
delayed disclosure (up to 45 days after the quarter, longer for confidential positions) and say
nothing about what the manager holds today.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models.institutional import InstitutionalFiling


SPLIT_RATIOS = (2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 50)
EXACT = Decimal("0.001")  # a share count multiplied by a split ratio to within 0.1%


@dataclass
class Position:
    cusip: str
    issuer_name: str
    title_of_class: str | None
    shares: Decimal
    value: Decimal


@dataclass
class Report:
    """A manager's disclosed holdings for one quarter, as known at some moment."""

    status: str  # "reported" | "reported_elsewhere" | "not_filed"
    positions: dict[str, Position] = field(default_factory=dict)  # shares only, by CUSIP
    filings: list[str] = field(default_factory=list)  # accession numbers used
    disclosed_at: datetime | None = None  # when the latest of them became public
    option_rows: int = 0  # put/call rows, which are not share ownership and are left out
    excluded_rows: int = 0  # rows with data problems or reported as principal amount
    confidential_omitted: bool = False  # the manager withheld some positions


def previous_quarter(period: date) -> date:
    first = period.replace(day=1)
    month = (first.month - 1) // 3 * 3 + 1  # first month of this quarter
    return first.replace(month=month) - timedelta(days=1)


def report_as_of(session: Session, cik: int, period: date, as_of: datetime) -> Report:
    filings = list(
        session.scalars(
            select(InstitutionalFiling)
            .where(
                InstitutionalFiling.manager_cik == cik,
                InstitutionalFiling.period == period,
                InstitutionalFiling.accepted_at <= as_of,
            )
            .options(selectinload(InstitutionalFiling.holdings))
            .order_by(InstitutionalFiling.accepted_at, InstitutionalFiling.accession)
        )
    )
    # The original report or a restatement replaces everything before it; a "new holdings"
    # amendment adds positions (typically ones that were confidential) to what stands.
    used: list[InstitutionalFiling] = []
    for filing in filings:
        if filing.is_amendment and (filing.amendment_type or "").upper() == "NEW HOLDINGS":
            used.append(filing)
        else:
            used = [filing]
    if not used:
        return Report("not_filed")
    if not any(f.has_holdings_table for f in used):
        # A 13F-NT: another manager reports these holdings. Unknown here, not zero.
        return Report("reported_elsewhere", filings=[f.accession for f in used])

    report = Report(
        "reported",
        filings=[f.accession for f in used],
        disclosed_at=max(f.accepted_at for f in used),
        confidential_omitted=any(f.confidential_omitted for f in used),
    )
    for filing in used:
        for row in filing.holdings:
            if row.put_call:
                report.option_rows += 1
            elif row.issues or row.amount_type != "SH":
                report.excluded_rows += 1
            elif row.cusip in report.positions:  # one security on several rows: add them up
                report.positions[row.cusip].shares += row.amount
                report.positions[row.cusip].value += row.value
            else:
                report.positions[row.cusip] = Position(
                    row.cusip, row.issuer_name, row.title_of_class, row.amount, row.value
                )
    return report


def split_ratios(pairs: list[tuple[Report, Report]]) -> dict[str, Decimal | None]:
    """Per CUSIP, the share-count adjustment between two quarters, from the holders themselves.

    13F filings do not say when a stock split. Two signs are used across all (previous, current)
    report pairs: a holder whose share count is multiplied by exactly a split ratio, and the
    implied price (value / shares) moving by a factor that only a split explains.
    Returns the ratio to multiply previous shares by, or None when a split is likely but cannot
    be pinned down, in which case the security's changes must not be interpreted.
    shortcut: inferred from holders; replace with corporate-action data once a market data
    provider is verified.
    """
    share_ratios: dict[str, list[Decimal]] = defaultdict(list)
    price_ratios: dict[str, list[Decimal]] = defaultdict(list)
    for previous, current in pairs:
        for cusip in previous.positions.keys() & current.positions.keys():
            before, after = previous.positions[cusip], current.positions[cusip]
            if before.shares > 0 and after.shares > 0:
                share_ratios[cusip].append(after.shares / before.shares)
                if before.value > 0 and after.value > 0:
                    price_ratios[cusip].append(
                        (after.value / after.shares) / (before.value / before.shares)
                    )
    result: dict[str, Decimal | None] = {}
    for cusip, ratios in share_ratios.items():
        prices = sorted(price_ratios[cusip])
        price = prices[len(prices) // 2] if prices else None
        for k in (Decimal(n) for n in SPLIT_RATIOS):
            for factor in (k, 1 / k):  # forward split, reverse split
                carried = any(abs(r / factor - 1) <= EXACT for r in ratios)
                # The implied price must also have moved the other way, and by more than half
                # of what the split implies (in ratio terms): a manager who simply doubles a
                # position leaves the price where it was.
                undone = None if price is None else price * factor
                plausible = undone is not None and Decimal("0.5") < undone < 2
                moved = undone is not None and abs(undone.ln()) < abs(price.ln())
                if carried and plausible and moved:
                    result[cusip] = factor
        if cusip not in result and price is not None and not Decimal("0.45") < price < 2:
            result[cusip] = None  # a move this large may be a split nobody carried exactly
    return result


@dataclass
class Change:
    cusip: str
    issuer_name: str
    title_of_class: str | None
    previous_shares: Decimal  # as filed
    shares: Decimal
    status: str  # "new" | "increased" | "reduced" | "exited" | "unchanged" | "unclear"
    change_pct: float | None  # None for new positions and unclear cases
    value: Decimal
    note: str = ""


def changes(previous: Report, current: Report, ratios: dict[str, Decimal | None]) -> list[Change]:
    """Position changes between two reported quarters, split-adjusted where a split is known."""
    out = []
    for cusip in sorted(previous.positions.keys() | current.positions.keys()):
        before, after = previous.positions.get(cusip), current.positions.get(cusip)
        described = after or before
        old = before.shares if before else Decimal(0)
        new = after.shares if after else Decimal(0)
        note, pct = "", None
        if cusip in ratios and ratios[cusip] is None:
            status = "unclear"
            note = "the implied price moved so much that a stock split is likely; not interpreted"
        else:
            factor = ratios.get(cusip, Decimal(1))
            adjusted = old * factor
            if factor != 1 and old > 0:
                note = f"previous shares adjusted for a {_split_text(factor)} stock split"
            if adjusted == 0:
                status = "new"
            elif new == 0:
                status, pct = "exited", -100.0
            else:
                pct = float((new - adjusted) / adjusted * 100)
                # Under 0.5% is rounding or a dividend reinvestment, not a decision.
                status = "unchanged" if abs(pct) < 0.5 else "increased" if pct > 0 else "reduced"
        out.append(
            Change(
                cusip=cusip,
                issuer_name=described.issuer_name,
                title_of_class=described.title_of_class,
                previous_shares=old,
                shares=new,
                status=status,
                change_pct=None if pct is None else round(pct, 2),
                value=after.value if after else Decimal(0),
                note=note,
            )
        )
    return out


def _split_text(factor: Decimal) -> str:
    return f"{factor:f}-for-1" if factor > 1 else f"1-for-{1 / factor:f}"
