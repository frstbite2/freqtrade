"""Live checks against SEC EDGAR. Opt-in, because they need network access and a contact string:

    EDGAR_LIVE_TESTS=1 SEC_USER_AGENT="Your Name you@example.com" pytest -m live

They assert facts about accepted filings, which never change.
"""

import os
from datetime import UTC, date, datetime

import pytest

from backend.services.edgar import EdgarClient, filing_index_url
from backend.tests.conftest import fixture_entry, fixture_xml


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (os.environ.get("EDGAR_LIVE_TESTS") and os.environ.get("SEC_USER_AGENT")),
        reason="set EDGAR_LIVE_TESTS=1 and SEC_USER_AGENT to run against SEC EDGAR",
    ),
]

NKE = 320187
COOK_PURCHASE = "0000320187-26-000049"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    client = EdgarClient(os.environ["SEC_USER_AGENT"], tmp_path_factory.mktemp("edgar_live"))
    yield client
    client.close()


def test_ticker_lookup(client):
    assert client.ticker_to_cik("NKE") == NKE
    assert client.ticker_to_cik("aapl") == 320193
    assert client.ticker_to_cik("NOT-A-TICKER") is None


def test_index_lists_the_known_filing_with_its_utc_acceptance_time(client):
    name, refs = client.ownership_filings(NKE, date(2026, 4, 1))
    assert name == "NIKE, Inc."
    assert {r.form for r in refs} <= {"3", "4", "5", "3/A", "4/A", "5/A"}
    ref = next(r for r in refs if r.accession == COOK_PURCHASE)
    assert (ref.form, ref.filed_date) == ("4", date(2026, 4, 14))
    # EDGAR's own header for this filing says 16:25:45 Eastern (daylight time) = 20:25:45 UTC.
    assert ref.accepted_at == datetime(2026, 4, 14, 20, 25, 45, tzinfo=UTC)


def test_fixtures_are_byte_identical_to_what_edgar_serves(client):
    _, refs = client.ownership_filings(NKE, date(2026, 4, 1))
    ref = next(r for r in refs if r.accession == COOK_PURCHASE)
    assert ref.primary_document == fixture_entry(COOK_PURCHASE)["primaryDocument"]
    assert client.ownership_xml(NKE, ref) == fixture_xml(COOK_PURCHASE)


def test_filing_link_resolves(client):
    page = client.get(filing_index_url(NKE, COOK_PURCHASE), max_age=None)
    assert COOK_PURCHASE.encode() in page
