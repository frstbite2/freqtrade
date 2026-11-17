"""Parse SEC ownership documents (Forms 3, 4, 5 and amendments) into typed rows.

Parsing only extracts what the filing says. Interpretation lives in classify.py.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation


DOCUMENT_TYPES = frozenset({"3", "4", "5", "3/A", "4/A", "5/A"})
_ROW_TAGS = {
    "nonDerivativeTransaction": ("non_derivative", False),
    "nonDerivativeHolding": ("non_derivative", True),
    "derivativeTransaction": ("derivative", False),
    "derivativeHolding": ("derivative", True),
}
# Footnotes on these cells describe the resulting position, not the transaction itself.
_POSITION_CELLS = ("postTransactionAmounts", "ownershipNature")


class FilingParseError(ValueError):
    """The document is not a usable ownership filing. Nothing from it may be stored."""


@dataclass
class Owner:
    cik: int
    name: str
    is_director: bool
    is_officer: bool
    is_ten_percent_owner: bool
    is_other: bool
    officer_title: str | None


@dataclass
class Row:
    row_index: int
    table: str  # "non_derivative" | "derivative"
    is_holding: bool
    security_title: str | None
    transaction_date: date | None = None
    code: str | None = None
    equity_swap: bool = False
    shares: Decimal | None = None
    price: Decimal | None = None
    acquired_disposed: str | None = None  # "A" | "D"
    shares_after: Decimal | None = None
    ownership: str | None = None  # "D" direct | "I" indirect
    nature_of_ownership: str | None = None
    exercise_price: Decimal | None = None
    underlying_title: str | None = None
    underlying_shares: Decimal | None = None
    footnotes: str = ""  # every footnote referenced by the row
    transaction_footnotes: str = ""  # only those on transaction cells
    issues: list[str] = field(default_factory=list)
    # Set by classify.py:
    category: str = ""
    plan_10b5_1: bool = False
    plan_basis: str | None = None
    signal: str | None = None


@dataclass
class ParsedFiling:
    document_type: str
    schema_version: str | None
    period_of_report: date | None
    original_filed_date: date | None  # amendments only
    issuer_cik: int
    issuer_name: str
    issuer_ticker: str | None
    owners: list[Owner]
    aff10b5one: bool | None  # None: the form version predates the checkbox (before April 2023)
    remarks: str
    rows: list[Row]


def _text(parent: ET.Element | None, path: str) -> str | None:
    if parent is None:
        return None
    found = parent.find(path)
    text = (found.text or "").strip() if found is not None else ""
    return text or None


def _flag(parent: ET.Element | None, path: str) -> bool | None:
    text = _text(parent, path)
    if text is None:
        return None
    if text.lower() in ("1", "true"):
        return True
    if text.lower() in ("0", "false"):
        return False
    raise FilingParseError(f"invalid boolean {text!r} at {path}")


def _date(text: str | None, issues: list[str] | None, name: str) -> date | None:
    """xs:date, optionally with a timezone suffix (2023-05-01-05:00)."""
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        if issues is None:
            raise FilingParseError(f"invalid date {text!r} for {name}") from None
        issues.append(f"invalid_{name}")
        return None


def _decimal(row: ET.Element, path: str, issues: list[str], name: str) -> Decimal | None:
    text = _text(row, path)
    if text is None:
        return None
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation:
        issues.append(f"invalid_{name}")
        return None
    if not value.is_finite() or value < 0:
        issues.append(f"invalid_{name}")
        return None
    return value


def _owners(root: ET.Element) -> list[Owner]:
    owners = []
    for el in root.findall("reportingOwner"):
        cik = _text(el, "reportingOwnerId/rptOwnerCik")
        name = _text(el, "reportingOwnerId/rptOwnerName")
        if not cik or not cik.isdigit() or not name:
            raise FilingParseError("missing or invalid reporting owner")
        rel = el.find("reportingOwnerRelationship")
        owners.append(
            Owner(
                cik=int(cik),
                name=name,
                is_director=bool(_flag(rel, "isDirector")),
                is_officer=bool(_flag(rel, "isOfficer")),
                is_ten_percent_owner=bool(_flag(rel, "isTenPercentOwner")),
                is_other=bool(_flag(rel, "isOther")),
                officer_title=_text(rel, "officerTitle"),
            )
        )
    if not owners:
        raise FilingParseError("no reporting owner")
    return owners


def _choice(el: ET.Element, path: str, allowed: str, issues: list[str], name: str) -> str | None:
    value = _text(el, path)
    if value is None or value in allowed:
        return value
    issues.append(f"invalid_{name}")
    return None


def _row(el: ET.Element, index: int, footnotes: dict[str | None, str]) -> Row:
    def notes(elements: list[ET.Element]) -> str:
        ids = dict.fromkeys(fid.get("id") for e in elements for fid in e.iter("footnoteId"))
        return " | ".join(footnotes[i] for i in ids if i in footnotes)

    table, is_holding = _ROW_TAGS[el.tag]
    issues: list[str] = []
    amounts = "transactionAmounts/"
    return Row(
        row_index=index,
        table=table,
        is_holding=is_holding,
        security_title=_text(el, "securityTitle/value"),
        transaction_date=_date(_text(el, "transactionDate/value"), issues, "transaction_date"),
        code=_text(el, "transactionCoding/transactionCode"),
        equity_swap=bool(_flag(el, "transactionCoding/equitySwapInvolved")),
        shares=_decimal(el, amounts + "transactionShares/value", issues, "shares"),
        price=_decimal(el, amounts + "transactionPricePerShare/value", issues, "price"),
        acquired_disposed=_choice(
            el, amounts + "transactionAcquiredDisposedCode/value", "AD", issues, "acquired_disposed"
        ),
        shares_after=_decimal(
            el,
            "postTransactionAmounts/sharesOwnedFollowingTransaction/value",
            issues,
            "shares_after",
        ),
        ownership=_choice(
            el, "ownershipNature/directOrIndirectOwnership/value", "DI", issues, "ownership"
        ),
        nature_of_ownership=_text(el, "ownershipNature/natureOfOwnership/value"),
        exercise_price=_decimal(el, "conversionOrExercisePrice/value", issues, "exercise_price"),
        underlying_title=_text(el, "underlyingSecurity/underlyingSecurityTitle/value"),
        underlying_shares=_decimal(
            el, "underlyingSecurity/underlyingSecurityShares/value", issues, "underlying_shares"
        ),
        footnotes=notes([el]),
        transaction_footnotes=notes([child for child in el if child.tag not in _POSITION_CELLS]),
        issues=issues,
    )


def parse_ownership_xml(xml: bytes) -> ParsedFiling:
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise FilingParseError("document declares a DTD or entities; refusing to parse")
    try:
        root = ET.fromstring(xml)  # noqa: S314
    except ET.ParseError as exc:
        raise FilingParseError(f"malformed XML: {exc}") from exc
    if root.tag != "ownershipDocument":
        raise FilingParseError(f"not an ownership document (root <{root.tag}>)")

    document_type = _text(root, "documentType")
    if document_type not in DOCUMENT_TYPES:
        raise FilingParseError(f"unsupported documentType {document_type!r}")
    issuer_cik = _text(root, "issuer/issuerCik")
    issuer_name = _text(root, "issuer/issuerName")
    if not issuer_cik or not issuer_cik.isdigit() or not issuer_name:
        raise FilingParseError("missing or invalid issuer")

    footnotes = {
        el.get("id"): " ".join("".join(el.itertext()).split())
        for el in root.findall("footnotes/footnote")
    }
    rows: list[Row] = []
    for table_tag in ("nonDerivativeTable", "derivativeTable"):
        for el in root.findall(f"{table_tag}/*"):
            if el.tag not in _ROW_TAGS:
                raise FilingParseError(f"unexpected element <{el.tag}> in {table_tag}")
            rows.append(_row(el, len(rows), footnotes))

    ticker = _text(root, "issuer/issuerTradingSymbol")
    return ParsedFiling(
        document_type=document_type,
        schema_version=_text(root, "schemaVersion"),
        period_of_report=_date(_text(root, "periodOfReport"), None, "periodOfReport"),
        original_filed_date=_date(
            _text(root, "dateOfOriginalSubmission"), None, "dateOfOriginalSubmission"
        ),
        issuer_cik=int(issuer_cik),
        issuer_name=issuer_name,
        issuer_ticker=ticker.upper() if ticker else None,
        owners=_owners(root),
        aff10b5one=_flag(root, "aff10b5One"),
        remarks=" ".join((_text(root, "remarks") or "").split()),
        rows=rows,
    )
