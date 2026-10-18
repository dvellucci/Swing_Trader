"""Darvas Strategy daily-bar research: chronological three-following-session boxes.

This is a deterministic modern reconstruction, NOT a verified reproduction of
Darvas's discretionary historical decisions. It never executes or simulates fills.
"""
from decimal import Decimal, ROUND_FLOOR
import math
import pandas as pd

TICK = Decimal('0.01')  # Assumed for ordinary US/TSX equities; verify exchange rules.


def price(v):
    v = float(v)
    cents = round(v, 2)
    return Decimal(str(cents if abs(v - cents) <= .00005 else v))


def order_levels(reference, floor, tick=TICK):
    ref, floor, tick = price(reference), price(floor), Decimal(str(tick))
    if ref <= 0 or floor <= 0 or floor >= ref or tick <= 0:
        raise ValueError('Invalid box boundaries or tick')
    # Round reference to tick lattice to avoid untradeable order prices.
    units = (ref / tick).to_integral_value(rounding=ROUND_FLOOR)
    base = units * tick
    floor_units = (floor / tick).to_integral_value(rounding=ROUND_FLOOR)
    stop = floor_units * tick - tick
    return {'reference': float(ref), 'floor': float(floor), 'buy_stop': float(base + tick),
            'protective_stop': float(stop), 'tick': float(tick)}


def position_size(equity, entry, stop, estimated_cost_per_share=0):
    if not all(math.isfinite(float(v)) for v in (equity, entry, stop, estimated_cost_per_share)):
        raise ValueError('Inputs must be finite')
    if equity <= 0 or entry <= stop or stop <= 0 or estimated_cost_per_share < 0:
        raise ValueError('Invalid capital, entry, stop or cost')
    risk = float(entry) - float(stop) + float(estimated_cost_per_share)
    shares = min(math.floor(.005 * float(equity) / risk),
                 math.floor(.20 * float(equity) / float(entry)))
    return {'shares': max(0, shares), 'planned_risk': max(0, shares) * risk,
            'allocation': max(0, shares) * float(entry), 'risk_per_share': risk}


