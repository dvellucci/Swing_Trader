import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from portfolio.repository import PortfolioRepository

class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.repo=PortfolioRepository(Path(self.temp.name)/'positions.sqlite3')
    def tearDown(self):
        self.temp.cleanup()
    def create(self):
        return self.repo.add('amzn','Darvas 3.1','2026-10-20','3','267.57','244.29','USD')
    def test_persist_and_pl(self):
        i=self.create()
        other=PortfolioRepository(self.repo.path)
        p=other.get(i)
        self.assertEqual(p.ticker,'AMZN')
        self.assertEqual(p.initial_risk,Decimal('69.84'))
        other.update_price(i,'280','2026-10-20')
        self.assertEqual(other.get(i).unrealized_pl,Decimal('37.29'))
    def test_stop_never_lowered(self):
        i=self.create()
        self.repo.raise_stop(i,'260')
        with self.assertRaises(ValueError): self.repo.raise_stop(i,'250')
        with self.assertRaises(ValueError): self.repo.update_details(i,'AMZN','Darvas 3.1','2026-10-20','3','267.57','260','USD')
        self.assertEqual(self.repo.get(i).current_stop,Decimal('260'))
        self.assertEqual(self.repo.get(i).initial_stop,Decimal('244.29'))
    def test_close_and_history(self):
        i=self.create()
        self.repo.close(i,'2026-10-22','290')
        self.assertFalse(self.repo.list_positions())
        p=self.repo.list_positions(True)[0]
        self.assertEqual(p.realized_pl,Decimal('67.29'))
        with self.assertRaises(ValueError): self.repo.raise_stop(i,'270')
    def test_reject_invalid(self):
        for qty in ['0','-1','nan']:
            with self.assertRaises(ValueError): self.repo.add('AMZN','Darvas 3.1','2026-10-20',qty,'267','244','USD')
        with self.assertRaises(ValueError): self.repo.add('AMZN','Darvas 3.1','2026-10-20','1','200','250','USD')
    def test_delete(self):
        i=self.create()
        self.repo.delete(i)
        self.assertEqual(self.repo.list_positions(True),[])
