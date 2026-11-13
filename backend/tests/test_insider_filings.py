"""Parsing and classification of real SEC filings (see fixtures/edgar/README.md).

Expected values were read from the original filing documents, not from this code's output.
"""

from datetime import date
from decimal import Decimal

import pytest

from backend.services.insider_intelligence.classify import affirms_10b5_1, classify_filing
from backend.services.insider_intelligence.parser import (
    FilingParseError,
    ParsedFiling,
    parse_ownership_xml,
)
from backend.tests.conftest import MANIFEST, fixture_entry, fixture_xml


def load(accession: str) -> ParsedFiling:
    filing = parse_ownership_xml(fixture_xml(accession))
    classify_filing(filing, date.fromisoformat(fixture_entry(accession)["filingDate"]))
    return filing


def trades(filing: ParsedFiling) -> list[tuple]:
    return [
        (r.code, r.shares, r.price, r.category, r.signal)
        for r in filing.rows
        if r.table == "non_derivative" and not r.is_holding
    ]


# --- parsing ---


def test_every_fixture_parses_and_matches_its_index_entry():
    for entry in MANIFEST:
        filing = parse_ownership_xml(fixture_xml(entry["accession"]))
        assert filing.document_type == entry["form"], entry["accession"]
        assert all(not r.issues for r in filing.rows), entry["accession"]


def test_form4_open_market_purchase_fields():
    """Intel CEO purchase, accession 0000050863-26-000195."""
    f = load("0000050863-26-000195")
    assert (f.document_type, f.schema_version) == ("4", "X0609")
    assert (f.issuer_cik, f.issuer_name, f.issuer_ticker) == (50863, "INTEL CORP", "INTC")
    assert f.period_of_report == date(2026, 11, 2)
    assert f.original_filed_date is None and f.aff10b5one is False
    (owner,) = f.owners
    assert (owner.name, owner.officer_title) == ("TAN LIP BU", "CEO")
    assert (owner.is_director, owner.is_officer, owner.is_ten_percent_owner) == (True, True, False)

    buy, direct, plan401k = f.rows
    assert (buy.table, buy.is_holding, buy.code) == ("non_derivative", False, "P")
    assert (buy.shares, buy.price) == (Decimal(150000), Decimal("64.7312"))
    assert (buy.acquired_disposed, buy.shares_after) == ("A", Decimal(1464669))
    assert (buy.ownership, buy.nature_of_ownership) == ("I", "by Family Trust")
    assert buy.transaction_date == date(2026, 11, 2)
    assert "weighted average" in buy.footnotes
    assert (direct.is_holding, direct.shares_after, direct.ownership) == (
        True,
        Decimal(16471),
        "D",
    )
    assert (plan401k.shares_after, plan401k.nature_of_ownership) == (Decimal(500), "by 401(k)")


def test_fractional_shares_and_escaped_text_are_exact():
    f = load("0000320187-26-000051")
    assert f.owners[0].officer_title == "PRESIDENT & CEO"
    assert f.rows[0].shares == Decimal("23660.235")
    assert f.rows[0].shares_after == Decimal("265247.235")


def test_form3_is_holdings_only():
    f = load("0000050863-25-000199")
    assert f.document_type == "3" and f.aff10b5one is None
    assert f.rows and all(r.is_holding and r.category == "holding" for r in f.rows)
    assert all(r.signal is None and r.code is None for r in f.rows)


def test_form5_inheritance_is_not_a_signal():
    f = load("0001127602-25-002794")
    assert f.document_type == "5"
    assert trades(f) == [("W", Decimal(154), Decimal(0), "inheritance", None)]


def test_amendment_carries_original_filing_date():
    f = load("0000320187-26-000053")
    assert f.document_type == "4/A"
    assert f.original_filed_date == date(2026, 4, 14)
    assert f.rows[0].price == Decimal("42.27")  # the original said 42.265


def test_joint_filing_keeps_each_owners_own_role():
    f = load("0001437749-24-028607")
    assert [(o.name, o.is_director, o.is_ten_percent_owner) for o in f.owners] == [
        ("STAHL MURRAY", True, False),
        ("HORIZON KINETICS ASSET MANAGEMENT LLC", False, True),
    ]


