# Swing Trading Screener GUI — v0.3

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
