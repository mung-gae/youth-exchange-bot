import tempfile
import unittest
from pathlib import Path

from youth_exchange import YouthExchangeService, sale_unit_price


class YouthExchangeServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / 'test.db')
        self.svc = YouthExchangeService(self.db_path)
        self.event_id = self.svc.create_event('guild', '테스트', 'channel')
        self.svc.add_participant(self.event_id, 'u1')
        self.svc.add_participant(self.event_id, 'u2')

    def tearDown(self):
        self.svc.close()
        self.tmp.cleanup()

    def test_starting_fund_duplicate_rules_and_admin_grant(self):
        result = self.svc.grant_starting_fund(self.event_id, 'admin', ['u1', 'u2'], 15000)
        self.assertEqual(result['paid'], 2)
        duplicate = self.svc.grant_starting_fund(self.event_id, 'admin', ['u1', 'u2'], 15000)
        self.assertEqual(duplicate['skipped'], 2)
        grant = self.svc.grant_admin_fund(self.event_id, 'admin', 'u1', 5000, '보너스')
        self.assertEqual(grant['after'], 20000)
        tx_count = self.svc.db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        self.assertEqual(tx_count, 3)

    def test_purchase_buyout_sale_and_settlement(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1', 'u2'], 50000)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        bought = self.svc.purchase(self.event_id, 'u1', 1, 2)
        self.assertEqual(bought['balance'], 44000)
        self.svc.purchase(self.event_id, 'u2', 1, 1)
        with self.assertRaises(ValueError):
            self.svc.purchase(self.event_id, 'u1', 2, 1)
        self.svc.close_buying(self.event_id)
        for item_id in range(1, 13):
            self.svc.set_buyout(self.event_id, 'admin', item_id, 300000 if item_id == 1 else 0)
        self.svc.publish_buyouts(self.event_id, 'admin')
        self.svc.set_season(self.event_id, 'admin', '봄')
        self.svc.start_selling(self.event_id, 'admin', 5)
        self.svc.sale_request(self.event_id, 'u1', 1, 2)
        self.svc.sale_request(self.event_id, 'u2', 1, 1)
        with self.assertRaises(ValueError):
            self.svc.sale_request(self.event_id, 'u1', 4, 1)
        self.svc.close_selling(self.event_id)
        preview = [r for r in self.svc.preview_settlement(self.event_id) if r['item_id'] == 1][0]
        self.assertEqual(preview['unit_price'], 100000)
        self.svc.settle(self.event_id, 'admin')
        balance = self.svc.db.execute('SELECT balance FROM participants WHERE user_id=?', ('u1',)).fetchone()[0]
        self.assertEqual(balance, 244000)
        with self.assertRaises(ValueError):
            self.svc.settle(self.event_id, 'admin')

    def test_sale_unit_price_floor(self):
        self.assertEqual(sale_unit_price(39500, 3), 13000)
        self.assertEqual(sale_unit_price(9999, 1), 9000)
        self.assertEqual(sale_unit_price(10000, 0), 0)


if __name__ == '__main__':
    unittest.main()
