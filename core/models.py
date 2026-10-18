"""Stable inputs and machine-readable outcomes for strategies."""
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class StrategyRequest:
    strategy_id: str
    ticker: str
    as_of: date | None = None
    related_tickers: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class StrategyResult:
    strategy_id: str
    ticker: str
    verdict: str
    report_path: Path
    output_dir: Path
    status: str = 'DATA READY'
