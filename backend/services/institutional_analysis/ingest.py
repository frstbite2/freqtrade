"""Ingest investment managers' Form 13F filings from SEC EDGAR.

Usage: python -m backend.services.institutional_analysis.ingest [CIK ...] --since 2024-01-01
With no CIK, the `tracked_managers` of config/settings.yaml are ingested.
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
from backend.models.institutional import (
    InstitutionalFiling,
    InstitutionalHolding,
    InstitutionalManager,
)
from backend.services.edgar import EdgarClient, EdgarError, FilingRef, filing_index_url
from backend.services.institutional_analysis.parser import (
    FORMS,
    Form13FError,
    Parsed13F,
    parse_13f,
)


logger = logging.getLogger(__name__)

DEFAULT_HISTORY_DAYS = 2 * 365 + 60  # eight quarters and their filing delay


@dataclass
class IngestReport:
    cik: int
    name: str
    since: date
    listed: int = 0
    stored: int = 0
    already_stored: int = 0
    with_issues: list[str] = field(default_factory=list)  # stored, but totals did not reconcile
    failed: dict[str, str] = field(default_factory=dict)  # accession -> reason; retried next run


def ingest_manager(session: Session, client: EdgarClient, cik: int, since: date) -> IngestReport:
    name, refs = client.filings(cik, since, FORMS)
    report = IngestReport(cik=cik, name=name, since=since, listed=len(refs))
    stored = set(
        session.scalars(
            select(InstitutionalFiling.accession).where(InstitutionalFiling.manager_cik == cik)
        )
    )
    for ref in refs:
        if ref.accession in stored:
            report.already_stored += 1
            continue
        try:
            parsed = parse_13f(client.submission_text(cik, ref.accession), ref.filed_date)
            if parsed.form != ref.form:
                raise Form13FError(f"index says {ref.form}, document says {parsed.form}")
            session.add(_to_model(cik, parsed, ref))
            session.commit()  # one filing is stored completely or not at all
            stored.add(ref.accession)
            report.stored += 1
            if parsed.issues:
                report.with_issues.append(ref.accession)
                logger.warning("%s stored with issues: %s", ref.accession, parsed.issues)
        except (EdgarError, Form13FError) as exc:
            session.rollback()
            report.failed[ref.accession] = str(exc)
            logger.warning("skipped %s: %s", ref.accession, exc)

    manager = session.get(InstitutionalManager, cik)
    if manager is None:
        manager = InstitutionalManager(cik=cik, history_since=since)
        session.add(manager)
    manager.name = name
    manager.history_since = min(manager.history_since, since)
    manager.last_ingested_at = datetime.now(UTC)
    manager.failed_filings = len(report.failed)
    record_audit(  # commits the manager row with it
        session,
        "ingest",
        "institutional.ingest",
        cik=cik,
        name=name,
        since=since.isoformat(),
        listed=report.listed,
        stored=report.stored,
        with_issues=report.with_issues,
        failed=report.failed,
    )
    return report


def _to_model(cik: int, parsed: Parsed13F, ref: FilingRef) -> InstitutionalFiling:
    return InstitutionalFiling(
        accession=ref.accession,
        manager_cik=cik,
        form=parsed.form,
        period=parsed.period,
        filed_date=ref.filed_date,
        accepted_at=ref.accepted_at,
        report_type=parsed.report_type,
        is_amendment=parsed.is_amendment,
        amendment_type=parsed.amendment_type,
        confidential_omitted=parsed.confidential_omitted,
        value_multiplier=parsed.value_multiplier,
        entry_total=parsed.entry_total,
        value_total=parsed.value_total,
        issues=parsed.issues,
        url=filing_index_url(cik, ref.accession),
        holdings=[
            InstitutionalHolding(
                row_index=r.row_index,
                issuer_name=r.issuer_name,
                title_of_class=r.title_of_class,
                cusip=r.cusip[:16],
                value=r.value,
                amount=r.amount,
                amount_type=r.amount_type,
                put_call=r.put_call,
                discretion=r.discretion,
                other_managers=r.other_managers,
                voting_sole=r.voting_sole,
                voting_shared=r.voting_shared,
                voting_none=r.voting_none,
                issues=r.issues,
            )
            for r in parsed.rows
        ],
    )


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("ciks", nargs="*", type=int)
    args.add_argument(
        "--since",
        type=date.fromisoformat,
        default=datetime.now(UTC).date() - timedelta(days=DEFAULT_HISTORY_DAYS),
        help="ingest filings filed on or after this date (default: about eight quarters)",
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
            for cik in opts.ciks or settings.app.tracked_managers:
                r = ingest_manager(session, client, cik, opts.since)
                print(
                    f"{r.name} (CIK {r.cik}): {r.listed} listed since {r.since}, "
                    f"{r.stored} stored, "
                    f"{r.already_stored} already stored, {len(r.with_issues)} with issues, "
                    f"{len(r.failed)} failed"
                )
                for accession, reason in r.failed.items():
                    print(f"  FAILED {accession}: {reason}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
