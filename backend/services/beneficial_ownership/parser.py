"""Parse SEC Schedules 13D and 13G (beneficial ownership above 5% of a class).

13D and 13G are different statements and must not be mixed up:
- Schedule 13D is filed by a holder who has, or may have, the purpose of influencing or
  controlling the company. It states that purpose (Item 4) and must be amended promptly.
- Schedule 13G is the short form for passive holders (institutions, passive investors). It
  says nothing about intent and is mostly updated on a quarterly or annual schedule.

Both are disclosures as of an event date, filed days to weeks later. Neither says what the
holder owns today. Structured (XML) filings exist only since December 2024; earlier ones are
free-form documents and are not parsed here.
"""

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


STRUCTURED_FORMS = frozenset({"SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A"})
LEGACY_FORMS = frozenset({"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"})  # free-form documents
FORMS = STRUCTURED_FORMS | LEGACY_FORMS


def schedule_of(form: str) -> str:
    """ "13D" or "13G"."""
    return "13D" if "13D" in form else "13G"


class ScheduleParseError(ValueError):
    """The document is not a usable Schedule 13D/13G. Nothing from it may be stored."""


@dataclass
class ReportingPerson:
    name: str
    cik: int | None
    shares: Decimal | None  # aggregate amount beneficially owned
    percent: Decimal | None  # of the class, as the filer states it
    person_type: str | None  # e.g. IN individual, IA investment adviser, HC holding company
    sole_voting: Decimal | None
    shared_voting: Decimal | None
    sole_dispositive: Decimal | None
    shared_dispositive: Decimal | None
    issues: list[str] = field(default_factory=list)


@dataclass
class ParsedSchedule:
    form: str
    schedule: str  # "13D" | "13G"
    is_amendment: bool
    amendment_number: int | None
    filer_cik: int | None
    issuer_cik: int
    issuer_name: str
    cusip: str | None
    security_title: str | None
    event_date: date | None  # the date of the event that required the filing
    rule: str | None  # 13G only: the rule the passive filer relies on
    purpose: str | None  # 13D only: Item 4, purpose of the transaction
    persons: list[ReportingPerson]
    issues: list[str]


def _local(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1].lower()  # filers' schemas differ in namespace and in case


def _find(el: ET.Element | None, *path: str) -> ET.Element | None:
    for name in path:
        if el is None:
            return None
        el = next((c for c in el if _local(c) == name.lower()), None)
    return el


def _text(el: ET.Element | None, *path: str) -> str | None:
    found = _find(el, *path)
    text = " ".join("".join(found.itertext()).split()) if found is not None else ""
    return text or None


def _number(text: str | None, issues: list[str], name: str) -> Decimal | None:
    if text is None:
        return None
    try:
        value = Decimal(text.replace(",", "").rstrip("%").strip())
    except InvalidOperation:
        issues.append(f"invalid_{name}")
        return None
    if not value.is_finite() or value < 0:
        issues.append(f"invalid_{name}")
        return None
    return value


def _date(text: str | None, issues: list[str]) -> date | None:
    if text is None:
        return None
    try:
        return datetime.strptime(text, "%m/%d/%Y").date()
    except ValueError:
        issues.append("invalid_event_date")
        return None


def _person(el: ET.Element, schedule: str) -> ReportingPerson:
    issues: list[str] = []
    powers = (
        _find(el, "reportingPersonBeneficiallyOwnedNumberOfShares") if schedule == "13G" else el
    )
    shares_tag = (
        "reportingPersonBeneficiallyOwnedAggregateNumberOfShares"
        if schedule == "13G"
        else "aggregateAmountOwned"
    )
    percent_tag = "classPercent" if schedule == "13G" else "percentOfClass"
    cik = _text(el, "reportingPersonCIK")
    percent = _number(_text(el, percent_tag), issues, "percent")
    if percent is not None and percent > 100:
        issues.append("percent_over_100")
    name = _text(el, "reportingPersonName")
    if not name:
        issues.append("missing_name")
    types = [_text(c) for c in el if _local(c) == "typeofreportingperson"]
    return ReportingPerson(
        name=name or "",
        cik=int(cik) if cik and cik.isdigit() else None,
        shares=_number(_text(el, shares_tag), issues, "shares"),
        percent=percent,
        person_type=", ".join(t for t in types if t) or None,
        sole_voting=_number(_text(powers, "soleVotingPower"), issues, "sole_voting"),
        shared_voting=_number(_text(powers, "sharedVotingPower"), issues, "shared_voting"),
        sole_dispositive=_number(_text(powers, "soleDispositivePower"), issues, "sole_dispositive"),
        shared_dispositive=_number(
            _text(powers, "sharedDispositivePower"), issues, "shared_dispositive"
        ),
        issues=issues,
    )


