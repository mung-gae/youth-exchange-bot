from __future__ import annotations

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
        return {'before': before, 'after': after, 'amount': amount}

    def audit(self, event_id: int, round_no: int, admin_id: str, action: str, target_user_id: str | None = None, before: str | None = None, after: str | None = None, reason: str | None = None) -> None:
        self.db.execute('INSERT INTO admin_audit_logs(event_id,round,admin_id,action,target_user_id,before_value,after_value,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)', (event_id, round_no, admin_id, action, target_user_id, before, after, reason, now_iso()))

    def set_status(self, event_id: int, status: Status) -> None:
        self.db.execute('UPDATE events SET status=? WHERE event_id=?', (status, event_id))
        self.db.commit()

    def require_status(self, event: sqlite3.Row, allowed: set[str], next_step: str) -> None:
        if event['status'] not in allowed:
            raise ValueError(f"현재 상태({event['status']})에서는 사용할 수 없습니다. 다음 단계: {next_step}")

    def set_item_public(self, event_id: int, admin_id: str, item_ids: Iterable[int], is_public: bool) -> None:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        with self.db:
            for item_id in item_ids:
                if not is_public:
                    bought = self.db.execute('SELECT COALESCE(SUM(quantity),0) FROM inventories WHERE item_id=?', (item_id,)).fetchone()[0]
                    if bought > 0:
                        raise ValueError('이미 구매된 아이템은 비공개로 변경할 수 없습니다.')
                self.db.execute('INSERT OR IGNORE INTO event_items(event_id,item_id,is_public) VALUES(?,?,0)', (event_id, item_id))
                self.db.execute('UPDATE event_items SET is_public=? WHERE event_id=? AND item_id=?', (1 if is_public else 0, event_id, item_id))
            self.audit(event_id, event['current_round'], admin_id, 'ITEM_PUBLIC' if is_public else 'ITEM_PRIVATE', after=','.join(map(str, item_ids)))

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
        if int(p['balance']) < total:
            raise ValueError('보유 자금이 부족합니다.')
        with self.db:
            cur = self.db.execute('UPDATE participants SET balance=balance-? WHERE event_id=? AND user_id=? AND balance>=?', (total, event_id, user_id, total))
            if cur.rowcount != 1:
                raise ValueError('동시 구매 처리 중 잔액이 부족해졌습니다.')
            self.db.execute('INSERT INTO inventories(event_id,user_id,item_id,quantity) VALUES(?,?,?,?) ON CONFLICT(event_id,user_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity', (event_id, user_id, item_id, qty))
            self.db.execute('INSERT INTO transactions(event_id,round,user_id,item_id,type,quantity,amount,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)', (event_id, event['current_round'], user_id, item_id, 'ITEM_PURCHASE', qty, total, '아이템 구매', now_iso()))
        bal = self.db.execute('SELECT balance FROM participants WHERE event_id=? AND user_id=?', (event_id, user_id)).fetchone()[0]
        inv = self.db.execute('SELECT quantity FROM inventories WHERE event_id=? AND user_id=? AND item_id=?', (event_id, user_id, item_id)).fetchone()[0]
        return {'item': item['name'], 'qty': qty, 'total': total, 'balance': bal, 'item_quantity': inv}

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
        self.db.execute("INSERT INTO sale_requests(event_id,round,user_id,item_id,quantity,status,settled,created_at,updated_at) VALUES(?,?,?,?,?,'ACTIVE',0,?,?) ON CONFLICT(event_id,round,user_id,item_id) DO UPDATE SET quantity=excluded.quantity,status='ACTIVE',updated_at=excluded.updated_at", (event_id, event['current_round'], user_id, item_id, qty, now_iso(), now_iso()))
        self.db.commit()

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
                    self.db.execute('INSERT INTO transactions(event_id,round,user_id,item_id,type,quantity,amount,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)', (event_id, event['current_round'], r['user_id'], r['item_id'], 'ITEM_SALE', r['quantity'], amount, '아이템 판매 정산', now_iso()))
                self.db.execute('INSERT INTO settlements(event_id,round,item_id,total_quantity,unit_price,total_paid,unused_buyout,settled_at) VALUES(?,?,?,?,?,?,?,?)', (event_id, event['current_round'], p['item_id'], p['total_qty'], p['unit_price'], p['total_paid'], p['unused_buyout'], now_iso()))
            self.db.execute("UPDATE sale_requests SET settled=1,status='SETTLED',updated_at=? WHERE event_id=? AND round=? AND status='ACTIVE'", (now_iso(), event_id, event['current_round']))
            self.db.execute('UPDATE events SET status=? WHERE event_id=?', ('SETTLED', event_id))
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

    def cancel_sale_request(self, event_id: int, user_id: str, item_id: int) -> None:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'SELLING'}, '판매 중에만 취소할 수 있습니다.')
        self.db.execute("UPDATE sale_requests SET quantity=0,status='CANCELLED',updated_at=? WHERE event_id=? AND round=? AND user_id=? AND item_id=?", (now_iso(), event_id, event['current_round'], user_id, item_id))
        self.db.commit()

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

    def next_round(self, event_id: int, admin_id: str) -> int:
        event = self.db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        self.require_status(event, {'SETTLED'}, '정산 완료 후 다음 라운드')
        next_round = int(event['current_round']) + 1
        self.db.execute("UPDATE events SET current_round=?, status='BUYOUT_SETTING', selected_season=NULL, sale_start_at=NULL, sale_end_at=NULL WHERE event_id=?", (next_round, event_id))
        self.audit(event_id, event['current_round'], admin_id, 'NEXT_ROUND', after=str(next_round))
        self.db.commit()
        return next_round

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
