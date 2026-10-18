"""Machine-readable manifest for an analysis run."""
import json
from pathlib import Path

def write_manifest(folder: Path, *, strategy_id: str, ticker: str, verdict: str, status: str, report_path: Path):
    path = folder / 'result.json'
    payload = dict(strategy_id=strategy_id, ticker=ticker, verdict=verdict,
                   status=status, report_path=str(report_path.resolve()),
                   output_dir=str(folder.resolve()))
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    return path

def read_manifest(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))
