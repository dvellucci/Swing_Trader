# Swing Trading Screener GUI — with Manual Positions

CustomTkinter desktop GUI with the **actual Darvas screener** bundled in `strategies/darvas/`.

## Windows quick start

1. Install Python 3.10 or newer (with the `py` launcher). Internet is required for first-time dependency installation and market data.
2. Download/extract this complete repository (GitHub: **Code → Download ZIP**).
3. Double-click `run_windows.bat`. It creates `.venv`, installs both GUI and strategy dependencies, and starts the GUI.
4. Select **Darvas**, enter `NVDA` or `DOL.TO`, and click **Run Analysis**.

No script browsing or hard-coded user paths. No separate strategy download required. The bundled screener writes run folders to `strategies/darvas/output/`, which the GUI discovers and opens. These generated files are ignored by Git.

The first run needs network access to install dependencies. Each stock analysis also needs internet access to Yahoo Finance. Python 3.15 uses the version-specific pandas requirement supplied with your screener.

## Development

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_analysis.py"
.venv\Scripts\python.exe -m trading_gui
```

The bundled Darvas command-line interface remains usable:

```powershell
.venv\Scripts\python.exe strategies\darvas\screener.py NVDA
```

Run it from the repository root with `--output strategies/darvas/output` if you want its CLI results to appear alongside GUI runs.

## Design

- `trading_gui/ui.py`: presentation only, polls worker events on the UI thread.
- `trading_gui/runner.py`: background subprocess execution and streaming output.
- `trading_gui/strategy_registry.py`: maps strategy labels to bundled entry points.
- `trading_gui/analysis.py`: ticker validation, verdict parsing, fresh report discovery.
- `strategies/darvas/`: **original supplied** `screener.py`, `data_stage.py`, `darvas.py`, and `research.py`, unchanged. The Darvas launcher starts its worker subprocess as originally designed.
- `tests/`: GUI parser tests and original Darvas test file.

Mean Reversion and Moving Averages are intentionally marked coming soon; no fabricated implementations.

## Limits

The GUI and Python code were tested for compilation and offline unit tests. A live end-to-end market-data run and Windows GUI visual verification were not performed here. Your screener currently supports US stocks and CAD-quoted TSX symbols with `.TO`, as specified by its own validation. The application is a screener, not a brokerage order executor.


## Refactor: shared strategy infrastructure

The `core/` package contains reusable market-data retrieval/validation, typed
strategy requests/results, and JSON result manifests. `strategies/darvas/strategy.py`
is the strategy adapter; the original Darvas box rules remain in `darvas.py`.
The GUI uses the registry for its dropdown and receives an exact report path
from the launcher rather than relying exclusively on filename searches.

To add a strategy, create an independent module under `strategies/`, register
its ID/display name/launcher in `trading_gui/strategy_registry.py`, and
use the shared `core.market_data` and `core.reporting` facilities. The GUI
needs no strategy-specific imports. Multiple-symbol requests are supported
by the shared request model; a future runner/launcher adapter will be needed
for strategies that actually consume more than one symbol.

Offline tests: `python -m unittest discover -s tests -v`.
Live Yahoo Finance and Windows visual testing are not covered by offline tests.

## My Positions tab (manual trade journal)

The desktop GUI now has two tabs: **Strategy Analysis** and **My Positions**.
Use **+ Add Purchase** to record a real or paper purchase: ticker, strategy, date,
share quantity, actual fill price, initial protective stop, currency, and notes.
Open positions remain saved after restarting the app. The journal lives at
`%USERPROFILE%\.swing_trading_gui\portfolio.sqlite3` on Windows (a local SQLite
file outside the source repository). Back up this file to preserve your records.

Each position offers **Update Price** (manual mark for unrealized P/L), **Raise
Stop** (only higher protective stops are allowed), **Edit**, **Close Trade**
(record actual exit and realized P/L), and **Delete** (requires confirmation).
Enable **Show closed trades** to review completed trades. CAD and USD results
are kept separate and never combined using an assumed FX rate. Values exclude
commissions, spreads, taxes, and currency conversion costs.

This feature does **not** connect to your broker, place orders, fetch live prices,
automatically detect new Darvas boxes, or move stops for you. You must enter
prices and any confirmed stop changes yourself. A BUY signal from Strategy
Analysis does not create a position until you record the purchase.

The portfolio is implemented independently of the trading strategies:
`portfolio/models.py` (domain and validation), `portfolio/repository.py`
(SQLite persistence), `portfolio/ui.py` (presentation). Tests are in
`tests/test_portfolio.py`. Run all tests with
`python -m unittest discover -s tests -v`.
