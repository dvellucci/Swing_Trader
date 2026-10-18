import tempfile
import time
import unittest
from pathlib import Path
from trading_gui.analysis import normalize_ticker, parse_verdict, find_new_report
from trading_gui.config import discover_script

class AnalysisTests(unittest.TestCase):
    def test_ticker(self):
        self.assertEqual(normalize_ticker(' dol.to '), 'DOL.TO')
        with self.assertRaises(ValueError):
            normalize_ticker('NVDA; echo bad')

    def test_verdict(self):
        self.assertEqual(parse_verdict('Result: WAIT - developing box\n'), 'WAIT - developing box')
        self.assertIsNone(parse_verdict('No result yet'))

    def test_report_is_new(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'screener.py'
            script.touch()
            output = Path(folder) / 'output'
            output.mkdir()
            report = output / 'COST_report.txt'
            report.write_text('Result: WAIT')
            self.assertIsNone(find_new_report(script, 'COST', time.time() + 100))
            self.assertEqual(find_new_report(script, 'COST', time.time()), report)

    def test_discover_saved_script(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'screener.py'
            script.touch()
            self.assertEqual(discover_script(str(script)), script.resolve())

if __name__ == '__main__':
    unittest.main()
