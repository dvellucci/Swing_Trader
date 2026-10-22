"""Domain model and input validation for manually entered positions."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re

SYMBOL = re.compile(r'[A-Z0-9][A-Z0-9-]{0,19}(?:\.TO)?\Z')

def positive(value, name):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{name} must be a number') from None
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f'{name} must be greater than zero')
    return amount

@dataclass(frozen=True)
class Position:
    id: int
    ticker: str
    strategy: str
    entry_date: str
    shares: Decimal
    entry_price: Decimal
    initial_stop: Decimal
    current_stop: Decimal
    currency: str
    latest_price: Decimal | None = None
    latest_price_date: str | None = None
    notes: str = ''
    exit_date: str | None = None
    exit_price: Decimal | None = None

    @property
    def is_open(self):
        return self.exit_date is None

    @property
    def cost_basis(self):
        return self.shares * self.entry_price

    @property
    def unrealized_pl(self):
        return None if self.latest_price is None or not self.is_open else self.shares * (self.latest_price-self.entry_price)

    @property
    def realized_pl(self):
        return None if self.exit_price is None else self.shares * (self.exit_price-self.entry_price)

    @property
    def planned_stop_pl(self):
        return self.shares * (self.current_stop-self.entry_price)

    @property
    def initial_risk(self):
        return self.shares * (self.entry_price-self.initial_stop)


def validate_new(ticker, strategy, entry_date, shares, entry_price, stop, currency):
    ticker = ticker.strip().upper()
    if not SYMBOL.fullmatch(ticker):
        raise ValueError('Enter a valid symbol such as AMZN or RY.TO')
    if not strategy.strip():
        raise ValueError('Choose a strategy')
    try:
        date.fromisoformat(entry_date)
    except ValueError:
        raise ValueError('Date must be YYYY-MM-DD') from None
    if currency not in ('USD','CAD'):
        raise ValueError('Currency must be USD or CAD')
    qty = positive(shares, 'Shares')
    entry = positive(entry_price, 'Entry price')
    protective = positive(stop, 'Initial stop')
    if protective >= entry:
        raise ValueError('Initial stop must be below entry price for a long position')
    return ticker, strategy.strip(), entry_date, qty, entry, protective, currency
