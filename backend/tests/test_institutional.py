"""Form 13F parsing, ingestion, quarter-over-quarter changes, scoring and API.

Runs on real 13F submissions stored unmodified (see fixtures/edgar13f/README.md). Expected
numbers were read from the original filings, not taken from this code's output.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.core.config import load_settings
from backend.main import create_app
from backend.models import AuditLog
from backend.models.institutional import (
    InstitutionalFiling,
    InstitutionalManager,
)
from backend.services.institutional_analysis.holdings import (
    changes,
    previous_quarter,
    report_as_of,
    split_ratios,
)
from backend.services.institutional_analysis.ingest import ingest_manager
from backend.services.institutional_analysis.parser import Form13FError, parse_13f
from backend.services.institutional_analysis.scoring import score_security
from backend.tests.conftest import FIXTURES_13F, MANIFEST_13F


D = Decimal
PERSHING, ELLIOTT, TIGER, APPALOOSA, DUQUESNE = 1336528, 1791786, 1167483, 1656456, 1536411
SINCE = date(2022, 6, 1)
NVIDIA, HERTZ, NIKE, UBER, CHIPOTLE = (
    "67066G104",
    "42806J700",
    "654106103",
    "90353T100",
    "169656105",
)


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def parsed(accession: str):
    entry = next(m for m in MANIFEST_13F if m["accession"] == accession)
    text = (FIXTURES_13F / f"{accession}.txt").read_bytes()
    return parse_13f(text, date.fromisoformat(entry["filingDate"]))


# --- parsing ---


def test_every_fixture_parses_and_reconciles_with_its_cover_page():
    for entry in MANIFEST_13F:
        filing = parsed(entry["accession"])
        assert filing.form == entry["form"], entry["accession"]
        if filing.entry_total is not None:
            assert len(filing.rows) == filing.entry_total
            assert (
                abs(sum(r.value for r in filing.rows) - filing.value_total)
                <= len(filing.rows) * filing.value_multiplier
            )
        assert all(not r.issues for r in filing.rows)


def test_holdings_report_fields():
    f = parsed("0001172661-25-001119")
    assert (f.form, f.period, f.report_type) == (
        "13F-HR",
        date(2024, 12, 31),
        "13F HOLDINGS REPORT",
    )
    assert f.manager_name == "Pershing Square Capital Management, L.P."
    assert (f.is_amendment, f.amendment_type, f.confidential_omitted) == (False, None, True)
    assert (f.entry_total, f.value_total, f.value_multiplier, f.issues) == (
        10,
        D("12614560346"),
        1,
        [],
    )
    nike = next(r for r in f.rows if r.cusip == NIKE)
    assert (nike.issuer_name, nike.title_of_class) == ("NIKE INC", "CL B")
    assert (nike.value, nike.amount, nike.amount_type, nike.put_call) == (
        D("1420246144"),
        D("18768946"),
        "SH",
        None,
    )


def test_values_filed_before_2023_are_thousands_of_dollars():
    f = parsed("0001172661-22-002568")
    assert (f.value_multiplier, f.value_total, f.issues) == (1000, D("7877045000"), [])
    chipotle = next(r for r in f.rows if r.cusip == CHIPOTLE)
    assert (chipotle.value, chipotle.amount) == (
        D("1660862000"),
        D("1105208"),
    )  # about $1,503 a share


def test_thousands_are_recognised_when_a_manager_ignores_the_2023_rule():
    f = parsed("0001536411-26-000006")  # filed August 2026, cover total 5,210,860
    assert f.value_multiplier == 1000 and f.value_total == D("5210860000")
    assert len(f.issues) == 1 and "values taken as thousands of dollars" in f.issues[0]
    first = f.rows[0]
    assert (first.issuer_name, first.value, first.amount) == (
        "10X Genomics Inc",
        D("15455000"),
        D("403100"),
    )


def test_amendment_and_notice_types():
    added = parsed("0001172661-25-001497")
    assert (added.form, added.is_amendment, added.amendment_type) == (
        "13F-HR/A",
        True,
        "NEW HOLDINGS",
    )
    assert [(r.cusip, r.amount) for r in added.rows] == [(HERTZ, D("12713963"))]
    assert parsed("0001013594-25-000512").amendment_type == "RESTATEMENT"
    notice = parsed("0001172661-26-003777")
    assert (notice.form, notice.report_type, notice.rows, notice.entry_total) == (
        "13F-NT",
        "13F NOTICE",
        [],
        None,
    )


GOOD = (FIXTURES_13F / "0001172661-25-001497.txt").read_bytes()


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (b"<SEC-DOCUMENT>plain text filing from 2010</SEC-DOCUMENT>", "no XML documents"),
        (
            GOOD.replace(b"<submissionType>13F-HR/A", b"<submissionType>10-K"),
            "unsupported submission type",
        ),
        (GOOD.replace(b"12-31-2024", b"2024-12-31"), "invalid report period"),
        (GOOD.replace(b"<XML>", b'<XML><!DOCTYPE x [<!ENTITY a "b">]>', 1), "DTD"),
        (GOOD.replace(b"</coverPage>", b"</coverPag>"), "malformed XML"),
    ],
)
def test_unusable_submissions_are_rejected(broken, message):
    assert broken != GOOD
    with pytest.raises(Form13FError, match=message):
        parse_13f(broken, date(2025, 4, 16))


@pytest.mark.parametrize(
    ("old", "new", "row_issue", "filing_issue"),
    [
        (b"<cusip>42806J700", b"<cusip>42806J70", "invalid_cusip", None),
        (b"<value>46533105<", b"<value>lots<", "invalid_value", "rows sum to"),
        (b"<sshPrnamt>12713963<", b"<sshPrnamt>-5<", "invalid_amount", None),
        (b"<sshPrnamtType>SH<", b"<sshPrnamtType>XX<", "invalid_amount_type", None),
        (b"<tableEntryTotal>1<", b"<tableEntryTotal>2<", None, "cover states 2 rows, table has 1"),
        (b"<tableValueTotal>46533105<", b"<tableValueTotal>99<", None, "cover states value 99"),
    ],
)
def test_damaged_rows_and_totals_are_flagged(old, new, row_issue, filing_issue):
    assert old in GOOD
    filing = parse_13f(GOOD.replace(old, new), date(2025, 4, 16))
    if row_issue:
        assert filing.rows[0].issues == [row_issue]
    if filing_issue:
        assert any(filing_issue in issue for issue in filing.issues)


# --- ingestion ---


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_ingest_is_complete_idempotent_and_audited(db_session, edgar_client):
    listed = sum(1 for m in MANIFEST_13F if m["cik"] == PERSHING)
    report = ingest_manager(db_session, edgar_client, PERSHING, SINCE)
    assert (report.name, report.listed, report.stored, report.failed) == (
        "Pershing Square Capital Management, L.P.", listed, listed, {},
    )  # fmt: skip
    requests = edgar_client.requests_made
    again = ingest_manager(db_session, edgar_client, PERSHING, SINCE)
    assert (again.stored, again.already_stored) == (0, listed)
    assert edgar_client.requests_made == requests  # served from cache
    assert count(db_session, InstitutionalFiling) == listed

    filing = db_session.get(InstitutionalFiling, "0001172661-25-001497")
    assert filing.accepted_at == datetime(2025, 4, 16, 11, 43, 9, tzinfo=UTC)
    assert (filing.period, filing.amendment_type) == (date(2024, 12, 31), "NEW HOLDINGS")
    assert filing.url.endswith("/000117266125001497/0001172661-25-001497-index.htm")
    (row,) = filing.holdings
    assert (row.cusip, row.amount, row.value) == (HERTZ, D("12713963"), D("46533105"))
    manager = db_session.get(InstitutionalManager, PERSHING)
    assert (manager.history_since, manager.failed_filings) == (SINCE, 0)
    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "institutional.ingest")
    ).all()
    assert [a.detail["stored"] for a in audits] == [listed, 0]


def test_filing_with_inferred_unit_is_stored_and_reported(db_session, edgar_client):
    report = ingest_manager(db_session, edgar_client, DUQUESNE, SINCE)
    assert report.with_issues == ["0001536411-26-000006"] and report.stored == 1
    stored = db_session.get(InstitutionalFiling, "0001536411-26-000006")
    assert stored.value_multiplier == 1000 and "thousands" in stored.issues[0]


# --- what was disclosed, and when ---


def test_confidential_position_appears_only_once_its_amendment_is_public(db_session, edgar_client):
    ingest_manager(db_session, edgar_client, PERSHING, SINCE)
    q4 = date(2024, 12, 31)
    assert report_as_of(db_session, PERSHING, q4, at("2025-02-14T21:02:09")).status == "not_filed"

    before = report_as_of(db_session, PERSHING, q4, at("2025-04-16T11:43:08"))
    assert before.status == "reported" and before.confidential_omitted
    assert len(before.positions) == 10 and HERTZ not in before.positions
    assert before.disclosed_at == at("2025-02-14T21:02:10")

    after = report_as_of(db_session, PERSHING, q4, at("2025-04-16T11:43:09"))
    assert after.filings == ["0001172661-25-001119", "0001172661-25-001497"]
    assert after.positions[HERTZ].shares == D("12713963") and len(after.positions) == 11
    assert after.disclosed_at == at("2025-04-16T11:43:09")


def test_restatement_replaces_the_original(db_session, edgar_client):
    ingest_manager(db_session, edgar_client, ELLIOTT, SINCE)
    q4 = date(2024, 12, 31)
    original = report_as_of(db_session, ELLIOTT, q4, at("2025-03-01T00:00:00"))
    restated = report_as_of(db_session, ELLIOTT, q4, at("2025-05-01T00:00:00"))
    assert original.filings == ["0001013594-25-000294"]
    assert restated.filings == ["0001013594-25-000512"]  # not both: that would double every share
    assert {c: p.shares for c, p in restated.positions.items()} == {
        c: p.shares for c, p in original.positions.items()
    }
    assert (
        original.option_rows == restated.option_rows > 0
    )  # puts and calls are not share ownership


def test_notice_means_reported_elsewhere_not_sold_out(db_session, edgar_client):
    ingest_manager(db_session, edgar_client, PERSHING, SINCE)
    report = report_as_of(db_session, PERSHING, date(2026, 6, 30), at("2026-09-01T00:00:00"))
    assert (report.status, report.positions, report.filings) == (
        "reported_elsewhere",
        {},
        ["0001172661-26-003777"],
    )


def test_previous_quarter():
    assert previous_quarter(date(2025, 3, 31)) == date(2024, 12, 31)
    assert previous_quarter(date(2024, 12, 31)) == date(2024, 9, 30)
    assert previous_quarter(date(2024, 6, 30)) == date(2024, 3, 31)


# --- changes between quarters ---


def test_quarter_over_quarter_changes(db_session, edgar_client):
    """Pershing Square, 30 Sep 2024 to 31 Dec 2024, share counts from the two filings."""
    ingest_manager(db_session, edgar_client, PERSHING, SINCE)
    as_of = at("2025-03-01T00:00:00")  # before the Hertz amendment
    previous = report_as_of(db_session, PERSHING, date(2024, 9, 30), as_of)
    current = report_as_of(db_session, PERSHING, date(2024, 12, 31), as_of)
    found = {c.cusip: c for c in changes(previous, current, split_ratios([(previous, current)]))}
    assert {cusip: (c.status, c.change_pct) for cusip, c in found.items()} == {
        "02079K107": ("unchanged", 0.0),  # Alphabet C: 7,547,582 both quarters
        "02079K305": ("unchanged", 0.0),
        "11271J107": ("increased", pytest.approx(6.59)),  # Brookfield 32,735,883 -> 34,893,064
        "13646K108": ("unchanged", 0.0),
        CHIPOTLE: ("reduced", pytest.approx(-14.44)),  # 28,815,165 -> 24,653,533
        "43300A203": ("reduced", pytest.approx(-26.18)),  # Hilton 7,370,168 -> 5,440,546
        "44267T102": ("unchanged", 0.0),
        NIKE: ("increased", pytest.approx(15.29)),  # 16,280,338 -> 18,768,946
        "76131D103": ("unchanged", 0.0),
        "812215101": ("exited", -100.0),  # Seaport rights, gone after the offering
        "812215200": ("increased", pytest.approx(139.84)),  # 2,094,673 -> 5,023,780
    }
    assert (found[NIKE].previous_shares, found[NIKE].shares) == (D("16280338"), D("18768946"))

    later = at("2025-06-01T00:00:00")
    q4 = report_as_of(db_session, PERSHING, date(2024, 12, 31), later)
    q1 = report_as_of(db_session, PERSHING, date(2025, 3, 31), later)
    found = {c.cusip: c for c in changes(q4, q1, split_ratios([(q4, q1)]))}
    assert (found[UBER].status, found[UBER].change_pct, found[UBER].shares) == (
        "new",
        None,
        D("30301161"),
    )
    assert (found[NIKE].status, found[NIKE].shares) == ("exited", D(0))
    # Hertz was held (confidentially) at year end, so it is an increase, not a new position.
    assert (found[HERTZ].status, found[HERTZ].change_pct) == ("increased", pytest.approx(17.98))


def test_stock_split_is_not_read_as_buying(db_session, edgar_client):
    """Nvidia split 10-for-1 in June 2024. Tiger held 968,355 then 9,683,550 shares (unchanged);
    Appaloosa held 442,000 then 690,000, which is a sale of 84%, not a purchase of 56%."""
    for cik in (TIGER, APPALOOSA):
        ingest_manager(db_session, edgar_client, cik, SINCE)
    as_of = at("2024-09-01T00:00:00")
    pairs = {
        cik: (
            report_as_of(db_session, cik, date(2024, 3, 31), as_of),
            report_as_of(db_session, cik, date(2024, 6, 30), as_of),
        )
        for cik in (TIGER, APPALOOSA)
    }
    ratios = split_ratios(list(pairs.values()))
    assert ratios[NVIDIA] == 10
    nvda = {
        cik: next(c for c in changes(*pair, ratios) if c.cusip == NVIDIA)
        for cik, pair in pairs.items()
    }
    assert (nvda[TIGER].status, nvda[TIGER].change_pct) == ("unchanged", 0.0)
    assert (nvda[APPALOOSA].status, nvda[APPALOOSA].change_pct) == (
        "reduced",
        pytest.approx(-84.39),
    )
    assert "10-for-1 stock split" in nvda[APPALOOSA].note
    assert (nvda[APPALOOSA].previous_shares, nvda[APPALOOSA].shares) == (
        D("442000"),
        D("690000"),
    )  # as filed

    # Without a holder who carried the split exactly, the security is left uninterpreted.
    alone = split_ratios([pairs[APPALOOSA]])
    assert alone[NVIDIA] is None
    unclear = next(c for c in changes(*pairs[APPALOOSA], alone) if c.cusip == NVIDIA)
    assert (unclear.status, unclear.change_pct) == (
        "unclear",
        None,
    ) and "split is likely" in unclear.note
    # Ordinary securities are untouched: a manager doubling a position is not a split.
    assert all(v is None or v == 10 for v in ratios.values())


# --- scoring ---


def test_score_counts_only_comparable_managers_and_respects_the_split(db_session, edgar_client):
    for cik in (TIGER, APPALOOSA, PERSHING):
        ingest_manager(db_session, edgar_client, cik, SINCE)
    result = score_security(db_session, NVIDIA, at("2024-09-01T00:00:00"))
    assert (result["period"], result["previous_period"]) == ("2024-06-30", "2024-03-31")
    assert result["issuer_name"] == "NVIDIA CORPORATION"
    assert result["counts"] == {
        "new": 0,
        "increased": 0,
        "reduced": 1,
        "exited": 0,
        "unchanged": 1,
        "unclear": 0,
    }
    assert result["score"] == 0.0  # net selling: reported, never scored as accumulation
    assert result["managers_compared"] == 2
    # Pershing's fixtures lack those two quarters: not comparable, which is not "sold".
    assert list(result["managers_not_comparable"]) == ["Pershing Square Capital Management, L.P."]
    tiger = next(h for h in result["holders"] if h["manager_cik"] == TIGER)
    assert (tiger["previous_shares"], tiger["shares"], tiger["status"]) == (
        "968355.0000",
        "9683550.0000",
        "unchanged",
    )
    assert tiger["disclosed_at"].startswith("2024-08-14")  # the day the filing was accepted
    assert "not current positions" in result["disclaimer"]


def test_score_of_a_new_position_and_of_nothing(db_session, edgar_client):
    ingest_manager(db_session, edgar_client, PERSHING, SINCE)
    as_of = at("2025-06-01T00:00:00")
    uber = score_security(db_session, UBER, as_of)
    assert uber["counts"]["new"] == 1 and uber["managers_compared"] == 1
    got = {c["name"]: c for c in uber["components"]}
    assert (
        got["breadth"]["points"],
        got["new_positions"]["points"],
        got["net_buying"]["points"],
    ) == (30.0, 10.0, 25.0)
    assert got["consistency"]["available"] is False  # nobody held it two quarters back
    assert uber["score"] == pytest.approx(100 * 65 / 75, abs=0.1)

    nike = score_security(db_session, NIKE, as_of)  # sold out in the quarter
    assert nike["counts"]["exited"] == 1 and nike["score"] == 0.0
    unknown = score_security(db_session, "000000000", as_of)
    assert (
        unknown["score"] == 0.0
        and unknown["holders"] == []
        and "None of the 1" in unknown["explanation"]
    )
    # Nothing public yet at that moment: unavailable, not zero.
    assert score_security(db_session, UBER, at("2020-01-01T00:00:00")) is None


# --- API ---

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def api(tmp_path, monkeypatch, edgar_client):
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.sqlite")
    app = create_app(load_settings())
    with TestClient(app) as client:
        yield client, app, edgar_client


def test_api_reports_unavailable_before_anything_is_ingested(api):
    client, _, _ = api
    response = client.get(f"/api/v1/institutional/securities/{UBER}", headers=AUTH)
    assert (
        response.status_code == 404
        and "unavailable, not that there was no" in response.json()["detail"]
    )
    assert client.get("/api/v1/institutional/managers", headers=AUTH).json()["managers"] == []
    assert client.get(f"/api/v1/institutional/securities/{UBER}").status_code == 401


def test_api_endpoints(api):
    client, app, edgar = api
    with app.state.sessions() as session:
        ingest_manager(session, edgar, PERSHING, SINCE)
    when = {"as_of": "2025-06-01T00:00:00Z"}

    security = client.get(
        f"/api/v1/institutional/securities/{UBER.lower()}", params=when, headers=AUTH
    ).json()
    assert security["cusip"] == UBER and security["holders"][0]["institution"].startswith(
        "Pershing Square"
    )

    found = client.get("/api/v1/institutional/search", params={"name": "uber"}, headers=AUTH).json()
    assert found["matches"][0] == {
        "cusip": UBER,
        "title_of_class": "COM",
        "issuer_name": "UBER TECHNOLOGIES INC",
        "rows": 2,
    }

    (manager,) = client.get("/api/v1/institutional/managers", headers=AUTH).json()["managers"]
    assert (manager["cik"], manager["latest_period"], manager["missing_filings"]) == (
        PERSHING,
        "2026-06-30",
        0,
    )

    moves = client.get(
        f"/api/v1/institutional/managers/{PERSHING}/changes", params=when, headers=AUTH
    ).json()
    assert (moves["period"], moves["previous_period"], moves["total"]) == (
        "2025-03-31",
        "2024-12-31",
        12,
    )
    assert moves["changes"][0]["issuer_name"] == "UBER TECHNOLOGIES INC"  # largest position first
    assert moves["filings"] == ["0001172661-25-002315"]

    # Latest quarter is a notice, so there is nothing to compare; say so rather than show zeros.
    latest = client.get(f"/api/v1/institutional/managers/{PERSHING}/changes", headers=AUTH)
    assert latest.status_code == 404 and "reported_elsewhere" in latest.json()["detail"]


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/v1/institutional/securities/TOOSHORT", {}),
        ("/api/v1/institutional/securities/90353T100", {"as_of": "2025-06-01T00:00:00"}),
        ("/api/v1/institutional/search", {"name": "u"}),
        ("/api/v1/institutional/managers/0/changes", {}),
        ("/api/v1/institutional/managers/1336528/changes", {"limit": 0}),
    ],
)
def test_api_validates_input(api, path, params):
    assert api[0].get(path, params=params, headers=AUTH).status_code == 422
