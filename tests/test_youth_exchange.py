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


    def test_event_items_are_event_scoped_and_private_by_default(self):
        second = self.svc.create_event('guild-2', '두번째', 'channel')
        public_count = self.svc.db.execute('SELECT COUNT(*) FROM event_items WHERE event_id=? AND is_public=1', (second,)).fetchone()[0]
        self.assertEqual(public_count, 0)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        first_public = self.svc.db.execute('SELECT is_public FROM event_items WHERE event_id=? AND item_id=1', (self.event_id,)).fetchone()[0]
        second_public = self.svc.db.execute('SELECT is_public FROM event_items WHERE event_id=? AND item_id=1', (second,)).fetchone()[0]
        self.assertEqual(first_public, 1)
        self.assertEqual(second_public, 0)

    def test_tier_buyout_sale_cancel_lookup_next_round_and_end(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1'], 50000)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        self.svc.purchase(self.event_id, 'u1', 1, 1)
        self.svc.close_buying(self.event_id)
        self.svc.set_tier_buyout(self.event_id, 'admin', '저가', 3000)
        self.svc.set_tier_buyout(self.event_id, 'admin', '중가', 0)
        self.svc.set_tier_buyout(self.event_id, 'admin', '고가', 0)
        self.svc.publish_buyouts(self.event_id, 'admin')
        self.svc.set_season(self.event_id, 'admin', '봄')
        self.svc.start_selling(self.event_id, 'admin', 5)
        self.svc.sale_request(self.event_id, 'u1', 1, 1)
        self.svc.cancel_sale_request(self.event_id, 'u1', 1)
        self.assertEqual(self.svc.my_sale_requests(self.event_id, 'u1')[0]['status'], 'CANCELLED')
        self.svc.sale_request(self.event_id, 'u1', 1, 1)
        self.svc.close_selling(self.event_id)
        self.svc.settle(self.event_id, 'admin')
        self.assertEqual(self.svc.next_round(self.event_id, 'admin'), 2)
        info = self.svc.participant_summary(self.event_id, 'u1')
        self.assertIn('balance', info)
        self.svc.end_event(self.event_id, 'admin')
        status = self.svc.db.execute('SELECT status FROM events WHERE event_id=?', (self.event_id,)).fetchone()[0]
        self.assertEqual(status, 'ENDED')

    def test_sale_unit_price_floor(self):
        self.assertEqual(sale_unit_price(39500, 3), 13000)
        self.assertEqual(sale_unit_price(9999, 1), 9000)
        self.assertEqual(sale_unit_price(10000, 0), 0)


if __name__ == '__main__':
    unittest.main()
