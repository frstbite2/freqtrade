"""EDGAR client transport behaviour: identification, throttling, retries, caching, URL safety.

The responses here are synthetic on purpose: these tests exercise failure handling that cannot
be provoked from the real service. Data accuracy is tested on real filings elsewhere.
"""

import time
from datetime import UTC, date, datetime

import httpx
import pytest

from backend.services.edgar import (
    EdgarClient,
    EdgarError,
    EdgarNotConfigured,
    EdgarNotFound,
    FilingRef,
    filing_index_url,
)
from backend.tests.conftest import SINCE, TEST_USER_AGENT


URL = "https://www.sec.gov/Archives/edgar/data/1/x.xml"


def make_client(tmp_path, handler, **kwargs):
    kwargs.setdefault("min_interval", 0)
    return EdgarClient(
        TEST_USER_AGENT, tmp_path / "cache", transport=httpx.MockTransport(handler), **kwargs
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)
    return slept


@pytest.mark.parametrize("user_agent", [None, "", "no contact details"])
def test_user_agent_with_contact_is_required(tmp_path, user_agent):
    with pytest.raises(EdgarNotConfigured):
        EdgarClient(user_agent, tmp_path)


def test_sends_declared_user_agent(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, content=b"ok")

    make_client(tmp_path, handler).get(URL, None)
    assert seen == [TEST_USER_AGENT]


def test_refuses_non_sec_hosts(tmp_path):
    client = make_client(tmp_path, lambda r: httpx.Response(200, content=b"x"))
    for url in (
        "https://evil.example/x",
        "https://www.sec.gov.evil.example/x",
        "http://www.sec.gov/x",
    ):
        with pytest.raises(EdgarError, match="non-SEC"):
            client.get(url, None)
    assert client.requests_made == 0


def test_immutable_documents_are_fetched_once(tmp_path):
    client = make_client(tmp_path, lambda r: httpx.Response(200, content=b"filing"))
    assert client.get(URL, None) == client.get(URL, None) == b"filing"
    assert client.requests_made == 1
    # A second client (a later run) reuses the on-disk cache.
    assert make_client(tmp_path, lambda r: httpx.Response(500)).get(URL, None) == b"filing"


def test_index_cache_expires(tmp_path):
    client = make_client(tmp_path, lambda r: httpx.Response(200, content=b"index"))
    client.get(URL, max_age=3600)
    client.get(URL, max_age=3600)
    assert client.requests_made == 1
    client.get(URL, max_age=0)
    assert client.requests_made == 2


def test_failed_requests_are_never_cached(tmp_path):
    client = make_client(tmp_path, lambda r: httpx.Response(404))
    with pytest.raises(EdgarNotFound):
        client.get(URL, None)
    assert not list((tmp_path / "cache").rglob("*"))


def test_retries_transient_errors_then_succeeds(tmp_path, _no_sleep):
    replies = iter([httpx.Response(503), httpx.Response(429, headers={"Retry-After": "7"})])

    def handler(request):
        return next(replies, httpx.Response(200, content=b"ok"))

    client = make_client(tmp_path, handler)
    assert client.get(URL, None) == b"ok"
    assert client.requests_made == 3
    assert _no_sleep == [1.0, 7.0]  # exponential backoff, then the server's Retry-After