_HEADER_PARTY = re.compile(
    r"(SUBJECT COMPANY|FILED BY):.*?COMPANY CONFORMED NAME:\s*([^\n]+)"
    r".*?CENTRAL INDEX KEY:\s*(\d+)",
    re.DOTALL,
)


def parse_header(page: bytes) -> tuple[int, int, str]:
    """(subject company CIK, filer CIK, filer name) from EDGAR's own header of a filing.

    EDGAR writes this header itself, so it is reliable even for free-form filings. It is what
    tells a stake *in* a company from a stake that company reports in someone else.
    """
    text = html.unescape(page.decode("utf-8", "replace"))
    parties = {label: (name.strip(), int(cik)) for label, name, cik in _HEADER_PARTY.findall(text)}
    if "SUBJECT COMPANY" not in parties or "FILED BY" not in parties:
        raise ScheduleParseError("filing header names no subject company or filer")
    return parties["SUBJECT COMPANY"][1], parties["FILED BY"][1], parties["FILED BY"][0]


def parse_schedule(xml: bytes) -> ParsedSchedule:
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ScheduleParseError("document declares a DTD or entities; refusing to parse")
    try:
        root = ET.fromstring(xml)  # noqa: S314
    except ET.ParseError as exc:
        raise ScheduleParseError(f"malformed XML: {exc}") from exc
    form = _text(root, "headerData", "submissionType")
    if form not in STRUCTURED_FORMS:
        raise ScheduleParseError(f"unsupported submission type {form!r}")
    schedule = schedule_of(form)
    data = _find(root, "formData")
    cover = _find(data, "coverPageHeader")
    issuer = _find(cover, "issuerInfo")
    issuer_cik, issuer_name = _text(issuer, "issuerCik"), _text(issuer, "issuerName")
    if not issuer_cik or not issuer_cik.isdigit() or not issuer_name:
        raise ScheduleParseError("missing or invalid issuer")

    if schedule == "13G":
        elements = [c for c in data if _local(c) == "coverpageheaderreportingpersondetails"]
    else:
        group = _find(data, "reportingPersons")
        elements = [
            c for c in (group if group is not None else []) if _local(c) == "reportingpersoninfo"
        ]
    persons = [_person(el, schedule) for el in elements]
    if not persons:
        raise ScheduleParseError("no reporting person")

    issues: list[str] = []
    amendment = _text(cover, "amendmentNo")
    filer = _text(root, "headerData", "filerInfo", "filer", "filerCredentials", "cik")
    event_tag = "eventDateRequiresFilingThisStatement" if schedule == "13G" else "dateOfEvent"
    return ParsedSchedule(
        form=form,
        schedule=schedule,
        is_amendment=form.endswith("/A"),
        amendment_number=int(amendment) if amendment and amendment.isdigit() else None,
        filer_cik=int(filer) if filer and filer.isdigit() else None,
        issuer_cik=int(issuer_cik),
        issuer_name=issuer_name,
        # Schema versions differ: a list of CUSIPs (the first is used) or a single element.
        cusip=(
            _text(issuer, "issuerCusips", "issuerCusipNumber") or _text(issuer, "issuerCusip") or ""
        ).upper()
        or None,
        security_title=_text(cover, "securitiesClassTitle"),
        event_date=_date(_text(cover, event_tag), issues),
        rule=_text(cover, "designateRulesPursuantThisScheduleFiled") if schedule == "13G" else None,
        purpose=_text(data, "items1To7", "item4") if schedule == "13D" else None,
        persons=persons,
        issues=issues,
    )
