import fs from 'node:fs';
import path from 'node:path';
import Database from 'better-sqlite3';
export function openDatabase(dbPath = process.env.DATABASE_PATH || './data/youth-exchange.db') { const dir = path.dirname(dbPath); if (dir && !fs.existsSync(dir))
    fs.mkdirSync(dir, { recursive: true }); const db = new Database(dbPath); db.pragma('foreign_keys = ON'); db.pragma('journal_mode = WAL'); console.log('[청춘거래소] 데이터베이스 연결 완료'); return db; }
