"""Single source of truth for bundled strategies."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class Strategy:
    key: str
    label: str
    script: Path | None

STRATEGIES = (
    Strategy('darvas', 'Darvas 3.1', ROOT / 'strategies' / 'darvas' / 'screener.py'),
    Strategy('mean_reversion', 'Mean Reversion 4.0 (coming soon)', None),
    Strategy('moving_average', 'Moving Averages 5.0 (coming soon)', None),
)
BY_LABEL = {strategy.label: strategy for strategy in STRATEGIES}
