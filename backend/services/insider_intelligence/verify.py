"""Check the parser against SEC's own extraction of the same filings.

SEC publishes quarterly "Insider Transactions Data Sets" (flat tables built from every Form
3/4/5): https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
This tool draws a random sample of filings from one quarterly zip, downloads each original
filing from EDGAR, parses it with our parser and compares every field both sides carry.

Properties of SEC's data set that shape the comparison, each confirmed against original filings:
- Numbers are rounded to two decimals (a filing's 27.103 appears as 27.1), so numbers are
  compared at two decimals.
- When a row leaves an optional field blank, the data set can shift the following rows' values
  for that field up a row. A filing whose every column holds the same values as ours but in
  different rows is therefore reported separately as "realigned", not as a match or a mismatch.
- For joint filings every owner's roles are merged onto the first owner, and older data sets
  write roles without a separator ("DirectorOther"); roles are compared as a set per filing.

Usage: python -m backend.services.insider_intelligence.verify 2024q3_form345.zip --sample 300
"""

import argparse
import csv
import io
import random
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from backend.core.config import get_settings
from backend.services.edgar import EdgarClient, EdgarError
from backend.services.insider_intelligence.parser import (
    FilingParseError,
    ParsedFiling,
    Row,
    parse_ownership_xml,
)


_XML = re.compile(rb"<XML>\s*(.*?)\s*</XML>", re.DOTALL)
_ROLES = re.compile(r"Director|Officer|TenPercentOwner|Other")


def _table(archive: zipfile.ZipFile, name: str, wanted: set[str]) -> dict[str, list[dict]]:
    rows = defaultdict(list)
    with archive.open(name) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t")
        for row in reader:
            if row["ACCESSION_NUMBER"] in wanted:
                rows[row["ACCESSION_NUMBER"]].append(row)
    return rows


def _num(value: str | Decimal | None) -> Decimal | None:
    """Two-decimal form, the precision SEC's data set keeps."""
    try:
        if value is None or value == "":
            return None
        return Decimal(value).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _day(text: str | None):
    return datetime.strptime(text, "%d-%b-%Y").date() if text else None


def _str(text: str | None) -> str | None:
    return " ".join(text.split()) or None if text else None


def _ours(row: Row, derivative: bool, holding: bool) -> tuple:
    base = (
        _str(row.security_title),
        _num(row.shares_after),
        row.ownership,
        _str(row.nature_of_ownership),
    )
    if derivative:
        base += (
            _num(row.exercise_price),
            _str(row.underlying_title),
            _num(row.underlying_shares),
        )
    if holding:
        return base
    return base + (
        row.transaction_date,
        row.code,
        row.equity_swap,
        _num(row.shares),
        _num(row.price),
        row.acquired_disposed,
    )


def _theirs(row: dict, derivative: bool, holding: bool) -> tuple:
    base = (
        _str(row["SECURITY_TITLE"]),
        _num(row["SHRS_OWND_FOLWNG_TRANS"]),
        row["DIRECT_INDIRECT_OWNERSHIP"] or None,
        _str(row["NATURE_OF_OWNERSHIP"]),
    )
    if derivative:
        base += (
            _num(row["CONV_EXERCISE_PRICE"]),
            _str(row["UNDLYNG_SEC_TITLE"]),
            _num(row["UNDLYNG_SEC_SHARES"]),
        )
    if holding:
        return base
    return base + (
        _day(row["TRANS_DATE"]),
        row["TRANS_CODE"] or None,
        row["EQUITY_SWAP_INVOLVED"] in ("1", "true"),
        _num(row["TRANS_SHARES"]),
        _num(row["TRANS_PRICEPERSHARE"]),
        row["TRANS_ACQUIRED_DISP_CD"] or None,
    )