def test_retries_network_errors(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(200, content=b"ok")

    assert make_client(tmp_path, handler).get(URL, None) == b"ok"


def test_gives_up_after_max_attempts(tmp_path):
    client = make_client(tmp_path, lambda r: httpx.Response(503), max_attempts=3)
    with pytest.raises(EdgarError, match="failed after 3 attempts"):
        client.get(URL, None)
    assert client.requests_made == 3


def test_403_is_not_retried(tmp_path):
    client = make_client(tmp_path, lambda r: httpx.Response(403))
    with pytest.raises(EdgarError, match="403"):
        client.get(URL, None)
    assert client.requests_made == 1


def test_empty_body_is_an_error(tmp_path):
    with pytest.raises(EdgarError, match="empty"):
        make_client(tmp_path, lambda r: httpx.Response(200, content=b"")).get(URL, None)


def test_requests_are_spaced_to_respect_the_rate_limit(tmp_path, monkeypatch, _no_sleep):
    clock = iter([100.0, 100.0, 100.01, 100.2])
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    client = make_client(tmp_path, lambda r: httpx.Response(200, content=b"x"), min_interval=0.125)
    client.get(URL, None)
    client.get(URL + "2", None)
    assert _no_sleep == [pytest.approx(0.115)]  # 0.125s minus the 0.01s already elapsed


def test_invalid_json_is_an_error(tmp_path):
    client = make_client(tmp_path, lambda r: httpx.Response(200, content=b"<html>busy</html>"))
    with pytest.raises(EdgarError, match="invalid JSON"):
        client.ticker_to_cik("AAPL")


def _submissions(**overrides):
    recent = {
        "accessionNumber": ["0000000001-24-000001", "0000000001-24-000002", "0000000001-22-000003"],
        "form": ["4", "10-K", "4"],
        "filingDate": ["2024-03-01", "2024-02-01", "2022-06-01"],
        "acceptanceDateTime": [
            "2024-03-01T21:05:09.000Z",
            "2024-02-01T12:00:00.000Z",
            "2022-06-01T12:00:00.000Z",
        ],
        "primaryDocument": ["xslF345X05/form4.xml", "a10k.htm", "xslF345X03/form4.xml"],
    }
    recent.update(overrides)
    return {"name": "Example Co", "filings": {"recent": recent, "files": []}}


def test_index_keeps_only_ownership_forms_since_the_cutoff(tmp_path):
    client = make_client(tmp_path, lambda r: httpx.Response(200, json=_submissions()))
    name, refs = client.ownership_filings(1, SINCE)
    assert name == "Example Co"
    assert refs == [
        FilingRef(
            accession="0000000001-24-000001",
            form="4",
            filed_date=date(2024, 3, 1),
            accepted_at=datetime(2024, 3, 1, 21, 5, 9, tzinfo=UTC),
            primary_document="xslF345X05/form4.xml",
        )
    ]


def test_older_index_pages_are_loaded_only_when_needed(tmp_path):
    requested = []
    older = _submissions()["filings"]["recent"]

    def handler(request):
        requested.append(str(request.url).rsplit("/", 1)[-1])
        if "submissions-001" in str(request.url):
            return httpx.Response(200, json=older)
        main = _submissions()
        main["filings"]["files"] = [
            {"name": "CIK0000000001-submissions-001.json", "filingTo": "2021-12-31"}
        ]
        return httpx.Response(200, json=main)

    client = make_client(tmp_path, handler)
    client.ownership_filings(1, SINCE)
    assert requested == ["CIK0000000001.json"]
    _, refs = client.ownership_filings(1, date(2021, 1, 1))
    assert "CIK0000000001-submissions-001.json" in requested
    assert "0000000001-22-000003" in [r.accession for r in refs]


@pytest.mark.parametrize(
    "overrides",
    [
        {"acceptanceDateTime": ["2024-03-01T21:05:09", "x", "y"]},  # no timezone
        {"filingDate": ["not a date", "2024-02-01", "2022-06-01"]},
        {"form": ["4"]},  # columns of different length
    ],
)
def test_malformed_index_is_rejected(tmp_path, overrides):
    client = make_client(tmp_path, lambda r: httpx.Response(200, json=_submissions(**overrides)))
    with pytest.raises(EdgarError, match="unexpected submissions format"):
        client.ownership_filings(1, SINCE)


def test_filing_paths_cannot_escape_the_filing_directory(tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=b"<ownershipDocument/>")

    client = make_client(tmp_path, handler)
    with pytest.raises(EdgarError, match="unsafe"):
        client.ownership_xml(1, FilingRef("../0000000001", "4", SINCE, datetime.now(UTC), "a.xml"))
    with pytest.raises(EdgarError, match="unsafe"):
        client.ownership_xml(
            1, FilingRef("0000000001-24-000001", "4", SINCE, datetime.now(UTC), "a.xml?x=1")
        )
    assert seen == []
    # Only the last path component of the listed document is ever used.
    ref = FilingRef("0000000001-24-000001", "4", SINCE, datetime.now(UTC), "../../etc/passwd")
    client.ownership_xml(1, ref)
    assert seen == ["https://www.sec.gov/Archives/edgar/data/1/000000000124000001/passwd"]


def test_error_page_served_as_success_is_rejected_and_not_cached(tmp_path):
    client = make_client(tmp_path, lambda r: httpx.Response(200, content=b"<html>busy</html>"))
    ref = FilingRef("0000000001-24-000001", "4", SINCE, datetime.now(UTC), "form4.xml")
    for _ in range(2):
        with pytest.raises(EdgarError, match="unexpected content"):
            client.ownership_xml(1, ref)
    assert client.requests_made == 2


def test_raw_xml_is_fetched_beside_the_rendered_path(tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=b"<ownershipDocument/>")

    ref = FilingRef("0000050863-26-000195", "4", SINCE, datetime.now(UTC), "xslF345X06/form4.xml")
    make_client(tmp_path, handler).ownership_xml(50863, ref)
    assert seen == ["https://www.sec.gov/Archives/edgar/data/50863/000005086326000195/form4.xml"]
    assert filing_index_url(50863, ref.accession) == (
        "https://www.sec.gov/Archives/edgar/data/50863/000005086326000195/"
        "0000050863-26-000195-index.htm"
    )
