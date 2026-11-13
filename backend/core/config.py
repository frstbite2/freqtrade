"""Configuration: non-secret settings from config/*.yaml, secrets only from the environment."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


REPO_ROOT = Path(__file__).resolve().parents[2]

# Every secret the platform may use. Values are read from the environment only and never
# returned by the API or written to logs; only "is it configured?" is exposed.
SECRET_ENV_VARS: dict[str, tuple[str, ...]] = {
    "alpaca": ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
    "polygon": ("POLYGON_API_KEY",),
    "finnhub": ("FINNHUB_API_KEY",),
    "alpha_vantage": ("ALPHA_VANTAGE_API_KEY",),
    "fmp": ("FMP_API_KEY",),
    "tradier": ("TRADIER_API_TOKEN",),
    "coinbase": ("COINBASE_API_KEY", "COINBASE_API_SECRET"),
    "api_auth": ("API_AUTH_TOKEN",),
}


class _Strict(BaseModel):
    # Unknown keys are errors, so a typo (or a secret pasted into YAML) fails loudly.
    model_config = ConfigDict(extra="forbid", frozen=True)


class RiskConfig(_Strict):
    risk_per_trade_pct: float = Field(0.5, gt=0, le=5)
    max_daily_loss_pct: float = Field(2.0, gt=0, le=20)
    max_weekly_loss_pct: float = Field(5.0, gt=0, le=40)
    max_drawdown_pct: float = Field(15.0, gt=0, le=60)
    max_open_positions: int = Field(5, ge=1, le=100)
    max_portfolio_exposure_pct: float = Field(50.0, gt=0, le=100)
    max_asset_exposure_pct: float = Field(10.0, gt=0, le=100)
    consecutive_losses_before_cooldown: int = Field(3, ge=1)
    cooldown_minutes: int = Field(60, ge=0)

    @model_validator(mode="after")
    def _ordered_limits(self) -> "RiskConfig":
        if not self.max_daily_loss_pct <= self.max_weekly_loss_pct <= self.max_drawdown_pct:
            raise ValueError(
                "require max_daily_loss_pct <= max_weekly_loss_pct <= max_drawdown_pct"
            )
        if self.max_asset_exposure_pct > self.max_portfolio_exposure_pct:
            raise ValueError("max_asset_exposure_pct cannot exceed max_portfolio_exposure_pct")
        return self


class ScoringWeights(_Strict):
    """Opportunity-score weights. Research rankings, not probabilities; validate via backtests."""

    technical: float = Field(0.20, ge=0)
    pattern: float = Field(0.20, ge=0)
    insider: float = Field(0.15, ge=0)
    institutional: float = Field(0.10, ge=0)
    options: float = Field(0.10, ge=0)
    sentiment: float = Field(0.10, ge=0)
    volume_momentum: float = Field(0.10, ge=0)
    regime: float = Field(0.05, ge=0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> "ScoringWeights":
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring weights must sum to 1.0, got {total:.4f}")
        return self


class StrategiesConfig(_Strict):
    scoring_weights: ScoringWeights = ScoringWeights()


class AppConfig(_Strict):
    environment: Literal["development", "test", "production"] = "development"
    # Only paper trading exists. Live trading gets its own gated config in Milestone 7.
    trading_mode: Literal["paper"] = "paper"
    database_url: str = "sqlite:///data/platform.sqlite"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True
    # SEC requires a descriptive User-Agent with contact info for EDGAR requests.
    sec_user_agent: str | None = None
    # Raw SEC responses; filing documents are immutable and kept forever.
    edgar_cache_dir: str = "data/edgar_cache"


class Settings(_Strict):
    app: AppConfig
    risk: RiskConfig
    strategies: StrategiesConfig

    def configured_providers(self) -> dict[str, bool]:
        """Which integrations have credentials. False means unavailable, not 'zero activity'."""
        status = {
            name: all(os.environ.get(v) for v in env) for name, env in SECRET_ENV_VARS.items()
        }
        status["sec_edgar"] = bool(self.app.sec_user_agent)
        return status


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping at the top level")
    return data


def load_settings(config_dir: Path | None = None) -> Settings:
    config_dir = Path(config_dir or os.environ.get("CONFIG_DIR") or REPO_ROOT / "config")
    app = _read_yaml(config_dir / "settings.yaml")
    # Environment overrides for deployment-specific values.
    for key, env in (
        ("environment", "APP_ENV"),
        ("database_url", "DATABASE_URL"),
        ("log_level", "LOG_LEVEL"),
        ("sec_user_agent", "SEC_USER_AGENT"),
    ):
        if os.environ.get(env):
            app[key] = os.environ[env]
    return Settings(
        app=AppConfig(**app),
        risk=RiskConfig(**_read_yaml(config_dir / "risk.yaml")),
        strategies=StrategiesConfig(**_read_yaml(config_dir / "strategies.yaml")),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def secret_values() -> list[str]:
    """Current secret values, used only by the log redactor."""
    names = [v for env in SECRET_ENV_VARS.values() for v in env]
    return [os.environ[n] for n in names if os.environ.get(n)]