def test_derivative_rows_are_separate_from_stock():
    """Intel RSU vesting, 0000050863-26-000194: exercise and tax withholding, no signal."""
    f = load("0000050863-26-000194")
    assert {r.category for r in f.rows if r.table == "derivative" and not r.is_holding} == {
        "option_exercise"
    }
    first = next(r for r in f.rows if r.table == "derivative")
    assert (first.security_title, first.underlying_title) == (
        "Restricted Stock Units",
        "Common Stock",
    )
    assert first.underlying_shares == Decimal(33008)
    assert {r.category for r in f.rows if r.table == "non_derivative"} == {
        "option_exercise",
        "tax_withholding",
    }
    assert all(r.signal is None for r in f.rows)
    withheld = next(r for r in f.rows if r.code == "F")
    assert (withheld.shares, withheld.price) == (Decimal(14739), Decimal("65.99"))


# --- malformed input (derived from a real filing by breaking one thing) ---

GOOD = fixture_xml("0000320187-26-000049")


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (b"not xml at all", "malformed XML"),
        (b"<html><body>Too many requests</body></html>", "not an ownership document"),
        (b'<!DOCTYPE x [<!ENTITY a "b">]>' + GOOD, "DTD"),
        (
            GOOD.replace(b"<documentType>4</documentType>", b"<documentType>13F</documentType>"),
            "documentType",
        ),
        (
            GOOD.replace(b"<issuerCik>0000320187</issuerCik>", b"<issuerCik>abc</issuerCik>"),
            "issuer",
        ),
        (
            GOOD.replace(b"<rptOwnerCik>", b"<x>").replace(b"</rptOwnerCik>", b"</x>"),
            "reporting owner",
        ),
        (GOOD.replace(b"<aff10b5One>0</aff10b5One>", b"<aff10b5One>maybe</aff10b5One>"), "boolean"),
        (
            GOOD.replace(b"<periodOfReport>2026-04-10", b"<periodOfReport>10/04/2026"),
            "invalid date",
        ),
    ],
)
def test_unusable_documents_are_rejected(broken, message):
    assert GOOD != broken
    with pytest.raises(FilingParseError, match=message):
        parse_ownership_xml(broken)


@pytest.mark.parametrize(
    ("old", "new", "issue"),
    [
        (b"<value>42.43</value>", b"<value>forty</value>", "invalid_price"),
        (b"<value>42.43</value>", b"<value>-42.43</value>", "invalid_price"),
        (b"<value>42.43</value>", b"<value>0</value>", "zero_price"),
        (b"<value>25000</value>", b"<value>NaN</value>", "invalid_shares"),
        (b"<value>25000</value>", b"<value>0</value>", "missing_shares"),
        (b"<value>2026-04-10</value>", b"<value>2026-13-45</value>", "invalid_transaction_date"),
        (
            b"<value>2026-04-10</value>",
            b"<value>2027-04-10</value>",
            "transaction_date_after_filing",
        ),
        (
            b"<transactionAcquiredDisposedCode>\n                    <value>A</value>",
            b"<transactionAcquiredDisposedCode>\n                    <value>D</value>",
            "code_direction_mismatch",
        ),
        (b"<equitySwapInvolved>0<", b"<equitySwapInvolved>1<", "equity_swap"),
    ],
)
def test_a_damaged_purchase_row_is_flagged_and_never_a_signal(old, new, issue):
    assert old in GOOD
    filing = parse_ownership_xml(GOOD.replace(old, new, 1))
    classify_filing(filing, date(2026, 4, 14))
    row = filing.rows[0]
    assert issue in row.issues
    assert row.signal is None


def test_unknown_transaction_code_is_flagged():
    xml = GOOD.replace(
        b"<transactionCode>P</transactionCode>", b"<transactionCode>Q</transactionCode>"
    )
    filing = parse_ownership_xml(xml)
    classify_filing(filing, date(2026, 4, 14))
    assert (filing.rows[0].category, filing.rows[0].signal) == ("unknown", None)
    assert "unknown_transaction_code" in filing.rows[0].issues


# --- classification: what is a discretionary signal ---


def test_open_market_purchase_is_a_buy_signal():
    f = load("0000050863-26-000195")
    assert trades(f) == [
        ("P", Decimal(150000), Decimal("64.7312"), "open_market_purchase", "discretionary_buy")
    ]
    assert f.rows[0].plan_10b5_1 is False


