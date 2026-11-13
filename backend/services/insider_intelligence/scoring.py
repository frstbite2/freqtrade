"""Insider activity score (0-100) for one issuer at one point in time.

The score ranks evidence of voluntary open-market *buying* by insiders. It is a research
ranking, not a probability of profit. Component weights and thresholds are unvalidated priors
and must be tested by walk-forward backtests (Milestone 8) before they are relied on.

Only rows classified as a discretionary signal count. A component that cannot be computed is
reported as unavailable and left out of the normalisation; it never counts as zero.
"""

import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models.insider import InsiderFiling, InsiderIssuer, InsiderTransaction
from backend.services.insider_intelligence.history import effective_transactions, filings_as_of


LOOKBACK_DAYS = 90
CLUSTER_DAYS = 30
HISTORY_DAYS = 730
MIN_HISTORY_COVERAGE_DAYS = 365
DISCLAIMER = (
    "Research ranking of publicly disclosed insider buying, not a probability of profit. "
    "Weights are unvalidated priors until backtested."
)

_TOP_EXECUTIVE = re.compile(
    r"\bchief executive\b|\bCEO\b|\bchief financial\b|\bCFO\b|principal (?:executive|financial)",
    re.IGNORECASE,
)
_CLUSTER_POINTS = {1: 0.0, 2: 12.0, 3: 20.0}


@dataclass
class Component:
    name: str
    points: float
    max_points: float
    available: bool
    detail: str


def _unit(x: float) -> float:
    return max(0.0, min(1.0, x))


def _seniority(t: InsiderTransaction) -> tuple[float, str]:
    f = t.filing
    if f.is_officer and f.officer_title and _TOP_EXECUTIVE.search(f.officer_title):
        return 20.0, f"{f.owner_name} ({f.officer_title})"
    if f.is_officer:
        return 14.0, f"{f.owner_name} (officer: {f.officer_title or 'title not stated'})"
    if f.is_director:
        return 10.0, f"{f.owner_name} (director)"
    if f.is_ten_percent_owner:
        return 5.0, f"{f.owner_name} (10% owner)"
    return 3.0, f"{f.owner_name} (other reporting person)"


def _cluster(buys: list[InsiderTransaction]) -> int:
    """Most distinct insiders buying within any CLUSTER_DAYS span."""
    dated = sorted((t.transaction_date, t.filing.owner_cik) for t in buys)
    best = 0
    for start, _ in dated:
        end = start + timedelta(days=CLUSTER_DAYS)
        best = max(best, len({owner for day, owner in dated if start <= day <= end}))
    return best


def _holdings_reported(filing: InsiderFiling) -> Decimal | None:
    """Non-derivative shares held after the filing's transactions, as the filing states them.

    shortcut: two separately held lots with identical title and ownership text that both trade
    in one filing are read as one lot (understates holdings); needs lot identity SEC forms lack.
    """
    holdings = Decimal(0)
    traded_lots: dict[tuple, Decimal] = {}
    found = False
    for t in filing.transactions:  # row order: the last row of a lot carries its final balance
        if t.table != "non_derivative" or t.shares_after is None:
            continue
        found = True
        if t.is_holding:
            holdings += t.shares_after
        else:
            traded_lots[(t.security_title, t.ownership, t.nature_of_ownership)] = t.shares_after
    return holdings + sum(traded_lots.values()) if found else None


def _ownership_change(buys: list[InsiderTransaction]) -> tuple[float, int] | None:
    """Value-weighted increase in each buyer's total reported holdings, capped at 100%."""
    by_owner: dict[int, list[InsiderTransaction]] = defaultdict(list)
    for t in buys:
        by_owner[t.filing.owner_cik].append(t)
    weighted = total = Decimal(0)
    measured = 0
    for rows in by_owner.values():
        latest = max((t.filing for t in rows), key=lambda f: (f.accepted_at, f.accession))
        held = _holdings_reported(latest)
        if held is None:
            continue
        bought = sum(t.shares for t in rows)
        before = held - bought
        increase = min(Decimal(1), bought / before) if before > 0 else Decimal(1)
        value = sum(t.value for t in rows)
        weighted += increase * value
        total += value
        measured += 1
    return (float(weighted / total), measured) if total else None


