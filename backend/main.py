"""API entry point: `uvicorn --factory backend.main:create_app`."""

import logging
import os
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI
from sqlalchemy.orm import sessionmaker

from backend import __version__
from backend.api.insider import router as insider_router
from backend.api.institutional import router as institutional_router
from backend.api.jobs import health_router
from backend.api.jobs import router as jobs_router
from backend.api.market import router as market_router
from backend.api.ownership import router as ownership_router
from backend.api.routes import public, rate_limit, v1
from backend.api.technical import router as technical_router
from backend.core.config import Settings, get_settings
from backend.core.logging import setup_logging
from backend.database.session import init_db, make_engine
from backend.models import record_audit
from backend.services.market_data.alpaca import AlpacaMarketData
from backend.services.market_data.service import MarketDataService


logger = logging.getLogger(__name__)


# Values copied from examples or typed as stand-ins; never accepted outside development.
PLACEHOLDER_TOKENS = frozenset(
    {"change-me", "changeme", "change_me", "dev", "test", "token", "secret", "password", "admin"}
)
MIN_PRODUCTION_TOKEN_LENGTH = 32


def check_api_token(environment: str) -> None:
    """Refuse to start with a missing, placeholder or (in production) weak API token.

    Development accepts any token, so local use stays simple. Messages never include the token.
    """
    if environment == "development":
        return
    token = os.environ.get("API_AUTH_TOKEN") or ""
    if not token:
        raise RuntimeError(f"API_AUTH_TOKEN must be set when APP_ENV is {environment}")
    if token.strip().lower() in PLACEHOLDER_TOKENS:
        raise RuntimeError(
            "API_AUTH_TOKEN is a placeholder value; generate one with "
            'python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    if environment == "production":
        if len(token) < MIN_PRODUCTION_TOKEN_LENGTH:
            raise RuntimeError(
                f"API_AUTH_TOKEN must be at least {MIN_PRODUCTION_TOKEN_LENGTH} characters "
                "in production"
            )
        if len(set(token)) < 8:
            raise RuntimeError("API_AUTH_TOKEN is too simple (too few distinct characters)")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    check_api_token(settings.app.environment)
    development = settings.app.environment == "development"
    engine = make_engine(settings.app.database_url)
    sessions = sessionmaker(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings.app.log_level, settings.app.log_json)
        init_db(engine)
        with sessions() as s:
            record_audit(s, "system", "startup", trading_mode=settings.app.trading_mode)
        logger.info(
            "platform started in %s mode (%s)", settings.app.trading_mode, settings.app.environment
        )
        yield
        with sessions() as s:
            record_audit(s, "system", "shutdown")
        engine.dispose()
        logger.info("platform stopped")

    app = FastAPI(
        title="AI Trading Platform",
        version=__version__,
        lifespan=lifespan,
        dependencies=[Depends(rate_limit)],
        # The interactive docs and schema describe every endpoint: development only.
        docs_url="/docs" if development else None,
        redoc_url="/redoc" if development else None,
        openapi_url="/openapi.json" if development else None,
    )
    app.state.request_times = defaultdict(deque)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = sessions
    app.state.clock = lambda: datetime.now(UTC)  # tests set a fixed clock
    # Without keys there is no provider: stored bars stay readable, anything else is "unavailable".
    alpaca_keys = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    provider = (
        AlpacaMarketData(*alpaca_keys, feed=settings.app.alpaca_feed) if all(alpaca_keys) else None
    )
    app.state.market_data = MarketDataService(provider, source=f"alpaca:{settings.app.alpaca_feed}")
    app.include_router(public)
    app.include_router(v1)
    app.include_router(insider_router)
    app.include_router(institutional_router)
    app.include_router(jobs_router)
    app.include_router(health_router)
    app.include_router(market_router)
    app.include_router(ownership_router)
    app.include_router(technical_router)
    return app
