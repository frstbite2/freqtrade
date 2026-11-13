"""SEC EDGAR HTTP client: identified, throttled, retried and cached.

SEC fair-access rules: declare a User-Agent with contact details and stay under 10 requests per
second. Accepted filing documents never change, so they are cached forever; index files are
cached with a TTL.
"""

import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx


logger = logging.getLogger(__name__)

ALLOWED_HOSTS = ("https://www.sec.gov/", "https://data.sec.gov/")
OWNERSHIP_FORMS = frozenset({"3", "4", "5", "3/A", "4/A", "5/A"})
_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_DOCUMENT = re.compile(r"^[A-Za-z0-9_.\-]+$")
_RETRY_STATUS = {429, 500, 502, 503, 504}


class EdgarError(Exception):
    """EDGAR request failed (after retries) or returned something unusable."""


class EdgarNotConfigured(EdgarError):
    """No SEC_USER_AGENT: the source is unavailable, which is not the same as 'no filings'."""


class EdgarNotFound(EdgarError):
    pass


@dataclass(frozen=True)
class FilingRef:
    accession: str
    form: str
    filed_date: date
    accepted_at: datetime  # UTC; the moment the filing became public
    primary_document: str


def filing_index_url(cik: int, accession: str) -> str:
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
        f"/{accession}-index.htm"
    )


class EdgarClient:
    def __init__(
        self,
        user_agent: str | None,
        cache_dir: str | Path,
        min_interval: float = 0.125,  # 8 requests/second, under SEC's limit of 10
        max_attempts: int = 4,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not user_agent or "@" not in user_agent:
            raise EdgarNotConfigured(
                "SEC_USER_AGENT must be set to a name and contact email, as SEC requires"
            )
        self._http = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=30,
            transport=transport,
        )
        self._cache_dir = Path(cache_dir)
        self._min_interval = min_interval
        self._max_attempts = max_attempts
        self._lock = threading.Lock()
        self._last_request = 0.0
        self.requests_made = 0

    def close(self) -> None:
        self._http.close()

    # --- transport ---

    def get(self, url: str, max_age: float | None, must_contain: bytes | None = None) -> bytes:
        """GET with cache. max_age=None caches forever (immutable filing documents).

        A body without `must_contain` (an error page served with status 200) is rejected before
        it can be cached, so it cannot poison the permanent cache.
        """
        if not url.startswith(ALLOWED_HOSTS):
            raise EdgarError(f"refusing non-SEC URL: {url}")
        digest = hashlib.sha256(url.encode()).hexdigest()
        path = self._cache_dir / digest[:2] / digest
        if path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age):
            return path.read_bytes()
        body = self._fetch(url)
        if must_contain is not None and must_contain not in body:
            raise EdgarError(f"unexpected content from {url}")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(body)
        tmp.replace(path)  # atomic: a crash never leaves a truncated cache entry
        return body

    def _fetch(self, url: str) -> bytes:
        error = "no attempt made"
        for attempt in range(self._max_attempts):
            with self._lock:
                wait = self._min_interval - (time.monotonic() - self._last_request)
                if wait > 0:
                    time.sleep(wait)
                self._last_request = time.monotonic()
                self.requests_made += 1
            delay = 2.0**attempt
            try:
                response = self._http.get(url)
            except httpx.TransportError as exc:
                error = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code == 200:
                    if not response.content:
                        raise EdgarError(f"empty response from {url}")
                    return response.content
                if response.status_code == 404:
                    raise EdgarNotFound(url)
                if response.status_code == 403:
                    # SEC answers 403 to a missing/blocked User-Agent and to rate-limit bans.
                    # Retrying only extends a ban, so stop immediately.
                    raise EdgarError(f"SEC refused the request (403) for {url}")
                if response.status_code not in _RETRY_STATUS:
                    raise EdgarError(f"unexpected status {response.status_code} for {url}")
                error = f"status {response.status_code}"
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    delay = max(delay, float(retry_after))
            if attempt + 1 < self._max_attempts:
                logger.warning("EDGAR %s for %s; retrying in %.0fs", error, url, delay)
                time.sleep(delay)
        raise EdgarError(f"{url} failed after {self._max_attempts} attempts: {error}")

    def _json(self, url: str, max_age: float) -> dict:
        try:
            data = json.loads(self.get(url, max_age))
        except ValueError as exc:
            raise EdgarError(f"invalid JSON from {url}") from exc
        if not isinstance(data, dict):
            raise EdgarError(f"unexpected JSON shape from {url}")
        return data

    # --- EDGAR resources ---

    def ticker_to_cik(self, ticker: str) -> int | None:
        data = self._json("https://www.sec.gov/files/company_tickers.json", max_age=86400)
        wanted = ticker.strip().upper()
        for row in data.values():
            if isinstance(row, dict) and str(row.get("ticker", "")).upper() == wanted:
                return int(row["cik_str"])
        return None

    def ownership_filings(self, cik: int, since: date) -> tuple[str, list[FilingRef]]:
        """Entity name and all Form 3/4/5 filings (and amendments) filed on or after `since`."""
        base = "https://data.sec.gov/submissions/"
        main = self._json(f"{base}CIK{cik:010d}.json", max_age=900)
        try:
            pages = [main["filings"]["recent"]]
            for older in main["filings"].get("files", []):
                if date.fromisoformat(older["filingTo"]) >= since:
                    name = older["name"]
                    if not _DOCUMENT.match(name):
                        raise EdgarError(f"unexpected submissions page name: {name!r}")
                    pages.append(self._json(base + name, max_age=86400))
            refs = [ref for page in pages for ref in _refs_from_page(page, since)]
            return str(main["name"]), refs
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise EdgarError(f"unexpected submissions format for CIK {cik}: {exc!r}") from exc

    def ownership_xml(self, cik: int, ref: FilingRef) -> bytes:
        # The index lists the XSL-rendered path (xslF345X06/form4.xml); the raw XML sits beside it.
        document = ref.primary_document.rsplit("/", 1)[-1]
        if not _ACCESSION.match(ref.accession) or not _DOCUMENT.match(document):
            raise EdgarError(f"unsafe filing path: {ref.accession} {ref.primary_document!r}")
        return self.get(
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{ref.accession.replace('-', '')}"
            f"/{document}",
            max_age=None,
            must_contain=b"<ownershipDocument",
        )


def _refs_from_page(page: dict, since: date) -> list[FilingRef]:
    columns = ("accessionNumber", "form", "filingDate", "acceptanceDateTime", "primaryDocument")
    if len({len(page[c]) for c in columns}) != 1:
        # A truncated column would silently drop filings.
        raise ValueError("index columns have different lengths")
    refs = []
    for i, form in enumerate(page["form"]):
        if form not in OWNERSHIP_FORMS:
            continue
        filed = date.fromisoformat(page["filingDate"][i])
        if filed < since:
            continue
        accepted = datetime.fromisoformat(page["acceptanceDateTime"][i])
        if accepted.tzinfo is None:
            raise ValueError(f"acceptanceDateTime without timezone: {accepted}")
        refs.append(
            FilingRef(
                accession=page["accessionNumber"][i],
                form=form,
                filed_date=filed,
                accepted_at=accepted.astimezone(UTC),
                primary_document=page["primaryDocument"][i],
            )
        )
    return refs
