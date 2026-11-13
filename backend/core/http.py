"""Shared outbound-HTTP behaviour for data providers: request spacing and retries."""

import logging
import threading
import time

import httpx


logger = logging.getLogger(__name__)

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class RetriesExhausted(Exception):
    pass


class Throttle:
    """Keeps at least `min_interval` seconds between requests, across threads."""

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0
        self.requests_made = 0

    def wait(self) -> None:
        with self._lock:
            pause = self._min_interval - (time.monotonic() - self._last)
            if pause > 0:
                time.sleep(pause)
            self._last = time.monotonic()
            self.requests_made += 1


def get_with_retry(
    http: httpx.Client,
    url: str,
    throttle: Throttle,
    params: dict | None = None,
    max_attempts: int = 4,
) -> httpx.Response:
    """GET with retries for network errors and 429/5xx responses.

    Waits 1s, 2s, 4s... between attempts, or longer if the server sends Retry-After. Any other
    status is returned at once for the caller to interpret; credentials are never logged.
    """
    error = "no attempt made"
    for attempt in range(max_attempts):
        throttle.wait()
        delay = 2.0**attempt
        try:
            response = http.get(url, params=params)
        except httpx.TransportError as exc:
            error = f"{type(exc).__name__}: {exc}"
        else:
            if response.status_code not in RETRY_STATUS:
                return response
            error = f"status {response.status_code}"
            retry_after = response.headers.get("Retry-After", "")
            if retry_after.isdigit():
                delay = max(delay, float(retry_after))
        if attempt + 1 < max_attempts:
            logger.warning("%s for %s; retrying in %.0fs", error, url, delay)
            time.sleep(delay)
    raise RetriesExhausted(f"{url} failed after {max_attempts} attempts: {error}")
