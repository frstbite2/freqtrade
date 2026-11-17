"""The parser-versus-SEC comparison, on real rows from SEC's 2024 Q3 insider data set.

`fixtures/sec_dataset/2024q3_excerpt.json` holds the rows SEC published for three filings that
are also in `fixtures/edgar`. Only the columns the comparison reads were kept; the values are
exactly as published. They show the data set's quirks that the comparison has to allow for.
"""

import copy
import json
from decimal import Decimal

import pytest

from backend.services.insider_intelligence.parser import parse_ownership_xml
from backend.services.insider_intelligence.verify import compare
from backend.tests.conftest import FIXTURES, fixture_xml


SEC = json.loads((FIXTURES.parent / "sec_dataset" / "2024q3_excerpt.json").read_text())
PLAN_PURCHASE, CEO_PURCHASE, JOINT = (
    "0001127602-24-019550",
    "0001127602-24-021794",
    "0001437749-24-028607",
)


def check(accession: str, sec: dict | None = None) -> tuple[list[str], list[str]]:
    return compare(parse_ownership_xml(fixture_xml(accession)), sec or SEC[accession])


def test_identical_filing_matches():
    assert check(PLAN_PURCHASE) == ([], [])


def test_sec_rounds_numbers_and_shifts_optional_text_between_rows():
    sec = SEC[CEO_PURCHASE]
    filed = parse_ownership_xml(fixture_xml(CEO_PURCHASE))
    # The filing says 20.3137 and 19.9186; the data set keeps two decimals.
    assert sorted(r.price for r in filed.rows if r.price) == [
        Decimal("19.9186"),
        Decimal("20.3137"),
    ]
    assert sorted(r["TRANS_PRICEPERSHARE"] for r in sec["NONDERIV_TRANS"]) == ["19.92", "20.31"]
    # The filing's directly held lot has no "nature of ownership"; the data set gives it one
    # that belongs to another row.
    direct = next(r for r in filed.rows if r.is_holding and r.ownership == "D")
    assert direct.nature_of_ownership is None
    assert [
        r["NATURE_OF_OWNERSHIP"]
        for r in sec["NONDERIV_HOLDING"]
        if r["DIRECT_INDIRECT_OWNERSHIP"] == "D"
    ] == ["By Family Trust"]
    # Same values, different rows: reported as realigned, not as a match and not as a mismatch.
    assert check(CEO_PURCHASE) == ([], ["NONDERIV_HOLDING"])


def test_sec_merges_joint_filers_roles_onto_the_first_owner():
    roles = [r["RPTOWNER_RELATIONSHIP"] for r in SEC[JOINT]["REPORTINGOWNER"]]
    assert roles == ["Director,TenPercentOwner", ""]  # the filing gives one role to each owner
    differing, _ = check(JOINT)
    assert differing == []


@pytest.mark.parametrize(
    ("table", "column", "value", "field"),
    [
        ("NONDERIV_TRANS", "TRANS_PRICEPERSHARE", "20.32", "NONDERIV_TRANS"),
        ("NONDERIV_TRANS", "TRANS_CODE", "S", "NONDERIV_TRANS"),
        ("NONDERIV_TRANS", "TRANS_SHARES", "7501.0", "NONDERIV_TRANS"),
        ("NONDERIV_HOLDING", "SHRS_OWND_FOLWNG_TRANS", "1.0", "NONDERIV_HOLDING"),
        ("SUBMISSION", "PERIOD_OF_REPORT", "06-AUG-2024", "period_of_report"),
        ("SUBMISSION", "ISSUERCIK", "0000000001", "issuer_cik"),
        ("REPORTINGOWNER", "RPTOWNER_RELATIONSHIP", "Director", "owner_roles"),
    ],
)
def test_a_real_difference_is_reported(table, column, value, field):
    sec = copy.deepcopy(SEC[CEO_PURCHASE])
    sec[table][0][column] = value
    differing, _ = check(CEO_PURCHASE, sec)
    assert differing == [field]


def test_a_missing_row_is_a_difference_not_a_realignment():
    sec = copy.deepcopy(SEC[CEO_PURCHASE])
    sec["NONDERIV_HOLDING"].pop()
    assert check(CEO_PURCHASE, sec) == (["NONDERIV_HOLDING"], [])
