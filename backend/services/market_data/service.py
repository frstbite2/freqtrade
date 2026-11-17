"""Price bars for the rest of the platform: fetch once, check, store, and serve from storage.

What is cached and for how long:
- Only bars whose period ended at least SETTLE ago are stored; the newest bars can still change
  (late trade reports, a bar still forming) and are fetched fresh every time.
- Raw (unadjusted) bars never change, so their coverage never expires.
- Adjusted bars are rewritten by every later split or dividend, so their coverage expires after
  ADJUSTED_MAX_AGE and the range is fetched again.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models.market import PriceBar, PriceCoverage
from backend.services.market_data.base import (
    TIMEFRAMES,
    Bar,
    MarketDataProvider,
    ProviderNotConfigured,
    Quote,
    check_request,
    normalize_symbol,
)
from backend.services.market_data.integrity import check_bars


logger = logging.getLogger(__name__)

SETTLE = timedelta(minutes=20)
ADJUSTED_MAX_AGE = timedelta(hours=24)
MAX_BARS_PER_REQUEST = 50_000
STALE_QUOTE = timedelta(minutes=15)

Range = tuple[datetime, datetime]


@dataclass
class BarsResult:
    symbol: str
    timeframe: str
    adjustment: str
    source: str
    bars: list[Bar]
    fetched_ranges: int = 0  # 0 means everything came from storage
    rejected: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def uncovered(wanted: Range, covered: list[Range]) -> list[Range]:
    """The parts of `wanted` that no range in `covered` includes."""
    gaps = [wanted]
    for c_start, c_end in covered:
        remaining = []
        for start, end in gaps:
            if c_end <= start or c_start >= end:
                remaining.append((start, end))
                continue
            if start < c_start:
                remaining.append((start, c_start))
            if c_end < end:
                remaining.append((c_end, end))
        gaps = remaining
    return sorted(gaps)


class MarketDataService:
    def __init__(self, provider: MarketDataProvider | None, source: str | None = None) -> None:
        self._provider = provider
        self.source = source or (f"{provider.name}:{provider.feed}" if provider else None)

    def _require_provider(self) -> MarketDataProvider:
        if self._provider is None:
            raise ProviderNotConfigured(
                "No market data provider is configured, so prices are unavailable."
            )
        return self._provider

    def get_bars(
        self,
        session: Session,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        adjustment: str = "raw",
        now: datetime | None = None,
    ) -> BarsResult:
        symbol = normalize_symbol(symbol)
        check_request(timeframe, start, end, adjustment)
        now = now or datetime.now(UTC)
        start, end = start.astimezone(UTC), min(end.astimezone(UTC), now)
        if start >= end:
            raise ValueError("start must be in the past")
        length = TIMEFRAMES[timeframe]
        if (end - start) / length > MAX_BARS_PER_REQUEST:
            raise ValueError(f"range too large: more than {MAX_BARS_PER_REQUEST} {timeframe} bars")
        if self.source is None:
            self._require_provider()
        result = BarsResult(symbol, timeframe, adjustment, self.source, [])
        key = (symbol, timeframe, adjustment, self.source)

        # Bars starting at or after this may still change, so they are never stored.
        settled_end = max(start, min(end, now - SETTLE - length))
        if start < settled_end:
            for gap in uncovered((start, settled_end), self._fresh_coverage(session, key, now)):
                self._fetch_and_store(session, key, gap, now, result)
            result.bars = self._stored(session, key, start, settled_end)
        if settled_end < end:
            report = check_bars(
                self._require_provider().get_bars(symbol, timeframe, settled_end, end, adjustment),
                symbol,
                timeframe,
                settled_end,
                end,
            )
            self._note(result, report)
            result.bars += report.accepted
        return result

    def _fresh_coverage(self, session: Session, key: tuple, now: datetime) -> list[Range]:
        symbol, timeframe, adjustment, source = key
        query = select(PriceCoverage.start, PriceCoverage.end).where(
            PriceCoverage.symbol == symbol,
            PriceCoverage.timeframe == timeframe,
            PriceCoverage.adjustment == adjustment,
            PriceCoverage.source == source,
        )
        if adjustment != "raw":
            query = query.where(PriceCoverage.fetched_at >= now - ADJUSTED_MAX_AGE)
        return [(row.start, row.end) for row in session.execute(query)]

    def _fetch_and_store(
        self, session: Session, key: tuple, gap: Range, now: datetime, result: BarsResult
    ) -> None:
        symbol, timeframe, adjustment, source = key
        start, end = gap
        report = check_bars(
            self._require_provider().get_bars(symbol, timeframe, start, end, adjustment),
            symbol,
            timeframe,
            start,
            end,
        )
        self._note(result, report)
        result.fetched_ranges += 1
        same_key = (
            PriceBar.symbol == symbol,
            PriceBar.timeframe == timeframe,
            PriceBar.adjustment == adjustment,
            PriceBar.source == source,
        )
        # Replace whatever an expired fetch left in this range, in one transaction.
        session.execute(delete(PriceBar).where(*same_key, PriceBar.ts >= start, PriceBar.ts < end))
        session.execute(
            delete(PriceCoverage).where(
                PriceCoverage.symbol == symbol,
                PriceCoverage.timeframe == timeframe,
                PriceCoverage.adjustment == adjustment,
                PriceCoverage.source == source,
                PriceCoverage.start >= start,
                PriceCoverage.end <= end,
            )
        )
        session.add_all(
            PriceBar(
                symbol=symbol,
                timeframe=timeframe,
                adjustment=adjustment,
                source=source,
                ts=bar.ts,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                trade_count=bar.trade_count,
                vwap=bar.vwap,
            )
            for bar in report.accepted
        )
        session.add(
            PriceCoverage(
                symbol=symbol,
                timeframe=timeframe,
                adjustment=adjustment,
                source=source,
                start=start,
                end=end,
                fetched_at=now,
                rejected_bars=len(report.rejected),
            )
        )
        session.commit()

    @staticmethod
    def _note(result: BarsResult, report) -> None:
        for bar, problems in report.rejected:
            logger.warning(
                "rejected %s %s bar at %s: %s", bar.symbol, bar.timeframe, bar.ts, problems
            )
            result.rejected.append({"ts": bar.ts.isoformat(), "problems": problems})
        result.warnings += report.warnings

    @staticmethod
    def _stored(session: Session, key: tuple, start: datetime, end: datetime) -> list[Bar]:
        symbol, timeframe, adjustment, source = key
        rows = session.scalars(
            select(PriceBar)
            .where(
                PriceBar.symbol == symbol,
                PriceBar.timeframe == timeframe,
                PriceBar.adjustment == adjustment,
                PriceBar.source == source,
                PriceBar.ts >= start,
                PriceBar.ts < end,
            )
            .order_by(PriceBar.ts)
        )
        return [
            Bar(
                symbol=r.symbol,
                timeframe=r.timeframe,
                ts=r.ts,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                trade_count=r.trade_count,
                vwap=r.vwap,
            )
            for r in rows
        ]

    def get_latest_quote(self, symbol: str, now: datetime | None = None) -> dict:
        quote: Quote = self._require_provider().get_latest_quote(normalize_symbol(symbol))
        now = now or datetime.now(UTC)
        problems = []
        if min(quote.bid_price, quote.ask_price) <= 0:
            problems.append("non_positive_price")  # a one-sided or empty book
        elif quote.ask_price < quote.bid_price:
            problems.append("crossed_market")
        if min(quote.bid_size, quote.ask_size) < 0:
            problems.append("negative_size")
        age = (now - quote.ts).total_seconds()
        if age > STALE_QUOTE.total_seconds():
            problems.append("stale")  # normal outside market hours; never treat as a live price
        return {
            "symbol": quote.symbol,
            "source": self.source,
            "ts": quote.ts.isoformat(),
            "age_seconds": round(age, 1),
            "bid_price": str(quote.bid_price),
            "bid_size": str(quote.bid_size),
            "ask_price": str(quote.ask_price),
            "ask_size": str(quote.ask_size),
            "usable": not problems,
            "problems": problems,
        }
