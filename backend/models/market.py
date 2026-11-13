"""Stored price bars and the record of which ranges have been fetched."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base, UTCDateTime


_Price = Numeric(24, 8)


class PriceBar(Base):
    __tablename__ = "price_bar"

    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(4), primary_key=True)
    adjustment: Mapped[str] = mapped_column(String(8), primary_key=True)
    # Provider and feed, e.g. "alpaca:iex". Volumes from different feeds are not comparable
    # (IEX is one exchange; SIP is the whole market), so they are never mixed.
    source: Mapped[str] = mapped_column(String(24), primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, primary_key=True)  # start of the bar
    open: Mapped[Decimal] = mapped_column(_Price)
    high: Mapped[Decimal] = mapped_column(_Price)
    low: Mapped[Decimal] = mapped_column(_Price)
    close: Mapped[Decimal] = mapped_column(_Price)
    volume: Mapped[Decimal] = mapped_column(_Price)
    trade_count: Mapped[int | None]
    vwap: Mapped[Decimal | None] = mapped_column(_Price)


class PriceCoverage(Base):
    """A range that was fetched from the provider. Without it, 'no bars stored' could mean
    either 'nothing traded' or 'never asked'."""

    __tablename__ = "price_coverage"
    __table_args__ = (
        Index("ix_price_coverage_key", "symbol", "timeframe", "adjustment", "source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(10))
    timeframe: Mapped[str] = mapped_column(String(4))
    adjustment: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(24))
    start: Mapped[datetime] = mapped_column(UTCDateTime)
    end: Mapped[datetime] = mapped_column(UTCDateTime)  # exclusive
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime)
    rejected_bars: Mapped[int]  # bars the provider sent that failed integrity checks
