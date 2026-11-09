"""SQLite storage: datasets, candles, strategies, runs, trades (migrates older versions in place)."""
import os
import sqlite3

from flask import g

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "data", "lab.db")

TABLES = """
CREATE TABLE IF NOT EXISTS datasets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL,                -- 'upload' or 'synthetic'
    path       TEXT NOT NULL DEFAULT '',     -- legacy: v1 stored CSV files on disk
    bars       INTEGER NOT NULL DEFAULT 0,
    first_bar  TEXT,
    last_bar   TEXT,
    symbol     TEXT,
    timeframe  TEXT,
    meta       TEXT,                         -- JSON: bars per year, largest gap
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS candles (
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    ts         TEXT NOT NULL,                -- 'YYYY-MM-DD HH:MM:SS'
    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
    PRIMARY KEY (dataset_id, ts)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS strategies (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    code       TEXT NOT NULL,
    params     TEXT NOT NULL DEFAULT '[]',   -- JSON parameter definitions read from the code
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id    INTEGER REFERENCES datasets(id) ON DELETE SET NULL,
    dataset_name  TEXT NOT NULL,
    strategy_id   INTEGER,
    strategy_name TEXT,
    strategy_type TEXT NOT NULL DEFAULT 'custom',
    mode          TEXT NOT NULL,             -- 'quick' or 'validate'
    params        TEXT NOT NULL,             -- JSON
    cost          REAL NOT NULL,
    split         REAL NOT NULL,
    verdict       TEXT NOT NULL,
    oos_exp       REAL,
    oos_n         INTEGER,
    result        TEXT NOT NULL,             -- JSON (stats, checks, grid, curve)
    code          TEXT,                      -- snapshot of the strategy code used
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS trades (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id   INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    ts_entry TEXT,
    ts_exit  TEXT,
    side     INTEGER,
    entry    REAL,
    exit     REAL,
    r        REAL,
    segment  TEXT,                           -- 'is' or 'oos'
    sl       REAL,
    tp       REAL
);
"""

# columns added by newer versions; applied to databases created by older ones
ADD_COLUMNS = {
    "datasets": [("symbol", "TEXT"), ("timeframe", "TEXT"), ("meta", "TEXT")],
    "runs": [("strategy_id", "INTEGER"), ("strategy_name", "TEXT"), ("code", "TEXT")],
    "trades": [("sl", "REAL"), ("tp", "REAL")],
}

INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_datasets_symbol_tf ON datasets(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_trades_run ON trades(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
"""


def init():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(TABLES)
    for table, cols in ADD_COLUMNS.items():
        have = {r[1] for r in con.execute("PRAGMA table_info(%s)" % table)}
        for name, typ in cols:
            if name not in have:
                con.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, typ))
    con.executescript(INDEXES)
    con.commit()
    con.close()


def raw_conn():
    """A connection for use outside a web request (startup, migration)."""
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def conn():
    if "db" not in g:
        g.db = raw_conn()
    return g.db


def close(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def query(sql, args=(), one=False):
    rows = conn().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    con = conn()
    cur = con.execute(sql, args)
    con.commit()
    return cur.lastrowid


def executemany(sql, rows):
    con = conn()
    con.executemany(sql, rows)
    con.commit()