"""Check the 13F parser against SEC's own extraction of the same filings.

SEC publishes "Form 13F Data Sets" (flat tables built from every 13F filed in a period):
https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
This tool draws a random sample of holdings reports from one zip, downloads each original
submission from EDGAR, parses it and compares the cover page fields and every holdings row.
Values are compared as filed (before our thousands-to-dollars conversion).

Usage: python -m backend.services.institutional_analysis.verify <data set>.zip --sample 150
"""

import argparse
import csv
import io
import random
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal

from backend.core.config import get_settings
from backend.services.edgar import EdgarClient, EdgarError
from backend.services.institutional_analysis.parser import Form13FError, Parsed13F, parse_13f


MAX_ROWS = 5000  # larger filings are skipped to keep downloads reasonable


def _rows(archive: zipfile.ZipFile, name: str, wanted: set[str] | None = None):
    member = next(n for n in archive.namelist() if n.endswith(f"/{name}.tsv") or n == f"{name}.tsv")
    with archive.open(member) as raw:
        for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t"):
            if wanted is None or row["ACCESSION_NUMBER"] in wanted:
                yield row


def _text(value: str | None) -> str | None:
    return " ".join(value.split()) or None if value else None


def _num(value: str | None) -> Decimal | None:
    return Decimal(value) if value else None


def compare(parsed: Parsed13F, sec: dict[str, list[dict]]) -> list[str]:
    """Names of the fields where our parse differs from SEC's extraction."""
    cover, summary = sec["COVERPAGE"][0], (sec["SUMMARYPAGE"] or [{}])[0]
    multiplier = parsed.value_multiplier
    checks = {
        "form": (parsed.form, sec["SUBMISSION"][0]["SUBMISSIONTYPE"]),
        "period": (
            parsed.period,
            datetime.strptime(cover["REPORTCALENDARORQUARTER"], "%d-%b-%Y").date(),
        ),
        "report_type": (parsed.report_type, cover["REPORTTYPE"]),
        "is_amendment": (parsed.is_amendment, cover["ISAMENDMENT"] == "Y"),
        "amendment_type": (parsed.amendment_type, cover["AMENDMENTTYPE"] or None),
        "manager_name": (_text(parsed.manager_name), _text(cover["FILINGMANAGER_NAME"])),
        "entry_total": (parsed.entry_total, int(summary.get("TABLEENTRYTOTAL") or 0) or None),
        "value_total": (
            None if parsed.value_total is None else parsed.value_total / multiplier,
            _num(summary.get("TABLEVALUETOTAL")),
        ),
        "rows": (
            Counter(
                (
                    _text(r.issuer_name),
                    _text(r.title_of_class),
                    r.cusip,
                    r.value / multiplier,
                    r.amount,
                    r.amount_type,
                    r.put_call,
                )
                for r in parsed.rows
            ),
            Counter(
                (
                    _text(r["NAMEOFISSUER"]),
                    _text(r["TITLEOFCLASS"]),
                    r["CUSIP"].upper().replace(" ", ""),
                    _num(r["VALUE"]),
                    _num(r["SSHPRNAMT"]),
                    r["SSHPRNAMTTYPE"].upper() or None,
                    r["PUTCALL"].capitalize() or None,
                )
                for r in sec["INFOTABLE"]
            ),
        ),
    }
    return [name for name, (ours, theirs) in checks.items() if ours != theirs]


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("dataset_zip")
    args.add_argument("--sample", type=int, default=150)
    args.add_argument("--seed", type=int, default=1)
    opts = args.parse_args()
    settings = get_settings()
    client = EdgarClient(settings.app.sec_user_agent, settings.app.edgar_cache_dir)

    with zipfile.ZipFile(opts.dataset_zip) as archive:
        sizes = {
            r["ACCESSION_NUMBER"]: int(r["TABLEENTRYTOTAL"] or 0)
            for r in _rows(archive, "SUMMARYPAGE")
        }
        submissions = {
            r["ACCESSION_NUMBER"]: r
            for r in _rows(archive, "SUBMISSION")
            if r["SUBMISSIONTYPE"].startswith("13F-HR")
            and 0 < sizes.get(r["ACCESSION_NUMBER"], 0) <= MAX_ROWS
        }
        sample = random.Random(opts.seed).sample(  # noqa: S311
            sorted(submissions), min(opts.sample, len(submissions))
        )
        wanted = set(sample)
        tables: dict[str, dict[str, list[dict]]] = {}
        for name in ("SUBMISSION", "COVERPAGE", "SUMMARYPAGE", "INFOTABLE"):
            tables[name] = defaultdict(list)
            for row in _rows(archive, name, wanted):
                tables[name][row["ACCESSION_NUMBER"]].append(row)

    outcome: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    rows_checked = 0
    for accession in sample:
        sub = submissions[accession]
        filed = datetime.strptime(sub["FILING_DATE"], "%d-%b-%Y").date()
        try:
            parsed = parse_13f(client.submission_text(int(sub["CIK"]), accession), filed)
        except (EdgarError, Form13FError) as exc:
            outcome["could_not_parse"] += 1
            print(f"COULD NOT PARSE {accession}: {exc}")
            continue
        differing = compare(parsed, {name: tables[name][accession] for name in tables})
        rows_checked += len(parsed.rows)
        outcome["mismatch" if differing else "match"] += 1
        fields.update(differing)
        if differing:
            print(f"MISMATCH {accession} (CIK {int(sub['CIK'])}): {differing}")
        if parsed.value_multiplier != 1:
            outcome["of which filed in thousands"] += 1
    client.close()
    print(f"sampled {len(sample)} of {len(submissions)} holdings reports (seed {opts.seed}), "
          f"{rows_checked} rows: {dict(outcome)}")  # fmt: skip
    if fields:
        print(f"differing fields: {dict(fields)}")
    sys.exit(1 if outcome["mismatch"] or outcome["could_not_parse"] else 0)


if __name__ == "__main__":
    main()
