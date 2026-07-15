from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Literal

KST = timezone(timedelta(hours=9))
Status = Literal['SETTING','BUYING','BUYING_CLOSED','BUYOUT_SETTING','BUYOUT_PUBLISHED','SEASON_SELECTED','SELLING','SELLING_CLOSED','SETTLED','ENDED']
Season = Literal['봄','여름','가을','겨울']

FIXED_ITEMS = [
    ('마스크','봄',3000,'저가'),('화분','봄',6000,'중가'),('원피스','봄',10000,'고가'),
    ('선풍기','여름',3000,'저가'),('튜브','여름',6000,'중가'),('수영복','여름',10000,'고가'),
    ('책','가을',3000,'저가'),('머플러','가을',6000,'중가'),('트렌치 코트','가을',10000,'고가'),
    ('핫팩','겨울',3000,'저가'),('목도리','겨울',6000,'중가'),('패딩','겨울',10000,'고가'),
]
SEASONS = {'봄','여름','가을','겨울'}
TIERS = {'저가','중가','고가'}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_won(amount: int) -> str:
    return f"{amount:,}원"


def assert_int(value: int, label: str, minimum: int = 1) -> None:
    if not isinstance(value, int) or value < minimum:
        raise ValueError(f'{label}은 {minimum} 이상의 정수여야 합니다.')


