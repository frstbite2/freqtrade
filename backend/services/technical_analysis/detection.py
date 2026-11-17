"""The record every detector produces."""

from dataclasses import dataclass, field
from datetime import datetime


NO_HISTORY = "unavailable: comparable setups are measured by backtesting (Milestone 8)"


@dataclass
class Detection:
    name: str
    kind: str  # "candlestick" | "chart" | "structure"
    direction: str  # "bullish" | "bearish" | "neutral"
    detected_at: datetime  # start of the bar that completed it; nothing later is used
    # How cleanly the rules matched, 0-1. A ranking aid, not a probability of profit.
    confidence: float
    explanation: str
    entry_zone: tuple[float, float] | None = None
    stop_loss: float | None = None
    targets: list[float] = field(default_factory=list)
    zone: tuple[float, float] | None = None  # the price area a structure event refers to
    symbol: str = ""  # filled in by the engine
    timeframe: str = ""
    higher_timeframe: dict | None = None  # None: no higher timeframe data was available
    historical_performance: str = NO_HISTORY


def with_levels(
    detection: Detection, entry: float, stop: float, target: float | None = None
) -> Detection:
    """Attach entry, stop and targets. Without a measured target, use 1x and 2x the risk."""
    risk = abs(entry - stop)
    if risk <= 0:
        return detection
    sign = 1 if detection.direction == "bullish" else -1
    near = entry - sign * 0.25 * risk  # a pullback entry a quarter of the way to the stop
    detection.entry_zone = (min(near, entry), max(near, entry))
    detection.stop_loss = stop
    detection.targets = [
        entry + sign * risk,
        target if target is not None else entry + sign * 2 * risk,
    ]
    detection.targets.sort(reverse=sign < 0)
    return detection