def compare(parsed: ParsedFiling, sec: dict[str, list[dict]]) -> tuple[list[str], list[str]]:
    """(fields whose values differ, tables whose values agree but sit in different rows)."""
    sub = sec["SUBMISSION"][0]
    checks = {
        "document_type": (parsed.document_type, sub["DOCUMENT_TYPE"]),
        "period_of_report": (parsed.period_of_report, _day(sub["PERIOD_OF_REPORT"])),
        "original_filed_date": (parsed.original_filed_date, _day(sub["DATE_OF_ORIG_SUB"])),
        "issuer_cik": (parsed.issuer_cik, int(sub["ISSUERCIK"])),
        "issuer_ticker": (
            _str(parsed.issuer_ticker),
            (_str(sub["ISSUERTRADINGSYMBOL"]) or "").upper() or None,
        ),
        "aff10b5one": (
            parsed.aff10b5one,
            # Data sets from before April 2023 have no AFF10B5ONE column, matching our None.
            {"1": True, "true": True, "0": False, "false": False}.get(
                (sub.get("AFF10B5ONE") or "").lower()
            ),
        ),
        "owner_ciks": (
            sorted(o.cik for o in parsed.owners),
            sorted(int(o["RPTOWNERCIK"]) for o in sec["REPORTINGOWNER"]),
        ),
        "owner_roles": (
            {
                role
                for o in parsed.owners
                for role, held in (
                    ("Director", o.is_director),
                    ("Officer", o.is_officer),
                    ("TenPercentOwner", o.is_ten_percent_owner),
                    ("Other", o.is_other),
                )
                if held
            },
            {
                role
                for o in sec["REPORTINGOWNER"]
                for role in _ROLES.findall(o["RPTOWNER_RELATIONSHIP"])
            },
        ),
        "officer_titles": (
            Counter(_str(o.officer_title) for o in parsed.owners),
            Counter(_str(o["RPTOWNER_TITLE"]) for o in sec["REPORTINGOWNER"]),
        ),
    }
    differing = [name for name, (ours, theirs) in checks.items() if ours != theirs]
    realigned = []
    for name, table, holding in (
        ("NONDERIV_TRANS", "non_derivative", False),
        ("NONDERIV_HOLDING", "non_derivative", True),
        ("DERIV_TRANS", "derivative", False),
        ("DERIV_HOLDING", "derivative", True),
    ):
        derivative = table == "derivative"
        ours = [
            _ours(r, derivative, holding)
            for r in parsed.rows
            if r.table == table and r.is_holding == holding
        ]
        theirs = [_theirs(r, derivative, holding) for r in sec[name]]
        if Counter(ours) == Counter(theirs):
            continue
        same_values = len(ours) == len(theirs) and all(
            Counter(column_ours) == Counter(column_theirs)
            for column_ours, column_theirs in zip(
                zip(*ours, strict=True), zip(*theirs, strict=True), strict=True
            )
        )
        (realigned if same_values else differing).append(name)
    return differing, realigned


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("dataset_zip")
    args.add_argument("--sample", type=int, default=300)
    args.add_argument("--seed", type=int, default=1)
    args.add_argument("--show", type=int, default=10, help="mismatching filings to list")
    opts = args.parse_args()

    settings = get_settings()
    client = EdgarClient(settings.app.sec_user_agent, settings.app.edgar_cache_dir)
    with zipfile.ZipFile(opts.dataset_zip) as archive:
        with archive.open("SUBMISSION.tsv") as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t")
            everything = sorted({(r["ACCESSION_NUMBER"], int(r["ISSUERCIK"])) for r in reader})
        sample = random.Random(opts.seed).sample(everything, min(opts.sample, len(everything)))  # noqa: S311
        wanted = {accession for accession, _ in sample}
        names = ("SUBMISSION", "REPORTINGOWNER", "NONDERIV_TRANS", "NONDERIV_HOLDING")
        names += ("DERIV_TRANS", "DERIV_HOLDING")
        tables = {name: _table(archive, f"{name}.tsv", wanted) for name in names}

    outcome: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    listed = 0
    for accession, cik in sample:
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
            f"/{accession}.txt"
        )
        try:
            match = _XML.search(client.get(url, max_age=None))
            if match is None:
                raise FilingParseError("no <XML> block in the submission file")
            parsed = parse_ownership_xml(match.group(1))
        except (EdgarError, FilingParseError) as exc:
            outcome["could_not_parse"] += 1
            print(f"COULD NOT PARSE {accession}: {exc}")
            continue
        differing, realigned = compare(parsed, {name: tables[name][accession] for name in names})
        outcome["mismatch" if differing else "realigned" if realigned else "match"] += 1
        fields.update(differing)
        if (differing or realigned) and listed < opts.show:
            listed += 1
            label = f"MISMATCH {differing}" if differing else f"realigned {realigned}"
            print(f"{label} {accession}  {url}")
    client.close()
    print(f"sampled {len(sample)} of {len(everything)} filings (seed {opts.seed}): {dict(outcome)}")
    if fields:
        print(f"differing fields: {dict(fields)}")
    sys.exit(1 if outcome["mismatch"] or outcome["could_not_parse"] else 0)


if __name__ == "__main__":
    main()
