"""Shared fixtures.

backend/tests/fixtures/edgar holds real SEC filings, byte-for-byte as served by EDGAR, plus
manifest.json with each filing's real index metadata (see the README there). `edgar_transport`
serves them the way EDGAR does, so pipeline tests run offline on real documents.
"""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from backend.database.session import init_db, make_engine
from backend.services.edgar import EdgarClient


FIXTURES = Path(__file__).parent / "fixtures" / "edgar"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
FIXTURES_13F = Path(__file__).parent / "fixtures" / "edgar13f"
MANIFEST_13F = json.loads((FIXTURES_13F / "manifest.json").read_text())
TEST_USER_AGENT = "platform-tests tests@example.com"
SINCE = date(2023, 1, 1)


def fixture_xml(accession: str) -> bytes:
    return (FIXTURES / f"{accession}.xml").read_bytes()


def fixture_entry(accession: str) -> dict:
    return next(m for m in MANIFEST if m["accession"] == accession)


def edgar_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url == "https://www.sec.gov/files/company_tickers.json":
        issuers = {(m["cik"], m["ticker"], m["name"]) for m in MANIFEST}
        return httpx.Response(
            200,
            json={
                str(i): {"cik_str": cik, "ticker": ticker, "title": name}
                for i, (cik, ticker, name) in enumerate(sorted(issuers))
            },
        )
    if url.startswith("https://data.sec.gov/submissions/CIK"):
        cik = int(url.removeprefix("https://data.sec.gov/submissions/CIK").removesuffix(".json"))
        rows = [m for m in MANIFEST + MANIFEST_13F if m["cik"] == cik]
        if not rows:
            return httpx.Response(404)
        columns = ("accessionNumber", "form", "filingDate", "acceptanceDateTime", "primaryDocument")
        recent = {
            c: [m["accession" if c == "accessionNumber" else c] for m in rows] for c in columns
        }
        return httpx.Response(
            200, json={"name": rows[0]["name"], "filings": {"recent": recent, "files": []}}
        )
    for m in MANIFEST_13F:
        if url.endswith(f"/{m['accession'].replace('-', '')}/{m['accession']}.txt"):
            return httpx.Response(
                200, content=(FIXTURES_13F / f"{m['accession']}.txt").read_bytes()
            )
    for m in MANIFEST:
        document = m["primaryDocument"].rsplit("/", 1)[-1]
        if url.endswith(f"/{m['accession'].replace('-', '')}/{document}"):
            return httpx.Response(200, content=fixture_xml(m["accession"]))
    return httpx.Response(404)


@pytest.fixture
def edgar_client(tmp_path):
    client = EdgarClient(
        TEST_USER_AGENT,
        tmp_path / "edgar_cache",
        min_interval=0,
        transport=httpx.MockTransport(edgar_handler),
    )
    yield client
    client.close()


@pytest.fixture
def db_session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/insider.sqlite")
    init_db(engine)
    with sessionmaker(engine)() as session:
        yield session
    engine.dispose()
