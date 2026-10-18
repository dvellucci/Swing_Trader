"""Darvas strategy adapter; no modifications to the original algorithm."""
from .darvas import scan, report
from .research import research

def analyze(ticker, data, currency, historical=False):
    events, active_box = scan(data)
    context = research(ticker, data, historical=historical)
    lines = report(data, events, active_box, currency, ticker=ticker, research_data=context)
    return lines, {'boxes': events}