def test_policy_boilerplate_mentioning_10b5_1_does_not_hide_a_real_purchase():
    """Nike director purchase, 0000320187-26-000049. Its footnote says trades are allowed only in
    a window 'except pursuant to approved 10b5-1 trading plans' - that is not a plan trade."""
    f = load("0000320187-26-000049")
    assert "except pursuant to approved 10b5-1 trading plans" in f.rows[0].footnotes
    assert trades(f) == [
        ("P", Decimal(25000), Decimal("42.43"), "open_market_purchase", "discretionary_buy")
    ]


def test_purchase_under_a_10b5_1_plan_is_not_a_signal():
    """Nike director, 0001127602-24-019550: 'effected pursuant to a 10b5-1 trading plan'."""
    f = load("0001127602-24-019550")
    assert trades(f) == [("P", Decimal(2941), Decimal("77.02"), "planned_purchase", None)]
    assert (f.rows[0].plan_10b5_1, f.rows[0].plan_basis) == (True, "footnote")


def test_plan_sale_is_caught_from_the_footnote_when_the_checkbox_is_unchecked():
    """Apple CFO, 0000320193-23-000096: checkbox says 0, every footnote says 10b5-1 plan."""
    f = load("0000320193-23-000096")
    assert f.aff10b5one is False
    assert trades(f) == [
        ("S", Decimal(32010), Decimal("177.89"), "planned_sale", None),
        ("S", Decimal(19000), Decimal("178.55"), "planned_sale", None),
        ("S", Decimal(12685), Decimal("178.91"), "planned_sale", None),
    ]
    assert {r.plan_basis for r in f.rows} == {"footnote"}


def test_plan_sale_is_caught_from_the_checkbox_alone():
    """Nike officer, 0000320187-26-000013: checkbox checked, no footnote names the plan."""
    f = load("0000320187-26-000013")
    assert f.aff10b5one is True
    sale = next(r for r in f.rows if r.code == "S")
    assert not affirms_10b5_1(sale.footnotes)
    assert (sale.category, sale.plan_basis, sale.signal) == ("planned_sale", "checkbox", None)


def test_sale_under_standing_instructions_is_not_a_signal():
    """Intel officer, 0001127602-23-006774: sold 'pursuant to trading instructions' (ESPP)."""
    f = load("0001127602-23-006774")
    sale = next(r for r in f.rows if r.code == "S")
    assert f.aff10b5one is None  # form version predates the checkbox
    assert (sale.category, sale.plan_basis, sale.signal) == (
        "planned_sale",
        "trading_instructions",
        None,
    )


def test_mixed_form_never_yields_a_signal():
    """Apple CEO, 0000320193-24-000049: RSU vesting, tax withholding, plan sales, and one sale
    footnoted as tax withholding that the plan footnotes do not cover."""
    f = load("0000320193-24-000049")
    assert f.aff10b5one is True
    assert all(r.signal is None for r in f.rows)
    categories = [r.category for r in f.rows if r.code == "S"]
    assert set(categories) == {"planned_sale", "sale_to_cover_taxes"}
    covered = next(r for r in f.rows if r.category == "sale_to_cover_taxes")
    assert covered.issues == ["plan_scope_ambiguous"]
    assert (covered.shares, covered.price) == (Decimal(99183), Decimal("170.03"))


def test_sale_of_same_day_exercised_shares_is_not_a_signal():
    """Nike officer, 0001127602-24-014652: exercised 45,000 options and sold 45,000 shares."""
    f = load("0001127602-24-014652")
    by_code = {r.code: r for r in f.rows if r.table == "non_derivative" and not r.is_holding}
    assert (by_code["M"].shares, by_code["M"].category) == (Decimal(45000), "option_exercise")
    assert (by_code["S"].shares, by_code["S"].category) == (
        Decimal(45000),
        "sale_linked_to_exercise",
    )
    assert all(r.signal is None for r in f.rows)


def test_discretionary_open_market_sale_is_a_sell_signal():
    """Apple director, 0001140361-26-023363: plain sale, no plan, no exercise."""
    f = load("0001140361-26-023363")
    sale = next(r for r in f.rows if r.code == "S")
    assert (sale.shares, sale.price) == (Decimal(50000), Decimal("311.02"))
    assert (sale.category, sale.signal, sale.plan_10b5_1) == (
        "open_market_sale",
        "discretionary_sell",
        False,
    )


