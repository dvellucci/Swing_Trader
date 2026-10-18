"""Best-effort fundamental and market research for Darvas Strategy.

Qualitative evidence does not create hard filters. Failures are reported, never
silently converted to favorable signals. Historical --as-of runs do not use
current financial statements or metadata as if they were point-in-time data.
"""
import math
import pandas as pd


def finite(v):
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def growth(current, prior):
    a, b = finite(current), finite(prior)
    return 100*(a/b-1) if a is not None and b is not None and b > 0 else None


def find_growth(table, names):
    if table is None or table.empty or len(table.columns) < 2:
        return None
    for key in names:
        if key in table.index:
            return growth(table.loc[key].iloc[0], table.loc[key].iloc[1])
    return None


def market_stats(history, last_date):
    if history is None or history.empty:
        return None
    if isinstance(history.columns, pd.MultiIndex):
        history.columns = history.columns.get_level_values(0)
    close = history['Close'].dropna().copy()
    close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize() if close.index.tz is None else pd.DatetimeIndex(close.index).tz_convert('America/New_York').tz_localize(None).normalize()
    close = close.loc[close.index <= pd.Timestamp(last_date)]
    if len(close) < 200:
        return None
    last = float(close.iloc[-1]); sma50 = float(close.tail(50).mean()); sma200 = float(close.tail(200).mean())
    return {'close': last, 'sma50': sma50, 'sma200': sma200, 'bullish': last > sma200 and sma50 > sma200,
            'return63': growth(last, close.iloc[-64]) if len(close) >= 64 else None}


def research(ticker, data, historical=False):
    result = {'lines': [], 'warnings': [], 'market': None, 'earnings_date': None, 'historical': historical}
    lines, warnings = result['lines'], result['warnings']
    try:
        import yfinance as yf
    except Exception as exc:
        warnings.append('Research library unavailable: '+str(exc))
        return result
    last_date = data.index[-1]
    # Index history is useful for both current and historical inspection.
    index_ticker = '^GSPC' if not ticker.endswith('.TO') else '^GSPTSE'
    try:
        ix = yf.Ticker(index_ticker).history(start=(last_date-pd.Timedelta(days=440)).date().isoformat(),
                                              end=(last_date+pd.Timedelta(days=1)).date().isoformat(),
                                              auto_adjust=False, timeout=12)
        result['market'] = market_stats(ix, last_date)
        if result['market']:
            m = result['market']
            lines.append(f'Market {index_ticker}: close {m["close"]:.2f}; 50-day SMA {m["sma50"]:.2f}; 200-day SMA {m["sma200"]:.2f}; '+('UPTREND' if m['bullish'] else 'CAUTION'))
            stock_return = growth(data.Close.iloc[-1], data.Close.iloc[-64]) if len(data) >= 64 else None
            if stock_return is not None and m['return63'] is not None:
                lines.append(f'63-session relative performance: stock {stock_return:+.2f}%; index {m["return63"]:+.2f}%; difference {stock_return-m["return63"]:+.2f} percentage points')
        else:
            warnings.append('Market trend unavailable: insufficient index history')
    except Exception as exc:
        warnings.append('Market/index retrieval failed: '+type(exc).__name__+': '+str(exc)[:150])
    high52 = float(data.High.tail(min(len(data),252)).max())
    lines.append(f'52-week high within downloaded history: {high52:.4f}; latest close {float(data.Close.iloc[-1]):.4f}; distance {(float(data.Close.iloc[-1])/high52-1)*100:+.2f}%')
    # Company fundamentals and corporate-event risks are deliberately excluded
    # from the technical decision. They are external, nonblocking considerations.
    # No slow Yahoo company-metadata calls are made for those topics.
    lines.append('Company fundamentals / industry growth: external, optional review only.')
    lines.append('Bankruptcy / delisting / trading halt news: external, optional review only.')
    return result
