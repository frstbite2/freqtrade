"""Ingestion, deduplication, point-in-time reads, scoring and API, on real filings served offline.

Expected money and holdings figures are worked out here from numbers read in the original
filings (shares, prices, post-transaction holdings), not taken from the code under test.
"""

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.core.config import load_settings
from backend.main import create_app
from backend.models import AuditLog
from backend.models.insider import InsiderFiling, InsiderIssuer, InsiderTransaction
from backend.services.edgar import EdgarClient, EdgarError
from backend.services.insider_intelligence import classify
from backend.services.insider_intelligence.history import effective_transactions, filings_as_of
from backend.services.insider_intelligence.ingest import ingest_issuer
from backend.services.insider_intelligence.scoring import score_issuer
from backend.tests.conftest import MANIFEST, SINCE, TEST_USER_AGENT, edgar_handler


NKE, INTC, AAPL = 320187, 50863, 320193
D = Decimal

# Nike purchases of April 2026, from the filings: (shares, price, total holdings afterwards).
HILL_ORIGINAL_PRICE, HILL_AMENDED_PRICE = D("42.265"), D("42.27")
HILL = (D("23660.235"), HILL_AMENDED_PRICE, D("265247.235"))
COOK = (D("25000"), D("42.43"), D("130480"))
ROGERS = (D("4000"), D("43.34"), D("41022"))
SWAN = (D("11781.387"), D("42.44"), D("55074.387") + D("1580"))
APRIL_BUYS = (HILL, COOK, ROGERS, SWAN)
APRIL_VALUE = sum(shares * price for shares, price, _ in APRIL_BUYS)


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


# --- ingestion ---


def test_ingest_stores_every_listed_filing_once(db_session, edgar_client):
    listed = sum(1 for m in MANIFEST if m["ticker"] == "NKE")
    report = ingest_issuer(db_session, edgar_client, "nke", SINCE)
    assert (report.cik, report.name, report.listed, report.stored) == (
        NKE,
        "NIKE, Inc.",
        listed,
        listed,
    )
    assert report.complete and not report.no_xml and report.other_issuer == 0

    requests_after_first_run = edgar_client.requests_made
    again = ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    assert (again.stored, again.already_stored) == (0, listed)
    assert edgar_client.requests_made == requests_after_first_run  # served from cache
    assert count(db_session, InsiderFiling) == listed

    issuer = db_session.get(InsiderIssuer, NKE)
    assert (issuer.ticker, issuer.history_since) == ("NKE", SINCE)
    assert datetime.now(UTC) - issuer.last_ingested_at < timedelta(minutes=1)


def test_rule_change_reclassifies_stored_filings(db_session, edgar_client, monkeypatch):
    first = ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    rows = count(db_session, InsiderTransaction)
    monkeypatch.setattr(classify, "CLASSIFIER_VERSION", classify.CLASSIFIER_VERSION + 1)
    again = ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    assert (again.stored, again.reclassified, again.already_stored) == (
        first.listed,
        first.listed,
        0,
    )
    assert count(db_session, InsiderFiling) == first.listed
    assert count(db_session, InsiderTransaction) == rows
    assert set(db_session.scalars(select(InsiderFiling.classifier_version))) == {
        classify.CLASSIFIER_VERSION
    }


