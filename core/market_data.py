"""Shared price retrieval, exchange sessions, metadata, and OHLCV validation."""
from __future__ import annotations
import argparse
import re
import time
import numpy as np
import pandas as pd
OHLCV = ["Open", "High", "Low", "Close", "Volume"]

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