def scan(data):
    """Single-pass, one-box-at-a-time reconstruction.

    A candidate high needs three STRICTLY lower subsequent highs; after this,
    a candidate low needs three STRICTLY higher subsequent lows. The floor search
    starts on the next session after ceiling confirmation. Before floor
    confirmation a high >= confirmed ceiling restarts ceiling discovery.
    A confirmed box is breached by intraday high > ceiling (possible buy-stop
    touch) or low < floor (downside break); daily bars cannot determine fills.
    On a bar touching both boundaries, mark ambiguity, not an invented sequence.
    """
    if data.empty:
        raise ValueError('Nonempty daily data required')
    state = 'HIGH'
    candidate_high = candidate_low = None
    high_date = low_date = None
    high_count = low_count = 0
    active = None
    box_id = 0
    events = []
    for i, (date, row) in enumerate(data.iterrows()):
        day = str(pd.Timestamp(date).date())
        high, low = price(row.High), price(row.Low)
        avg = float(data.Volume.iloc[i-20:i].mean()) if i >= 20 else None
        ratio = float(row.Volume)/avg if avg and avg > 0 else None
        event = dict(Date=day, Event='', StateBefore=state, BoxId=active['id'] if active else None,
                     CandidateHigh=None, CandidateHighDate=None, HighConfirmCount=0,
                     CandidateLow=None, CandidateLowDate=None, LowConfirmCount=0,
                     Ceiling=None, Floor=None, CeilingConfirmedDate=None,
                     FloorConfirmedDate=None, BuyStop=None, ProtectiveStop=None,
                     TouchedBuyStop=False, TouchedFloor=False, AmbiguousIntraday=False,
                     Volume=int(row.Volume), PriorAverageVolume20=avg, VolumeRatio20=ratio,
                     Close=float(row.Close), High=float(high), Low=float(low))
        if state == 'HIGH':
            if candidate_high is None or high >= candidate_high:
                candidate_high, high_date, high_count = high, day, 0
                event['Event'] = 'HIGH_CANDIDATE'
            else:
                high_count += 1
                event['Event'] = 'HIGH_CONFIRMING'
                if high_count == 3:
                    state = 'LOW'
                    candidate_low = None
                    event['Event'] = 'CEILING_CONFIRMED'
        elif state == 'LOW':
            if high >= candidate_high:
                candidate_high, high_date, high_count = high, day, 0
                candidate_low, low_count = None, 0
                state = 'HIGH'
                event['Event'] = 'CEILING_RESET'
            elif candidate_low is None or low <= candidate_low:
                candidate_low, low_date, low_count = low, day, 0
                event['Event'] = 'LOW_CANDIDATE'
            else:
                low_count += 1
                event['Event'] = 'LOW_CONFIRMING'
                if low_count == 3:
                    box_id += 1
                    active = dict(id=box_id, ceiling=candidate_high, floor=candidate_low,
                                  high_date=high_date, low_date=low_date,
                                  ceiling_confirmed_date=ceiling_confirmed_date,
                                  floor_confirmed_date=day)
                    state = 'ACTIVE'
                    event['Event'] = 'BOX_CONFIRMED'
        else:
            prior_active = active
            levels = order_levels(active['ceiling'], active['floor'])
            up = high >= price(levels['buy_stop'])
            down = low < active['floor']
            if up and down:
                event['Event'] = 'BOTH_BOUNDARIES_TOUCHED_REVIEW'
            elif up:
                event['Event'] = 'BUY_STOP_TOUCHED_UNVERIFIED_FILL'
            elif down:
                event['Event'] = 'BOX_DOWNSIDE_BREAK'
            else:
                event['Event'] = 'BOX_ACTIVE'
            event['TouchedBuyStop'], event['TouchedFloor'] = up, down
            event['AmbiguousIntraday'] = up and down
            if up or down:
                # End this candidate and begin searching on the following bar.
                state, active = 'HIGH', None
                candidate_high = candidate_low = None
                high_count = low_count = 0
        if event['Event'] == 'CEILING_CONFIRMED':
            ceiling_confirmed_date = day
        event.update(StateAfter=state,
                     CandidateHigh=float(candidate_high) if candidate_high is not None else None,
                     CandidateHighDate=high_date if candidate_high is not None else None,
                     HighConfirmCount=high_count,
                     CandidateLow=float(candidate_low) if candidate_low is not None else None,
                     CandidateLowDate=low_date if candidate_low is not None else None,
                     LowConfirmCount=low_count)
        if active:
            event.update(BoxId=active['id'], Ceiling=float(active['ceiling']),
                         Floor=float(active['floor']),
                         CeilingConfirmedDate=active['ceiling_confirmed_date'],
                         FloorConfirmedDate=active['floor_confirmed_date'],
                         BuyStop=order_levels(active['ceiling'], active['floor'])['buy_stop'],
                         ProtectiveStop=order_levels(active['ceiling'], active['floor'])['protective_stop'])
        elif event['Event'] in ('BUY_STOP_TOUCHED_UNVERIFIED_FILL',
                                'BOTH_BOUNDARIES_TOUCHED_REVIEW', 'BOX_DOWNSIDE_BREAK'):
            # Store prior box values on the terminating event for auditability.
            event.update(BoxId=prior_active['id'], Ceiling=float(prior_active['ceiling']),
                         Floor=float(prior_active['floor']),
                         CeilingConfirmedDate=prior_active['ceiling_confirmed_date'],
                         FloorConfirmedDate=prior_active['floor_confirmed_date'],
                         BuyStop=order_levels(prior_active['ceiling'], prior_active['floor'])['buy_stop'],
                         ProtectiveStop=order_levels(prior_active['ceiling'], prior_active['floor'])['protective_stop'])
        events.append(event)
        # Capture active box for the following day's terminating-event audit.
        prior_active = active
    return pd.DataFrame(events), active


