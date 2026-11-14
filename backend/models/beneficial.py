"""Beneficial ownership history (SEC Schedules 13D and 13G)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base, UTCDateTime


class BeneficialIssuer(Base):
    """An issuer whose 13D/13G filings have been ingested. Absence means 'never ingested'."""

    __tablename__ = "beneficial_issuer"

    cik: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    ticker: Mapped[str | None] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(Text)
    history_since: Mapped[date] = mapped_column(Date)
    last_ingested_at: Mapped[datetime] = mapped_column(UTCDateTime)
    failed_filings: Mapped[int]  # of the last ingestion; above zero, the history has holes


class BeneficialFiling(Base):
    __tablename__ = "beneficial_filing"

    accession: Mapped[str] = mapped_column(String(20), primary_key=True)
    issuer_cik: Mapped[int] = mapped_column(index=True)
    form: Mapped[str] = mapped_column(String(16))
    schedule: Mapped[str] = mapped_column(String(3))  # "13D" (active) | "13G" (passive)
    is_amendment: Mapped[bool]
    amendment_number: Mapped[int | None]
    # False for filings before December 2024: free-form documents whose contents are not parsed.
    structured: Mapped[bool]
    filer_cik: Mapped[int | None] = mapped_column(index=True)
    filer_name: Mapped[str | None] = mapped_column(Text)
    cusip: Mapped[str | None] = mapped_column(String(16))
    security_title: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[date | None] = mapped_column(Date)
    filed_date: Mapped[date] = mapped_column(Date)
    # When the filing became public (UTC). Nothing may use it before this moment.
    accepted_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    rule: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    issues: Mapped[list] = mapped_column(JSON)
    url: Mapped[str] = mapped_column(Text)

    persons: Mapped[list["BeneficialOwner"]] = relationship(
        back_populates="filing", cascade="all, delete-orphan", order_by="BeneficialOwner.row_index"
    )


class BeneficialOwner(Base):
    """One reporting person on a filing. Persons on one filing usually report the same shares."""

    __tablename__ = "beneficial_owner"
    __table_args__ = (UniqueConstraint("accession", "row_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    accession: Mapped[str] = mapped_column(ForeignKey("beneficial_filing.accession"), index=True)
    row_index: Mapped[int]
    name: Mapped[str] = mapped_column(Text)
    cik: Mapped[int | None]
    shares: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    person_type: Mapped[str | None] = mapped_column(Text)
    sole_voting: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    shared_voting: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    sole_dispositive: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    shared_dispositive: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    issues: Mapped[list] = mapped_column(JSON)

    filing: Mapped[BeneficialFiling] = relationship(back_populates="persons")
