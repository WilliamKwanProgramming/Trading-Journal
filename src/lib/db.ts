import { mkdirSync } from "node:fs";
import path from "node:path";
import Database from "better-sqlite3";

const DB_PATH = path.join(process.cwd(), "data", "trading-journal.db");
let database: Database.Database | null = null;

function initialize(db: Database.Database) {
  db.pragma("journal_mode = WAL");
  db.exec(`
    CREATE TABLE IF NOT EXISTS trades (
      id TEXT PRIMARY KEY,
      ticker TEXT NOT NULL,
      side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
      quantity REAL NOT NULL CHECK (quantity > 0),
      price REAL NOT NULL CHECK (price > 0),
      trade_date TEXT NOT NULL,
      currency TEXT NOT NULL CHECK (currency IN ('USD', 'CAD')),
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS market_bars (
      ticker TEXT NOT NULL,
      bar_date TEXT NOT NULL,
      open REAL NOT NULL,
      high REAL NOT NULL,
      low REAL NOT NULL,
      close REAL NOT NULL,
      volume REAL,
      PRIMARY KEY (ticker, bar_date)
    );

    CREATE TABLE IF NOT EXISTS sync_status (
      ticker TEXT PRIMARY KEY,
      status TEXT NOT NULL CHECK (status IN ('ok', 'error')),
      message TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS fx_rates (
      pair TEXT PRIMARY KEY,
      rate REAL NOT NULL,
      rate_date TEXT NOT NULL,
      source TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_trades_date ON trades (trade_date, created_at);
    CREATE INDEX IF NOT EXISTS idx_bars_ticker_date ON market_bars (ticker, bar_date);
  `);
}

export function getDb() {
  if (database) return database;
  mkdirSync(path.dirname(DB_PATH), { recursive: true });
  database = new Database(DB_PATH);
  initialize(database);
  return database;
}
