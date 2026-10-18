"""Application-wide settings and UI copy."""
from dataclasses import dataclass
from pathlib import Path
import json

APP_NAME = 'Swing Trading Screener'
WINDOW_SIZE = '980x720'
MIN_WINDOW_SIZE = (760, 580)
POLL_INTERVAL_MS = 100
COLORS = {'neutral': '#374151', 'buy': '#166534', 'wait': '#92400e', 'reject': '#991b1b'}
MESSAGES = {
    'intro': 'Ready. Darvas Strategy is bundled; enter a ticker to begin.\n',
    'missing_script': 'Bundled Darvas screener is missing. Re-download the complete repository.\n',
    'invalid_ticker': 'Enter a ticker such as COST or DOL.TO.',
    'not_found': 'Bundled strategy file is missing. Re-download the complete repository.',
    'no_report': '\nNo new matching report was found under output/.\n',
}
ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = Path.home() / '.swing_trading_gui' / 'settings.json'

@dataclass(frozen=True)
class Settings:
    script_path: str = ''


def load_settings() -> Settings:
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        return Settings(script_path=str(raw.get('script_path', '')))
    except (OSError, ValueError, TypeError):
        return Settings()


def save_settings(settings: Settings) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps({'script_path': settings.script_path}, indent=2), encoding='utf-8')


def discover_script(saved_path: str = '') -> Path | None:
    candidates = [Path(saved_path).expanduser()] if saved_path else []
    candidates += [ROOT / 'screener.py', ROOT / 'darvas_step1' / 'screener.py', ROOT.parent / 'darvas_step1' / 'screener.py']
    return next((p.resolve() for p in candidates if p.is_file() and p.suffix.lower() == '.py'), None)
