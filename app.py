"""Strategy Lab backend (Flask). Run: python app.py   then open http://127.0.0.1:5000"""
import bisect
import csv
import io
import json
import os
import re
import subprocess
import sys
import uuid
from contextlib import closing

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import db
import engine
import library
from templates import TEMPLATES

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
PORT = int(os.environ.get("LAB_PORT", "5000"))
HOSTS = {"127.0.0.1:%d" % PORT, "localhost:%d" % PORT}
WORKER = os.path.join(BASE, "worker.py")
os.makedirs(DATA, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024  # 300 MB per upload
app.json.sort_keys = False
app.teardown_appcontext(db.close)

db.init()
with closing(db.raw_conn()) as _con:
    library.migrate_old(_con)  # pulls v1 datasets into the new candle table
    if _con.execute("SELECT 1 FROM strategies LIMIT 1").fetchone() is None:
        _t = TEMPLATES[0]
        _con.execute("INSERT INTO strategies(name, code, params) VALUES (?,?,?)",
                     (_t["name"], _t["code"], json.dumps(engine.Strategy(_t["code"]).defs)))
        _con.commit()


# ---------------- security ----------------
@app.before_request
def protect():
    """This app can run code, so refuse other websites and DNS-rebinding tricks."""
    if request.host not in HOSTS:
        abort(403)
    if request.method not in ("GET", "HEAD") and request.headers.get("X-Lab") != "1":
        abort(403)


class CodeError(ValueError):
    def __init__(self, msg, line=None, log=""):
        super().__init__(msg)
        self.line, self.log = line, log


@app.errorhandler(CodeError)
def on_code_error(e):
    return jsonify(error=str(e), line=e.line, log=e.log), 400


@app.errorhandler(ValueError)
def on_value_error(e):
    return jsonify(error=str(e)), 400


@app.errorhandler(LookupError)
def on_not_found(e):
    return jsonify(error=str(e)), 404


@app.errorhandler(403)
def on_forbidden(_e):
    return jsonify(error="Blocked: requests must come from the Strategy Lab page"), 403


@app.errorhandler(413)
def on_too_large(_e):
    return jsonify(error="File too large (limit is 300 MB)"), 413


# ---------------- helpers ----------------
def call_worker(req, timeout):
    """Run user code in a separate process; returns its JSON answer plus its console output."""
    req["db"] = db.DB_PATH
    try:
        p = subprocess.run([sys.executable, WORKER], input=json.dumps(req), capture_output=True,
                           text=True, encoding="utf-8", timeout=timeout, cwd=BASE)
    except subprocess.TimeoutExpired:
        raise CodeError("The strategy ran longer than %d seconds and was stopped." % timeout)
    log = (p.stderr or "")[-4000:]
    lines = (p.stdout or "").strip().splitlines()
    if not lines:
        raise CodeError("The strategy process crashed.", log=log)
    out = json.loads(lines[-1])
    out["log"] = log
    return out


def need_ok(out):
    if not out.get("ok"):
        raise CodeError(out.get("error", "Strategy failed"), out.get("line"), out.get("log", ""))
    return out


def dataset_or_404(ds_id):
    ds = db.query("SELECT * FROM datasets WHERE id = ?", (ds_id,), one=True)
    if ds is None:
        raise LookupError("Dataset not found")
    return ds


def ds_json(r):
    d = dict(r)
    d["meta"] = json.loads(d["meta"]) if d.get("meta") else {}
    d.pop("path", None)
    return d


def strategy_row(sid):
    row = db.query("SELECT * FROM strategies WHERE id = ?", (sid,), one=True)
    if row is None:
        raise LookupError("Strategy not found")
    return row


def strategy_json(r, with_code=False):
    d = {"id": r["id"], "name": r["name"], "params": json.loads(r["params"]), "updated_at": r["updated_at"]}
    if with_code:
        d["code"] = r["code"]
    return d


def run_row(run_id):
    row = db.query("SELECT * FROM runs WHERE id = ?", (run_id,), one=True)
    if row is None:
        raise LookupError("Run not found")
    return row


def run_json(row):
    d = dict(row)
    d["params"] = json.loads(d["params"])
    d["result"] = json.loads(d["result"])
    d["has_code"] = bool(d.pop("code", None))
    return d


# ---------------- pages ----------------
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------- data library ----------------
TF_ORDER = list(engine.TF_SECONDS)


@app.get("/api/datasets")
def list_datasets():
    rows = [ds_json(r) for r in db.query("SELECT * FROM datasets")]
    rows.sort(key=lambda d: (d["symbol"] or "", TF_ORDER.index(d["timeframe"]) if d["timeframe"] in TF_ORDER else 99))
    return jsonify(rows)


@app.post("/api/datasets")
def upload_dataset():
    f = request.files.get("file")
    if f is None or not f.filename:
        raise ValueError("Choose a CSV file to upload")
    tmp = os.path.join(DATA, "upload_" + uuid.uuid4().hex + ".csv")
    f.save(tmp)
    try:
        df = engine.load_csv(tmp)
    except ValueError:
        raise
    except Exception:
        raise ValueError("Could not read that file as OHLC price data")
    finally:
        os.remove(tmp)
    detected = engine.detect_timeframe(df)
    symbol = (request.form.get("symbol") or "").strip().upper() or engine.guess_symbol(f.filename)
    if not symbol or not re.fullmatch(r"[A-Z0-9#.]{2,20}", symbol):
        raise ValueError("Could not read the symbol from the file name. Type it in the Symbol box.")
    label = (request.form.get("timeframe") or "").strip().upper() or engine.guess_timeframe(f.filename) or detected
    if label != detected:
        raise ValueError("%s looks like %s data but is labelled %s" % (f.filename, detected, label))
    return jsonify(library.add_bars(db.conn(), symbol, detected, df, "upload")), 201


@app.post("/api/datasets/synthetic")
def add_synthetic():
    seed = int((request.get_json(silent=True) or {}).get("seed", 1))
    return jsonify(library.add_bars(db.conn(), "RANDOM%d" % seed, "H1", engine.synthetic(seed=seed), "synthetic")), 201


@app.delete("/api/datasets/<int:ds_id>")
def delete_dataset(ds_id):
    dataset_or_404(ds_id)
    db.execute("DELETE FROM datasets WHERE id = ?", (ds_id,))  # candles cascade; past runs are kept
    return jsonify(ok=True)


@app.get("/api/datasets/<int:ds_id>/candles")
def dataset_candles(ds_id):
    dataset_or_404(ds_id)
    start = max(0, request.args.get("start", 0, type=int))
    count = min(5000, max(1, request.args.get("count", 2000, type=int)))
    rows = db.conn().execute("SELECT ts, open, high, low, close FROM candles WHERE dataset_id = ? "
                             "ORDER BY ts LIMIT ? OFFSET ?", (ds_id, count, start)).fetchall()
    return jsonify(start=start, rows=[list(r) for r in rows])


# ---------------- strategies (the code IDE) ----------------
@app.get("/api/strategies")
def list_strategies():
    return jsonify([strategy_json(r) for r in db.query("SELECT * FROM strategies ORDER BY name COLLATE NOCASE")])


@app.get("/api/strategies/templates")
def strategy_templates():
    return jsonify(TEMPLATES)


@app.post("/api/strategies/check")
def check_strategy():
    b = request.get_json(silent=True) or {}
    code = b.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Write some code first")
    ds_id = b.get("dataset_id")
    if ds_id:
        dataset_or_404(ds_id)
    out = call_worker({"op": "check", "code": code, "dataset_id": ds_id, "max_bars": 4000}, 90)
    return jsonify(out)


def save_strategy(sid, data):
    name = (data.get("name") or "").strip()[:60] or "Untitled strategy"
    code = data.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Strategy code is empty")
    if len(code) > 200_000:
        raise ValueError("Strategy code is too long")
    info = call_worker({"op": "inspect", "code": code}, 30)
    params = json.dumps(info["params"]) if info.get("ok") else None  # keep old params if the code is broken
    if sid is None:
        sid = db.execute("INSERT INTO strategies(name, code, params) VALUES (?,?,?)", (name, code, params or "[]"))
    else:
        strategy_row(sid)
        db.execute("UPDATE strategies SET name = ?, code = ?, params = COALESCE(?, params), "
                   "updated_at = CURRENT_TIMESTAMP WHERE id = ?", (name, code, params, sid))
    return jsonify(strategy=strategy_json(strategy_row(sid), True), check=info)


@app.post("/api/strategies")
def create_strategy():
    return save_strategy(None, request.get_json(silent=True) or {}), 201


@app.get("/api/strategies/<int:sid>")
def get_strategy(sid):
    return jsonify(strategy_json(strategy_row(sid), True))


@app.put("/api/strategies/<int:sid>")
def update_strategy(sid):
    return save_strategy(sid, request.get_json(silent=True) or {})


@app.delete("/api/strategies/<int:sid>")
def delete_strategy(sid):
    strategy_row(sid)
    db.execute("DELETE FROM strategies WHERE id = ?", (sid,))
    return jsonify(ok=True)


# ---------------- runs ----------------
@app.post("/api/runs")
def create_run():
    b = request.get_json(silent=True) or {}
    ds = dataset_or_404(b.get("dataset_id"))
    strat = strategy_row(b.get("strategy_id"))
    try:
        cost, split = float(b.get("cost", 0.35)), float(b.get("split", 0.7))
    except (TypeError, ValueError):
        raise ValueError("Cost and split must be numbers")
    mode = b.get("mode", "validate")
    if not 0 <= cost <= 1000:
        raise ValueError("Cost must be between 0 and 1000")
    if not 0.3 <= split <= 0.9:
        raise ValueError("In-sample share must be between 30% and 90%")
    if mode not in ("quick", "validate"):
        raise ValueError("Unknown mode")

    out = need_ok(call_worker({"op": "run", "code": strat["code"], "dataset_id": ds["id"],
                               "params": b.get("params") or {}, "cost": cost, "split": split,
                               "mode": mode}, 1800))
    res = out["result"]
    trades, chosen = res.pop("trades"), res["chosen"]
    run_id = db.execute(
        "INSERT INTO runs(dataset_id, dataset_name, strategy_id, strategy_name, strategy_type, mode, params, "
        "cost, split, verdict, oos_exp, oos_n, result, code) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ds["id"], ds["name"], strat["id"], strat["name"], "custom", mode, json.dumps(chosen["params"]),
         cost, split, res["verdict"], chosen["oos"]["exp"], chosen["oos"]["n"], json.dumps(res), strat["code"]))
    db.executemany(
        "INSERT INTO trades(run_id, ts_entry, ts_exit, side, entry, exit, r, segment, sl, tp) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)", [[run_id] + t for t in trades])
    j = run_json(run_row(run_id))
    j["log"] = out["log"]
    return jsonify(j), 201


