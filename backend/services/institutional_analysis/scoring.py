"""Institutional activity for one security, from the tracked managers' 13F filings.

The score (0-100) ranks evidence of disclosed *accumulation* among the tracked managers between
the two most recent quarters public at `as_of`. It is a research ranking, not a probability, and
its weights are unvalidated priors until backtested (Milestone 8).

What it cannot say: 13F data is a quarter-end snapshot disclosed up to 45 days later; it covers
only the managers tracked here, only long positions in listed securities, and never what a manager
holds today.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.institutional import InstitutionalFiling, InstitutionalManager
from backend.services.institutional_analysis.holdings import (
    Change,
    Report,
    changes,
    previous_quarter,
    report_as_of,
    split_ratios,
)


DISCLAIMER = (
    "Delayed public disclosures (Form 13F) from a limited list of tracked managers. Holdings are "
    "as of the quarter end shown, not current positions. A research ranking, not a probability."
)
_NEW_POINTS = {0: 0.0, 1: 10.0, 2: 16.0}


@dataclass
class Component:
    name: str
    points: float
    max_points: float
    available: bool
    detail: str


def latest_period(session: Session, as_of: datetime) -> date | None:
    """The most recent quarter for which any tracked manager's report was public at `as_of`."""
    return session.scalar(
        select(func.max(InstitutionalFiling.period)).where(InstitutionalFiling.accepted_at <= as_of)
    )


def quarter_changes(
    session: Session, period: date, as_of: datetime
) -> tuple[dict[int, list[Change]], dict[int, tuple[Report, Report]], dict[int, str]]:
    """Every tracked manager's changes into `period`, plus who could not be compared and why."""
    reports, skipped = {}, {}
    for manager in session.scalars(select(InstitutionalManager)):
        previous = report_as_of(session, manager.cik, previous_quarter(period), as_of)
        current = report_as_of(session, manager.cik, period, as_of)
        if previous.status == current.status == "reported":
            reports[manager.cik] = (previous, current)
        else:
            skipped[manager.cik] = (
                f"{previous_quarter(period)}: {previous.status}, {period}: {current.status}"
            )
    ratios = split_ratios(list(reports.values()))
    return {cik: changes(*pair, ratios) for cik, pair in reports.items()}, reports, skipped


def _net(rows: list[Change]) -> tuple[Decimal, Decimal]:
    """(net share change, split-adjusted previous shares) over interpretable rows."""
    net = previous = Decimal(0)
    for c in rows:
        if c.status == "unclear":
            continue
        if c.status == "new":
            before = Decimal(0)
        elif c.status == "exited":
            before = c.previous_shares  # the split adjustment does not matter for a full exit
            net -= before
            previous += before
            continue
        else:
            before = c.shares / (1 + Decimal(str(c.change_pct)) / 100)
        net += c.shares - before
        previous += before
    return net, previous


def score_security(session: Session, cusip: str, as_of: datetime) -> dict | None:
    """None when no tracked manager's filings are public at `as_of` (unavailable, not zero)."""
    period = latest_period(session, as_of)
    if period is None:
        return None
    names = {m.cik: m.name for m in session.scalars(select(InstitutionalManager))}
    by_manager, reports, skipped = quarter_changes(session, period, as_of)
    rows = {cik: c for cik, cs in by_manager.items() for c in cs if c.cusip == cusip}
    counts = {
        s: sum(c.status == s for c in rows.values())
        for s in ("new", "increased", "reduced", "exited", "unchanged", "unclear")
    }
    buyers, sellers = counts["new"] + counts["increased"], counts["reduced"] + counts["exited"]
    net, previous = _net(list(rows.values()))

    components = []
    if buyers + sellers:
        breadth = (buyers - sellers) / (buyers + sellers)
        components.append(
            Component(
                "breadth",
                30 * max(0.0, breadth),
                30,
                True,
                f"{buyers} manager(s) added, {sellers} reduced",
            )
        )
        components.append(
            Component(
                "new_positions",
                _NEW_POINTS.get(counts["new"], 20.0),
                20,
                True,
                f"{counts['new']} new position(s)",
            )
        )
        if previous > 0:
            growth = float(net / previous)
            components.append(
                Component(
                    "net_buying",
                    25 * min(1.0, max(0.0, growth / 0.25)),
                    25,
                    True,
                    f"tracked managers' combined shares changed {growth:+.1%}",
                )
            )
        else:
            components.append(
                Component(
                    "net_buying",
                    25.0 if net > 0 else 0.0,
                    25,
                    True,
                    "no tracked manager held it the quarter before",
                )
            )
        earlier, _, _ = quarter_changes(session, previous_quarter(period), as_of)
        prior = [
            c for cs in earlier.values() for c in cs if c.cusip == cusip and c.status != "unclear"
        ]
        if prior:
            prior_net, _ = _net(prior)
            both = net > 0 and prior_net > 0
            components.append(
                Component(
                    "consistency",
                    25.0 if both else 0.0,
                    25,
                    True,
                    "net buying in the previous quarter too"
                    if both
                    else "no net buying in the previous quarter",
                )
            )
        else:
            components.append(
                Component("consistency", 0, 25, False, "no comparable holdings two quarters back")
            )
    available = sum(c.max_points for c in components if c.available)
    score = (
        round(100 * sum(c.points for c in components if c.available) / available, 1)
        if available
        else 0.0
    )
    if net <= 0:
        score = 0.0  # the score ranks accumulation; net selling is reported, not scored

    if not rows:
        explanation = (
            f"None of the {len(reports)} comparable tracked managers reported this security "
            f"for {period} or the quarter before."
        )
    else:
        explanation = (
            f"For the quarter ended {period}: {counts['new']} new, "
            f"{counts['increased']} increased, {counts['reduced']} reduced, "
            f"{counts['exited']} exited, {counts['unchanged']} unchanged"
            + (
                f", {counts['unclear']} not interpreted (possible stock split)"
                if counts["unclear"]
                else ""
            )
            + f" among {len(reports)} tracked managers with comparable reports."
        )
    described = next(iter(rows.values()), None)
    return {
        "cusip": cusip,
        "issuer_name": described.issuer_name if described else None,
        "title_of_class": described.title_of_class if described else None,
        "as_of": as_of.isoformat(),
        "period": period.isoformat(),
        "previous_period": previous_quarter(period).isoformat(),
        "score": score,
        "explanation": explanation,
        "components": [asdict(c) | {"points": round(c.points, 1)} for c in components],
        "counts": counts,
        "managers_compared": len(reports),
        "managers_not_comparable": {names.get(cik, str(cik)): why for cik, why in skipped.items()},
        "holders": [
            change_dict(c)
            | {
                "institution": names.get(cik, str(cik)),
                "manager_cik": cik,
                "disclosed_at": reports[cik][1].disclosed_at.isoformat(),
                "filings": reports[cik][1].filings,
            }
            for cik, c in sorted(rows.items(), key=lambda kv: -kv[1].value)
        ],
        "disclaimer": DISCLAIMER,
    }


def change_dict(c: Change) -> dict:
    return {
        "cusip": c.cusip,
        "issuer_name": c.issuer_name,
        "title_of_class": c.title_of_class,
        "previous_shares": str(c.previous_shares),
        "shares": str(c.shares),
        "status": c.status,
        "change_pct": c.change_pct,
        "value": f"{c.value:.2f}",
        "note": c.note,
    }