def test_shares_bought_from_the_company_are_not_an_open_market_purchase():
    """Intel CEO, 0001127602-25-010360: 1,043,406 shares at $23.96 acquired from Intel under his
    offer letter (code A). Paid for, but not bought in the market, so not a signal."""
    f = load("0001127602-25-010360")
    assert "acquired these shares from Intel" in f.rows[0].footnotes
    assert trades(f) == [("A", Decimal(1043406), Decimal("23.96"), "acquisition_from_issuer", None)]


def test_trades_made_without_the_insiders_knowledge_are_not_signals():
    """Carvana director, 0001088011-26-000004: 'effected by an investment manager with
    discretionary authority ... without the knowledge or direction of the Reporting Person'."""
    f = load("0001088011-26-000004")
    assert "without the knowledge or direction of the Reporting Person" in f.rows[0].footnotes
    assert trades(f) == [
        ("P", Decimal(5), Decimal("441.36"), "third_party_managed", None),
        ("S", Decimal(3), Decimal("411.61"), "third_party_managed", None),
        ("S", Decimal(2), Decimal("310.76"), "third_party_managed", None),
    ]


def test_gifts_are_not_signals():
    f = load("0001127602-23-002926")
    gifts = [r for r in f.rows if r.code == "G"]
    assert gifts and all((r.category, r.signal) == ("gift", None) for r in gifts)
    assert all(r.signal is None for r in f.rows)


def test_only_open_market_trades_ever_become_signals():
    """Across every fixture: a signal implies code P/S in the stock table, no plan, no issue."""
    seen = set()
    for entry in MANIFEST:
        for r in load(entry["accession"]).rows:
            seen.add(r.category)
            if r.signal:
                assert r.code in ("P", "S") and r.table == "non_derivative"
                assert r.category in ("open_market_purchase", "open_market_sale")
                assert not r.plan_10b5_1 and r.plan_basis is None and not r.issues
                assert r.price > 0 and r.shares > 0
            if r.code in ("A", "M", "F", "G", "W", "C", "J", "D", "X", None):
                assert r.signal is None
    assert {
        "acquisition_from_issuer",
        "option_exercise",
        "tax_withholding",
        "gift",
        "inheritance",
        "holding",
        "planned_sale",
        "planned_purchase",
        "sale_linked_to_exercise",
        "sale_to_cover_taxes",
    } <= seen


APPLE_PLAN = (
    "This transaction was made pursuant to a Rule 10b5-1 trading plan adopted by the reporting "
    "person on November 15, 2022."
)
NIKE_PLAN = (
    "The transaction was effected pursuant to a 10b5-1 trading plan adopted by the reporting "
    "person on July 3, 2023."
)
NIKE_POLICY = (
    "Pursuant to Company policy, market transactions in Company stock by officers and directors "
    "are permitted only after the first full trading day after the release of quarterly earnings "
    "and ending on the fourteenth day of the third month of the following fiscal quarter, except "
    "pursuant to approved 10b5-1 trading plans."
)


def test_quoted_footnotes_are_verbatim_from_the_filings():
    assert APPLE_PLAN.encode() in fixture_xml("0000320193-23-000096")
    assert NIKE_PLAN.encode() in fixture_xml("0001127602-24-019550")
    assert NIKE_POLICY.encode() in fixture_xml("0001127602-24-019550")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (APPLE_PLAN, True),
        (NIKE_PLAN, True),
        (NIKE_POLICY, False),
        (f"{NIKE_POLICY} | {NIKE_PLAN}", True),
        # Constructed wording, to pin the rule's edges.
        ("Exercise and sale was pursuant to an approved 10b5-1 trading plan.", True),
        ("The sale was not made pursuant to a Rule 10b5-1 plan.", False),
        ("Sales were not discretionary and were made under a Rule 10b5-1 plan.", True),
        ("Shares sold under a Rule 10b5 1 plan.", True),
        ("Weighted average price.", False),
        ("", False),
    ],
)
def test_affirms_10b5_1(text, expected):
    assert affirms_10b5_1(text) is expected
