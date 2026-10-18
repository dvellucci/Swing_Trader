"""Run CLI strategies without blocking Tk's event loop."""
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
import subprocess
import sys
import threading
import time

@dataclass(frozen=True)
class Event:
    kind: str
    data: object

@dataclass(frozen=True)
class Completed:
    code: int
    script: Path
    ticker: str
    started_at: float
    report_path: Path | None = None

class ScriptRunner:
    def __init__(self, events: Queue):
        self.events = events
        self.process: subprocess.Popen | None = None
        self.running = False
        self._lock = threading.Lock()

    def start(self, script: Path, ticker: str) -> None:
        with self._lock:
            if self.running:
                raise RuntimeError('Analysis already running')
            self.running = True
        threading.Thread(target=self._execute, args=(script, ticker), daemon=True).start()

    def _execute(self, script: Path, ticker: str) -> None:
        started_at = time.time()
        report_path = None
        try:
            self.events.put(Event('line', f'Running: {script.name} {ticker}\n\n'))
            with subprocess.Popen([sys.executable, '-u', str(script), ticker], cwd=script.parent,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, bufsize=1, encoding='utf-8', errors='replace') as proc:
                self.process = proc
                assert proc.stdout is not None
                for line in proc.stdout:
                    if line.startswith('[launcher] Report: '):
                        report_path = Path(line.split(': ', 1)[1].strip())
                    self.events.put(Event('line', line))
                code = proc.wait()
            self.events.put(Event('done', Completed(code, script, ticker, started_at, report_path)))
        except Exception as exc:
            self.events.put(Event('error', str(exc)))
        finally:
            self.process = None
            with self._lock:
                self.running = False

    def stop(self) -> None:
        proc = self.process
        if proc is not None and proc.poll() is None:
            proc.terminate()
