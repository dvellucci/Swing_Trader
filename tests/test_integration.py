import unittest
from trading_gui.strategy_registry import BY_LABEL
from trading_gui.analysis import normalize_ticker

class IntegrationTests(unittest.TestCase):
    def test_bundled_darvas_exists(self):
        self.assertTrue(BY_LABEL['Darvas 3.1'].script.is_file())
    def test_ticker_rules_match_darvas(self):
        from strategies.darvas.screener import ticker_arg
        for ticker in ['NVDA','DOL.TO','BBD-B.TO','BRK-B']:
            self.assertEqual(normalize_ticker(ticker), ticker_arg(ticker))
        for ticker in ['BAD.X','NVDA;ECHO']:
            with self.assertRaises(ValueError): normalize_ticker(ticker)

    def test_ui_does_not_reference_undefined_detected(self):
        import ast
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / 'trading_gui' / 'ui.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        build = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == '_build_ui')
        names = {node.id for node in ast.walk(build) if isinstance(node, ast.Name)}
        self.assertNotIn('detected', names)
