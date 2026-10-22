"""SQLite persistence for manually entered trades; no GUI or strategy dependencies."""
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
import sqlite3
from .models import Position, positive, validate_new

DEFAULT_DB = Path.home() / '.swing_trading_gui' / 'portfolio.sqlite3'

class PortfolioRepository:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL,
                strategy TEXT NOT NULL, entry_date TEXT NOT NULL,
                shares TEXT NOT NULL, entry_price TEXT NOT NULL,
                initial_stop TEXT NOT NULL, current_stop TEXT NOT NULL,
                currency TEXT NOT NULL, latest_price TEXT, latest_price_date TEXT,
                notes TEXT NOT NULL DEFAULT '', exit_date TEXT, exit_price TEXT)''')

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _position(row):
        return Position(row['id'], row['ticker'], row['strategy'], row['entry_date'],
                        Decimal(row['shares']), Decimal(row['entry_price']),
                        Decimal(row['initial_stop']), Decimal(row['current_stop']),
                        row['currency'], Decimal(row['latest_price']) if row['latest_price'] is not None else None,
                        row['latest_price_date'], row['notes'], row['exit_date'],
                        Decimal(row['exit_price']) if row['exit_price'] is not None else None)

    def list_positions(self, include_closed=False):
        sql = 'SELECT * FROM positions' + ('' if include_closed else ' WHERE exit_date IS NULL') + ' ORDER BY entry_date DESC, id DESC'
        with self._connect() as conn:
            return [self._position(row) for row in conn.execute(sql)]

    def get(self, position_id):
        with self._connect() as conn:
            row = conn.execute('SELECT * FROM positions WHERE id=?', (position_id,)).fetchone()
        if row is None:
            raise ValueError('Position no longer exists')
        return self._position(row)

    def add(self, ticker, strategy, entry_date, shares, entry_price, stop, currency, notes=''):
        ticker, strategy, entry_date, shares, entry_price, stop, currency = validate_new(
            ticker, strategy, entry_date, shares, entry_price, stop, currency)
        with self._connect() as conn:
            cursor = conn.execute('''INSERT INTO positions
                (ticker,strategy,entry_date,shares,entry_price,initial_stop,current_stop,currency,notes)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (ticker,strategy,entry_date,str(shares),str(entry_price),str(stop),str(stop),currency,notes.strip()))
            return cursor.lastrowid

    def update_details(self, position_id, ticker, strategy, entry_date, shares, entry_price, stop, currency, notes=''):
        original = self.get(position_id)
        if not original.is_open:
            raise ValueError('Closed positions cannot be edited')
        ticker, strategy, entry_date, shares, entry_price, stop, currency = validate_new(
            ticker, strategy, entry_date, shares, entry_price, stop, currency)
        if stop != original.initial_stop:
            raise ValueError('Initial stop is part of the original trade record; use Raise Stop for changes to the active stop')
        with self._connect() as conn:
            conn.execute('''UPDATE positions SET ticker=?,strategy=?,entry_date=?,shares=?,entry_price=?,
                initial_stop=?,currency=?,notes=? WHERE id=? AND exit_date IS NULL''',
                (ticker,strategy,entry_date,str(shares),str(entry_price),str(stop),
                 currency,notes.strip(),position_id))

    def update_price(self, position_id, price, observed_date=None):
        p = self.get(position_id)
        if not p.is_open:
            raise ValueError('Position is closed')
        price = positive(price, 'Latest price')
        observed_date = observed_date or date.today().isoformat()
        date.fromisoformat(observed_date)
        with self._connect() as conn:
            conn.execute('UPDATE positions SET latest_price=?,latest_price_date=? WHERE id=?',
                         (str(price),observed_date,position_id))

    def raise_stop(self, position_id, stop):
        p = self.get(position_id)
        if not p.is_open:
            raise ValueError('Position is closed')
        stop = positive(stop, 'New stop')
        if stop <= p.current_stop:
            raise ValueError('The new stop must be higher than the existing stop')
        with self._connect() as conn:
            conn.execute('UPDATE positions SET current_stop=? WHERE id=?', (str(stop),position_id))

    def close(self, position_id, exit_date, exit_price):
        p = self.get(position_id)
        if not p.is_open:
            raise ValueError('Position already closed')
        date.fromisoformat(exit_date)
        price = positive(exit_price, 'Exit price')
        with self._connect() as conn:
            conn.execute('UPDATE positions SET exit_date=?,exit_price=? WHERE id=?',
                         (exit_date,str(price),position_id))

    def delete(self, position_id):
        with self._connect() as conn:
            conn.execute('DELETE FROM positions WHERE id=?', (position_id,))