def sale_unit_price(buyout: int, total_qty: int) -> int:
    if total_qty <= 0:
        return 0
    return (buyout // total_qty // 1000) * 1000


@dataclass
class Event:
    event_id: int
    guild_id: str
    name: str
    status: str
    current_round: int
    starting_fund: int
    channel_id: str | None
    participant_role_id: str | None
    selected_season: str | None
    sale_start_at: str | None
    sale_end_at: str | None


class YouthExchangeService:
    def __init__(self, db_path: str = './data/youth-exchange.db') -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys = ON')
        self.migrate()
        self.seed_items()

    def close(self) -> None:
        self.db.close()

    def migrate(self) -> None:
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS events(
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id TEXT NOT NULL,
          name TEXT NOT NULL,
          status TEXT NOT NULL,
          current_round INTEGER NOT NULL DEFAULT 1,
          starting_fund INTEGER NOT NULL DEFAULT 15000 CHECK(starting_fund >= 1),
          channel_id TEXT,
          participant_role_id TEXT,
          selected_season TEXT,
          sale_start_at TEXT,
          sale_end_at TEXT,
          created_at TEXT NOT NULL,
          ended_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_active_event ON events(guild_id) WHERE status != 'ENDED';
        CREATE TABLE IF NOT EXISTS guild_settings(
          guild_id TEXT PRIMARY KEY,
          trade_log_channel_id TEXT,
          trade_log_enabled INTEGER NOT NULL DEFAULT 0 CHECK(trade_log_enabled IN (0,1)),
          updated_by TEXT,
          updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS participants(
          event_id INTEGER NOT NULL,
          user_id TEXT NOT NULL,
          balance INTEGER NOT NULL DEFAULT 0 CHECK(balance >= 0),
          starting_fund_paid INTEGER NOT NULL DEFAULT 0 CHECK(starting_fund_paid IN (0,1)),
          status TEXT NOT NULL DEFAULT 'ACTIVE',
          registered_at TEXT NOT NULL,
          PRIMARY KEY(event_id,user_id),
          FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS items(
          item_id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          season TEXT NOT NULL,
          price INTEGER NOT NULL CHECK(price >= 0),
          price_tier TEXT NOT NULL,
          is_public INTEGER NOT NULL DEFAULT 0 CHECK(is_public IN (0,1))
        );
        CREATE TABLE IF NOT EXISTS event_items(
          event_id INTEGER NOT NULL,
          item_id INTEGER NOT NULL,
          is_public INTEGER NOT NULL DEFAULT 0 CHECK(is_public IN (0,1)),
          PRIMARY KEY(event_id,item_id),
          FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE,
          FOREIGN KEY(item_id) REFERENCES items(item_id)
        );
        CREATE TABLE IF NOT EXISTS inventories(
          event_id INTEGER NOT NULL,
          user_id TEXT NOT NULL,
          item_id INTEGER NOT NULL,
          quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
          PRIMARY KEY(event_id,user_id,item_id)
        );
        CREATE TABLE IF NOT EXISTS round_buyouts(
          event_id INTEGER NOT NULL,
          round INTEGER NOT NULL,
          item_id INTEGER NOT NULL,
          buyout_amount INTEGER NOT NULL CHECK(buyout_amount >= 0),
          is_public INTEGER NOT NULL DEFAULT 0,
          source TEXT NOT NULL DEFAULT 'ITEM',
          PRIMARY KEY(event_id,round,item_id)
        );
        CREATE TABLE IF NOT EXISTS sale_requests(
          event_id INTEGER NOT NULL,
          round INTEGER NOT NULL,
          user_id TEXT NOT NULL,
          item_id INTEGER NOT NULL,
          quantity INTEGER NOT NULL CHECK(quantity >= 0),
          status TEXT NOT NULL,
          settled INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(event_id,round,user_id,item_id)
        );
        CREATE TABLE IF NOT EXISTS settlements(
          event_id INTEGER NOT NULL,
          round INTEGER NOT NULL,
          item_id INTEGER NOT NULL,
          total_quantity INTEGER NOT NULL,
          unit_price INTEGER NOT NULL,
          total_paid INTEGER NOT NULL,
          unused_buyout INTEGER NOT NULL,
          settled_at TEXT NOT NULL,
          PRIMARY KEY(event_id,round,item_id)
        );
        CREATE TABLE IF NOT EXISTS transactions(
          transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id TEXT,
          event_id INTEGER NOT NULL,
          round INTEGER NOT NULL,
          user_id TEXT NOT NULL,
          item_id INTEGER,
          type TEXT NOT NULL,
          quantity INTEGER NOT NULL DEFAULT 0,
          amount INTEGER NOT NULL DEFAULT 0,
          reason TEXT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trade_activity_logs(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id TEXT NOT NULL,
          event_id INTEGER NOT NULL,
          round_number INTEGER NOT NULL,
          user_id TEXT,
          action_type TEXT NOT NULL,
          item_id INTEGER,
          quantity_before INTEGER,
          quantity_after INTEGER,
          unit_price INTEGER,
          total_amount INTEGER,
          balance_before INTEGER,
          balance_after INTEGER,
          metadata_json TEXT,
          created_at TEXT NOT NULL,
          delivered_at TEXT,
          discord_message_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_trade_activity_event_round ON trade_activity_logs(event_id,round_number,action_type);
        CREATE INDEX IF NOT EXISTS idx_trade_activity_delivery ON trade_activity_logs(guild_id,delivered_at,id);
        CREATE TABLE IF NOT EXISTS admin_audit_logs(
          log_id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_id INTEGER,
          round INTEGER,
          admin_id TEXT NOT NULL,
          action TEXT NOT NULL,
          target_user_id TEXT,
          before_value TEXT,
          after_value TEXT,
          reason TEXT,
          created_at TEXT NOT NULL
        );
        ''')
        transaction_columns = {row['name'] for row in self.db.execute('PRAGMA table_info(transactions)').fetchall()}
        if 'guild_id' not in transaction_columns:
            self.db.execute('ALTER TABLE transactions ADD COLUMN guild_id TEXT')
        guild_setting_columns = {row['name'] for row in self.db.execute('PRAGMA table_info(guild_settings)').fetchall()}
        for column, ddl in {
            'trade_log_channel_id': 'ALTER TABLE guild_settings ADD COLUMN trade_log_channel_id TEXT',
            'trade_log_enabled': 'ALTER TABLE guild_settings ADD COLUMN trade_log_enabled INTEGER NOT NULL DEFAULT 0 CHECK(trade_log_enabled IN (0,1))',
            'updated_by': 'ALTER TABLE guild_settings ADD COLUMN updated_by TEXT',
            'updated_at': 'ALTER TABLE guild_settings ADD COLUMN updated_at TEXT',
        }.items():
            if column not in guild_setting_columns:
                self.db.execute(ddl)
        self.db.execute('''INSERT OR IGNORE INTO event_items(event_id,item_id,is_public)
            SELECT e.event_id, i.item_id, COALESCE(i.is_public,0)
            FROM events e CROSS JOIN items i''')
        self.db.commit()

    def seed_items(self) -> None:
        self.db.executemany(
            'INSERT OR IGNORE INTO items(name,season,price,price_tier,is_public) VALUES(?,?,?,?,0)',
            FIXED_ITEMS,
        )
        self.db.commit()

    def active_event(self, guild_id: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM events WHERE guild_id=? AND status!='ENDED'", (guild_id,)).fetchone()
        if not row:
            raise ValueError('활성 청춘거래소 이벤트가 없습니다.')
        return row

    def create_event(self, guild_id: str, name: str, channel_id: str, role_id: str | None = None, starting_fund: int = 15000) -> int:
        assert_int(starting_fund, '기본금')
        cur = self.db.execute(
            'INSERT INTO events(guild_id,name,status,current_round,starting_fund,channel_id,participant_role_id,created_at) VALUES(?,?,?,?,?,?,?,?)',
            (guild_id, name, 'SETTING', 1, starting_fund, channel_id, role_id, now_iso()),
        )
        event_id = int(cur.lastrowid)
        self.db.execute('INSERT OR IGNORE INTO event_items(event_id,item_id,is_public) SELECT ?, item_id, 0 FROM items', (event_id,))
        self.db.commit()
        return event_id

    def add_participant(self, event_id: int, user_id: str) -> None:
        self.db.execute(
            'INSERT OR IGNORE INTO participants(event_id,user_id,balance,starting_fund_paid,status,registered_at) VALUES(?,?,0,0,?,?)',
            (event_id, user_id, 'ACTIVE', now_iso()),
        )
        self.db.commit()

    def grant_starting_fund(self, event_id: int, admin_id: str, users: Iterable[str], amount: int, allow_duplicate: bool = False) -> dict[str, int]:
        assert_int(amount, '지급 금액')
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        if event['status'] == 'ENDED':
            raise ValueError('종료된 이벤트에서는 지급할 수 없습니다.')
        paid = skipped = 0
        with self.db:
            for user_id in users:
                self.db.execute('INSERT OR IGNORE INTO participants(event_id,user_id,balance,starting_fund_paid,status,registered_at) VALUES(?,?,0,0,?,?)', (event_id, user_id, 'ACTIVE', now_iso()))
                p = self.db.execute('SELECT * FROM participants WHERE event_id=? AND user_id=?', (event_id, user_id)).fetchone()
                if p['starting_fund_paid'] and not allow_duplicate:
                    skipped += 1
                    continue
                self.db.execute('UPDATE participants SET balance=balance+?, starting_fund_paid=1 WHERE event_id=? AND user_id=?', (amount, event_id, user_id))
                self.db.execute('INSERT INTO transactions(event_id,round,user_id,type,amount,reason,created_at) VALUES(?,?,?,?,?,?,?)', (event_id, event['current_round'], user_id, 'STARTING_FUND', amount, '기본금 지급', now_iso()))
                paid += 1
            self.audit(event_id, event['current_round'], admin_id, 'STARTING_FUND', after=f'paid={paid},amount={amount}')
            self.record_trade_activity(event, 'STARTING_FUND', unit_price=amount, total_amount=paid * amount, metadata={'admin_id': admin_id, 'paid': paid, 'skipped': skipped})
        return {'paid': paid, 'skipped': skipped, 'amount': amount, 'total': paid * amount}

    def grant_admin_fund(self, event_id: int, admin_id: str, user_id: str, amount: int, reason: str) -> dict[str, int]:
        assert_int(amount, '지급 금액')
        if not reason.strip():
            raise ValueError('지급 사유는 필수입니다.')
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        if event['status'] == 'ENDED':
            raise ValueError('종료된 이벤트에서는 지급할 수 없습니다.')
        p = self.db.execute('SELECT * FROM participants WHERE event_id=? AND user_id=?', (event_id, user_id)).fetchone()
        if not p:
            raise ValueError('대상은 현재 이벤트 참가자여야 합니다.')
        before = int(p['balance'])
        after = before + amount
        with self.db:
            self.db.execute('UPDATE participants SET balance=? WHERE event_id=? AND user_id=?', (after, event_id, user_id))
            self.db.execute('INSERT INTO transactions(event_id,round,user_id,type,amount,reason,created_at) VALUES(?,?,?,?,?,?,?)', (event_id, event['current_round'], user_id, 'ADMIN_FUND_GRANT', amount, reason, now_iso()))
            self.audit(event_id, event['current_round'], admin_id, 'ADMIN_FUND_GRANT', target_user_id=user_id, before=str(before), after=str(after), reason=reason)
            self.record_trade_activity(event, 'ADMIN_FUND_GRANT', user_id=user_id, total_amount=amount, balance_before=before, balance_after=after, metadata={'admin_id': admin_id, 'reason': reason})
        return {'before': before, 'after': after, 'amount': amount}

    def audit(self, event_id: int, round_no: int, admin_id: str, action: str, target_user_id: str | None = None, before: str | None = None, after: str | None = None, reason: str | None = None) -> None:
        self.db.execute('INSERT INTO admin_audit_logs(event_id,round,admin_id,action,target_user_id,before_value,after_value,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)', (event_id, round_no, admin_id, action, target_user_id, before, after, reason, now_iso()))


    def configure_trade_log(self, guild_id: str, event_id: int, admin_id: str, channel_id: str, enabled: bool = True) -> None:
        previous = self.db.execute('SELECT * FROM guild_settings WHERE guild_id=?', (guild_id,)).fetchone()
        before_channel = previous['trade_log_channel_id'] if previous else None
        before_enabled = previous['trade_log_enabled'] if previous else 0
        with self.db:
            self.db.execute(
                'INSERT INTO guild_settings(guild_id,trade_log_channel_id,trade_log_enabled,updated_by,updated_at) VALUES(?,?,?,?,?) '
                'ON CONFLICT(guild_id) DO UPDATE SET trade_log_channel_id=excluded.trade_log_channel_id, trade_log_enabled=excluded.trade_log_enabled, updated_by=excluded.updated_by, updated_at=excluded.updated_at',
                (guild_id, channel_id, 1 if enabled else 0, admin_id, now_iso()),
            )
            action = 'TRADE_LOG_ENABLED' if enabled and before_channel == channel_id else 'TRADE_LOG_CHANNEL_SET' if enabled else 'TRADE_LOG_DISABLED'
            self.audit(event_id, self.db.execute('SELECT current_round FROM events WHERE event_id=?', (event_id,)).fetchone()[0], admin_id, action, before=f'{before_channel}:{before_enabled}', after=f'{channel_id}:{1 if enabled else 0}')

    def trade_log_settings(self, guild_id: str) -> sqlite3.Row | None:
        return self.db.execute('SELECT * FROM guild_settings WHERE guild_id=?', (guild_id,)).fetchone()

    def record_trade_activity(
        self,
        event: sqlite3.Row,
        action_type: str,
        user_id: str | None = None,
        item_id: int | None = None,
        quantity_before: int | None = None,
        quantity_after: int | None = None,
        unit_price: int | None = None,
        total_amount: int | None = None,
        balance_before: int | None = None,
        balance_after: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> int:
        cur = self.db.execute(
            'INSERT INTO trade_activity_logs(guild_id,event_id,round_number,user_id,action_type,item_id,quantity_before,quantity_after,unit_price,total_amount,balance_before,balance_after,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (
                event['guild_id'],
                event['event_id'],
                event['current_round'],
                user_id,
                action_type,
                item_id,
                quantity_before,
                quantity_after,
                unit_price,
                total_amount,
                balance_before,
                balance_after,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                now_iso(),
            ),
        )
        return int(cur.lastrowid)

    def trade_activity_rows(self, event_id: int, action_type: str | None = None, limit: int = 20, user_id: str | None = None, item_id: int | None = None, round_number: int | None = None) -> list[sqlite3.Row]:
        limit = max(1, min(int(limit), 100))
        clauses = ['event_id=?']
        params: list[object] = [event_id]
        if action_type and action_type != '전체':
            clauses.append('action_type=?')
            params.append(action_type)
        if user_id:
            clauses.append('user_id=?')
            params.append(user_id)
        if item_id is not None:
            clauses.append('item_id=?')
            params.append(item_id)
        if round_number is not None:
            clauses.append('round_number=?')
            params.append(round_number)
        params.append(limit)
        return self.db.execute(f"SELECT * FROM trade_activity_logs WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT ?", params).fetchall()

    def pending_trade_activity_rows(self, guild_id: str, limit: int = 100) -> list[sqlite3.Row]:
        return self.db.execute('SELECT * FROM trade_activity_logs WHERE guild_id=? AND delivered_at IS NULL ORDER BY id DESC LIMIT ?', (guild_id, min(limit, 100))).fetchall()

    def mark_trade_activity_delivered(self, activity_id: int, message_id: str) -> None:
        self.db.execute('UPDATE trade_activity_logs SET delivered_at=?, discord_message_id=? WHERE id=? AND delivered_at IS NULL', (now_iso(), message_id, activity_id))
        self.db.commit()

    def render_trade_activity_text(self, row: sqlite3.Row) -> str:
        meta = json.loads(row['metadata_json'] or '{}')
        action = row['action_type']
        created = datetime.fromisoformat(row['created_at']).astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')
        user = f"<@{row['user_id']}>" if row['user_id'] else '대상 없음'
        if action == 'ITEM_PURCHASE':
            return (
                f"🛒 아이템 구매\n\n이벤트: {meta.get('event_name')}\n참가자: {meta.get('display_name', row['user_id'])}\n유저: {user}\n유저 ID: {row['user_id']}\n라운드: {row['round_number']}라운드\n\n"
                f"아이템: {meta.get('item_name')}\n계절: {meta.get('season')}\n아이템 ID: {row['item_id']}\n구매 수량: {row['quantity_after']}개\n개당 가격: {format_won(int(row['unit_price'] or 0))}\n총 구매 금액: {format_won(int(row['total_amount'] or 0))}\n\n"
                f"구매 전 잔액: {format_won(int(row['balance_before'] or 0))}\n구매 후 잔액: {format_won(int(row['balance_after'] or 0))}\n\n현재 개인 보유량: {meta.get('user_inventory')}개\n현재 전체 보유량: {meta.get('total_inventory')}개\n처리 시각: {created}"
            )
        if action in {'SALE_REQUEST', 'SALE_REQUEST_CHANGE', 'SALE_REQUEST_CANCEL'}:
            title = {'SALE_REQUEST': '📤 판매 신청', 'SALE_REQUEST_CHANGE': '✏️ 판매 신청 변경', 'SALE_REQUEST_CANCEL': '❌ 판매 신청 취소'}[action]
            before = '' if row['quantity_before'] is None else f"변경 전 수량: {row['quantity_before']}개\n"
            return (
                f"{title}\n\n참가자: {meta.get('display_name', row['user_id'])}\n유저: {user}\n유저 ID: {row['user_id']}\n라운드: {row['round_number']}라운드\n추첨 계절: {meta.get('selected_season')}\n\n"
                f"아이템: {meta.get('item_name')}\n아이템 ID: {row['item_id']}\n현재 보유량: {meta.get('current_inventory')}개\n{before}신청 수량: {row['quantity_after']}개\n판매 후 남게 될 수량: {meta.get('remaining_after_request')}개\n\n"
                f"현재 전체 판매 신청량: {meta.get('total_requested')}개\n현재 판매 신청 인원: {meta.get('request_users')}명\n처리 시각: {created}"
            )
        if action == 'SETTLEMENT':
            items = '\n'.join(f"- {item['name']}: {item['total_qty']}개 / 개당 {format_won(int(item['unit_price']))}" for item in meta.get('items', [])) or '- 정산 대상 없음'
            return (
                f"💰 {row['round_number']}라운드 정산 완료\n\n추첨 계절: {meta.get('selected_season')}\n정산 참가자: {meta.get('participant_count')}명\n판매된 전체 아이템: {meta.get('total_quantity')}개\n지급된 전체 금액: {format_won(int(row['total_amount'] or 0))}\n\n정산 아이템:\n{items}\n\n처리 시각: {created}"
            )
        if action == 'STARTING_FUND':
            return f"💵 기본금 지급\n\n지급 인원: {meta.get('paid')}명\n제외 인원: {meta.get('skipped')}명\n1인 지급액: {format_won(int(row['unit_price'] or 0))}\n총 지급액: {format_won(int(row['total_amount'] or 0))}\n실행 관리자: {meta.get('admin_id')}\n처리 시각: {created}"
        if action == 'ADMIN_FUND_GRANT':
            return f"🎁 관리자 자금 지급\n\n대상: {user}\n지급액: {format_won(int(row['total_amount'] or 0))}\n지급 전 잔액: {format_won(int(row['balance_before'] or 0))}\n지급 후 잔액: {format_won(int(row['balance_after'] or 0))}\n사유: {meta.get('reason')}\n실행 관리자: {meta.get('admin_id')}\n처리 시각: {created}"
        return f"{action}\n유저: {user}\n라운드: {row['round_number']}\n처리 시각: {created}"

    def purchase_status_rows(self, event_id: int, detailed: bool = False) -> list[sqlite3.Row]:
        detail_cols = ', t.user_id' if detailed else ''
        group_cols = ', t.user_id' if detailed else ''
        return self.db.execute(f"""
            SELECT i.item_id,i.name,i.season,COALESCE(SUM(t.quantity),0) purchased_quantity,
                   COUNT(DISTINCT t.user_id) buyer_count,COALESCE(SUM(t.amount),0) total_amount,
                   COALESCE(ei.is_public,0) is_public{detail_cols}
            FROM items i
            LEFT JOIN event_items ei ON ei.event_id=? AND ei.item_id=i.item_id
            LEFT JOIN transactions t ON t.event_id=? AND t.item_id=i.item_id AND t.type='ITEM_PURCHASE'
            GROUP BY i.item_id{group_cols}
            ORDER BY i.item_id{group_cols}
        """, (event_id, event_id)).fetchall()

    def sale_status_rows(self, event_id: int) -> list[sqlite3.Row]:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        return self.db.execute("""
            SELECT i.item_id,i.name,COALESCE(SUM(CASE WHEN s.status='ACTIVE' THEN s.quantity ELSE 0 END),0) total_requested,
                   COUNT(DISTINCT CASE WHEN s.status='ACTIVE' THEN s.user_id END) request_users,
                   SUM(CASE WHEN s.status='CANCELLED' THEN 1 ELSE 0 END) cancelled_count,
                   MAX(s.updated_at) last_updated
            FROM items i
            LEFT JOIN sale_requests s ON s.event_id=? AND s.round=? AND s.item_id=i.item_id
            GROUP BY i.item_id
            ORDER BY i.item_id
        """, (event_id, event['current_round'])).fetchall()

    def set_status(self, event_id: int, status: Status) -> None:
        self.db.execute('UPDATE events SET status=? WHERE event_id=?', (status, event_id))
        self.db.commit()

    def require_status(self, event: sqlite3.Row, allowed: set[str], next_step: str) -> None:
        if event['status'] not in allowed:
            raise ValueError(f"현재 상태({event['status']})에서는 사용할 수 없습니다. 다음 단계: {next_step}")

    def set_item_public(self, event_id: int, admin_id: str, item_ids: Iterable[int], is_public: bool) -> dict[str, int]:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        normalized_ids = list(dict.fromkeys(int(item_id) for item_id in item_ids))
        if not normalized_ids:
            raise ValueError('아이템 ID를 하나 이상 입력해야 합니다.')
        newly_public = already_public = newly_private = already_private = 0
        with self.db:
            for item_id in normalized_ids:
                if not self.db.execute('SELECT 1 FROM items WHERE item_id=?', (item_id,)).fetchone():
                    raise ValueError(f'존재하지 않는 아이템입니다: {item_id}')
                current = self.db.execute('SELECT is_public FROM event_items WHERE event_id=? AND item_id=?', (event_id, item_id)).fetchone()
                current_public = bool(current['is_public']) if current else False
                if not is_public:
                    if event['status'] == 'BUYING':
                        raise ValueError('구매 진행 중에는 아이템을 비공개로 변경할 수 없습니다.')
                    held = self.db.execute('SELECT COALESCE(SUM(quantity),0) FROM inventories WHERE event_id=? AND item_id=?', (event_id, item_id)).fetchone()[0]
                    if held > 0:
                        raise ValueError('현재 참가자가 보유 중인 아이템은 비공개로 변경할 수 없습니다.')
                    purchased_this_round = self.db.execute("SELECT 1 FROM transactions WHERE event_id=? AND round=? AND item_id=? AND type='ITEM_PURCHASE' LIMIT 1", (event_id, event['current_round'], item_id)).fetchone()
                    if purchased_this_round:
                        raise ValueError('현재 라운드에서 구매 기록이 있는 아이템은 비공개로 변경할 수 없습니다.')
                self.db.execute('INSERT OR IGNORE INTO event_items(event_id,item_id,is_public) VALUES(?,?,0)', (event_id, item_id))
                self.db.execute('UPDATE event_items SET is_public=? WHERE event_id=? AND item_id=?', (1 if is_public else 0, event_id, item_id))
                if is_public:
                    if current_public:
                        already_public += 1
                    else:
                        newly_public += 1
                else:
                    if current_public:
                        newly_private += 1
                    else:
                        already_private += 1
            total_public = self.db.execute('SELECT COUNT(*) FROM event_items WHERE event_id=? AND is_public=1', (event_id,)).fetchone()[0]
            self.audit(event_id, event['current_round'], admin_id, 'ITEM_PUBLIC' if is_public else 'ITEM_PRIVATE', after=','.join(map(str, normalized_ids)))
        return {
            'newly_public': newly_public,
            'already_public': already_public,
            'newly_private': newly_private,
            'already_private': already_private,
            'total_public': int(total_public),
        }

    def start_buying(self, event_id: int) -> None:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'SETTING'}, '아이템 공개 후 구매시작')
        self.set_status(event_id, 'BUYING')

    def close_buying(self, event_id: int) -> None:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'BUYING'}, '매입금 설정')
        self.set_status(event_id, 'BUYING_CLOSED')

    def purchase(self, event_id: int, user_id: str, item_id: int, qty: int) -> dict[str, int | str]:
        assert_int(qty, '구매 수량')
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'BUYING'}, '관리자가 구매시작을 해야 합니다.')
        p = self.db.execute('SELECT * FROM participants WHERE event_id=? AND user_id=?', (event_id, user_id)).fetchone()
        if not p:
            raise ValueError('이벤트 참가자만 구매할 수 있습니다.')
        item = self.db.execute('SELECT i.* FROM items i JOIN event_items ei ON ei.item_id=i.item_id WHERE i.item_id=? AND ei.event_id=? AND ei.is_public=1', (item_id, event_id)).fetchone()
        if not item:
            raise ValueError('공개된 아이템만 구매할 수 있습니다.')
        total = int(item['price']) * qty
        before_balance = int(p['balance'])
        if before_balance < total:
            raise ValueError('보유 자금이 부족합니다.')
        with self.db:
            cur = self.db.execute('UPDATE participants SET balance=balance-? WHERE event_id=? AND user_id=? AND balance>=?', (total, event_id, user_id, total))
            if cur.rowcount != 1:
                raise ValueError('동시 구매 처리 중 잔액이 부족해졌습니다.')
            self.db.execute('INSERT INTO inventories(event_id,user_id,item_id,quantity) VALUES(?,?,?,?) ON CONFLICT(event_id,user_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity', (event_id, user_id, item_id, qty))
            self.db.execute('INSERT INTO transactions(event_id,round,user_id,item_id,type,quantity,amount,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)', (event_id, event['current_round'], user_id, item_id, 'ITEM_PURCHASE', qty, total, '아이템 구매', now_iso()))
            after_balance = before_balance - total
            user_inventory = int(self.db.execute('SELECT quantity FROM inventories WHERE event_id=? AND user_id=? AND item_id=?', (event_id, user_id, item_id)).fetchone()[0])
            total_inventory = int(self.db.execute('SELECT COALESCE(SUM(quantity),0) FROM inventories WHERE event_id=? AND item_id=?', (event_id, item_id)).fetchone()[0])
            activity_id = self.record_trade_activity(
                event,
                'ITEM_PURCHASE',
                user_id=user_id,
                item_id=item_id,
                quantity_after=qty,
                unit_price=int(item['price']),
                total_amount=total,
                balance_before=before_balance,
                balance_after=after_balance,
                metadata={'event_name': event['name'], 'item_name': item['name'], 'season': item['season'], 'user_inventory': user_inventory, 'total_inventory': total_inventory},
            )
        return {'item': item['name'], 'qty': qty, 'total': total, 'balance': after_balance, 'item_quantity': user_inventory, 'activity_id': activity_id}

    def set_buyout(self, event_id: int, admin_id: str, item_id: int, amount: int, source: str = 'ITEM') -> None:
        if not isinstance(amount, int) or amount < 0:
            raise ValueError('매입금은 0 이상의 정수여야 합니다.')
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'BUYING_CLOSED','BUYOUT_SETTING'}, '구매종료 후 매입금 설정')
        if self.db.execute('SELECT 1 FROM round_buyouts WHERE event_id=? AND round=? AND is_public=1', (event_id, event['current_round'])).fetchone():
            raise ValueError('매입금 공개 후에는 수정할 수 없습니다.')
        row = self.db.execute('SELECT i.price, COALESCE(SUM(inv.quantity),0) qty FROM items i LEFT JOIN inventories inv ON inv.item_id=i.item_id AND inv.event_id=? WHERE i.item_id=?', (event_id, item_id)).fetchone()
        minimum = int(row['price']) * int(row['qty'])
        if amount < minimum:
            raise ValueError(f"입력 매입금 {amount}원은 최소 설정 가능 매입금 {minimum}원보다 낮습니다.")
        self.db.execute('INSERT INTO round_buyouts(event_id,round,item_id,buyout_amount,is_public,source) VALUES(?,?,?,?,0,?) ON CONFLICT(event_id,round,item_id) DO UPDATE SET buyout_amount=excluded.buyout_amount, source=excluded.source', (event_id, event['current_round'], item_id, amount, source))
        self.db.execute('UPDATE events SET status=? WHERE event_id=?', ('BUYOUT_SETTING', event_id))
        self.audit(event_id, event['current_round'], admin_id, 'BUYOUT_SET', after=f'{item_id}:{amount}')
        self.db.commit()

    def publish_buyouts(self, event_id: int, admin_id: str) -> None:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        count = self.db.execute('SELECT COUNT(*) FROM round_buyouts WHERE event_id=? AND round=?', (event_id, event['current_round'])).fetchone()[0]
        if count < len(FIXED_ITEMS):
            raise ValueError('현재 라운드의 모든 아이템 매입금을 설정해야 합니다.')
        self.db.execute('UPDATE round_buyouts SET is_public=1 WHERE event_id=? AND round=?', (event_id, event['current_round']))
        self.db.execute('UPDATE events SET status=? WHERE event_id=?', ('BUYOUT_PUBLISHED', event_id))
        self.audit(event_id, event['current_round'], admin_id, 'BUYOUT_PUBLISH')
        self.db.commit()

    def set_season(self, event_id: int, admin_id: str, season: str) -> None:
        if season not in SEASONS:
            raise ValueError('계절은 봄, 여름, 가을, 겨울만 입력할 수 있습니다.')
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'BUYOUT_PUBLISHED'}, '매입금 공개 후 외부 추첨 결과 입력')
        self.db.execute('UPDATE events SET selected_season=?, status=? WHERE event_id=?', (season, 'SEASON_SELECTED', event_id))
        self.audit(event_id, event['current_round'], admin_id, 'SEASON_SET', after=season)
        self.db.commit()

    def start_selling(self, event_id: int, admin_id: str, minutes: int) -> str:
        assert_int(minutes, '판매 시간')
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'SEASON_SELECTED'}, '계절결과 입력 후 판매시작')
        end = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        self.db.execute('UPDATE events SET sale_start_at=?, sale_end_at=?, status=? WHERE event_id=?', (now_iso(), end.isoformat(), 'SELLING', event_id))
        self.audit(event_id, event['current_round'], admin_id, 'SALE_START', after=end.isoformat())
        self.db.commit()
        return end.isoformat()

    def close_selling(self, event_id: int) -> bool:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        if event['status'] == 'SELLING_CLOSED':
            return False
        self.require_status(event, {'SELLING'}, '정산미리보기 또는 정산')
        self.db.execute('UPDATE events SET status=? WHERE event_id=? AND status=?', ('SELLING_CLOSED', event_id, 'SELLING'))
        self.db.commit()
        return True

    def sale_request(self, event_id: int, user_id: str, item_id: int, qty: int) -> None:
        assert_int(qty, '판매 수량')
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'SELLING'}, '판매시작 후 판매 신청')
        if event['sale_end_at'] and datetime.fromisoformat(event['sale_end_at']) <= datetime.now(timezone.utc):
            raise ValueError('판매 종료 시간이 지났습니다.')
        item = self.db.execute('SELECT * FROM items WHERE item_id=?', (item_id,)).fetchone()
        if item['season'] != event['selected_season']:
            raise ValueError('외부 추첨으로 선택된 계절 아이템만 판매할 수 있습니다.')
        have = self.db.execute('SELECT COALESCE(quantity,0) FROM inventories WHERE event_id=? AND user_id=? AND item_id=?', (event_id, user_id, item_id)).fetchone()[0]
        if qty > have:
            raise ValueError('판매 수량은 보유 수량을 초과할 수 없습니다.')
        previous = self.db.execute('SELECT quantity,status FROM sale_requests WHERE event_id=? AND round=? AND user_id=? AND item_id=?', (event_id, event['current_round'], user_id, item_id)).fetchone()
        previous_qty = int(previous['quantity']) if previous and previous['status'] == 'ACTIVE' else 0
        action_type = 'SALE_REQUEST_CHANGE' if previous and previous['status'] == 'ACTIVE' else 'SALE_REQUEST'
        with self.db:
            self.db.execute("INSERT INTO sale_requests(event_id,round,user_id,item_id,quantity,status,settled,created_at,updated_at) VALUES(?,?,?,?,?,'ACTIVE',0,?,?) ON CONFLICT(event_id,round,user_id,item_id) DO UPDATE SET quantity=excluded.quantity,status='ACTIVE',updated_at=excluded.updated_at", (event_id, event['current_round'], user_id, item_id, qty, now_iso(), now_iso()))
            total_requested = int(self.db.execute("SELECT COALESCE(SUM(quantity),0) FROM sale_requests WHERE event_id=? AND round=? AND item_id=? AND status='ACTIVE'", (event_id, event['current_round'], item_id)).fetchone()[0])
            request_users = int(self.db.execute("SELECT COUNT(DISTINCT user_id) FROM sale_requests WHERE event_id=? AND round=? AND item_id=? AND status='ACTIVE' AND quantity>0", (event_id, event['current_round'], item_id)).fetchone()[0])
            activity_id = self.record_trade_activity(
                event,
                action_type,
                user_id=user_id,
                item_id=item_id,
                quantity_before=previous_qty if action_type == 'SALE_REQUEST_CHANGE' else None,
                quantity_after=qty,
                metadata={'item_name': item['name'], 'selected_season': event['selected_season'], 'current_inventory': int(have), 'remaining_after_request': int(have) - qty, 'total_requested': total_requested, 'request_users': request_users},
            )
        return activity_id

    def preview_settlement(self, event_id: int) -> list[dict[str, int | str]]:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        rows = self.db.execute("SELECT b.item_id,i.name,b.buyout_amount,COALESCE(SUM(CASE WHEN s.status='ACTIVE' THEN s.quantity ELSE 0 END),0) total_qty FROM round_buyouts b JOIN items i ON i.item_id=b.item_id LEFT JOIN sale_requests s ON s.event_id=b.event_id AND s.round=b.round AND s.item_id=b.item_id WHERE b.event_id=? AND b.round=? GROUP BY b.item_id", (event_id, event['current_round'])).fetchall()
        result = []
        for row in rows:
            unit = sale_unit_price(int(row['buyout_amount']), int(row['total_qty']))
            total = unit * int(row['total_qty'])
            result.append({'item_id': row['item_id'], 'name': row['name'], 'buyout_amount': row['buyout_amount'], 'total_qty': row['total_qty'], 'unit_price': unit, 'total_paid': total, 'unused_buyout': row['buyout_amount'] - total})
        return result

    def settle(self, event_id: int, admin_id: str) -> list[dict[str, int | str]]:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'SELLING_CLOSED'}, '판매종료 후 정산')
        if self.db.execute('SELECT 1 FROM settlements WHERE event_id=? AND round=?', (event_id, event['current_round'])).fetchone():
            raise ValueError('이미 정산된 라운드입니다.')
        preview = self.preview_settlement(event_id)
        settlement_details = []
        with self.db:
            for p in preview:
                if int(p['total_qty']) <= 0:
                    continue
                reqs = self.db.execute("SELECT * FROM sale_requests WHERE event_id=? AND round=? AND item_id=? AND status='ACTIVE' AND quantity>0", (event_id, event['current_round'], p['item_id'])).fetchall()
                for r in reqs:
                    have = self.db.execute('SELECT quantity FROM inventories WHERE event_id=? AND user_id=? AND item_id=?', (event_id, r['user_id'], r['item_id'])).fetchone()[0]
                    if have < r['quantity']:
                        raise ValueError('보유 수량 불일치로 정산할 수 없습니다.')
                    amount = int(p['unit_price']) * int(r['quantity'])
                    self.db.execute('UPDATE inventories SET quantity=quantity-? WHERE event_id=? AND user_id=? AND item_id=?', (r['quantity'], event_id, r['user_id'], r['item_id']))
                    self.db.execute('UPDATE participants SET balance=balance+? WHERE event_id=? AND user_id=?', (amount, event_id, r['user_id']))
                    balance_after = self.db.execute('SELECT balance FROM participants WHERE event_id=? AND user_id=?', (event_id, r['user_id'])).fetchone()[0]
                    self.db.execute('INSERT INTO transactions(event_id,round,user_id,item_id,type,quantity,amount,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)', (event_id, event['current_round'], r['user_id'], r['item_id'], 'ITEM_SALE', r['quantity'], amount, '아이템 판매 정산', now_iso()))
                    settlement_details.append({'user_id': r['user_id'], 'item_id': r['item_id'], 'item_name': p['name'], 'quantity': int(r['quantity']), 'unit_price': int(p['unit_price']), 'amount': amount, 'balance_after': int(balance_after)})
                self.db.execute('INSERT INTO settlements(event_id,round,item_id,total_quantity,unit_price,total_paid,unused_buyout,settled_at) VALUES(?,?,?,?,?,?,?,?)', (event_id, event['current_round'], p['item_id'], p['total_qty'], p['unit_price'], p['total_paid'], p['unused_buyout'], now_iso()))
            self.db.execute("UPDATE sale_requests SET settled=1,status='SETTLED',updated_at=? WHERE event_id=? AND round=? AND status='ACTIVE'", (now_iso(), event_id, event['current_round']))
            self.db.execute('UPDATE events SET status=? WHERE event_id=?', ('SETTLED', event_id))
            participant_count = self.db.execute("SELECT COUNT(DISTINCT user_id) FROM sale_requests WHERE event_id=? AND round=? AND status='SETTLED' AND quantity>0", (event_id, event['current_round'])).fetchone()[0]
            total_quantity = sum(int(p['total_qty']) for p in preview)
            total_paid = sum(int(p['total_paid']) for p in preview)
            self.record_trade_activity(
                event,
                'SETTLEMENT',
                total_amount=total_paid,
                metadata={'selected_season': event['selected_season'], 'participant_count': int(participant_count), 'total_quantity': total_quantity, 'items': [{'name': p['name'], 'total_qty': int(p['total_qty']), 'unit_price': int(p['unit_price'])} for p in preview if int(p['total_qty']) > 0], 'details': settlement_details},
            )
            self.audit(event_id, event['current_round'], admin_id, 'SETTLEMENT')
        return preview


    def set_tier_buyout(self, event_id: int, admin_id: str, tier: str, amount: int) -> None:
        if tier not in TIERS:
            raise ValueError('가격 등급은 저가, 중가, 고가만 가능합니다.')
        item_ids = [row['item_id'] for row in self.db.execute('SELECT item_id FROM items WHERE price_tier=?', (tier,)).fetchall()]
        for item_id in item_ids:
            self.set_buyout(event_id, admin_id, int(item_id), amount, 'TIER')

    def buyout_rows(self, event_id: int) -> list[sqlite3.Row]:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        return self.db.execute('SELECT i.item_id,i.name,i.season,i.price_tier,COALESCE(b.buyout_amount,0) buyout_amount,COALESCE(b.is_public,0) is_public FROM items i LEFT JOIN round_buyouts b ON b.item_id=i.item_id AND b.event_id=? AND b.round=? ORDER BY i.item_id', (event_id, event['current_round'])).fetchall()

    def cancel_sale_request(self, event_id: int, user_id: str, item_id: int) -> int:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'SELLING'}, '판매 중에만 취소할 수 있습니다.')
        existing = self.db.execute("SELECT * FROM sale_requests WHERE event_id=? AND round=? AND user_id=? AND item_id=? AND status='ACTIVE' AND quantity>0", (event_id, event['current_round'], user_id, item_id)).fetchone()
        if not existing:
            raise ValueError('취소할 활성 판매 신청이 없습니다.')
        item = self.db.execute('SELECT * FROM items WHERE item_id=?', (item_id,)).fetchone()
        have = int(self.db.execute('SELECT COALESCE(quantity,0) FROM inventories WHERE event_id=? AND user_id=? AND item_id=?', (event_id, user_id, item_id)).fetchone()[0])
        with self.db:
            self.db.execute("UPDATE sale_requests SET quantity=0,status='CANCELLED',updated_at=? WHERE event_id=? AND round=? AND user_id=? AND item_id=?", (now_iso(), event_id, event['current_round'], user_id, item_id))
            total_requested = int(self.db.execute("SELECT COALESCE(SUM(quantity),0) FROM sale_requests WHERE event_id=? AND round=? AND item_id=? AND status='ACTIVE'", (event_id, event['current_round'], item_id)).fetchone()[0])
            request_users = int(self.db.execute("SELECT COUNT(DISTINCT user_id) FROM sale_requests WHERE event_id=? AND round=? AND item_id=? AND status='ACTIVE' AND quantity>0", (event_id, event['current_round'], item_id)).fetchone()[0])
            activity_id = self.record_trade_activity(event, 'SALE_REQUEST_CANCEL', user_id=user_id, item_id=item_id, quantity_before=int(existing['quantity']), quantity_after=0, metadata={'item_name': item['name'], 'selected_season': event['selected_season'], 'current_inventory': have, 'remaining_after_request': have, 'total_requested': total_requested, 'request_users': request_users})
        return activity_id

    def my_sale_requests(self, event_id: int, user_id: str) -> list[sqlite3.Row]:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        return self.db.execute('SELECT i.name,s.item_id,s.quantity,s.status FROM sale_requests s JOIN items i ON i.item_id=s.item_id WHERE s.event_id=? AND s.round=? AND s.user_id=? ORDER BY s.item_id', (event_id, event['current_round'], user_id)).fetchall()

    def participant_summary(self, event_id: int, user_id: str) -> dict[str, object]:
        p = self.db.execute('SELECT * FROM participants WHERE event_id=? AND user_id=?', (event_id, user_id)).fetchone()
        if not p:
            raise ValueError('이벤트 참가자가 아닙니다.')
        inv = self.db.execute('SELECT i.name, inv.quantity FROM inventories inv JOIN items i ON i.item_id=inv.item_id WHERE inv.event_id=? AND inv.user_id=? AND inv.quantity>0 ORDER BY i.item_id', (event_id, user_id)).fetchall()
        bought = self.db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE event_id=? AND user_id=? AND type='ITEM_PURCHASE'", (event_id, user_id)).fetchone()[0]
        sold = self.db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE event_id=? AND user_id=? AND type='ITEM_SALE'", (event_id, user_id)).fetchone()[0]
        grants = self.db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE event_id=? AND user_id=? AND type='ADMIN_FUND_GRANT'", (event_id, user_id)).fetchone()[0]
        return {'balance': p['balance'], 'inventory': inv, 'bought': bought, 'sold': sold, 'grants': grants}

    def transactions_for(self, event_id: int, user_id: str, limit: int = 20) -> list[sqlite3.Row]:
        return self.db.execute('SELECT type,item_id,quantity,amount,reason,created_at FROM transactions WHERE event_id=? AND user_id=? ORDER BY transaction_id DESC LIMIT ?', (event_id, user_id, limit)).fetchall()

    def next_round(self, event_id: int, admin_id: str) -> dict[str, int | str]:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        if event['status'] != 'SETTLED':
            raise ValueError('현재 라운드의 정산이 완료된 뒤 다음 라운드로 이동할 수 있습니다.')
        previous_round = int(event['current_round'])
        next_round = previous_round + 1
        participant_count = int(self.db.execute("SELECT COUNT(*) FROM participants WHERE event_id=? AND status='ACTIVE'", (event_id,)).fetchone()[0])
        inventory_quantity = int(self.db.execute('SELECT COALESCE(SUM(quantity),0) FROM inventories WHERE event_id=?', (event_id,)).fetchone()[0])
        public_items = int(self.db.execute('SELECT COUNT(*) FROM event_items WHERE event_id=? AND is_public=1', (event_id,)).fetchone()[0])
        with self.db:
            self.db.execute("UPDATE events SET current_round=?, status='SETTING', selected_season=NULL, sale_start_at=NULL, sale_end_at=NULL WHERE event_id=?", (next_round, event_id))
            self.audit(
                event_id,
                previous_round,
                admin_id,
                'NEXT_ROUND',
                before=str(previous_round),
                after=str(next_round),
                reason=f'participants={participant_count},inventory_quantity={inventory_quantity},public_items={public_items},balances_preserved=true,inventories_preserved=true',
            )
        return {
            'previous_round': previous_round,
            'new_round': next_round,
            'participants': participant_count,
            'inventory_quantity': inventory_quantity,
            'public_items': public_items,
            'status': 'SETTING',
        }

    def end_event(self, event_id: int, admin_id: str) -> None:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        if event['status'] == 'ENDED':
            return
        with self.db:
            rows = self.db.execute('SELECT user_id,item_id,quantity FROM inventories WHERE event_id=? AND quantity>0', (event_id,)).fetchall()
            for row in rows:
                self.db.execute('INSERT INTO transactions(event_id,round,user_id,item_id,type,quantity,amount,reason,created_at) VALUES(?,?,?,?,?,?,0,?,?)', (event_id, event['current_round'], row['user_id'], row['item_id'], 'ITEM_EXPIRATION', row['quantity'], '이벤트 종료 소멸', now_iso()))
            self.db.execute('UPDATE inventories SET quantity=0 WHERE event_id=?', (event_id,))
            self.db.execute("UPDATE events SET status='ENDED', ended_at=? WHERE event_id=?", (now_iso(), event_id))
            self.audit(event_id, event['current_round'], admin_id, 'EVENT_END')
