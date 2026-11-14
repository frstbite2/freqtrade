"""Ingest an issuer's Schedule 13D/13G filings from SEC EDGAR.

Usage: python -m backend.services.beneficial_ownership.ingest GME CVNA --since 2024-12-01
With no ticker, the `watchlist` of config/settings.yaml is ingested.
"""

import argparse
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import get_settings
from backend.core.logging import setup_logging
from backend.database.session import init_db, make_engine
from backend.models import record_audit
from backend.models.beneficial import BeneficialFiling, BeneficialIssuer, BeneficialOwner
from backend.services.beneficial_ownership.parser import (
    FORMS,
    STRUCTURED_FORMS,
    ParsedSchedule,
    ScheduleParseError,
    parse_header,
    parse_schedule,
    schedule_of,
)
from backend.services.edgar import EdgarClient, EdgarError, FilingRef, filing_index_url


logger = logging.getLogger(__name__)

DEFAULT_HISTORY_DAYS = 3 * 365


@dataclass
class IngestReport:
    ticker: str
    cik: int
    name: str
    since: date
    listed: int = 0
    stored: int = 0
    already_stored: int = 0
    unstructured: int = 0  # of `stored`: older free-form filings kept as dated index entries
    other_issuer: int = 0  # the company reporting its own stake in a different issuer
    failed: dict[str, str] = field(default_factory=dict)  # accession -> reason; retried next run


def ingest_issuer(session: Session, client: EdgarClient, ticker: str, since: date) -> IngestReport:
    ticker = ticker.strip().upper()
    cik = client.ticker_to_cik(ticker)
    if cik is None:
        raise EdgarError(f"ticker {ticker!r} is not in SEC's company list")
    name, refs = client.filings(cik, since, FORMS)
    report = IngestReport(ticker=ticker, cik=cik, name=name, since=since, listed=len(refs))
    stored = set(
        session.scalars(
            select(BeneficialFiling.accession).where(BeneficialFiling.issuer_cik == cik)
        )
    )
    for ref in refs:
        if ref.accession in stored:
            report.already_stored += 1
            continue
        try:
            parsed = None
            if ref.form in STRUCTURED_FORMS:
                parsed = parse_schedule(client.primary_xml(cik, ref, b"<edgarSubmission"))
                if parsed.issuer_cik != cik:
                    report.other_issuer += 1
                    continue
                if parsed.form != ref.form:
                    raise ScheduleParseError(f"index says {ref.form}, document says {parsed.form}")
                filer = (parsed.filer_cik, parsed.persons[0].name)
            else:
                # Free-form document: its contents are not parsed. EDGAR's header still says who
                # filed it and about which company (a company's index also lists its own stakes).
                subject, filer_cik, filer_name = parse_header(
                    client.filing_header(cik, ref.accession)
                )
                filer = (filer_cik, filer_name)
                if subject != cik:
                    report.other_issuer += 1
                    continue
                report.unstructured += 1
            session.add(_to_model(cik, ref, parsed, filer))
            session.commit()  # one filing is stored completely or not at all
            stored.add(ref.accession)
            report.stored += 1
        except (EdgarError, ScheduleParseError) as exc:
            session.rollback()
            report.failed[ref.accession] = str(exc)
            logger.warning("skipped %s: %s", ref.accession, exc)

    issuer = session.get(BeneficialIssuer, cik)
    if issuer is None:
        issuer = BeneficialIssuer(cik=cik, history_since=since)
        session.add(issuer)
    issuer.ticker, issuer.name = ticker, name
    issuer.history_since = min(issuer.history_since, since)
    issuer.last_ingested_at = datetime.now(UTC)
    issuer.failed_filings = len(report.failed)
    record_audit(  # commits the issuer row with it
        session,
        "ingest",
        "beneficial.ingest",
        ticker=ticker,
        cik=cik,
        since=since.isoformat(),
        listed=report.listed,
        stored=report.stored,
        unstructured=report.unstructured,
        other_issuer=report.other_issuer,
        failed=report.failed,
    )
    return report


def _to_model(
    cik: int, ref: FilingRef, parsed: ParsedSchedule | None, filer: tuple[int | None, str]
) -> BeneficialFiling:
    filing = BeneficialFiling(
        accession=ref.accession,
        issuer_cik=cik,
        form=ref.form,
        schedule=schedule_of(ref.form),
        is_amendment=ref.form.endswith("/A"),
        structured=parsed is not None,
        filer_cik=filer[0],
        filer_name=filer[1],
        filed_date=ref.filed_date,
        accepted_at=ref.accepted_at,
        issues=[] if parsed else ["free-form filing: shares and percentage are not parsed"],
        url=filing_index_url(cik, ref.accession),
    )
    if parsed is None:
        return filing
    filing.amendment_number = parsed.amendment_number
    filing.cusip = (parsed.cusip or "")[:16] or None
    filing.security_title = parsed.security_title
    filing.event_date = parsed.event_date
    filing.rule = parsed.rule
    filing.purpose = parsed.purpose
    filing.issues = parsed.issues
    filing.persons = [
        BeneficialOwner(
            row_index=i,
            name=p.name,
            cik=p.cik,
            shares=p.shares,
            percent=p.percent,
            person_type=p.person_type,
            sole_voting=p.sole_voting,
            shared_voting=p.shared_voting,
            sole_dispositive=p.sole_dispositive,
            shared_dispositive=p.shared_dispositive,
            issues=p.issues,
        )
        for i, p in enumerate(parsed.persons)
    ]
    return filing


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("tickers", nargs="*")
    args.add_argument(
        "--since",
        type=date.fromisoformat,
        default=datetime.now(UTC).date() - timedelta(days=DEFAULT_HISTORY_DAYS),
        help="ingest filings filed on or after this date (default: three years ago)",
    )
    opts = args.parse_args()
    settings = get_settings()
    setup_logging(settings.app.log_level, json_format=False)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    engine = make_engine(settings.app.database_url)
    init_db(engine)
    client = EdgarClient(settings.app.sec_user_agent, settings.app.edgar_cache_dir)
    try:
        with sessionmaker(engine)() as session:
            for ticker in opts.tickers or settings.app.watchlist:
                r = ingest_issuer(session, client, ticker, opts.since)
                print(
                    f"{r.ticker} (CIK {r.cik}, {r.name}): {r.listed} listed since {r.since}, "
                    f"{r.stored} stored ({r.unstructured} free-form), {r.already_stored} already "
                    f"stored, {r.other_issuer} other-issuer, {len(r.failed)} failed"
                )
                for accession, reason in r.failed.items():
                    print(f"  FAILED {accession}: {reason}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
