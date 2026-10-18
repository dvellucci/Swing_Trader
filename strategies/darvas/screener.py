#!/usr/bin/env python3
"""Single-stock data collector. Run: python screener.py NVDA

The launcher uses only Python's standard library. Dependencies run in a child
process so an import crash or abrupt native exit can be recorded by the parent.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import os
import platform
import re
import subprocess
import sys
import time

VERSION = '0.4.6'


def ticker_arg(value):
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{0,19}(?:\.TO)?', value):
        raise argparse.ArgumentTypeError('Use a US symbol (NVDA, BRK-B) or TSX symbol (BBD-B.TO).')
    return value


def supervise(command, folder, ticker, timeout):
    """Stream worker output from disk, enforce a deadline, and record fatal exits."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    report = folder / f'{ticker}_report.txt'
    log_path = folder / f'{ticker}_debug.log'
    header = (f'STOCK DATA REPORT - {ticker}\nScript version: {VERSION}\n'
              f'Started: {datetime.now(timezone.utc).isoformat()}\n'
              'Scope: Darvas 3.1 daily-data research; no order placement or fill confirmation.\n')
    report.write_text(header+'Status: RUNNING - collection has not completed.\n', encoding='utf-8')
    preamble = (f'[launcher] Python: {sys.version.split()[0]}\n'
                f'[launcher] Executable: {sys.executable}\n'
                f'[launcher] Platform: {platform.platform()}\n'
                f'[launcher] Files: {folder.resolve()}\n'
                f'[launcher] Maximum run time: {timeout:g} seconds\n')
    print(preamble, end='', flush=True)
    log_path.write_text(preamble, encoding='utf-8')
    reason = None
    process = None
    code = 1
    try:
        env = os.environ.copy()
        env.update(PYTHONUNBUFFERED='1', PYTHONFAULTHANDLER='1', PYTHONIOENCODING='utf-8')
        with log_path.open('ab', buffering=0) as writer, log_path.open('r', encoding='utf-8', errors='replace') as reader:
            reader.read()  # The preamble was already displayed.
            process = subprocess.Popen(command, stdout=writer, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, env=env)
            deadline = time.monotonic()+timeout
            while True:
                chunk = reader.read()
                if chunk:
                    print(chunk, end='', flush=True)
                code = process.poll()
                if code is not None:
                    print(reader.read(), end='', flush=True)
                    break
                if time.monotonic() >= deadline:
                    reason = f'Worker exceeded {timeout:g} seconds and was stopped.'
                    process.kill()
                    process.wait()
                    print(reader.read(), end='', flush=True)
                    code = 1
                    break
                time.sleep(0.1)
        if code != 0 and reason is None:
            reason = f'Worker exited with code {code} (hex 0x{code & 0xffffffff:08X}).'
        content = report.read_text(encoding='utf-8')
        if code == 0 and ('Status: DATA READY' not in content or not (folder/f'{ticker}_daily.csv').is_file()):
            reason = 'Worker exited without producing a successful report and daily CSV.'
            code = 1
    except KeyboardInterrupt:
        reason = 'Run interrupted by user.'
        code = 130
    except Exception as exc:
        reason = f'Launcher error: {type(exc).__name__}: {exc}'
        code = 1
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if reason:
            # Preserve the worker report if it explains an ordinary data error.
            old = report.read_text(encoding='utf-8')
            if 'Status: RUNNING' in old:
                old = header
            with report.open('w', encoding='utf-8') as out:
                out.write(old+'\nStatus: DATA ERROR\n'+reason+'\n'
                          'See the debug log for the last completed step.\n')
            with log_path.open('a', encoding='utf-8') as out:
                out.write('\n[launcher] '+reason+'\n')
            print('[launcher] '+reason, flush=True)
        print(f'[launcher] Report: {report.resolve()}', flush=True)
        print(f'[launcher] Debug log: {log_path.resolve()}', flush=True)
    return 0 if code == 0 else (130 if code == 130 else 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ticker', type=ticker_arg)
    parser.add_argument('--output', type=Path, default=Path('output'))
    parser.add_argument('--as-of', type=lambda x: datetime.strptime(x, '%Y-%m-%d').date())
    parser.add_argument('--timeout', type=int, default=120, help='Overall timeout in seconds (default: 120)')
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    if sys.version_info < (3, 10):
        parser.error('Python 3.10 or newer is required; use your newer Python installation.')
    print(f'[launcher] Starting {args.ticker} data collection (v{VERSION})...', flush=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = (args.output/f'{args.ticker}_{stamp}').resolve()
    worker = Path(__file__).resolve().with_name('data_stage.py')
    command = [sys.executable, '-u', '-X', 'faulthandler', str(worker), args.ticker,
               '--run-dir', str(folder)]
    if args.as_of:
        command += ['--as-of', str(args.as_of)]
    try:
        return supervise(command, folder, args.ticker, args.timeout)
    except OSError as exc:
        print(f'[launcher] Cannot create/write output files: {exc}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
