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

    def set_all_buyouts(self, amounts=None):
        amounts = amounts or {}
        for item_id in range(1, 13):
            if item_id in amounts:
                amount = amounts[item_id]
            else:
                row = self.svc.db.execute('SELECT i.price, COALESCE(SUM(inv.quantity),0) qty FROM items i LEFT JOIN inventories inv ON inv.event_id=? AND inv.item_id=i.item_id WHERE i.item_id=?', (self.event_id, item_id)).fetchone()
                amount = int(row['price']) * int(row['qty'])
            self.svc.set_buyout(self.event_id, 'admin', item_id, amount)

    def finish_round_without_sales(self, season='겨울'):
        self.svc.close_buying(self.event_id)
        self.set_all_buyouts()
        self.svc.publish_buyouts(self.event_id, 'admin')
        self.svc.set_season(self.event_id, 'admin', season)
        self.svc.start_selling(self.event_id, 'admin', 5)
        self.svc.close_selling(self.event_id)
        self.svc.settle(self.event_id, 'admin')

    def public_item_ids(self):
        rows = self.svc.db.execute('SELECT item_id FROM event_items WHERE event_id=? AND is_public=1 ORDER BY item_id', (self.event_id,)).fetchall()
        return [row['item_id'] for row in rows]

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
        self.set_all_buyouts({1: 300000})
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

    def test_next_round_restarts_buying_and_keeps_balance_without_starting_fund(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1'], 15000)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        self.svc.purchase(self.event_id, 'u1', 1, 1)
        self.svc.close_buying(self.event_id)
        self.set_all_buyouts({1: 30000})
        self.svc.publish_buyouts(self.event_id, 'admin')
        self.svc.set_season(self.event_id, 'admin', '봄')
        self.svc.start_selling(self.event_id, 'admin', 5)
        self.svc.sale_request(self.event_id, 'u1', 1, 1)
        self.svc.close_selling(self.event_id)
        self.svc.settle(self.event_id, 'admin')
        balance_before = self.svc.participant_summary(self.event_id, 'u1')['balance']
        self.assertEqual(balance_before, 42000)

        result = self.svc.next_round(self.event_id, 'admin')

        event = self.svc.db.execute('SELECT status,current_round FROM events WHERE event_id=?', (self.event_id,)).fetchone()
        self.assertEqual(result['new_round'], 2)
        self.assertEqual(event['status'], 'SETTING')
        self.assertEqual(event['current_round'], 2)
        self.assertEqual(self.svc.participant_summary(self.event_id, 'u1')['balance'], 42000)
        self.assertEqual(self.svc.db.execute("SELECT COUNT(*) FROM transactions WHERE type='STARTING_FUND'").fetchone()[0], 1)
        self.svc.start_buying(self.event_id)
        purchased = self.svc.purchase(self.event_id, 'u1', 1, 3)
        self.assertEqual(purchased['qty'], 3)
        self.assertEqual(self.svc.db.execute("SELECT round FROM transactions WHERE type='ITEM_PURCHASE' ORDER BY transaction_id DESC LIMIT 1").fetchone()[0], 2)

    def test_next_round_keeps_all_remaining_inventory_without_expiration(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1'], 50000)
        self.svc.set_item_public(self.event_id, 'admin', [1, 2], True)
        self.svc.start_buying(self.event_id)
        self.svc.purchase(self.event_id, 'u1', 1, 3)
        self.svc.purchase(self.event_id, 'u1', 2, 2)
        balance_before = self.svc.participant_summary(self.event_id, 'u1')['balance']
        self.finish_round_without_sales('겨울')
        result = self.svc.next_round(self.event_id, 'admin')

        remaining = self.svc.db.execute('SELECT COALESCE(SUM(quantity),0) FROM inventories WHERE event_id=?', (self.event_id,)).fetchone()[0]
        self.assertEqual(remaining, 5)
        self.assertEqual(result['inventory_quantity'], 5)
        self.assertEqual(self.svc.db.execute('SELECT quantity FROM inventories WHERE event_id=? AND user_id=? AND item_id=1', (self.event_id, 'u1')).fetchone()[0], 3)
        self.assertEqual(self.svc.db.execute('SELECT quantity FROM inventories WHERE event_id=? AND user_id=? AND item_id=2', (self.event_id, 'u1')).fetchone()[0], 2)
        self.assertEqual(self.svc.participant_summary(self.event_id, 'u1')['balance'], balance_before)
        self.assertEqual(self.svc.db.execute("SELECT COUNT(*) FROM transactions WHERE type='ROUND_ITEM_EXPIRATION'").fetchone()[0], 0)

    def test_next_round_keeps_unsold_remainder_after_partial_sale_and_keeps_profit(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1'], 50000)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        self.svc.purchase(self.event_id, 'u1', 1, 5)
        self.svc.close_buying(self.event_id)
        self.set_all_buyouts({1: 15000})
        self.svc.publish_buyouts(self.event_id, 'admin')
        self.svc.set_season(self.event_id, 'admin', '봄')
        self.svc.start_selling(self.event_id, 'admin', 5)
        self.svc.sale_request(self.event_id, 'u1', 1, 2)
        self.svc.close_selling(self.event_id)
        self.svc.settle(self.event_id, 'admin')
        balance_after_sale = self.svc.participant_summary(self.event_id, 'u1')['balance']
        self.assertEqual(self.svc.db.execute('SELECT quantity FROM inventories WHERE event_id=? AND user_id=? AND item_id=1', (self.event_id, 'u1')).fetchone()[0], 3)

        result = self.svc.next_round(self.event_id, 'admin')

        self.assertEqual(result['inventory_quantity'], 3)
        self.assertEqual(self.svc.db.execute('SELECT quantity FROM inventories WHERE event_id=? AND user_id=? AND item_id=1', (self.event_id, 'u1')).fetchone()[0], 3)
        self.assertEqual(self.svc.participant_summary(self.event_id, 'u1')['balance'], balance_after_sale)
        self.assertEqual(self.svc.db.execute("SELECT COUNT(*) FROM transactions WHERE type='ROUND_ITEM_EXPIRATION'").fetchone()[0], 0)
        self.svc.start_buying(self.event_id)
        self.svc.purchase(self.event_id, 'u1', 1, 2)
        self.assertEqual(self.svc.db.execute('SELECT quantity FROM inventories WHERE event_id=? AND user_id=? AND item_id=1', (self.event_id, 'u1')).fetchone()[0], 5)
        self.assertEqual(self.svc.db.execute("SELECT round FROM transactions WHERE type='ITEM_PURCHASE' ORDER BY transaction_id DESC LIMIT 1").fetchone()[0], 2)

    def test_public_items_persist_and_additional_public_items_accumulate(self):
        self.svc.set_item_public(self.event_id, 'admin', [1, 4, 7, 10], True)
        self.svc.start_buying(self.event_id)
        self.finish_round_without_sales('봄')
        self.svc.next_round(self.event_id, 'admin')
        self.assertEqual(self.public_item_ids(), [1, 4, 7, 10])
        self.assertEqual(self.svc.db.execute('SELECT COALESCE(SUM(quantity),0) FROM inventories WHERE event_id=?', (self.event_id,)).fetchone()[0], 0)

        result = self.svc.set_item_public(self.event_id, 'admin', [1, 2, 5, 8, 11], True)

        self.assertEqual(result['newly_public'], 4)
        self.assertEqual(result['already_public'], 1)
        self.assertEqual(result['total_public'], 8)
        self.assertEqual(self.public_item_ids(), [1, 2, 4, 5, 7, 8, 10, 11])

    def test_private_item_validation_checks_current_inventory_and_current_round_purchase(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1'], 50000)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        with self.assertRaises(ValueError):
            self.svc.set_item_public(self.event_id, 'admin', [1], False)
        self.svc.purchase(self.event_id, 'u1', 1, 1)
        self.svc.close_buying(self.event_id)
        with self.assertRaises(ValueError):
            self.svc.set_item_public(self.event_id, 'admin', [1], False)

    def test_previous_round_records_are_preserved_and_duplicate_next_round_is_blocked(self):
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        self.finish_round_without_sales('겨울')
        buyouts_before = self.svc.db.execute('SELECT COUNT(*) FROM round_buyouts WHERE event_id=? AND round=1', (self.event_id,)).fetchone()[0]
        requests_before = self.svc.db.execute('SELECT COUNT(*) FROM sale_requests WHERE event_id=? AND round=1', (self.event_id,)).fetchone()[0]
        settlements_before = self.svc.db.execute('SELECT COUNT(*) FROM settlements WHERE event_id=? AND round=1', (self.event_id,)).fetchone()[0]
        transactions_before = self.svc.db.execute('SELECT COUNT(*) FROM transactions WHERE event_id=?', (self.event_id,)).fetchone()[0]

        self.svc.next_round(self.event_id, 'admin')
        with self.assertRaises(ValueError):
            self.svc.next_round(self.event_id, 'admin')

        event = self.svc.db.execute('SELECT current_round,status FROM events WHERE event_id=?', (self.event_id,)).fetchone()
        self.assertEqual(event['current_round'], 2)
        self.assertEqual(event['status'], 'SETTING')
        self.assertEqual(self.svc.db.execute('SELECT COUNT(*) FROM round_buyouts WHERE event_id=? AND round=1', (self.event_id,)).fetchone()[0], buyouts_before)
        self.assertEqual(self.svc.db.execute('SELECT COUNT(*) FROM sale_requests WHERE event_id=? AND round=1', (self.event_id,)).fetchone()[0], requests_before)
        self.assertEqual(self.svc.db.execute('SELECT COUNT(*) FROM settlements WHERE event_id=? AND round=1', (self.event_id,)).fetchone()[0], settlements_before)
        self.assertGreaterEqual(self.svc.db.execute('SELECT COUNT(*) FROM transactions WHERE event_id=?', (self.event_id,)).fetchone()[0], transactions_before)

    def test_next_round_transaction_rolls_back_on_failure(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1'], 50000)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        self.svc.purchase(self.event_id, 'u1', 1, 1)
        balance_before = self.svc.participant_summary(self.event_id, 'u1')['balance']
        self.finish_round_without_sales('겨울')
        original_audit = self.svc.audit

        def failing_audit(*args, **kwargs):
            if len(args) >= 4 and args[3] == 'NEXT_ROUND':
                raise RuntimeError('forced rollback')
            return original_audit(*args, **kwargs)

        self.svc.audit = failing_audit
        with self.assertRaises(RuntimeError):
            self.svc.next_round(self.event_id, 'admin')
        self.svc.audit = original_audit

        event = self.svc.db.execute('SELECT current_round,status FROM events WHERE event_id=?', (self.event_id,)).fetchone()
        self.assertEqual(event['current_round'], 1)
        self.assertEqual(event['status'], 'SETTLED')
        self.assertEqual(self.svc.db.execute('SELECT quantity FROM inventories WHERE event_id=? AND user_id=? AND item_id=1', (self.event_id, 'u1')).fetchone()[0], 1)
        self.assertEqual(self.svc.participant_summary(self.event_id, 'u1')['balance'], balance_before)
        self.assertEqual(self.svc.db.execute("SELECT COUNT(*) FROM transactions WHERE type='ROUND_ITEM_EXPIRATION'").fetchone()[0], 0)
        self.assertEqual(self.public_item_ids(), [1])

    def test_tier_buyout_sale_cancel_lookup_and_end_event(self):
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
        info = self.svc.participant_summary(self.event_id, 'u1')
        self.assertIn('balance', info)
        self.svc.end_event(self.event_id, 'admin')
        status = self.svc.db.execute('SELECT status FROM events WHERE event_id=?', (self.event_id,)).fetchone()[0]
        self.assertEqual(status, 'ENDED')


    def test_trade_log_channel_configuration_and_audit(self):
        self.svc.configure_trade_log('guild', self.event_id, 'admin', 'log-channel', True)
        settings = self.svc.trade_log_settings('guild')
        self.assertEqual(settings['trade_log_channel_id'], 'log-channel')
        self.assertEqual(settings['trade_log_enabled'], 1)
        self.svc.configure_trade_log('guild', self.event_id, 'admin', 'log-channel', False)
        settings = self.svc.trade_log_settings('guild')
        self.assertEqual(settings['trade_log_enabled'], 0)
        actions = [row['action'] for row in self.svc.db.execute('SELECT action FROM admin_audit_logs WHERE action LIKE "TRADE_LOG%" ORDER BY log_id').fetchall()]
        self.assertIn('TRADE_LOG_CHANNEL_SET', actions)
        self.assertIn('TRADE_LOG_DISABLED', actions)

    def test_purchase_activity_log_success_and_failure(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1'], 15000)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        result = self.svc.purchase(self.event_id, 'u1', 1, 2)
        self.assertIn('activity_id', result)
        row = self.svc.db.execute("SELECT * FROM trade_activity_logs WHERE action_type='ITEM_PURCHASE'").fetchone()
        self.assertEqual(row['round_number'], 1)
        self.assertEqual(row['item_id'], 1)
        self.assertEqual(row['quantity_after'], 2)
        self.assertEqual(row['unit_price'], 3000)
        self.assertEqual(row['total_amount'], 6000)
        self.assertEqual(row['balance_before'], 15000)
        self.assertEqual(row['balance_after'], 9000)
        self.assertIn('현재 개인 보유량: 2개', self.svc.render_trade_activity_text(row))
        with self.assertRaises(ValueError):
            self.svc.purchase(self.event_id, 'u1', 1, 999)
        self.assertEqual(self.svc.db.execute("SELECT COUNT(*) FROM trade_activity_logs WHERE action_type='ITEM_PURCHASE'").fetchone()[0], 1)

    def test_sale_request_change_and_cancel_activity_logs(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1'], 50000)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        self.svc.purchase(self.event_id, 'u1', 1, 5)
        self.svc.close_buying(self.event_id)
        self.set_all_buyouts({1: 15000})
        self.svc.publish_buyouts(self.event_id, 'admin')
        self.svc.set_season(self.event_id, 'admin', '봄')
        self.svc.start_selling(self.event_id, 'admin', 5)
        self.svc.sale_request(self.event_id, 'u1', 1, 2)
        self.svc.sale_request(self.event_id, 'u1', 1, 3)
        self.svc.cancel_sale_request(self.event_id, 'u1', 1)
        rows = self.svc.db.execute("SELECT * FROM trade_activity_logs WHERE action_type LIKE 'SALE%' ORDER BY id").fetchall()
        self.assertEqual([row['action_type'] for row in rows], ['SALE_REQUEST', 'SALE_REQUEST_CHANGE', 'SALE_REQUEST_CANCEL'])
        self.assertIsNone(rows[0]['quantity_before'])
        self.assertEqual(rows[0]['quantity_after'], 2)
        self.assertEqual(rows[1]['quantity_before'], 2)
        self.assertEqual(rows[1]['quantity_after'], 3)
        self.assertEqual(rows[2]['quantity_before'], 3)
        self.assertEqual(rows[2]['quantity_after'], 0)
        self.assertIn('현재 전체 판매 신청량: 0개', self.svc.render_trade_activity_text(rows[2]))
        with self.assertRaises(ValueError):
            self.svc.cancel_sale_request(self.event_id, 'u1', 1)
        self.assertEqual(self.svc.db.execute("SELECT COUNT(*) FROM trade_activity_logs WHERE action_type='SALE_REQUEST_CANCEL'").fetchone()[0], 1)

    def test_settlement_activity_log_and_delivery_retry_state(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1'], 50000)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        self.svc.purchase(self.event_id, 'u1', 1, 2)
        self.svc.close_buying(self.event_id)
        self.set_all_buyouts({1: 20000})
        self.svc.publish_buyouts(self.event_id, 'admin')
        self.svc.set_season(self.event_id, 'admin', '봄')
        self.svc.start_selling(self.event_id, 'admin', 5)
        self.svc.sale_request(self.event_id, 'u1', 1, 2)
        self.svc.close_selling(self.event_id)
        self.svc.settle(self.event_id, 'admin')
        row = self.svc.db.execute("SELECT * FROM trade_activity_logs WHERE action_type='SETTLEMENT'").fetchone()
        self.assertEqual(row['round_number'], 1)
        self.assertEqual(row['total_amount'], 20000)
        self.assertIn('정산 완료', self.svc.render_trade_activity_text(row))
        pending = self.svc.pending_trade_activity_rows('guild')
        self.assertTrue(any(p['id'] == row['id'] for p in pending))
        self.svc.mark_trade_activity_delivered(row['id'], 'discord-message-id')
        delivered = self.svc.db.execute('SELECT delivered_at,discord_message_id FROM trade_activity_logs WHERE id=?', (row['id'],)).fetchone()
        self.assertIsNotNone(delivered['delivered_at'])
        self.assertEqual(delivered['discord_message_id'], 'discord-message-id')
        self.assertNotIn(row['id'], [p['id'] for p in self.svc.pending_trade_activity_rows('guild')])

    def test_admin_lookup_status_rows_for_purchase_and_sale(self):
        self.svc.grant_starting_fund(self.event_id, 'admin', ['u1'], 50000)
        self.svc.set_item_public(self.event_id, 'admin', [1], True)
        self.svc.start_buying(self.event_id)
        self.svc.purchase(self.event_id, 'u1', 1, 2)
        self.svc.close_buying(self.event_id)
        purchase_row = [row for row in self.svc.purchase_status_rows(self.event_id) if row['item_id'] == 1][0]
        self.assertEqual(purchase_row['purchased_quantity'], 2)
        self.assertEqual(purchase_row['buyer_count'], 1)
        self.set_all_buyouts({1: 6000})
        self.svc.publish_buyouts(self.event_id, 'admin')
        self.svc.set_season(self.event_id, 'admin', '봄')
        self.svc.start_selling(self.event_id, 'admin', 5)
        self.svc.sale_request(self.event_id, 'u1', 1, 1)
        sale_row = [row for row in self.svc.sale_status_rows(self.event_id) if row['item_id'] == 1][0]
        self.assertEqual(sale_row['total_requested'], 1)
        self.assertEqual(sale_row['request_users'], 1)

    def test_sale_unit_price_floor(self):
        self.assertEqual(sale_unit_price(39500, 3), 13000)
        self.assertEqual(sale_unit_price(9999, 1), 9000)
        self.assertEqual(sale_unit_price(10000, 0), 0)


if __name__ == '__main__':
    unittest.main()
