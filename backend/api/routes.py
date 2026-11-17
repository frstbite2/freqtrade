import math
import os
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend import __version__
from backend.database.session import db_ok


_bearer = HTTPBearer(auto_error=False)


def require_token(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    expected = os.environ.get("API_AUTH_TOKEN")
    if not expected:
        # Fail closed: no token configured means no access, never open access.
        raise HTTPException(503, "API_AUTH_TOKEN is not configured")
    if creds is None or not secrets.compare_digest(creds.credentials.encode(), expected.encode()):
        raise HTTPException(
            401, "invalid or missing bearer token", headers={"WWW-Authenticate": "Bearer"}
        )


_rate_lock = threading.Lock()


def rate_limit(request: Request) -> None:
    """Allow each client address `api_rate_limit_per_minute` requests in any 60 seconds.

    Runs before authentication, so guessing the token is limited too.
    shortcut: counts live in this process, one deque per client address; move them to a shared
    store (or a reverse proxy) before running several workers or exposing the API publicly.
    """
    limit = request.app.state.settings.app.api_rate_limit_per_minute
    now = time.monotonic()
    with _rate_lock:
        hits = request.app.state.request_times[request.client.host if request.client else ""]
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= limit:
            wait = math.ceil(60 - (now - hits[0]))
            raise HTTPException(429, "too many requests", headers={"Retry-After": str(wait)})
        hits.append(now)


public = APIRouter()
v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])


@public.get("/health")
def health(request: Request, response: Response) -> dict:
    ok = db_ok(request.app.state.engine)
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "degraded", "database": "ok" if ok else "unreachable"}


@v1.get("/status")
def status(request: Request) -> dict:
    s = request.app.state.settings
    return {
        "version": __version__,
        "environment": s.app.environment,
        "trading_mode": s.app.trading_mode,
        "providers_configured": s.configured_providers(),
    }


@v1.get("/config")
def config(request: Request) -> dict:
    s = request.app.state.settings
    return {
        "risk": s.risk.model_dump(),
        "scoring_weights": s.strategies.scoring_weights.model_dump(),
    }
