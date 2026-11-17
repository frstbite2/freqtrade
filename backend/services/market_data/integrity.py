"""Integrity checks for price bars.

A bar that is internally impossible is rejected and reported; it is never repaired or silently
dropped. Things that are unusual but can be legitimate are reported as warnings.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import pairwise

from backend.services.market_data.base import TIMEFRAMES, Bar


JUMP_WARNING = Decimal(
    "0.5"
)  # close-to-close move that deserves a look (often an unadjusted split)


@dataclass
class IntegrityReport:
    accepted: list[Bar] = field(default_factory=list)  # oldest first, unique timestamps
    rejected: list[tuple[Bar, list[str]]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _problems(bar: Bar, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[str]:
    problems = []
    if bar.symbol != symbol:
        problems.append("wrong_symbol")
    if bar.timeframe != timeframe:
        problems.append("wrong_timeframe")
    if bar.ts.tzinfo is None:
        problems.append("naive_timestamp")
    elif not start <= bar.ts < end:
        problems.append("outside_requested_range")
    numbers = (bar.open, bar.high, bar.low, bar.close, bar.volume)
    if not all(n.is_finite() for n in numbers) or (
        bar.vwap is not None and not bar.vwap.is_finite()
    ):
        return [*problems, "non_finite_number"]
    if min(bar.open, bar.high, bar.low, bar.close) <= 0:
        problems.append("non_positive_price")
    if bar.volume < 0:
        problems.append("negative_volume")
    if bar.trade_count is not None and bar.trade_count < 0:
        problems.append("negative_trade_count")
    if bar.high < bar.low:
        problems.append("high_below_low")
    else:
        if not bar.low <= bar.open <= bar.high:
            problems.append("open_outside_high_low")
        if not bar.low <= bar.close <= bar.high:
            problems.append("close_outside_high_low")
    return problems


def check_bars(
    bars: list[Bar], symbol: str, timeframe: str, start: datetime, end: datetime
) -> IntegrityReport:
    report = IntegrityReport()
    groups: dict[datetime, list[Bar]] = defaultdict(list)
    for bar in bars:
        groups[bar.ts].append(bar)
    for group in groups.values():
        # The same bar sent twice is harmless; two different bars for one moment are not.
        conflicting = any(bar != group[0] for bar in group)
        for bar in group if conflicting else group[:1]:
            problems = _problems(bar, symbol, timeframe, start, end)
            if conflicting:
                problems.append("conflicting_duplicate_timestamp")
            if problems:
                report.rejected.append((bar, problems))
            else:
                report.accepted.append(bar)
    report.accepted.sort(key=lambda bar: bar.ts)

    repeats = len(bars) - len(groups)
    if repeats:
        report.warnings.append(f"{repeats} repeated timestamp(s) in the provider response")
    aware = [bar.ts for bar in bars if bar.ts.tzinfo is not None]
    if aware != sorted(aware):
        report.warnings.append("provider returned bars out of chronological order")
    report.warnings += _warnings(report.accepted, timeframe, start, end)
    return report


def _warnings(bars: list[Bar], timeframe: str, start: datetime, end: datetime) -> list[str]:
    warnings = []
    length = TIMEFRAMES[timeframe]
    if length < timedelta(hours=1):
        minutes = int(length.total_seconds() // 60)
        off_grid = [b for b in bars if b.ts.second or b.ts.microsecond or b.ts.minute % minutes]
        if off_grid:
            warnings.append(f"{len(off_grid)} bar(s) do not start on a {timeframe} boundary")
    for previous, bar in pairwise(bars):
        move = abs(bar.close / previous.close - 1)
        if move > JUMP_WARNING:
            warnings.append(
                f"close moved {move:.0%} between {previous.ts.date()} and {bar.ts.date()} "
                "(check for an unadjusted split or bad data)"
            )
    out_of_range_vwap = [b for b in bars if b.vwap is not None and not b.low <= b.vwap <= b.high]
    if out_of_range_vwap:
        warnings.append(f"{len(out_of_range_vwap)} bar(s) have a VWAP outside their high-low range")
    if timeframe == "1d":
        # shortcut: weekdays stand in for trading days, so each market holiday is counted too;
        # replace with the exchange calendar once a broker connection provides one.
        have = {b.ts.date() for b in bars}
        day, missing = start.date(), 0
        while day < end.date():
            missing += day.weekday() < 5 and day not in have
            day += timedelta(days=1)
        if missing:
            warnings.append(
                f"{missing} weekday(s) in the range have no daily bar "
                "(market holidays are expected; anything else is a gap)"
            )
    return warnings