def report(data, events, active, currency, ticker='UNKNOWN', research_data=None):
    """Full, explicit PASS/FAIL/UNVERIFIED/NOT EVALUATED checklist.

    PASS means the technical condition is met as of the completed session.
    FAIL means it is not met; NOT EVALUATED means no applicable setup yet.
    Company research never affects the technical verdict.
    """
    last = events.iloc[-1]
    research_data = research_data or {}
    lines = ['', 'Darvas Strategy - TECHNICAL CHECKS',
             f'Ticker: {ticker}; As of: {last.Date}',
             f'Latest box event: {last.Event}; next state: {last.StateAfter}',
             'Strategy: three-session ceiling/floor confirmations; intraday buy-stop.',
             'One tick assumed = 0.01 listing currency (verify for actual orders).']
    checks = []
    def add(status, label, detail):
        checks.append((status, label, str(detail)))

    data_ok = (not data.empty and all(c in data for c in ('Open','High','Low','Close','Volume')))
    add('PASS' if data_ok else 'FAIL', 'Daily OHLCV available for chronological box scan',
        f'{len(data)} sessions; latest close {float(data.Close.iloc[-1]):.4f} {currency}' if data_ok else 'Missing data')
    state = str(last.StateAfter)
    ceiling_confirmed = state in ('LOW', 'ACTIVE') or active is not None
    floor_confirmed = active is not None
    hi = active['ceiling'] if active else (float(last.CandidateHigh) if pd.notna(last.CandidateHigh) else None)
    lo = active['floor'] if active else (float(last.CandidateLow) if pd.notna(last.CandidateLow) else None)
    hc = 3 if ceiling_confirmed else int(last.HighConfirmCount)
    lc = 3 if floor_confirmed else int(last.LowConfirmCount)
    add('PASS' if ceiling_confirmed else 'FAIL', 'Ceiling confirmed by three lower subsequent highs',
        f'{hc}/3; candidate {hi if hi is not None else "none"} {currency}; date {last.CandidateHighDate}')
    add('PASS' if floor_confirmed else 'FAIL' if ceiling_confirmed else 'NOT EVALUATED',
        'Floor confirmed by three higher subsequent lows',
        f'{lc}/3; candidate {lo if lo is not None else "none"} {currency}; date {last.CandidateLowDate}'
        if ceiling_confirmed else 'Ceiling confirmation required first')
    add('PASS' if active else 'FAIL', 'Complete active Darvas Box exists',
        f'ceiling {float(active["ceiling"]):.4f}; floor {float(active["floor"]):.4f} {currency}'
        if active else 'No active confirmed box at latest completed session')
    ratio = last.VolumeRatio20
    avg = last.PriorAverageVolume20
    ratio_ok = pd.notna(ratio) and float(ratio) >= 1.25
    add('UNVERIFIED' if pd.isna(ratio) else 'PASS' if ratio_ok else 'FAIL',
        'Latest completed-session volume >= 1.25x previous 20-session average',
        f'{float(ratio):.4f}x; volume {int(last.Volume):,}; previous average {float(avg):,.2f}'
        if pd.notna(ratio) else 'Insufficient preceding volume history or zero average')
    if active:
        levels = order_levels(active['ceiling'], active['floor'])
        add('PASS', 'Buy-stop trigger can be calculated',
            f'{levels["buy_stop"]:.4f} {currency} (ceiling {levels["reference"]:.4f} + tick {levels["tick"]:.2f})')
        add('PASS' if levels['protective_stop'] > 0 and levels['protective_stop'] < levels['buy_stop'] else 'FAIL',
            'Standard initial protective stop can be calculated',
            f'{levels["protective_stop"]:.4f} {currency} (BOX_FLOOR: floor {levels["floor"]:.4f} - one tick)')
    else:
        levels = None
        add('NOT EVALUATED', 'Buy-stop trigger can be calculated', 'Requires a complete active box')
        add('NOT EVALUATED', 'Standard initial protective stop can be calculated', 'Requires a complete active box; method BOX_FLOOR')
    add('NOT EVALUATED', 'Opening-gap / exceptional-fill review',
        'Requires a future opening price and executable order details; not a completed-day test')

    # The 0.5% and 20% rules remain mandatory at actual position sizing, not
    # prerequisites for identifying a technical buy-stop candidate.
    ready = bool(active and ratio_ok and levels and levels['protective_stop'] > 0)
    verdict = 'BUY - CONDITIONAL BUY-STOP SETUP READY' if ready else 'WAIT - TECHNICAL SETUP INCOMPLETE'
    reasons = [label for status, label, _ in checks if status in ('FAIL', 'UNVERIFIED')]
    lines += [f'Result: {verdict}', '', 'MANDATORY TECHNICAL CHECKS']
    lines += [f'[{status}] {label}: {detail}' for status,label,detail in checks]
    lines += ['', 'DARVAS BOX DETAILS',
              f'Ceiling candidate: {hi if hi is not None else "none"} {currency}; candidate date: {last.CandidateHighDate}',
              f'Ceiling confirmation: {hc}/3; confirmed date: {active["ceiling_confirmed_date"] if active else (last.Date if last.Event == "CEILING_CONFIRMED" else "see boxes CSV") if ceiling_confirmed else "pending"}',
              f'Floor candidate: {lo if lo is not None else "none"} {currency}; candidate date: {last.CandidateLowDate}',
              f'Floor confirmation: {lc}/3; confirmed date: {active["floor_confirmed_date"] if active else "pending"}',
              f'Latest event: {last.Event}']
    if active:
        lines += [f'Active box ID: {active["id"]}; ceiling {float(active["ceiling"]):.4f}; floor {float(active["floor"]):.4f} {currency}']
    if levels:
        lines += ['', 'CONDITIONAL TRADE PLAN',
                  f'Buy-stop trigger: {levels["buy_stop"]:.4f} {currency}',
                  f'Initial protective stop (original box floor - one tick): {levels["protective_stop"]:.4f} {currency}',
                  '[PASS] Initial stop method: BOX_FLOOR',
                  f'[PASS] Confirmed box floor: {levels["floor"]:.4f} {currency}',
                  f'[PASS] Initial protective stop: {levels["protective_stop"]:.4f} {currency}',
                  'Initial stop is one tick below the ORIGINAL confirmed box floor, not below its ceiling.',
                  '[NOT EVALUATED] Trailing stop method: CONFIRMED_HIGHER_BOX_FLOOR (no open-position ledger)',
                  'Trailing stop rule: after a NEW HIGHER box is fully confirmed, propose its floor minus one tick;',
                  'raise the active stop only if higher; never lower it.',
                  'This is an order setup, not a market BUY or a verified fill.',
                  'Position sizing after a fill: max 0.5% planned equity risk and 20% stock allocation.',
                  'No account-equity argument is required for this technical signal.']
    else:
        lines += ['', 'CONDITIONAL TRADE PLAN', 'Not available: no active confirmed box.',
                  '[NOT EVALUATED] Initial stop method: BOX_FLOOR (no actionable box)',
                  '[NOT EVALUATED] Trailing stop method: CONFIRMED_HIGHER_BOX_FLOOR (no open-position ledger)',
                  'Initial stop is defined relative to the ORIGINAL confirmed box floor, not its ceiling.',
                  'Trailing stop, once a new higher box is fully confirmed, uses that NEW box floor minus one tick.']
    lines += ['', 'DECISION EXPLANATION']
    if ready:
        lines += ['All currently applicable technical entry checks pass.',
                  'BUY means a conditional buy-stop setup is ready, NOT an immediate market purchase.']
    else:
        lines += ['WAIT because: ' + ('; '.join(reasons) if reasons else 'no eligible active setup')]
    lines += ['', 'OPTIONAL MARKET / PRICE CONTEXT - DOES NOT BLOCK BUY']
    lines += research_data.get('lines', [])
    lines += ['[INFO] '+w for w in research_data.get('warnings', [])]
    lines += ['', 'EXTERNAL CONSIDERATIONS - NOT SCRIPT REQUIREMENTS',
              'Market/industry strength, relative performance, earnings and fundamentals: informational only.',
              'Bankruptcy, delisting and trading-halt risk: external manual review only.',
              'These are NOT mandatory technical PASS/FAIL checks.',
              '', 'EXECUTION LIMITATIONS',
              'Volume threshold is based on the latest COMPLETED session, not unknown future breakout-day volume.',
              'Daily OHLCV cannot establish actual intraday fills, stop order sequence, spreads or gap slippage.',
              'One-tick size is assumed, not independently exchange-verified.',
              'Historical all-time-high reference overrides may require longer history and manual assessment.',
              'No automatic order placement, position ledger, or trailing-stop execution.',
              'No fixed profit target; trailing stop rises only after a NEW HIGHER box is fully confirmed.',
              'No pyramiding for the first 30 paper trades.']
    return lines
