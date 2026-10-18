"""Pure parsing and file-discovery functions, independent of the UI."""
import re
from pathlib import Path

TICKER_PATTERN = re.compile(r'[A-Z0-9][A-Z0-9-]{0,19}(?:\.TO)?\Z')
RESULT_PATTERN = re.compile(r'^\s*Result:\s*(BUY[^\r\n]*|WAIT[^\r\n]*|REJECT[^\r\n]*|INSUFFICIENT DATA[^\r\n]*)', re.I | re.M)


def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not TICKER_PATTERN.fullmatch(ticker):
        raise ValueError('Invalid ticker')
    return ticker


def parse_verdict(text: str) -> str | None:
    match = RESULT_PATTERN.search(text)
    return match.group(1).strip() if match else None


def verdict_color_key(verdict: str) -> str:
    name = verdict.upper()
    return 'buy' if name.startswith('BUY') else 'wait' if name.startswith('WAIT') else 'reject'


def find_new_report(script: Path, ticker: str, started_at: float) -> Path | None:
    output = script.parent / 'output'
    if not output.is_dir():
        return None
    reports = []
    for path in output.rglob('*.txt'):
        try:
            if ticker.upper() in path.name.upper() and path.stat().st_mtime >= started_at - 2:
                reports.append(path)
        except OSError:
            continue
    return max(reports, key=lambda p: p.stat().st_mtime) if reports else None