def score_issuer(session: Session, cik: int, as_of: datetime) -> dict | None:
    """Score from filings public at `as_of`. None if the issuer was never ingested."""
    issuer = session.get(InsiderIssuer, cik)
    if issuer is None:
        return None
    day = as_of.date()
    start = day - timedelta(days=LOOKBACK_DAYS)
    dated = [
        t
        for t in effective_transactions(filings_as_of(session, cik, as_of))
        if t.transaction_date is not None
    ]
    window = [t for t in dated if start <= t.transaction_date <= day]
    buys = [t for t in window if t.signal == "discretionary_buy"]
    sells = [t for t in window if t.signal == "discretionary_sell"]
    buy_value = sum((t.value for t in buys), Decimal(0))
    sell_value = sum((t.value for t in sells), Decimal(0))

    components = []
    if buys:
        size = _unit((math.log10(float(buy_value)) - 4) / 2.5) if buy_value > 0 else 0.0
        components.append(
            Component("purchase_value", 25 * size, 25, True, f"${buy_value:,.0f} bought")
        )
        points, who = max(_seniority(t) for t in buys)
        components.append(Component("seniority", points, 20, True, f"most senior buyer: {who}"))
        n = _cluster(buys)
        components.append(
            Component(
                "cluster",
                _CLUSTER_POINTS.get(n, 25.0),
                25,
                True,
                f"{n} distinct insider(s) buying within {CLUSTER_DAYS} days",
            )
        )
        change = _ownership_change(buys)
        if change is None:
            components.append(
                Component("ownership_change", 0, 15, False, "post-transaction holdings not stated")
            )
        else:
            components.append(
                Component(
                    "ownership_change",
                    15 * _unit(change[0] / 0.5),
                    15,
                    True,
                    f"buyers' reported holdings increased {change[0]:.1%} "
                    f"(value-weighted over {change[1]} buyer(s), capped at 100%)",
                )
            )
        if issuer.history_since > start - timedelta(days=MIN_HISTORY_COVERAGE_DAYS):
            components.append(
                Component(
                    "buyer_history",
                    0,
                    15,
                    False,
                    f"filing history starts {issuer.history_since}; "
                    f"at least {MIN_HISTORY_COVERAGE_DAYS} days before the window are needed",
                )
            )
        else:
            history_start = max(issuer.history_since, start - timedelta(days=HISTORY_DAYS))
            prior_days: dict[int, set] = defaultdict(set)
            for t in dated:
                if t.signal == "discretionary_buy" and history_start <= t.transaction_date < start:
                    prior_days[t.filing.owner_cik].add(t.transaction_date)
            weight = {0: Decimal(1), 1: Decimal("0.5"), 2: Decimal("0.5")}
            rarity = sum(
                t.value * weight.get(len(prior_days[t.filing.owner_cik]), Decimal("0.2"))
                for t in buys
            )
            rarity = float(rarity / buy_value) if buy_value else 0.0
            components.append(
                Component(
                    "buyer_history",
                    15 * rarity,
                    15,
                    True,
                    f"buyers' prior purchase days since {history_start}: "
                    f"{sorted(len(prior_days[o]) for o in {t.filing.owner_cik for t in buys})}",
                )
            )
    for name, need in (
        ("announcement_timing", "an earnings/news calendar (News engine)"),
        ("value_vs_market_cap", "market data (Milestone 2)"),
    ):
        components.append(Component(name, 0, 10, False, f"unavailable: needs {need}"))

    available_max = sum(c.max_points for c in components if c.available)
    raw = 100 * sum(c.points for c in components if c.available) / available_max if buys else 0.0
    buy_share = float(buy_value / (buy_value + sell_value)) if buys and buy_value > 0 else 0.0
    score = round(raw * buy_share, 1)

    if not buys:
        explanation = (
            f"No qualifying discretionary open-market purchases in the {LOOKBACK_DAYS} days to "
            f"{day}. Grants, exercises, tax withholding, gifts and plan trades are not counted."
        )
    else:
        explanation = (
            f"{len({t.filing.owner_cik for t in buys})} insider(s) made {len(buys)} discretionary "
            f"open-market purchase(s) worth ${buy_value:,.0f} in the {LOOKBACK_DAYS} days to {day}."
        )
        if sells:
            explanation += (
                f" Discretionary sales of ${sell_value:,.0f} in the same period scale the score "
                f"by {buy_share:.2f}."
            )
    return {
        "cik": cik,
        "ticker": issuer.ticker,
        "as_of": as_of.isoformat(),
        "window_days": LOOKBACK_DAYS,
        "score": score,
        "explanation": explanation,
        "components": [asdict(c) | {"points": round(c.points, 1)} for c in components],
        "coverage": round(available_max / sum(c.max_points for c in components), 2),
        "discretionary_buys": _summary(buys, buy_value),
        "discretionary_sells": _summary(sells, sell_value),
        "not_counted": dict(Counter(t.category for t in window if t.signal is None)),
        "evidence": [transaction_dict(t) for t in buys + sells],
        "history_since": issuer.history_since.isoformat(),
        "last_ingested_at": issuer.last_ingested_at.isoformat(),
        "disclaimer": DISCLAIMER,
    }


def _summary(rows: list[InsiderTransaction], value: Decimal) -> dict:
    return {
        "transactions": len(rows),
        "insiders": len({t.filing.owner_cik for t in rows}),
        "value": f"{value:.2f}",
    }


def transaction_dict(t: InsiderTransaction) -> dict:
    f = t.filing
    return {
        "insider": f.owner_name,
        "position": f.officer_title
        or ("Director" if f.is_director else "10% owner" if f.is_ten_percent_owner else None),
        "is_director": f.is_director,
        "is_officer": f.is_officer,
        "is_ten_percent_owner": f.is_ten_percent_owner,
        "company": f.issuer_name,
        "form": f.form_type,
        "security": t.security_title,
        "table": t.table,
        "code": t.code,
        "category": t.category,
        "signal": t.signal,
        "plan_10b5_1": t.plan_10b5_1,
        "plan_basis": t.plan_basis,
        "issues": t.issues,
        "transaction_date": t.transaction_date.isoformat() if t.transaction_date else None,
        "shares": None if t.shares is None else str(t.shares),
        "price": None if t.price is None else str(t.price),
        "value": None if t.value is None else f"{t.value:.2f}",
        "acquired_disposed": t.acquired_disposed,
        "shares_after": None if t.shares_after is None else str(t.shares_after),
        "ownership": t.ownership,
        "footnotes": t.footnotes,
        "filed_date": f.filed_date.isoformat(),
        "accepted_at": f.accepted_at.isoformat(),
        "accession": f.accession,
        "filing_url": f.url,
    }
