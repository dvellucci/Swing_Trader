"""Single source of truth for bundled strategies."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class Strategy:
    id: str
    display_name: str
    script: Path | None

STRATEGIES = (
    Strategy(
        id="darvas",
        display_name="Darvas Strategy",
        script=ROOT / "strategies" / "darvas" / "screener.py",
    ),
    Strategy(
        id="mean_reversion",
        display_name="Mean Reversion 4.0 (coming soon)",
        script=None,
    ),
    Strategy(
        id="moving_average",
        display_name="Moving Averages 5.0 (coming soon)",
        script=None,
    ),
)

BY_ID = {
    strategy.id: strategy
    for strategy in STRATEGIES
}

BY_LABEL = {
    strategy.display_name: strategy
    for strategy in STRATEGIES
}
