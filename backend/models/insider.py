"""Insider filing history (SEC Forms 3, 4, 5 and amendments)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base, UTCDateTime


# shortcut: SQLite stores NUMERIC as float (about 15 significant digits), enough for share
# counts and prices in dev/tests; PostgreSQL stores it exactly.
_Number = Numeric(24, 6)


class InsiderIssuer(Base):
    """An issuer whose filings have been ingested. Absence means 'never ingested', not 'quiet'."""

    __tablename__ = "insider_issuer"

    cik: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    ticker: Mapped[str | None] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(Text)
    history_since: Mapped[date] = mapped_column(Date)  # filings filed on/after this are held
    last_ingested_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Filings the last ingestion listed but could not store. Above zero, the history has holes.
    failed_filings: Mapped[int]


class InsiderFiling(Base):
    __tablename__ = "insider_filing"

    accession: Mapped[str] = mapped_column(String(20), primary_key=True)
    form_type: Mapped[str] = mapped_column(String(4))
    issuer_cik: Mapped[int] = mapped_column(index=True)
    issuer_name: Mapped[str] = mapped_column(Text)
    issuer_ticker: Mapped[str | None] = mapped_column(Text)
    period_of_report: Mapped[date | None] = mapped_column(Date)
    filed_date: Mapped[date] = mapped_column(Date)
    # When the filing became public (UTC). Backtests may only use rows with accepted_at <= now.
    accepted_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    original_filed_date: Mapped[date | None] = mapped_column(Date)  # amendments only
    aff10b5one: Mapped[bool | None]
    # First reporting owner identifies the filer; joint filers are kept in `owners`.
    owner_cik: Mapped[int] = mapped_column(index=True)
    owner_name: Mapped[str] = mapped_column(Text)
    is_director: Mapped[bool]
    is_officer: Mapped[bool]
    is_ten_percent_owner: Mapped[bool]
    officer_title: Mapped[str | None] = mapped_column(Text)
    owners: Mapped[list] = mapped_column(JSON)
    remarks: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    classifier_version: Mapped[int]  # rules that produced the rows' category and signal

    transactions: Mapped[list["InsiderTransaction"]] = relationship(
        back_populates="filing",
        cascade="all, delete-orphan",
        order_by="InsiderTransaction.row_index",
    )

    @property
    def is_amendment(self) -> bool:
        return self.form_type.endswith("/A")


class InsiderTransaction(Base):
    """One row of Table I or II: a transaction, or a holding with no transaction."""

    __tablename__ = "insider_transaction"
    __table_args__ = (UniqueConstraint("accession", "row_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    accession: Mapped[str] = mapped_column(ForeignKey("insider_filing.accession"), index=True)
    row_index: Mapped[int]
    table: Mapped[str] = mapped_column(String(16))
    is_holding: Mapped[bool]
    security_title: Mapped[str | None] = mapped_column(Text)
    transaction_date: Mapped[date | None] = mapped_column(Date, index=True)
    code: Mapped[str | None] = mapped_column(String(2))
    equity_swap: Mapped[bool]
    shares: Mapped[Decimal | None] = mapped_column(_Number)
    price: Mapped[Decimal | None] = mapped_column(_Number)
    acquired_disposed: Mapped[str | None] = mapped_column(String(1))
    shares_after: Mapped[Decimal | None] = mapped_column(_Number)
    ownership: Mapped[str | None] = mapped_column(String(1))
    nature_of_ownership: Mapped[str | None] = mapped_column(Text)
    exercise_price: Mapped[Decimal | None] = mapped_column(_Number)
    underlying_title: Mapped[str | None] = mapped_column(Text)
    underlying_shares: Mapped[Decimal | None] = mapped_column(_Number)
    footnotes: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), index=True)
    plan_10b5_1: Mapped[bool]
    plan_basis: Mapped[str | None] = mapped_column(String(24))
    issues: Mapped[list] = mapped_column(JSON)
    signal: Mapped[str | None] = mapped_column(String(20), index=True)

    filing: Mapped[InsiderFiling] = relationship(back_populates="transactions")

    @property
    def value(self) -> Decimal | None:
        if self.shares is None or self.price is None:
            return None
        return self.shares * self.price
