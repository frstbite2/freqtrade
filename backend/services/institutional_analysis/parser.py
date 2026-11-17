"""Parse SEC Form 13F submissions: the cover page and the information table of holdings.

A 13F lists what an investment manager held at a quarter end and is filed up to 45 days later.
It is a delayed disclosure, never a statement of what the manager holds now.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from statistics import median


FORMS = frozenset({"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"})
# Filings made before this date report values in thousands of dollars; from it on, in dollars.
DOLLARS_SINCE = date(2023, 1, 3)
_XML_BLOCK = re.compile(rb"<XML>\s*(.*?)\s*</XML>", re.DOTALL)
_CUSIP = re.compile(r"^[0-9A-Z]{9}$")


class Form13FError(ValueError):
    """The submission is not a usable 13F. Nothing from it may be stored."""


@dataclass
class HoldingRow:
    row_index: int
    issuer_name: str
    title_of_class: str | None
    cusip: str
    value: Decimal  # US dollars (after parse_13f has applied the unit)
    amount: Decimal  # shares, or principal amount for bonds
    amount_type: str | None  # "SH" shares | "PRN" principal
    put_call: str | None  # "Put" | "Call" | None for the security itself
    discretion: str | None
    other_managers: str | None
    voting_sole: Decimal | None
    voting_shared: Decimal | None
    voting_none: Decimal | None
    issues: list[str] = field(default_factory=list)


@dataclass
class Parsed13F:
    form: str
    period: date  # the quarter end the holdings are as of
    manager_name: str
    report_type: str  # "13F HOLDINGS REPORT" | "13F NOTICE" | "13F COMBINATION REPORT"
    is_amendment: bool
    amendment_type: str | None  # "RESTATEMENT" replaces the report | "NEW HOLDINGS" adds to it
    confidential_omitted: bool | None
    entry_total: int | None
    value_total: Decimal | None  # US dollars
    value_multiplier: int  # 1000 when the filing states values in thousands
    rows: list[HoldingRow]
    issues: list[str]


def _tree(xml: bytes) -> dict[str, list[ET.Element]]:
    """Elements by local tag name; filers use different namespace prefixes."""
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise Form13FError("document declares a DTD or entities; refusing to parse")
    try:
        root = ET.fromstring(xml)  # noqa: S314
    except ET.ParseError as exc:
        raise Form13FError(f"malformed XML: {exc}") from exc
    found: dict[str, list[ET.Element]] = {}
    for el in root.iter():
        found.setdefault(el.tag.rsplit("}", 1)[-1], []).append(el)
    return found


def _first(tree: dict[str, list[ET.Element]], tag: str) -> str | None:
    text = (tree[tag][0].text or "").strip() if tag in tree else ""
    return text or None


def _child(el: ET.Element, *path: str) -> str | None:
    for name in path:
        el = next((c for c in el if c.tag.rsplit("}", 1)[-1] == name), None)
        if el is None:
            return None
    return (el.text or "").strip() or None


def _number(text: str | None) -> Decimal | None:
    if text is None:
        return None
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None
    return value if value.is_finite() and value >= 0 else None


def _bool(text: str | None) -> bool | None:
    return None if text is None else text.strip().lower() in ("true", "y", "1")


def _reconcile(
    cover: dict[str, list[ET.Element]], rows: list[HoldingRow], filed_date: date, report_type: str
) -> tuple[int, Decimal | None, Decimal | None, list[str]]:
    """Settle the value unit, apply it to the rows, and check the table against the cover page."""
    issues = []
    multiplier = 1 if filed_date >= DOLLARS_SINCE else 1000
    # Some managers kept reporting thousands after the rule changed. Dollars per share tells:
    # typical holdings are tens of dollars a share, or hundredths if the values are thousands.
    per_share = [r.value / r.amount for r in rows if r.amount_type == "SH" and r.amount > 0]
    if multiplier == 1 and per_share and median(per_share) < 1:
        multiplier = 1000
        issues.append(
            f"values taken as thousands of dollars: the median value per share as filed is "
            f"{median(per_share):.4f}"
        )
    for r in rows:
        r.value *= multiplier
    entry_total = _number(_first(cover, "tableEntryTotal"))
    value_total = _number(_first(cover, "tableValueTotal"))
    if value_total is not None:
        value_total *= multiplier
    # The cover page states the table's size and value: a mismatch means a broken filing or parse.
    if entry_total is not None and int(entry_total) != len(rows):
        issues.append(f"cover states {int(entry_total)} rows, table has {len(rows)}")
    # Each row is rounded on its own, so the stated total may differ by a unit per row.
    if value_total is not None and abs(value_total - sum(r.value for r in rows)) > multiplier * (
        len(rows) + 1
    ):
        issues.append(f"cover states value {value_total}, rows sum to {sum(r.value for r in rows)}")
    if "NOTICE" in report_type.upper() and rows:
        issues.append("a notice filing should have no holdings")

    return multiplier, entry_total, value_total, issues


def parse_13f(submission: bytes, filed_date: date) -> Parsed13F:
    """Parse a complete submission text file (cover page plus, for a holdings report, the table)."""
    blocks = _XML_BLOCK.findall(submission)
    if not blocks:
        raise Form13FError("no XML documents in the submission (filings before 2013 are text only)")
    cover = _tree(blocks[0])
    form = _first(cover, "submissionType")
    if form not in FORMS:
        raise Form13FError(f"unsupported submission type {form!r}")
    period_text = _first(cover, "reportCalendarOrQuarter") or _first(cover, "periodOfReport")
    try:
        period = datetime.strptime(period_text or "", "%m-%d-%Y").date()
    except ValueError:
        raise Form13FError(f"invalid report period {period_text!r}") from None
    manager = cover["filingManager"][0] if "filingManager" in cover else None
    manager_name = _child(manager, "name") if manager is not None else None
    report_type = _first(cover, "reportType")
    if not manager_name or not report_type:
        raise Form13FError("cover page lacks the manager name or report type")

    rows: list[HoldingRow] = []
    for block in blocks[1:]:
        table = _tree(block)
        for el in table.get("infoTable", []):
            rows.append(_row(el, len(rows)))

    multiplier, entry_total, value_total, issues = _reconcile(cover, rows, filed_date, report_type)

    return Parsed13F(
        form=form,
        period=period,
        manager_name=manager_name,
        report_type=report_type,
        is_amendment=bool(_bool(_first(cover, "isAmendment"))),
        amendment_type=_first(cover, "amendmentType"),
        confidential_omitted=_bool(_first(cover, "isConfidentialOmitted")),
        entry_total=None if entry_total is None else int(entry_total),
        value_total=value_total,
        value_multiplier=multiplier,
        rows=rows,
        issues=issues,
    )


def _row(el: ET.Element, index: int) -> HoldingRow:
    issues = []
    cusip = (_child(el, "cusip") or "").upper().replace(" ", "")
    if not _CUSIP.match(cusip):
        issues.append("invalid_cusip")
    value = _number(_child(el, "value"))
    amount = _number(_child(el, "shrsOrPrnAmt", "sshPrnamt"))
    if value is None:
        issues.append("invalid_value")
    if amount is None:
        issues.append("invalid_amount")
    amount_type = (_child(el, "shrsOrPrnAmt", "sshPrnamtType") or "").upper() or None
    if amount_type not in ("SH", "PRN"):
        issues.append("invalid_amount_type")
    put_call = (_child(el, "putCall") or "").capitalize() or None
    if put_call not in (None, "Put", "Call"):
        issues.append("invalid_put_call")
    name = _child(el, "nameOfIssuer")
    if not name:
        issues.append("missing_issuer_name")
    return HoldingRow(
        row_index=index,
        issuer_name=name or "",
        title_of_class=_child(el, "titleOfClass"),
        cusip=cusip,
        value=value or Decimal(0),
        amount=amount or Decimal(0),
        amount_type=amount_type,
        put_call=put_call,
        discretion=_child(el, "investmentDiscretion"),
        other_managers=_child(el, "otherManager"),
        voting_sole=_number(_child(el, "votingAuthority", "Sole")),
        voting_shared=_number(_child(el, "votingAuthority", "Shared")),
        voting_none=_number(_child(el, "votingAuthority", "None")),
        issues=issues,
    )
