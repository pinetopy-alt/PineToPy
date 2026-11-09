"""Data library: candles live in SQLite; new periods merge into existing symbol/timeframe sets."""
import json
import os

import numpy as np
import pandas as pd

import engine

COLS = ["ts", "open", "high", "low", "close"]


def load_df(con, dataset_id, limit=None):
    sql = "SELECT ts, open, high, low, close FROM candles WHERE dataset_id = ? ORDER BY ts"
    args = [dataset_id]
    if limit:
        sql += " LIMIT ?"
        args.append(int(limit))
    rows = [tuple(r) for r in con.execute(sql, args).fetchall()]
    if not rows:
        raise ValueError("This dataset has no bars")
    df = pd.DataFrame(rows, columns=COLS)
    df.index = pd.to_datetime(df.pop("ts"))
    return df


def insert_candles(con, dataset_id, df):
    ts = df.index.strftime(engine.TS_FMT)
    rows = list(zip([dataset_id] * len(df), ts, df["open"].tolist(), df["high"].tolist(),
                    df["low"].tolist(), df["close"].tolist()))
    con.executemany("INSERT OR REPLACE INTO candles(dataset_id, ts, open, high, low, close) "
                    "VALUES (?,?,?,?,?,?)", rows)


def refresh_meta(con, ds_id):
    """Recompute bar count, date range, bars per year and the largest gap."""
    ts = pd.to_datetime([r[0] for r in con.execute(
        "SELECT ts FROM candles WHERE dataset_id = ? ORDER BY ts", (ds_id,))])
    meta = {"coverage": {}, "gap_days": 0.0, "gap_from": None, "gap_to": None}
    if len(ts):
        years, counts = np.unique(ts.year, return_counts=True)
        meta["coverage"] = {str(int(y)): int(c) for y, c in zip(years, counts)}
        if len(ts) > 1:
            d = np.diff(ts.values)
            k = int(np.argmax(d))
            meta.update(gap_days=round(float(d[k] / np.timedelta64(1, "D")), 1),
                        gap_from=engine.fmt_ts(ts[k]), gap_to=engine.fmt_ts(ts[k + 1]))
    con.execute("UPDATE datasets SET bars = ?, first_bar = ?, last_bar = ?, meta = ? WHERE id = ?",
                (len(ts), engine.fmt_ts(ts[0]) if len(ts) else None,
                 engine.fmt_ts(ts[-1]) if len(ts) else None, json.dumps(meta), ds_id))
    con.commit()


def add_bars(con, symbol, tf, df, kind="upload"):
    """Create the symbol/timeframe dataset, or merge new bars into it (new bars win on overlap)."""
    row = con.execute("SELECT id FROM datasets WHERE symbol = ? AND timeframe = ?", (symbol, tf)).fetchone()
    merged = row is not None
    ds_id = row[0] if merged else con.execute(
        "INSERT INTO datasets(name, kind, symbol, timeframe) VALUES (?,?,?,?)",
        ("%s %s" % (symbol, tf), kind, symbol, tf)).lastrowid
    before = con.execute("SELECT COUNT(*) FROM candles WHERE dataset_id = ?", (ds_id,)).fetchone()[0]
    insert_candles(con, ds_id, df)
    refresh_meta(con, ds_id)
    total = con.execute("SELECT COUNT(*) FROM candles WHERE dataset_id = ?", (ds_id,)).fetchone()[0]
    return {"id": ds_id, "symbol": symbol, "timeframe": tf, "added": total - before,
            "total": total, "merged": merged}


def migrate_old(con):
    """Move datasets saved by version 1 (CSV files on disk) into the candles table."""
    for r in con.execute("SELECT id, name, path FROM datasets WHERE symbol IS NULL").fetchall():
        sym = engine.guess_symbol(r["name"]) or "DATA"
        tf = "H1"
        df = None
        try:
            df = engine.load_csv(r["path"])
            tf = engine.detect_timeframe(df)
        except Exception:
            pass
        base, k = sym, 2
        while con.execute("SELECT 1 FROM datasets WHERE symbol = ? AND timeframe = ? AND id != ?",
                          (sym, tf, r["id"])).fetchone():
            sym, k = "%s_%d" % (base, k), k + 1
        con.execute("UPDATE datasets SET symbol = ?, timeframe = ?, name = ? WHERE id = ?",
                    (sym, tf, "%s %s" % (sym, tf), r["id"]))
        if df is not None:
            insert_candles(con, r["id"], df)
            refresh_meta(con, r["id"])
            got = con.execute("SELECT COUNT(*) FROM candles WHERE dataset_id = ?", (r["id"],)).fetchone()[0]
            if got == len(df) and r["path"] and os.path.exists(r["path"]):
                os.remove(r["path"])
                con.execute("UPDATE datasets SET path = '' WHERE id = ?", (r["id"],))
        con.commit()