def test_stored_values_are_exact_and_link_to_the_sec_filing(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    filing = db_session.get(InsiderFiling, "0000320187-26-000053")
    assert (filing.form_type, filing.is_amendment) == ("4/A", True)
    assert filing.original_filed_date == date(2026, 4, 14)
    assert (filing.owner_name, filing.officer_title) == ("Hill Elliott", "PRESIDENT & CEO")
    assert (filing.is_officer, filing.is_director, filing.is_ten_percent_owner) == (
        True,
        True,
        False,
    )
    assert filing.filed_date == date(2026, 4, 22)
    assert filing.accepted_at == datetime(2026, 4, 22, 20, 57, 24, tzinfo=UTC)
    assert filing.url == (
        "https://www.sec.gov/Archives/edgar/data/320187/000032018726000053/"
        "0000320187-26-000053-index.htm"
    )
    (row,) = filing.transactions
    assert (row.shares, row.price, row.shares_after) == HILL
    assert row.value == HILL[0] * HILL[1]
    assert (row.category, row.signal) == ("open_market_purchase", "discretionary_buy")


def test_filings_where_the_company_is_only_a_holder_are_skipped(db_session, edgar_client):
    """Intel's index lists Intel's own Form 4 about its Mobileye stake."""
    listed = sum(1 for m in MANIFEST if m["ticker"] == "INTC")
    report = ingest_issuer(db_session, edgar_client, "INTC", SINCE)
    assert (report.other_issuer, report.stored) == (1, listed - 1)
    assert db_session.get(InsiderFiling, "0000050863-25-000099") is None
    assert set(db_session.scalars(select(InsiderFiling.issuer_cik))) == {INTC}


def test_since_limits_the_history(db_session, edgar_client):
    report = ingest_issuer(db_session, edgar_client, "NKE", date(2026, 4, 1))
    expected = sum(1 for m in MANIFEST if m["ticker"] == "NKE" and m["filingDate"] >= "2026-04-01")
    assert report.stored == expected < 10
    assert db_session.get(InsiderIssuer, NKE).history_since == date(2026, 4, 1)
    ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    assert db_session.get(InsiderIssuer, NKE).history_since == SINCE


def test_unknown_ticker_is_an_error_not_an_empty_result(db_session, edgar_client):
    with pytest.raises(EdgarError, match="not in SEC's company list"):
        ingest_issuer(db_session, edgar_client, "NOSUCH", SINCE)
    assert count(db_session, InsiderIssuer) == 0


def _client(tmp_path, handler) -> EdgarClient:
    return EdgarClient(
        TEST_USER_AGENT,
        tmp_path / "cache",
        min_interval=0,
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )


def test_one_bad_download_does_not_lose_or_corrupt_the_rest(db_session, tmp_path):
    bad = "0000320187-26-000049"
    outage = {"on": True}

    def handler(request):
        if outage["on"] and bad.replace("-", "") in str(request.url):
            return httpx.Response(200, content=b"<html>Request Rate Threshold Exceeded</html>")
        return edgar_handler(request)

    client = _client(tmp_path, handler)
    report = ingest_issuer(db_session, client, "NKE", SINCE)
    assert list(report.failed) == [bad] and not report.complete
    assert "unexpected content" in report.failed[bad]
    assert report.stored == report.listed - 1
    assert db_session.get(InsiderFiling, bad) is None
    assert count(db_session, InsiderTransaction) > 0

    # The hole is recorded and every consumer of the score is told about it.
    assert db_session.get(InsiderIssuer, NKE).failed_filings == 1
    warned = score_issuer(db_session, NKE, at("2026-04-30T00:00:00"))
    assert warned["missing_filings"] == 1 and "history is incomplete" in warned["explanation"]
    audit = db_session.scalars(select(AuditLog).where(AuditLog.action == "insider.ingest")).one()
    assert (audit.actor, audit.detail["ticker"], audit.detail["stored"]) == ("ingest", "NKE", 9)
    assert list(audit.detail["failed"]) == [bad]

    outage["on"] = False  # the error page was not cached, so the next run recovers
    retry = ingest_issuer(db_session, client, "NKE", SINCE)
    assert (retry.stored, retry.failed) == (1, {})
    assert db_session.get(InsiderFiling, bad) is not None
    assert db_session.get(InsiderIssuer, NKE).failed_filings == 0
    healed = score_issuer(db_session, NKE, at("2026-04-30T00:00:00"))
    assert healed["missing_filings"] == 0 and "incomplete" not in healed["explanation"]


def test_document_that_contradicts_the_index_is_not_stored(db_session, tmp_path):
    original, amendment = "0000320187-26-000051", "0000320187-26-000053"

    def handler(request):
        if original.replace("-", "") in str(request.url):  # serve the 4/A where a 4 is listed
            request = httpx.Request(
                "GET",
                str(request.url).replace(
                    f"{original.replace('-', '')}/form4.xml",
                    f"{amendment.replace('-', '')}/form4a.xml",
                ),
            )
        return edgar_handler(request)

    report = ingest_issuer(db_session, _client(tmp_path, handler), "NKE", SINCE)
    assert "index says form 4, document says 4/A" in report.failed[original]
    assert db_session.get(InsiderFiling, original) is None


# --- point-in-time reads and deduplication ---


def _hill_rows(session, as_of):
    rows = effective_transactions(filings_as_of(session, NKE, as_of))
    return [t for t in rows if t.filing.owner_name == "Hill Elliott"]


def test_amendment_replaces_the_original_only_once_it_is_public(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    assert _hill_rows(db_session, at("2026-04-14T20:27:15")) == []  # one second before acceptance

    (before,) = _hill_rows(db_session, at("2026-04-22T20:57:23"))
    assert (before.accession, before.price) == ("0000320187-26-000051", HILL_ORIGINAL_PRICE)

    (after,) = _hill_rows(db_session, at("2026-04-22T20:57:24"))
    assert (after.accession, after.price) == ("0000320187-26-000053", HILL_AMENDED_PRICE)
    # Both filings stay in the database; only the effective view changes.
    assert db_session.get(InsiderFiling, "0000320187-26-000051") is not None


def test_restated_gift_counts_once(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    gifts = [
        t
        for t in effective_transactions(filings_as_of(db_session, NKE, at("2026-12-31")))
        if t.code == "G"
    ]
    assert [(t.accession, t.shares) for t in gifts] == [("0000320187-26-000129", D("22230"))]


def _filing(accession, owner_cik, accepted, form="4", original=None, rows=()):
    return InsiderFiling(
        accession=accession,
        form_type=form,
        owner_cik=owner_cik,
        accepted_at=accepted,
        filed_date=accepted.date(),
        period_of_report=date(2026, 1, 5),
        original_filed_date=original,
        transactions=[
            InsiderTransaction(
                row_index=i,
                table="non_derivative",
                is_holding=False,
                security_title="Common Stock",
                transaction_date=date(2026, 1, 5),
                code="P",
                acquired_disposed="A",
                ownership="I",
                nature_of_ownership="By Fund",
                shares=D(shares),
                price=D(price),
                shares_after=D(after),
            )
            for i, (shares, price, after) in enumerate(rows)
        ],
    )


def test_dedup_rules_on_constructed_filings():
    """Rule edges for which no single real filing set is in the fixtures (synthetic rows)."""
    t0 = at("2026-01-06T21:00:00")
    lots = [("1000", "10.00", "5000"), ("1000", "10.00", "6000")]
    fund = _filing("0000000001-26-000001", 1, t0, rows=lots)
    # The fund's general partner reports the very same trades in its own filing.
    partner = _filing("0000000002-26-000001", 2, t0 + timedelta(minutes=5), rows=lots)
    # A different insider who happens to buy the same amount ends with different holdings.
    other = _filing(
        "0000000003-26-000001", 3, t0 + timedelta(minutes=9), rows=[("1000", "10.00", "1000")]
    )
    effective = effective_transactions([other, partner, fund])
    assert [(t.filing.accession, t.shares_after) for t in effective] == [
        ("0000000001-26-000001", D("5000")),
        ("0000000001-26-000001", D("6000")),  # identical-looking lots inside one filing both count
        ("0000000003-26-000001", D("1000")),
    ]

    # An amendment for a different original filing date leaves this filing alone.
    unrelated = _filing(
        "0000000001-26-000009",
        1,
        t0 + timedelta(days=9),
        "4/A",
        date(2025, 12, 1),
        [("7", "9", "7")],
    )
    assert len(effective_transactions([fund, unrelated])) == 3
    related = _filing(
        "0000000001-26-000010",
        1,
        t0 + timedelta(days=9),
        "4/A",
        t0.date(),
        [("900", "10.00", "4900")],
    )
    assert [t.shares for t in effective_transactions([fund, related])] == [D("900")]


# --- scoring ---


def test_cluster_of_real_purchases_scores_as_hand_computed(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    result = score_issuer(db_session, NKE, at("2026-04-30T00:00:00"))

    assert result["discretionary_buys"] == {
        "transactions": 4,
        "insiders": 4,
        "value": f"{APRIL_VALUE:.2f}",
    }
    assert f"{APRIL_VALUE:.2f}" == "2734230.20"
    assert result["discretionary_sells"]["transactions"] == 0
    assert result["not_counted"]["planned_sale"] == 1  # a February 10b5-1 sale, not a signal

    increase = (
        sum(
            min(D(1), shares / (held - shares)) * shares * price
            for shares, price, held in APRIL_BUYS
        )
        / APRIL_VALUE
    )
    expected = {
        "purchase_value": 25 * (math.log10(float(APRIL_VALUE)) - 4) / 2.5,
        "seniority": 20.0,  # President & CEO
        "cluster": 25.0,  # four insiders inside 30 days
        "ownership_change": 15 * float(increase) / 0.5,
        "buyer_history": 15.0,  # none of the four has an earlier discretionary purchase on file
    }
    got = {c["name"]: c for c in result["components"]}
    for name, points in expected.items():
        assert got[name]["available"] and got[name]["points"] == pytest.approx(points, abs=0.05), (
            name
        )
    assert float(increase) == pytest.approx(0.1826, abs=0.0001)
    assert result["score"] == pytest.approx(sum(expected.values()), abs=0.1)

    for name in ("announcement_timing", "value_vs_market_cap"):
        assert got[name]["available"] is False  # unavailable, not zero
    assert result["coverage"] == pytest.approx(100 / 120, abs=0.01)
    assert {e["filing_url"] for e in result["evidence"]} == {
        f"https://www.sec.gov/Archives/edgar/data/320187/{a.replace('-', '')}/{a}-index.htm"
        for a in (
            "0000320187-26-000053",
            "0000320187-26-000049",
            "0000320187-26-000045",
            "0000320187-26-000043",
        )
    }


def test_score_uses_only_what_was_public_at_the_time(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    assert score_issuer(db_session, NKE, at("2026-04-08T20:27:59"))["score"] == 0.0

    one = score_issuer(db_session, NKE, at("2026-04-08T20:28:00"))  # first filing accepted
    assert one["discretionary_buys"] == {
        "transactions": 1,
        "insiders": 1,
        "value": f"{SWAN[0] * SWAN[1]:.2f}",
    }
    before_amendment = score_issuer(db_session, NKE, at("2026-04-20T00:00:00"))
    value = APRIL_VALUE - HILL[0] * (HILL_AMENDED_PRICE - HILL_ORIGINAL_PRICE)
    assert before_amendment["discretionary_buys"]["value"] == f"{value:.2f}"

    long_after = score_issuer(db_session, NKE, at("2026-12-01T00:00:00"))
    assert long_after["score"] == 0.0 and "No qualifying" in long_after["explanation"]


def test_holdings_increase_counts_every_lot_the_filing_reports(db_session, edgar_client):
    """Intel CEO bought 12,500 shares through one trust while reporting 631,307 in total."""
    ingest_issuer(db_session, edgar_client, "INTC", SINCE)
    result = score_issuer(db_session, INTC, at("2024-08-10T00:00:00"))
    held = sum(map(D, ["37975", "38416", "1480", "58558", "80047", "84419", "138486", "191926"]))
    assert held == D("631307")
    detail = next(c for c in result["components"] if c["name"] == "ownership_change")
    assert detail["points"] == pytest.approx(
        15 * float(D("12500") / (held - D("12500"))) / 0.5, abs=0.05
    )
    assert "2.0%" in detail["detail"]
    assert (
        result["discretionary_buys"]["value"]
        == f"{D('7500') * D('20.3137') + D('5000') * D('19.9186'):.2f}"
    )


def test_joint_filers_count_as_one_insider(db_session, edgar_client):
    """Texas Pacific Land, February 2023: a director and the fund he chairs file jointly
    (0001207097-23-000061), then the fund files alone (0001056823-23-000012). One buyer, not two."""
    ingest_issuer(db_session, edgar_client, "TPL", SINCE)
    result = score_issuer(db_session, 1811074, at("2023-02-17T00:00:00"))
    joint = D("1918.04") + (2 + 1 + 2 + 3) * D("1895.83") + 12 * D("1899.53")
    alone = 12 * D("1864.85")
    assert (joint, alone) == (D("39879.04"), D("22378.20"))
    assert result["discretionary_buys"] == {
        "transactions": 7,
        "insiders": 1,
        "value": f"{joint + alone:.2f}",
    }
    cluster = next(c for c in result["components"] if c["name"] == "cluster")
    assert cluster["points"] == 0.0 and cluster["detail"].startswith("1 distinct insider")
    assert {e["insider"] for e in result["evidence"]} == {
        "STAHL MURRAY",
        "HORIZON KINETICS ASSET MANAGEMENT LLC",
    }


def test_short_history_makes_buyer_history_unavailable(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "NKE", date(2026, 1, 1))
    result = score_issuer(db_session, NKE, at("2026-04-30T00:00:00"))
    history = next(c for c in result["components"] if c["name"] == "buyer_history")
    assert history["available"] is False and "2026-01-01" in history["detail"]
    assert result["coverage"] == pytest.approx(85 / 120, abs=0.01)


def test_sales_grants_and_exercises_alone_never_produce_a_score(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "AAPL", SINCE)
    for moment in ("2023-10-20T00:00:00", "2024-04-10T00:00:00", "2026-06-05T00:00:00"):
        result = score_issuer(db_session, AAPL, at(moment))
        assert result["score"] == 0.0 and result["discretionary_buys"]["transactions"] == 0
    assert result["discretionary_sells"] == {
        "transactions": 1,
        "insiders": 1,
        "value": f"{D('50000') * D('311.02'):.2f}",
    }
    planned = score_issuer(db_session, AAPL, at("2023-10-20T00:00:00"))
    assert planned["not_counted"] == {"planned_sale": 3}
    assert planned["discretionary_sells"]["transactions"] == 0


def test_never_ingested_issuer_has_no_score(db_session):
    assert score_issuer(db_session, NKE, datetime.now(UTC)) is None


def test_naive_timestamps_are_refused(db_session, edgar_client):
    ingest_issuer(db_session, edgar_client, "NKE", SINCE)
    with pytest.raises(Exception, match="timezone-aware"):
        filings_as_of(db_session, NKE, datetime(2026, 4, 30))  # noqa: DTZ001


# --- API ---

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def api(tmp_path, monkeypatch, edgar_client):
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.sqlite")
    app = create_app(load_settings())
    with TestClient(app) as client:
        with app.state.sessions() as session:
            ingest_issuer(session, edgar_client, "NKE", SINCE)
        yield client


def test_api_score(api):
    response = api.get(
        "/api/v1/insider/nke/score", params={"as_of": "2026-04-30T00:00:00Z"}, headers=AUTH
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "NKE" and body["discretionary_buys"]["value"] == "2734230.20"
    assert "not a probability" in body["disclaimer"]


def test_api_transactions(api):
    response = api.get(
        "/api/v1/insider/NKE/transactions",
        params={"as_of": "2026-04-30T00:00:00Z", "signals_only": "true"},
        headers=AUTH,
    )
    body = response.json()
    assert response.status_code == 200 and body["total"] == 4
    newest = body["transactions"][0]
    assert newest == newest | {
        "insider": "Hill Elliott",
        "position": "PRESIDENT & CEO",
        "form": "4/A",
        "category": "open_market_purchase",
        "signal": "discretionary_buy",
        "shares": "23660.235000",
        "price": "42.270000",
        "transaction_date": "2026-04-13",
        "filed_date": "2026-04-22",
        "accepted_at": "2026-04-22T20:57:24+00:00",
        "accession": "0000320187-26-000053",
    }
    assert newest["filing_url"].startswith("https://www.sec.gov/Archives/edgar/data/320187/")

    everything = api.get("/api/v1/insider/NKE/transactions", headers=AUTH).json()
    assert everything["total"] > 4
    assert {"planned_sale", "option_exercise", "gift"} <= {
        t["category"] for t in everything["transactions"]
    }
    assert (
        api.get("/api/v1/insider/NKE/transactions", params={"limit": 2}, headers=AUTH)
        .json()["transactions"]
        .__len__()
        == 2
    )


def test_api_says_unavailable_rather_than_zero(api):
    response = api.get("/api/v1/insider/TSLA/score", headers=AUTH)
    assert response.status_code == 404
    assert "unavailable, not that there was no activity" in response.json()["detail"]


@pytest.mark.parametrize(
    ("path", "params", "status"),
    [
        ("/api/v1/insider/NKE/score", {"as_of": "2026-04-30T00:00:00"}, 422),  # no UTC offset
        ("/api/v1/insider/NKE/score", {"as_of": "yesterday"}, 422),
        ("/api/v1/insider/NK$E/score", {}, 422),
        ("/api/v1/insider/NKE/transactions", {"limit": 0}, 422),
        ("/api/v1/insider/NKE/transactions", {"limit": 100000}, 422),
    ],
)
def test_api_validates_input(api, path, params, status):
    assert api.get(path, params=params, headers=AUTH).status_code == status


def test_api_requires_token(api):
    assert api.get("/api/v1/insider/NKE/score").status_code == 401
