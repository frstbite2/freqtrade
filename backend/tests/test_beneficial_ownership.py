"""Schedules 13D and 13G: parsing, ingestion, history, API.

Runs on real filings stored unmodified (see fixtures/edgar13dg/README.md). Expected numbers
were read from the original documents, not taken from this code's output.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.core.config import load_settings
from backend.main import create_app
from backend.models import AuditLog
from backend.models.beneficial import BeneficialFiling, BeneficialIssuer
from backend.services.beneficial_ownership.history import describe, filings_as_of, holders
from backend.services.beneficial_ownership.ingest import ingest_issuer
from backend.services.beneficial_ownership.parser import (
    ScheduleParseError,
    parse_header,
    parse_schedule,
    schedule_of,
)
from backend.services.edgar import EdgarError
from backend.tests.conftest import FIXTURES_13DG, MANIFEST_13DG


D = Decimal
GME, NKE, INTC = 1326380, 320187, 50863
SINCE = date(2023, 11, 15)
COHEN_14, COHEN_15, COHEN_21 = (
    "0000921895-26-000120",
    "0000921895-26-002474",
    "0000921895-26-002783",
)


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def raw(accession: str) -> bytes:
    return next(FIXTURES_13DG.glob(f"{accession}.*")).read_bytes()


# --- parsing ---


def test_every_structured_fixture_parses():
    for entry in MANIFEST_13DG:
        if entry["form"].startswith("SCHEDULE"):
            parsed = parse_schedule(raw(entry["accession"]))
            assert (parsed.form, parsed.issuer_cik) == (entry["form"], entry["cik"])
            assert parsed.schedule == schedule_of(entry["form"]) and parsed.persons
            assert parsed.cusip and parsed.event_date and not parsed.issues


def test_schedule_13d_amendment_fields():
    p = parse_schedule(raw(COHEN_14))
    assert (p.form, p.schedule, p.is_amendment, p.amendment_number) == (
        "SCHEDULE 13D/A",
        "13D",
        True,
        14,
    )
    assert (p.issuer_cik, p.issuer_name, p.cusip) == (GME, "GameStop Corp.", "36467W109")
    assert p.event_date == date(2026, 1, 21) and p.rule is None
    (cohen,) = p.persons
    assert (cohen.name, cohen.person_type) == ("Cohen Ryan", "IN")
    assert (cohen.shares, cohen.percent) == (D("42082626.00"), D("9.3"))


def test_schedule_13g_fields():
    p = parse_schedule(raw("0000093751-26-000274"))
    assert (p.form, p.schedule, p.is_amendment, p.amendment_number) == (
        "SCHEDULE 13G",
        "13G",
        False,
        None,
    )
    assert (p.issuer_cik, p.cusip, p.event_date) == (NKE, "654106103", date(2026, 3, 31))
    assert p.rule == "Rule 13d-1(b)" and p.purpose is None  # a passive filer states no purpose
    (holder,) = p.persons  # the signature block repeats the name; it is not a second holder
    assert (holder.name, holder.person_type) == ("STATE STREET CORPORATION", "HC")
    assert (holder.shares, holder.percent) == (D("59588679.00"), D("5"))


def test_both_cusip_layouts_are_read():
    assert b"<issuerCusip>654106103" in raw("0000093751-25-000620")  # older layout
    assert parse_schedule(raw("0000093751-25-000620")).cusip == "654106103"
    assert b"issuerCusipNumber>654106103" in raw("0000093751-26-000274")
    assert schedule_of("SC 13D/A") == "13D" and schedule_of("SCHEDULE 13G") == "13G"


def test_edgar_header_names_the_subject_and_the_filer():
    assert parse_header(raw("0001104659-24-021208")) == (INTC, 102909, "VANGUARD GROUP INC")
    # Filed by Intel about another company: the subject is not Intel.
    subject, filer, name = parse_header(raw("0000050863-24-000116"))
    assert (subject, filer, name) == (1929589, INTC, "INTEL CORP")
    with pytest.raises(ScheduleParseError, match="header"):
        parse_header(b"<html>Too many requests</html>")


GOOD = raw(COHEN_14)


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (b"<html>busy</html>", "unsupported submission type"),
        (b"not xml", "malformed XML"),
        (b'<!DOCTYPE x [<!ENTITY a "b">]>' + GOOD, "DTD"),
        (GOOD.replace(b"SCHEDULE 13D/A", b"13F-HR"), "unsupported submission type"),
        (GOOD.replace(b"0001326380</issuerCIK>", b"abc</issuerCIK>"), "issuer"),
        (GOOD.replace(b"reportingPersonInfo", b"somethingElse"), "no reporting person"),
    ],
)
def test_unusable_documents_are_rejected(broken, message):
    assert broken != GOOD
    with pytest.raises(ScheduleParseError, match=message):
        parse_schedule(broken)


@pytest.mark.parametrize(
    ("old", "new", "issue"),
    [
        (b"<percentOfClass>9.3<", b"<percentOfClass>about nine<", "invalid_percent"),
        (b"<percentOfClass>9.3<", b"<percentOfClass>930<", "percent_over_100"),
        (b"<aggregateAmountOwned>42082626.00<", b"<aggregateAmountOwned>-1<", "invalid_shares"),
    ],
)
def test_damaged_figures_are_flagged_not_guessed(old, new, issue):
    assert old in GOOD
    person = parse_schedule(GOOD.replace(old, new)).persons[0]
    assert issue in person.issues
    if issue != "percent_over_100":
        assert (person.percent if "percent" in issue else person.shares) is None


def test_percent_sign_and_bad_date():
    assert parse_schedule(GOOD.replace(b">9.3<", b">9.3%<")).persons[0].percent == D("9.3")
    bad = parse_schedule(GOOD.replace(b"01/21/2026</dateOfEvent>", b"2026-01-21</dateOfEvent>"))
    assert bad.event_date is None and bad.issues == ["invalid_event_date"]


# --- ingestion ---


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_ingest_is_complete_idempotent_and_audited(db_session, edgar_client):
    listed = sum(1 for m in MANIFEST_13DG if m["ticker"] == "GME")
    report = ingest_issuer(db_session, edgar_client, "gme", SINCE)
    assert (report.cik, report.listed, report.stored, report.unstructured, report.failed) == (
        GME,
        listed,
        listed,
        1,
        {},
    )
    requests = edgar_client.requests_made
    again = ingest_issuer(db_session, edgar_client, "GME", SINCE)
    assert (again.stored, again.already_stored) == (0, listed)
    assert edgar_client.requests_made == requests and count(db_session, BeneficialFiling) == listed

    filing = db_session.get(BeneficialFiling, COHEN_15)
    assert (filing.schedule, filing.form, filing.amendment_number, filing.structured) == (
        "13D",
        "SCHEDULE 13D/A",
        15,
        True,
    )
    assert filing.accepted_at == datetime(2026, 9, 3, 22, 42, 51, tzinfo=UTC)
    assert (filing.event_date, filing.filer_name, filing.cusip) == (
        date(2026, 9, 3),
        "Cohen Ryan",
        "36467W109",
    )
    assert filing.url.endswith("/000092189526002474/0000921895-26-002474-index.htm")
    assert [(p.name, p.shares, p.percent) for p in filing.persons] == [
        ("Cohen Ryan", D("42082626"), D("8.3"))
    ]

    old = db_session.get(BeneficialFiling, "0000921895-24-001394")
    assert (old.form, old.schedule, old.structured, old.filer_name, old.persons) == (
        "SC 13D/A",
        "13D",
        False,
        "RC Ventures LLC",
        [],
    )
    assert old.issues == ["free-form filing: shares and percentage are not parsed"]

    issuer = db_session.get(BeneficialIssuer, GME)
    assert (issuer.ticker, issuer.history_since, issuer.failed_filings) == ("GME", SINCE, 0)
    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "beneficial.ingest")
    ).all()
    assert [(a.detail["ticker"], a.detail["stored"]) for a in audits] == [
        ("GME", listed),
        ("GME", 0),
    ]


def test_a_companys_own_stake_in_another_company_is_skipped(db_session, edgar_client):
    report = ingest_issuer(db_session, edgar_client, "INTC", SINCE)
    assert (report.listed, report.stored, report.other_issuer) == (2, 1, 1)
    assert db_session.get(BeneficialFiling, "0000050863-24-000116") is None
    assert (
        db_session.get(BeneficialFiling, "0001104659-24-021208").filer_name == "VANGUARD GROUP INC"
    )


def test_unknown_ticker_is_an_error(db_session, edgar_client):
    with pytest.raises(EdgarError, match="not in SEC's company list"):
        ingest_issuer(db_session, edgar_client, "NOSUCH", SINCE)
    assert count(db_session, BeneficialIssuer) == 0


# --- history ---


def test_13d_history_separates_share_changes_from_percentage_changes(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "GME", SINCE)
    rows = {r["accession"]: r for r in describe(filings_as_of(db_session, GME, at("2026-12-01")))}
    first, diluted, latest = rows[COHEN_14], rows[COHEN_15], rows[COHEN_21]
    assert first["change"] is None  # nothing earlier from this holder in the fixtures
    assert (first["schedule"], first["shares"], first["percent"]) == (
        "13D",
        "42082626.0000",
        "9.3000",
    )
    assert "influencing or controlling" in first["schedule_meaning"]
    # Amendment 15: the same 42,082,626 shares are now 8.3% of a larger class.
    assert (diluted["change"]["shares"], diluted["change"]["percent_points"]) == (
        "0.0000",
        "-1.0000",
    )
    assert diluted["change"]["notes"] == [
        "same share count: the percentage moved because the share class changed size"
    ]
    assert diluted["change"]["since_accession"] == COHEN_14
    # Amendment 21: 46,227,436 shares, 9.1%.
    assert (latest["change"]["shares"], latest["change"]["percent_points"]) == (
        "4144810.0000",
        "0.8000",
    )
    assert latest["filing_url"].startswith("https://www.sec.gov/Archives/edgar/data/1326380/")


def test_history_is_point_in_time(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "GME", SINCE)
    before = filings_as_of(db_session, GME, at("2026-09-03T22:42:50"))
    assert COHEN_15 not in [f.accession for f in before]
    assert COHEN_15 in [
        f.accession for f in filings_as_of(db_session, GME, at("2026-09-03T22:42:51"))
    ]
    (cohen,) = (h for h in holders(before) if h["holder"] == "Cohen Ryan")
    assert (cohen["accession"], cohen["percent"]) == (COHEN_14, "9.3000")


def test_holders_latest_per_holder_passive_exits_and_unparsed_filings(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    found = holders(filings_as_of(db_session, NKE, at("2026-12-01")))
    assert [(h["holder"], h["percent"], h["above_5_percent"]) for h in found] == [
        ("Vanguard Capital Management", "7.5000", True),
        ("Capital World Investors", "6.0000", True),
        ("Vanguard Portfolio Management", "5.1900", True),
        ("STATE STREET CORPORATION", "5.0000", True),
        ("The Vanguard Group", "0.0000", False),  # reported an exit; kept, and marked
        ("BlackRock Inc.", None, None),  # free-form filing: figures unknown, not zero
        ("VANGUARD GROUP INC", None, None),
    ]
    assert all(h["schedule"] == "13G" and "passive" in h["schedule_meaning"] for h in found)
    state_street = found[3]
    # 58,049,195 shares (4.9%) on 30 Sep 2025, then 59,588,679 (5%) on 31 Mar 2026.
    assert state_street["change"] == {
        "since_accession": "0000093751-25-000620",
        "since_filed_date": "2025-11-10",
        "shares": "1539484.0000",
        "percent_points": "0.1000",
        "notes": [],
    }
    assert (state_street["event_date"], state_street["filed_date"]) == ("2026-03-31", "2026-05-12")
    assert found[5]["structured"] is False and found[5]["issues"]


def test_change_notes_on_constructed_filings():
    """Rule edges not present in the fixtures (synthetic rows)."""
    from backend.models.beneficial import BeneficialOwner

    def filing(accession, schedule, shares, percent, day):
        return BeneficialFiling(
            accession=accession,
            form=f"SCHEDULE {schedule}",
            schedule=schedule,
            is_amendment=False,
            structured=True,
            filer_cik=1,
            filer_name="Fund LP",
            filed_date=date(2026, 1, day),
            accepted_at=at(f"2026-01-{day:02d}T21:00:00"),
            issues=[],
            url="",
            persons=[
                BeneficialOwner(
                    row_index=0, name="Fund LP", shares=D(shares), percent=D(percent), issues=[]
                )
            ],
        )

    rows = describe(
        [
            filing("a", "13G", "1000000", "6.0", 5),
            filing("b", "13D", "1200000", "7.2", 10),  # passive holder turns active
            filing("c", "13D", "12000000", "7.2", 15),  # ten times the shares, same stake: a split
            filing("d", "13D", "5000000", "3.0", 20),  # falls under 5%
        ]
    )
    notes = [r["change"]["notes"] if r["change"] else None for r in rows]
    assert notes[0] is None
    assert notes[1] == ["switched from Schedule 13G to Schedule 13D"]
    assert notes[2] and notes[2][0].startswith("share count changed far more than the percentage")
    assert notes[3] == ["now below 5%: the holder need not file further updates"]


# --- API ---

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def api(tmp_path, monkeypatch, edgar_client):
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.sqlite")
    app = create_app(load_settings())
    with TestClient(app) as client:
        with app.state.sessions() as session:
            ingest_issuer(session, edgar_client, "GME", SINCE)
        yield client


def test_api_holders_and_filings(api):
    body = api.get("/api/v1/ownership/gme/holders", headers=AUTH).json()
    assert (body["ticker"], body["cik"], body["missing_filings"]) == ("GME", GME, 0)
    assert "not current holdings" in body["disclaimer"]
    assert [(h["holder"], h["schedule"], h["percent"]) for h in body["holders"]] == [
        ("Cohen Ryan", "13D", "9.1000"),
        ("The Vanguard Group", "13G", "0.0000"),
        ("RC Ventures LLC", "13D", None),
    ]
    active = api.get(
        "/api/v1/ownership/GME/holders", params={"schedule": "13D"}, headers=AUTH
    ).json()
    assert {h["schedule"] for h in active["holders"]} == {"13D"}

    history = api.get("/api/v1/ownership/GME/filings", headers=AUTH).json()
    assert history["total"] == 5 and history["filings"][0]["accession"] == COHEN_21  # newest first
    earlier = api.get(
        "/api/v1/ownership/GME/filings",
        params={"as_of": "2026-02-01T00:00:00Z", "limit": 1},
        headers=AUTH,
    ).json()
    assert (earlier["total"], len(earlier["filings"]), earlier["filings"][0]["accession"]) == (
        2,
        1,
        COHEN_14,
    )


def test_api_says_unavailable_rather_than_nobody(api):
    response = api.get("/api/v1/ownership/TSLA/holders", headers=AUTH)
    assert response.status_code == 404
    assert "unavailable, not that nobody holds more than 5%" in response.json()["detail"]
    assert api.get("/api/v1/ownership/GME/holders").status_code == 401


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/v1/ownership/GME/holders", {"as_of": "2026-02-01T00:00:00"}),
        ("/api/v1/ownership/GME/holders", {"schedule": "13F"}),
        ("/api/v1/ownership/G$ME/filings", {}),
        ("/api/v1/ownership/GME/filings", {"limit": 0}),
    ],
)
def test_api_validates_input(api, path, params):
    assert api.get(path, params=params, headers=AUTH).status_code == 422
