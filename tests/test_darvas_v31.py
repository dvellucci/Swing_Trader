import unittest
import pandas as pd
from strategies.darvas.darvas import scan, order_levels, position_size, report


def fixture(highs, lows=None):
    lows = lows or [x-3 for x in highs]
    idx = pd.date_range('2026-01-02', periods=len(highs), freq='B')
    return pd.DataFrame({'Open':[(h+l)/2 for h,l in zip(highs,lows)],
                         'High':highs,'Low':lows,
                         'Close':[(h+l)/2 for h,l in zip(highs,lows)],
                         'Volume':[1000000]*len(highs)}, index=idx)

class TestDarvas(unittest.TestCase):
    def test_three_following_sessions_and_no_early_signal(self):
        highs=[110,109,108,107,106,105,104,103,102,101,100,111]
        lows= [100,101,102,103,99,100,101,102,103,104,105,106]
        ev,active=scan(fixture(highs,lows))
        self.assertEqual(ev.iloc[3].Event,'CEILING_CONFIRMED')
        self.assertEqual(ev.iloc[7].Event,'BOX_CONFIRMED')
        self.assertEqual(ev.iloc[7].BuyStop,110.01)
        self.assertEqual(ev.iloc[11].Event,'BUY_STOP_TOUCHED_UNVERIFIED_FILL')
        self.assertIsNone(active)
    def test_equal_high_resets_confirmation(self):
        ev,_=scan(fixture([100,99,100,99,98,97]))
        self.assertEqual(ev.iloc[2].Event,'HIGH_CANDIDATE')
        self.assertEqual(ev.iloc[5].Event,'CEILING_CONFIRMED')
    def test_both_boundaries_are_ambiguous(self):
        highs=[110,109,108,107,106,105,104,103,112]
        lows=[100,101,102,103,99,100,101,102,98]
        ev,_=scan(fixture(highs,lows))
        self.assertEqual(ev.iloc[-1].Event,'BOTH_BOUNDARIES_TOUCHED_REVIEW')
    def test_no_volume_threshold(self):
        highs=[110,109,108,107,106,105,104,103]
        lows=[100,101,102,103,99,100,101,102]
        ev,active=scan(fixture(highs,lows))
        self.assertIsNotNone(active)
        self.assertEqual(ev.iloc[-1].Event,'BOX_CONFIRMED')
    def test_volume_is_mandatory_for_buy(self):
        highs=[110,109,108,107,106,105,104,103]+[105]*20
        lows=[100,101,102,103,99,100,101,102]+[102]*20
        data=fixture(highs,lows)
        ev,active=scan(data)
        text='\n'.join(report(data,ev,active,'USD'))
        self.assertIn('WAIT - TECHNICAL SETUP INCOMPLETE',text)
        self.assertIn('[FAIL] Latest completed-session volume >= 1.25x',text)
        data.loc[data.index[-1],'Volume']=1500000
        ev,active=scan(data)
        text='\n'.join(report(data,ev,active,'USD'))
        self.assertIn('BUY - CONDITIONAL BUY-STOP SETUP',text)
        self.assertIn('[PASS] Latest completed-session volume >= 1.25x',text)
        self.assertIn('[PASS] Complete active Darvas Box exists',text)
    def test_incomplete_box_checklist(self):
        data=fixture([110,109,108,107,106,105])
        ev,active=scan(data)
        text='\n'.join(report(data,ev,active,'USD'))
        self.assertIn('[PASS] Ceiling confirmed',text)
        self.assertIn('[FAIL] Floor confirmed',text)
        self.assertIn('[FAIL] Complete active Darvas Box exists',text)
        self.assertIn('[NOT EVALUATED] Buy-stop trigger',text)
        self.assertIn('WAIT - TECHNICAL SETUP INCOMPLETE',text)

    def test_stop_method_reporting(self):
        highs=[110,109,108,107,106,105,104,103]+[105]*20
        lows=[100,101,102,103,99,100,101,102]+[102]*20
        data=fixture(highs,lows)
        data.loc[data.index[-1],'Volume']=1500000
        events, active=scan(data)
        text='\n'.join(report(data,events,active,'USD'))
        self.assertIn('[PASS] Initial stop method: BOX_FLOOR',text)
        self.assertIn('below the ORIGINAL confirmed box floor',text)
        self.assertIn('[NOT EVALUATED] Trailing stop method: CONFIRMED_HIGHER_BOX_FLOOR',text)
        self.assertIn('Initial protective stop: 98.9900 USD',text)

    def test_order_and_sizing(self):
        lv=order_levels(100,94)
        self.assertEqual(lv['buy_stop'],100.01)
        self.assertEqual(lv['protective_stop'],93.99)
        self.assertEqual(position_size(20000,100.01,93.99)['shares'],16)
    def test_no_future_lookahead(self):
        data=fixture([110,109,108,107,106,105,104,103,102])
        full,_=scan(data)
        for n in range(1,len(data)+1):
            part,_=scan(data.iloc[:n])
            self.assertEqual(full.iloc[n-1].Event,part.iloc[-1].Event)

if __name__=='__main__': unittest.main()
