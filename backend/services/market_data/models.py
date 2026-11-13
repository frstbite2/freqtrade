"""Provider-neutral market data models and validation."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MarketDataError(RuntimeError):
    """Base error for market-data retrieval or validation failures."""


class ProviderConfigurationError(MarketDataError):
    """Raised when a provider cannot be used because credentials are missing."""


class ProviderRequestError(MarketDataError):
    """Raised when a provider request fails or returns an unusable response."""


class Bar(BaseModel):
    """A normalized OHLCV bar. Timestamps are always timezone-aware UTC."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1, max_length=32)
    timestamp: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)
    trade_count: int | None = Field(default=None, ge=0)
    vwap: Decimal | None = Field(default=None, gt=0)
    source: str = "alpaca"

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include timezone information")
        return value.astimezone(UTC)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_ohlc(self) -> "Bar":
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open, close, and high")
        return self


def decimal_value(value: object, field: str) -> Decimal:
    """Convert provider numbers without introducing binary-float arithmetic."""
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ProviderRequestError(f"Provider returned invalid {field}") from exc
    if not result.is_finite():
        raise ProviderRequestError(f"Provider returned non-finite {field}")
    return result
