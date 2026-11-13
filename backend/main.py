"""API entry point: `uvicorn --factory backend.main:create_app`."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from backend import __version__
from backend.api.insider import router as insider_router
from backend.api.market import router as market_router
from backend.api.routes import public, v1
from backend.core.config import Settings, get_settings
from backend.core.logging import setup_logging
from backend.database.session import init_db, make_engine
from backend.models import record_audit
from backend.services.market_data.alpaca import AlpacaMarketData
from backend.services.market_data.service import MarketDataService


logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
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

    app = FastAPI(title="AI Trading Platform", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = sessions
    # Without keys there is no provider: stored bars stay readable, anything else is "unavailable".
    alpaca_keys = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    provider = (
        AlpacaMarketData(*alpaca_keys, feed=settings.app.alpaca_feed) if all(alpaca_keys) else None
    )
    app.state.market_data = MarketDataService(provider, source=f"alpaca:{settings.app.alpaca_feed}")
    app.include_router(public)
    app.include_router(v1)
    app.include_router(insider_router)
    app.include_router(market_router)
    return app
