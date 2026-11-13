"""Ingest an issuer's Form 3/4/5 filings from SEC EDGAR into the filing-history database.

Usage: python -m backend.services.insider_intelligence.ingest AAPL NKE --since 2022-01-01
"""

import argparse
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import get_settings
from backend.core.logging import setup_logging
from backend.database.session import init_db, make_engine
from backend.models.insider import InsiderFiling, InsiderIssuer, InsiderTransaction
from backend.services.edgar import (
    EdgarClient,
    EdgarError,
    FilingRef,
    filing_index_url,
)
from backend.services.insider_intelligence import classify
from backend.services.insider_intelligence.parser import (
    FilingParseError,
    ParsedFiling,
    parse_ownership_xml,
)


logger = logging.getLogger(__name__)

DEFAULT_HISTORY_DAYS = 3 * 365


@dataclass
class IngestReport:
    ticker: str
    cik: int
    name: str
    since: date
    listed: int = 0  # ownership filings in the EDGAR index for the period
    stored: int = 0
    already_stored: int = 0
    reclassified: int = 0  # of `stored`: replaced because the classification rules changed
    other_issuer: int = 0  # the company reporting as an owner of a different issuer
    no_xml: list[str] = field(default_factory=list)  # paper-era filings without structured data
    failed: dict[str, str] = field(default_factory=dict)  # accession -> reason; retried next run

    @property
    def complete(self) -> bool:
        return not self.failed


def ingest_issuer(session: Session, client: EdgarClient, ticker: str, since: date) -> IngestReport:
    ticker = ticker.strip().upper()
    cik = client.ticker_to_cik(ticker)
    if cik is None:
        raise EdgarError(f"ticker {ticker!r} is not in SEC's company list")
    name, refs = client.ownership_filings(cik, since)
    report = IngestReport(ticker=ticker, cik=cik, name=name, since=since, listed=len(refs))
    stored = set(
        session.scalars(
            select(InsiderFiling.accession).where(
                InsiderFiling.issuer_cik == cik,
                InsiderFiling.classifier_version == classify.CLASSIFIER_VERSION,
            )
        )
    )
    for ref in refs:
        if ref.accession in stored:
            report.already_stored += 1
        elif not ref.primary_document.lower().endswith(".xml"):
            report.no_xml.append(ref.accession)
        else:
            try:
                parsed = parse_ownership_xml(client.ownership_xml(cik, ref))
                if parsed.issuer_cik != cik:
                    report.other_issuer += 1
                    continue
                if parsed.document_type != ref.form:
                    raise FilingParseError(
                        f"index says form {ref.form}, document says {parsed.document_type}"
                    )
                classify.classify_filing(parsed, ref.filed_date)
                outdated = session.get(InsiderFiling, ref.accession)
                if outdated is not None:  # classified under older rules: replace it
                    session.delete(outdated)
                    session.flush()
                    report.reclassified += 1
                session.add(_to_model(parsed, ref))
                session.commit()  # one filing is stored completely or not at all
                stored.add(ref.accession)  # an index that lists a filing twice stores it once
                report.stored += 1
            except (EdgarError, FilingParseError) as exc:
                session.rollback()
                report.failed[ref.accession] = str(exc)
                logger.warning("skipped %s: %s", ref.accession, exc)

    issuer = session.get(InsiderIssuer, cik)
    if issuer is None:
        issuer = InsiderIssuer(cik=cik, history_since=since)
        session.add(issuer)
    issuer.ticker, issuer.name = ticker, name
    issuer.history_since = min(issuer.history_since, since)
    issuer.last_ingested_at = datetime.now(UTC)
    session.commit()
    return report


def _to_model(parsed: ParsedFiling, ref: FilingRef) -> InsiderFiling:
    first = parsed.owners[0]
    title = next((o.officer_title for o in parsed.owners if o.officer_title), None)
    return InsiderFiling(
        accession=ref.accession,
        form_type=parsed.document_type,
        issuer_cik=parsed.issuer_cik,
        issuer_name=parsed.issuer_name,
        issuer_ticker=parsed.issuer_ticker,
        period_of_report=parsed.period_of_report,
        filed_date=ref.filed_date,
        accepted_at=ref.accepted_at,
        original_filed_date=parsed.original_filed_date,
        aff10b5one=parsed.aff10b5one,
        owner_cik=first.cik,
        owner_name=first.name,
        is_director=any(o.is_director for o in parsed.owners),
        is_officer=any(o.is_officer for o in parsed.owners),
        is_ten_percent_owner=any(o.is_ten_percent_owner for o in parsed.owners),
        officer_title=title,
        owners=[asdict(o) for o in parsed.owners],
        remarks=parsed.remarks,
        url=filing_index_url(parsed.issuer_cik, ref.accession),
        classifier_version=classify.CLASSIFIER_VERSION,
        transactions=[
            InsiderTransaction(
                row_index=r.row_index,
                table=r.table,
                is_holding=r.is_holding,
                security_title=r.security_title,
                transaction_date=r.transaction_date,
                code=r.code,
                equity_swap=r.equity_swap,
                shares=r.shares,
                price=r.price,
                acquired_disposed=r.acquired_disposed,
                shares_after=r.shares_after,
                ownership=r.ownership,
                nature_of_ownership=r.nature_of_ownership,
                exercise_price=r.exercise_price,
                underlying_title=r.underlying_title,
                underlying_shares=r.underlying_shares,
                footnotes=r.footnotes,
                category=r.category,
                plan_10b5_1=r.plan_10b5_1,
                plan_basis=r.plan_basis,
                issues=r.issues,
                signal=r.signal,
            )
            for r in parsed.rows
        ],
    )


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("tickers", nargs="+")
    args.add_argument(
        "--since",
        type=date.fromisoformat,
        default=datetime.now(UTC).date() - timedelta(days=DEFAULT_HISTORY_DAYS),
        help="ingest filings filed on or after this date (default: three years ago)",
    )
    opts = args.parse_args()
    settings = get_settings()
    setup_logging(settings.app.log_level, json_format=False)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request is noise
    engine = make_engine(settings.app.database_url)
    init_db(engine)
    client = EdgarClient(settings.app.sec_user_agent, settings.app.edgar_cache_dir)
    try:
        with sessionmaker(engine)() as session:
            for ticker in opts.tickers:
                r = ingest_issuer(session, client, ticker, opts.since)
                print(
                    f"{r.ticker} (CIK {r.cik}, {r.name}): {r.listed} listed since {r.since}, "
                    f"{r.stored} stored ({r.reclassified} re-classified), "
                    f"{r.already_stored} already stored, "
                    f"{r.other_issuer} other-issuer, {len(r.no_xml)} without XML, "
                    f"{len(r.failed)} failed"
                )
                for accession, reason in r.failed.items():
                    print(f"  FAILED {accession}: {reason}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