@app.get("/api/runs")
def list_runs():
    rows = db.query("SELECT id, created_at, dataset_name, strategy_name, mode, verdict, oos_exp, oos_n, params "
                    "FROM runs ORDER BY id DESC LIMIT 200")
    out = []
    for r in rows:
        d = dict(r)
        d["params"] = json.loads(d["params"])
        out.append(d)
    return jsonify(out)


@app.get("/api/runs/<int:run_id>")
def get_run(run_id):
    return jsonify(run_json(run_row(run_id)))


@app.delete("/api/runs/<int:run_id>")
def delete_run(run_id):
    run_row(run_id)
    db.execute("DELETE FROM runs WHERE id = ?", (run_id,))  # trades cascade
    return jsonify(ok=True)


@app.get("/api/runs/<int:run_id>/trades.csv")
def run_trades_csv(run_id):
    run_row(run_id)
    rows = db.query("SELECT ts_entry, ts_exit, side, entry, exit, r, segment, sl, tp FROM trades "
                    "WHERE run_id = ? ORDER BY id", (run_id,))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["entry_time", "exit_time", "side", "entry", "exit", "r_multiple", "segment", "stop", "target"])
    for r in rows:
        w.writerow(list(r))
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=run_%d_trades.csv" % run_id})


# ---------------- visual replay ----------------
@app.get("/api/runs/<int:run_id>/replay")
def run_replay(run_id):
    run = run_row(run_id)
    if run["dataset_id"] is None:
        raise ValueError("The data for this run was deleted, so it cannot be replayed")
    ds = dataset_or_404(run["dataset_id"])
    ts = [r[0] for r in db.conn().execute("SELECT ts FROM candles WHERE dataset_id = ? ORDER BY ts", (ds["id"],))]
    trades = []
    for r in db.query("SELECT ts_entry, ts_exit, side, entry, exit, r, segment, sl, tp FROM trades "
                      "WHERE run_id = ? ORDER BY id", (run_id,)):
        i, j = bisect.bisect_left(ts, r["ts_entry"]), bisect.bisect_left(ts, r["ts_exit"])
        if i < len(ts) and j < len(ts) and ts[i] == r["ts_entry"] and ts[j] == r["ts_exit"]:
            trades.append({"i": i, "j": j, "side": r["side"], "entry": r["entry"], "exit": r["exit"],
                           "r": r["r"], "seg": r["segment"], "sl": r["sl"], "tp": r["tp"]})
    split_at = json.loads(run["result"]).get("split_at") or ""
    return jsonify(run_id=run_id, dataset_id=ds["id"], symbol=ds["symbol"], timeframe=ds["timeframe"],
                   n_bars=len(ts), split_idx=bisect.bisect_left(ts, split_at), trades=trades,
                   verdict=run["verdict"], strategy_name=run["strategy_name"] or "Trend Pullback")


@app.get("/api/runs/<int:run_id>/plots")
def run_plots(run_id):
    run = run_row(run_id)
    if run["dataset_id"] is None:
        return jsonify(series={})
    code = run["code"] or TEMPLATES[0]["code"]  # v1 runs had no code snapshot: they were Trend Pullback
    out = need_ok(call_worker({"op": "plots", "code": code, "dataset_id": run["dataset_id"],
                               "params": json.loads(run["params"])}, 120))
    return jsonify(series=out["series"])


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)