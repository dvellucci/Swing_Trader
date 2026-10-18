#!/usr/bin/env python3
"""Darvas Strategy: single-stock daily OHLCV retrieval and box research. Python 3.10+.

Install: python -m pip install -r requirements.txt
Run:     python screener.py NVDA
Canada:  python screener.py BBD-B.TO
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import time
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print('[worker] Loading numpy...', flush=True)
import numpy as np
print('[worker] Loading pandas...', flush=True)
import pandas as pd
print('[worker] Numerical libraries loaded.', flush=True)


VERSION = '0.4.6'
from core.market_data import (DataError, parse_ticker, session_window, validate_daily,
                              read_metadata, retrieve, check_instrument, OHLCV)










def add_darvas_inputs(data):
    """Inputs only; the actual box and signal logic will be added separately."""
    out = data.copy()
    out['DollarVolume'] = out.Close * out.Volume
    # Liquidity window includes the current completed day; breakout benchmark does not.
    out['AverageDollarVolume20'] = out.DollarVolume.rolling(20, min_periods=20).mean()
    out['PriorAverageVolume20'] = out.Volume.shift(1).rolling(20, min_periods=20).mean()
    denominator = out.PriorAverageVolume20.replace(0, np.nan)
    out['VolumeRatio20'] = out.Volume / denominator
    out['Close63SessionsAgo'] = out.Close.shift(63)
    out['PriceReturn63Pct'] = (out.Close / out.Close63SessionsAgo - 1) * 100
    return out








def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('ticker', type=parse_ticker)
    parser.add_argument('--output', type=Path, default=Path('output'))
    parser.add_argument('--run-dir', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--as-of', type=lambda text: datetime.strptime(text, '%Y-%m-%d').date(),
                        help='Optional historical cutoff YYYY-MM-DD; nontrading dates use the prior session')
    args = parser.parse_args(argv)
    now = pd.Timestamp.now(tz='UTC')
    # Each run has its own folder, so an error cannot leave an old CSV looking current.
    folder = args.run_dir or args.output / f'{args.ticker}_{now.strftime("%Y%m%dT%H%M%S%fZ")}'
    folder.mkdir(parents=True, exist_ok=args.run_dir is not None)
    report_path = folder / f'{args.ticker}_report.txt'
    lines = [f'STOCK DATA REPORT - {args.ticker}', f'Script version: {VERSION}',
             f'Retrieved at: {now.isoformat()}', 'Scope: data collection and Darvas technical analysis.',
             'Daily-bar research only: no intraday fill verification or order execution.',
             'Source: Yahoo Finance via yfinance.']
    attempts = []
    try:
        print('[worker] Loading exchange calendar library...', flush=True)
        try:
            import exchange_calendars as xcals
        except ImportError as exc:
            raise DataError('Missing exchange-calendars. Run: python -m pip install -r requirements.txt') from exc
        canadian = args.ticker.endswith('.TO')
        calendar_name = 'XTSE' if canadian else 'XNYS'
        print(f'[worker] Building {calendar_name} session calendar...', flush=True)
        earliest = pd.Timestamp(args.as_of) if args.as_of else now.tz_localize(None)
        calendar = xcals.get_calendar(calendar_name,
            start=(min(earliest, now.tz_localize(None))-pd.Timedelta(days=450)).normalize(),
            end=(now.tz_localize(None)+pd.Timedelta(days=10)).normalize())
        expected = session_window(calendar, now, args.as_of)
        print(f'[worker] Requesting {len(expected)} sessions through {expected[-1].date()}.', flush=True)
        lines += [f'Calendar: {calendar_name}', f'Expected latest session: {expected[-1].date()}',
                  'Session inclusion: exchange close plus 60-minute publication buffer.']
        raw, metadata = retrieve(args.ticker, expected, attempts,
                                 raw_path=folder / f'{args.ticker}_raw.csv')
        # Preserve provider values even if validation subsequently rejects them.
        raw.to_csv(folder / f'{args.ticker}_raw.csv', index_label='Date')
        print('[worker] Raw CSV saved. Validating prices and session dates...', flush=True)
        exchange, currency = check_instrument(metadata, canadian)
        data = validate_daily(raw, expected, 'America/Toronto' if canadian else 'America/New_York')
        calculated = add_darvas_inputs(data)
        calculated.to_csv(folder / f'{args.ticker}_daily.csv', date_format='%Y-%m-%d')
        print('[worker] Validated daily CSV saved.', flush=True)
        print('[worker] Tracking Darvas boxes chronologically...', flush=True)
        from strategies.darvas.strategy import analyze
        strategy_lines, artifacts = analyze(args.ticker, calculated, currency, historical=bool(args.as_of))
        artifacts["boxes"].to_csv(folder / f"{args.ticker}_boxes.csv", index=False)
        lines += ['Status: DATA READY', f'Exchange: {exchange}; currency: {currency}',
                  f'Sessions: {len(data)}; {data.index[0].date()} through {data.index[-1].date()}',
                  'Price basis: provider split-adjusted OHLC, NOT dividend-adjusted.',
                  'Adj Close, when supplied, is preserved but not used for Darvas inputs.',
                  'AverageDollarVolume20: descriptive liquidity, not an eligibility threshold.',
                  'PriorAverageVolume20: mean(Volume) over the 20 sessions BEFORE each candle.',
                  'VolumeRatio20: current volume / PriorAverageVolume20.',
                  'Close63SessionsAgo: descriptive trend data, not a mandatory 3.1 filter.',
                  'Blank calculated cells mean insufficient lookback or a zero denominator.',
                  'Dollar-volume values are in quote currency; no CAD/USD conversion is performed.',
                  'Checks: complete expected session sequence, unique dates, finite positive prices,',
                  'nonnegative whole-share volume, and coherent OHLC ranges.',
                  f'Zero-volume sessions: {int((data.Volume == 0).sum())}',
                  '', 'LIMITATIONS',
                  'Validation checks consistency, not independent accuracy of Yahoo values.',
                  'Splits/dividends are saved when supplied; corporate-action adjustments are not',
                  'independently verified. Historical downloads reflect subsequent split adjustments.',
                  'Only US-listed stocks and CAD-quoted TSX stocks are supported in this version.',
                  'Company fundamentals and corporate-event checks are external and never block technical BUY.',
                  'Optional market data may be unavailable; no technical signal is rejected for that reason.',
                   'No live order placement or intraday fills; high >= trigger is only a possible touch.',
                   'Exchange tick size assumed $0.01 for supported ordinary equities; verify tick rules.',
                  'Technical box analysis uses only this downloaded history.', *strategy_lines]
        result = 0
    except Exception as exc:
        import traceback
        traceback.print_exc()
        lines += ['Status: DATA ERROR', f'Reason: {type(exc).__name__}: {exc}',
                  'No validated daily CSV or trading conclusion is produced for this run.']
        result = 1
    lines += ['', 'RETRIEVAL LOG', *attempts]
    report_path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    from core.reporting import write_manifest
    from trading_gui.analysis import parse_verdict
    write_manifest(folder, strategy_id='darvas', ticker=args.ticker,
                   verdict=parse_verdict('\n'.join(lines)) or 'INSUFFICIENT DATA',
                   status='DATA READY' if result == 0 else 'DATA ERROR', report_path=report_path)
    print('\n'.join(lines), flush=True)
    print(f'\nFiles: {folder.resolve()}', flush=True)
    return result


if __name__ == '__main__':
    sys.exit(main())
