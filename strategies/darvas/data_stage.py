#!/usr/bin/env python3
"""Darvas 3.1: single-stock daily OHLCV retrieval and box research. Python 3.10+.

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

print('[worker] Loading numpy...', flush=True)
import numpy as np
print('[worker] Loading pandas...', flush=True)
import pandas as pd
print('[worker] Numerical libraries loaded.', flush=True)


VERSION = '0.4.6'
OHLCV = ['Open', 'High', 'Low', 'Close', 'Volume']


class DataError(Exception):
    """Retrieval or validation failed; this is not a failed trading setup."""


def parse_ticker(value):
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{0,19}(?:\.TO)?', value):
        raise argparse.ArgumentTypeError(
            'Use a US Yahoo symbol (NVDA, BRK-B) or TSX symbol (BBD-B.TO).')
    return value


def session_window(calendar, now, requested=None):
    """Use exchange close plus a one-hour publication buffer, including early closes."""
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        raise DataError('Current time must have a timezone')
    schedule = calendar.schedule
    closes = pd.to_datetime(schedule['close'], utc=True)
    eligible = schedule.index[closes + pd.Timedelta(hours=1) <= now]
    if len(eligible) == 0:
        raise DataError('Calendar has no completed sessions')
    latest = pd.Timestamp(eligible[-1]).tz_localize(None).normalize()
    requested = pd.Timestamp(requested) if requested else latest
    requested = requested.tz_localize(None).normalize()
    if requested > latest:
        raise DataError(f'Requested date is not ready; latest available session is {latest.date()}')
    labels = pd.DatetimeIndex(schedule.index).tz_localize(None).normalize()
    available = labels[labels <= requested]
    if available.empty:
        raise DataError('Requested date is outside the calendar range')
    end = available[-1]
    # A full year supports six-month box analysis with ample indicator warmup.
    start = end - pd.DateOffset(years=1)
    expected = labels[(labels >= start) & (labels <= end)]
    return expected


def validate_daily(raw, expected, exchange_timezone):
    if raw is None or raw.empty:
        raise DataError('Provider returned no daily candles')
    missing_columns = set(OHLCV) - set(raw.columns)
    if missing_columns:
        raise DataError(f'Missing columns: {sorted(missing_columns)}')
    data = raw.copy()
    dates = pd.DatetimeIndex(data.index)
    if dates.hasnans:
        raise DataError('Invalid session dates')
    if dates.tz is not None:
        dates = dates.tz_convert(exchange_timezone).tz_localize(None)
    data.index = dates.normalize()
    data.index.name = 'Date'
    if data.index.has_duplicates:
        raise DataError('Duplicate session dates; no automatic deduplication')
    data = data.sort_index()
    # Refuse unexpected candles rather than silently incorporating intraday data.
    unexpected = data.index.difference(expected)
    if len(unexpected):
        raise DataError('Unexpected session dates: '+', '.join(unexpected.strftime('%Y-%m-%d')))
    try:
        data[OHLCV] = data[OHLCV].apply(pd.to_numeric, errors='raise')
    except (TypeError, ValueError) as exc:
        raise DataError('Nonnumeric OHLCV value') from exc
    if not np.isfinite(data[OHLCV].to_numpy(dtype=float)).all():
        raise DataError('Missing or nonfinite OHLCV; prices are never forward-filled')
    if (data[OHLCV[:4]] <= 0).any().any() or (data.Volume < 0).any():
        raise DataError('Nonpositive price or negative volume')
    if (data.Volume % 1 != 0).any():
        raise DataError('Noninteger daily share volume')
    invalid = ((data.High < data[['Open', 'Close', 'Low']].max(axis=1)) |
               (data.Low > data[['Open', 'Close', 'High']].min(axis=1)))
    if invalid.any():
        raise DataError('Inconsistent OHLC on '+', '.join(data.index[invalid].strftime('%Y-%m-%d')))
    missing = expected.difference(data.index)
    if len(missing):
        raise DataError('Missing expected sessions (possibly short listing history, halt, or feed error): '
                        + ', '.join(missing.strftime('%Y-%m-%d')))
    data.Volume = data.Volume.astype('int64')
    return data


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


def read_metadata(stock, attempts):
    """Accept dictionary-like metadata and fall back to alternate public interfaces."""
    result = {}
    aliases = {'exchangeName': ('exchangeName', 'exchange'),
               'currency': ('currency',),
               'instrumentType': ('instrumentType', 'quoteType', 'quote_type')}
    sources = [('history metadata', lambda: stock.get_history_metadata()),
               ('quote info', lambda: stock.get_info()),
               ('fast info', lambda: stock.fast_info)]
    for label, fetch in sources:
        print(f'[worker] Checking {label}...', flush=True)
        try:
            payload = fetch()
            attempts.append(f'{label}: returned {type(payload).__name__}')
            # Some releases return a lazy mapping rather than a literal dict.
            for field, keys in aliases.items():
                if field in result:
                    continue
                for key in keys:
                    try:
                        value = payload[key]
                    except (KeyError, TypeError, AttributeError, IndexError):
                        continue
                    if isinstance(value, str) and value.strip():
                        result[field] = value
                        break
            attempts.append(f'{label}: verified fields {sorted(result)}')
            if all(field in result for field in aliases):
                return result
        except Exception as exc:
            attempts.append(f'{label}: {type(exc).__name__}: {exc}')
    missing = sorted(set(aliases)-set(result))
    raise DataError(f'Prices downloaded, but listing metadata is incomplete after three interfaces: {missing}. '
                    'The raw CSV has been preserved; listing details were not guessed.')


def retrieve(ticker, expected, attempts, raw_path=None):
    print('[worker] Loading yfinance...', flush=True)
    try:
        import yfinance as yf
    except ImportError as exc:
        raise DataError('Missing yfinance. Run: python -m pip install -r requirements.txt') from exc
    # Use the current exception setting when available, retaining older-release support.
    debug = getattr(getattr(yf, 'config', None), 'debug', None)
    history_options = {}
    if debug is not None and hasattr(debug, 'hide_exceptions'):
        debug.hide_exceptions = False
    else:
        history_options['raise_errors'] = True
    last_error = None
    for number in range(1, 4):
        try:
            print(f'[worker] Download attempt {number}/3 for {ticker}...', flush=True)
            stock = yf.Ticker(ticker)
            data = stock.history(
                start=expected[0].date().isoformat(),
                end=(expected[-1]+pd.Timedelta(days=1)).date().isoformat(),
                interval='1d', auto_adjust=False, back_adjust=False, repair=False,
                actions=True, keepna=True, prepost=False, timeout=15,
                **history_options,
            )
            if data is None or data.empty:
                raise DataError('Empty price history')
            attempts.append(f'Attempt {number}: prices retrieved (yfinance {yf.__version__})')
            break
        except Exception as exc:
            last_error = f'{type(exc).__name__}: {exc}'
            attempts.append(f'Attempt {number}: {last_error}')
            print(f'[worker] Attempt {number} failed: {last_error}', flush=True)
            if number < 3:
                time.sleep(number)
    else:
        raise DataError(f'Download failed after three attempts: {last_error}')
    if raw_path is not None:
        data.to_csv(raw_path, index_label='Date')
        print('[worker] Prices received and raw CSV saved.', flush=True)
    metadata = read_metadata(stock, attempts)
    return data, metadata


def check_instrument(metadata, canadian):
    exchange = metadata.get('exchangeName')
    currency = metadata.get('currency')
    kind = metadata.get('instrumentType')
    if kind != 'EQUITY':
        raise DataError(f'Expected stock instrumentType EQUITY, received {kind!r}')
    allowed = {'TOR'} if canadian else {'NMS', 'NGM', 'NCM', 'NYQ', 'ASE', 'PCX', 'BTS', 'BATS'}
    if exchange not in allowed:
        raise DataError(f'Exchange {exchange!r} not supported by the selected calendar')
    if currency != ('CAD' if canadian else 'USD'):
        raise DataError(f'Unexpected quote currency {currency!r}')
    return exchange, currency


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
        from darvas import scan, report as darvas_report
        events, active_box = scan(calculated)
        events.to_csv(folder / f'{args.ticker}_boxes.csv', index=False)
        from research import research
        print('[worker] Checking optional market context...', flush=True)
        research_data = research(args.ticker, calculated, historical=bool(args.as_of))
        strategy_lines = darvas_report(calculated, events, active_box, currency, ticker=args.ticker, research_data=research_data)
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
    print('\n'.join(lines), flush=True)
    print(f'\nFiles: {folder.resolve()}', flush=True)
    return result


if __name__ == '__main__':
    sys.exit(main())
