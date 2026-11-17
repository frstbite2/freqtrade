"""Institutional holdings history (SEC Form 13F)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base, UTCDateTime


_Number = Numeric(28, 4)


class InstitutionalManager(Base):
    """A manager whose 13F filings have been ingested. Absence means 'never ingested'."""

    __tablename__ = "institutional_manager"

    cik: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text)
    history_since: Mapped[date] = mapped_column(Date)
    last_ingested_at: Mapped[datetime] = mapped_column(UTCDateTime)
    failed_filings: Mapped[int]  # of the last ingestion; above zero, the history has holes


class InstitutionalFiling(Base):
    __tablename__ = "institutional_filing"

    accession: Mapped[str] = mapped_column(String(20), primary_key=True)
    manager_cik: Mapped[int] = mapped_column(index=True)
    form: Mapped[str] = mapped_column(String(10))
    period: Mapped[date] = mapped_column(Date, index=True)  # quarter end the holdings are as of
    filed_date: Mapped[date] = mapped_column(Date)
    # When the filing became public (UTC). Nothing may use it before this moment.
    accepted_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    report_type: Mapped[str] = mapped_column(Text)
    is_amendment: Mapped[bool]
    amendment_type: Mapped[str | None] = mapped_column(Text)
    confidential_omitted: Mapped[bool | None]
    value_multiplier: Mapped[int]
    entry_total: Mapped[int | None]
    value_total: Mapped[Decimal | None] = mapped_column(_Number)
    issues: Mapped[list] = mapped_column(JSON)
    url: Mapped[str] = mapped_column(Text)

    holdings: Mapped[list["InstitutionalHolding"]] = relationship(
        back_populates="filing", cascade="all, delete-orphan"
    )

    @property
    def has_holdings_table(self) -> bool:
        return self.form.startswith("13F-HR")


class InstitutionalHolding(Base):
    """One row of a 13F information table. A manager may report one security on several rows."""

    __tablename__ = "institutional_holding"
    __table_args__ = (UniqueConstraint("accession", "row_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    accession: Mapped[str] = mapped_column(ForeignKey("institutional_filing.accession"), index=True)
    row_index: Mapped[int]
    issuer_name: Mapped[str] = mapped_column(Text)
    title_of_class: Mapped[str | None] = mapped_column(Text)
    cusip: Mapped[str] = mapped_column(String(16), index=True)
    value: Mapped[Decimal] = mapped_column(_Number)  # US dollars
    amount: Mapped[Decimal] = mapped_column(_Number)
    amount_type: Mapped[str | None] = mapped_column(String(8))
    put_call: Mapped[str | None] = mapped_column(String(8))
    discretion: Mapped[str | None] = mapped_column(Text)
    other_managers: Mapped[str | None] = mapped_column(Text)
    voting_sole: Mapped[Decimal | None] = mapped_column(_Number)
    voting_shared: Mapped[Decimal | None] = mapped_column(_Number)
    voting_none: Mapped[Decimal | None] = mapped_column(_Number)
    issues: Mapped[list] = mapped_column(JSON)

    filing: Mapped[InstitutionalFiling] = relationship(back_populates="holdings")
