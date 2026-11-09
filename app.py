# Strategy Lab - Flask server
# ONLINE: full Lab (Test / Visual / Strategies / Data / History + Pine Send)
# OFFLINE: static files + pine.js are cached by sw.js, Pine converter keeps working
# Pine conversion is 100% frontend in static/pine.js - no Python needed for it.
import os
import json
import io
import csv
import traceback
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, Response, g

import db
import worker
import library
import templates
from engine import run_test

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE, "static")
TEMPLATES_DIR = os.path.join(BASE, "templates")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB uploads
app.config["JSON_SORT_KEYS"] = False

# ---------- helpers ----------

def require_lab():
    # Simple CSRF check for mutating calls from browser - matches app.js X-Lab header
    # GETs are open, POST/DELETE need the header so random sites can't call us
    if request.method != "GET" and request.headers.get("X-Lab") != "1":
        # Allow FormData uploads from same page (browser sends no X-Lab on multipart in some cases)
        # but still require Origin check if present
        origin = request.headers.get("Origin", "")
        host = request.headers.get("Host", "")
        if origin and host and host not in origin:
            return False
    return True

def err(msg, code=400, extra=None):
    payload = {"error": str(msg)}
    if extra:
        payload.update(extra)
    return jsonify(payload), code

def get_db():
    if "db" not in g:
        g.db = db.connect()
    return g.db

@app.teardown_appcontext
def close_db(exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

# ---------- pages / offline files ----------

@app.route("/")
def index():
    # Serve the single-page app
    return send_from_directory(TEMPLATES_DIR, "index.html")

@app.route("/static/sw.js")
def sw():
    # Service Worker MUST be served from /static/ with correct MIME + no cache
    # This is what makes offline work: it caches / + style.css + app.js + pine.js
    path = os.path.join(STATIC_DIR, "sw.js")
    if not os.path.exists(path):
        return err("sw.js not found - create static/sw.js from the update", 404)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    resp = Response(content, mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp

@app.route("/static/manifest.json")
def manifest():
    path = os.path.join(STATIC_DIR, "manifest.json")
    if not os.path.exists(path):
        # Fallback so PWA install doesn't break if file missing
        return jsonify({
            "name": "Strategy Lab",
            "short_name": "Lab",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0d1117",
            "theme_color": "#0d1117",
            "icons": []
        })
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return Response(content, mimetype="application/manifest+json")

@app.route("/api/health")
def health():
    # Used by frontend to show Online / Offline badge + to test server
    # Also used by sw.js to decide if API is reachable
    try:
        conn = get_db()
        n_ds = db.count_datasets(conn)
        n_strat = db.count_strategies(conn)
        return jsonify({"ok": True, "online": True, "datasets": n_ds, "strategies": n_strat, "time": datetime.utcnow().isoformat()})
    except Exception as e:
        return jsonify({"ok": False, "online": False, "error": str(e)}), 500

# ---------- datasets ----------

@app.route("/api/datasets", methods=["GET"])
def list_datasets():
    conn = get_db()
    rows = db.list_datasets(conn)
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "symbol": r["symbol"],
            "timeframe": r["timeframe"],
            "kind": r.get("kind", "csv"),
            "first_bar": r.get("first_bar"),
            "last_bar": r.get("last_bar"),
            "bars": r.get("bars", 0),
            "meta": json.loads(r["meta"]) if r.get("meta") else {},
        })
    return jsonify(out)

@app.route("/api/datasets", methods=["POST"])
def upload_dataset():
    if not require_lab():
        return err("Forbidden", 403)
    if "file" not in request.files:
        return err("No file uploaded")
    f = request.files["file"]
    symbol = (request.form.get("symbol") or "").strip().upper()
    timeframe = (request.form.get("timeframe") or "").strip().upper()
    if not f or not f.filename:
        return err("Empty file")
    try:
        raw = f.read()
        # Decode - MT5 CSVs are often utf-16 / latin-1
        text = None
        for enc in ("utf-8-sig", "utf-16", "latin-1"):
            try:
                text = raw.decode(enc)
                if "date" in text.lower() or "," in text[:500]:
                    break
            except Exception:
                continue
        if text is None:
            text = raw.decode("utf-8", errors="ignore")
        conn = get_db()
        result = library.import_csv(conn, text, f.filename, symbol_hint=symbol, tf_hint=timeframe)
        conn.commit()
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return err(f"Could not read CSV: {e}")

@app.route("/api/datasets/synthetic", methods=["POST"])
def synthetic_dataset():
    if not require_lab():
        return err("Forbidden", 403)
    data = request.get_json(silent=True) or {}
    seed = int(data.get("seed", 1))
    try:
        conn = get_db()
        result = library.add_synthetic(conn, seed=seed)
        conn.commit()
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return err(str(e))

@app.route("/api/datasets/<int:ds_id>", methods=["DELETE"])
def delete_dataset(ds_id):
    if not require_lab():
        return err("Forbidden", 403)
    conn = get_db()
    db.delete_dataset(conn, ds_id)
    conn.commit()
    return jsonify({"ok": True})

# ---------- strategies ----------

@app.route("/api/strategies", methods=["GET"])
def list_strategies():
    conn = get_db()
    rows = db.list_strategies(conn)
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "name": r["name"],
            "code": r["code"],
            "params": json.loads(r["params"]) if r.get("params") else [],
            "created_at": r.get("created_at"),
        })
    return jsonify(out)

@app.route("/api/strategies", methods=["POST"])
def create_strategy():
    # Used by BOTH:
    # 1. IDE -> Save / Create
    # 2. Pine -> Py -> "Send to Strategies" (online only)
    if not require_lab():
        return err("Forbidden", 403)
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "Untitled").strip()[:60] or "Untitled"
    code = data.get("code") or ""
    if not code.strip():
        return err("Empty code")
    # Validate + extract PARAMS via engine (also catches syntax errors early)
    try:
        parsed = worker.parse_strategy(code)
    except Exception as e:
        return err(f"Strategy error: {e}", 400, extra={"line": getattr(e, "line", None)})
    conn = get_db()
    sid = db.create_strategy(conn, name, code, parsed.get("params", []))
    conn.commit()
    return jsonify({"id": sid, "name": name, "params": parsed.get("params", [])})

@app.route("/api/strategies/<int:sid>", methods=["GET"])
def get_strategy(sid):
    conn = get_db()
    r = db.get_strategy(conn, sid)
    if not r:
        return err("Strategy not found", 404)
    return jsonify({
        "id": r["id"],
        "name": r["name"],
        "code": r["code"],
        "params": json.loads(r["params"]) if r.get("params") else [],
    })

@app.route("/api/strategies/<int:sid>", methods=["PUT", "POST"])
def update_strategy(sid):
    if not require_lab():
        return err("Forbidden", 403)
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    code = data.get("code")
    conn = get_db()
    r = db.get_strategy(conn, sid)
    if not r:
        return err("Strategy not found", 404)
    if code is not None:
        try:
            parsed = worker.parse_strategy(code)
        except Exception as e:
            return err(f"Strategy error: {e}", 400, extra={"line": getattr(e, "line", None)})
        db.update_strategy(conn, sid, name=name, code=code, params=parsed.get("params", []))
    elif name is not None:
        db.update_strategy(conn, sid, name=name)
    conn.commit()
    return jsonify({"ok": True, "id": sid})

@app.route("/api/strategies/<int:sid>", methods=["DELETE"])
def delete_strategy(sid):
    if not require_lab():
        return err("Forbidden", 403)
    conn = get_db()
    db.delete_strategy(conn, sid)
    conn.commit()
    return jsonify({"ok": True})

@app.route("/api/strategies/<int:sid>/check", methods=["POST"])
def check_strategy(sid):
    # IDE -> Check code: runs strategy on a slice, returns errors / log
    if not require_lab():
        return err("Forbidden", 403)
    data = request.get_json(silent=True) or {}
    code = data.get("code")
    conn = get_db()
    if code is None:
        r = db.get_strategy(conn, sid)
        if not r:
            return err("Strategy not found", 404)
        code = r["code"]
    try:
        result = worker.check_code(conn, code, data.get("dataset_id"))
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return err(str(e), 400, extra={"line": getattr(e, "line", None), "log": getattr(e, "log", "")})

@app.route("/api/templates", methods=["GET"])
def list_templates():
    return jsonify(templates.all_templates())

# ---------- runs / tests ----------

@app.route("/api/runs", methods=["GET"])
def list_runs():
    conn = get_db()
    rows = db.list_runs(conn)
    out = []
    for r in rows:
        res = json.loads(r["result"]) if r.get("result") else {}
        ch = (res.get("chosen") or {})
        oos = (ch.get("oos") or {})
        out.append({
            "id": r["id"],
            "created_at": r.get("created_at"),
            "strategy_name": r.get("strategy_name"),
            "dataset_name": r.get("dataset_name"),
            "mode": r.get("mode"),
            "verdict": res.get("verdict", ""),
            "oos_n": oos.get("n", 0),
            "oos_exp": oos.get("exp"),
        })
    return jsonify(out)

@app.route("/api/runs", methods=["POST"])
def create_run():
    if not require_lab():
        return err("Forbidden", 403)
    data = request.get_json(silent=True) or {}
    try:
        dataset_id = int(data.get("dataset_id"))
        strategy_id = int(data.get("strategy_id"))
    except Exception:
        return err("Missing dataset_id / strategy_id")
    params = data.get("params") or {}
    mode = data.get("mode") or "validate"
    try:
        cost = float(data.get("cost", 0))
    except Exception:
        cost = 0
    try:
        split = float(data.get("split", 0.7))
    except Exception:
        split = 0.7
    conn = get_db()
    try:
        run = run_test(conn, dataset_id, strategy_id, params, mode, cost, split)
        conn.commit()
        return jsonify(run)
    except Exception as e:
        traceback.print_exc()
        return err(str(e), 400, extra={"line": getattr(e, "line", None), "log": getattr(e, "log", "")})

@app.route("/api/runs/<int:run_id>", methods=["GET"])
def get_run(run_id):
    conn = get_db()
    r = db.get_run(conn, run_id)
    if not r:
        return err("Run not found", 404)
    res = json.loads(r["result"]) if r.get("result") else {}
    return jsonify({
        "id": r["id"],
        "created_at": r.get("created_at"),
        "strategy_name": r.get("strategy_name"),
        "dataset_name": r.get("dataset_name"),
        "result": res,
        "log": r.get("log", ""),
    })

@app.route("/api/runs/<int:run_id>", methods=["DELETE"])
def delete_run(run_id):
    if not require_lab():
        return err("Forbidden", 403)
    conn = get_db()
    db.delete_run(conn, run_id)
    conn.commit()
    return jsonify({"ok": True})

@app.route("/api/runs/<int:run_id>/trades.csv", methods=["GET"])
def run_trades_csv(run_id):
    conn = get_db()
    r = db.get_run(conn, run_id)
    if not r:
        return err("Run not found", 404)
    res = json.loads(r["result"]) if r.get("result") else {}
    trades = res.get("trades") or []
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["trade", "entry_time", "exit_time", "side", "entry", "exit", "sl", "tp", "pnl_R", "oos"])
    for t in trades:
        w.writerow([t.get("n"), t.get("entry_time"), t.get("exit_time"), t.get("side"), t.get("entry"), t.get("exit"), t.get("sl"), t.get("tp"), t.get("pnl"), t.get("oos")])
    resp = Response(out.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f"attachment; filename=trades_{run_id}.csv"
    return resp

# ---------- boot ----------

def ensure_seed():
    # First run: create DB + seed default strategies if empty
    conn = db.connect()
    try:
        db.init_db(conn)
        if db.count_strategies(conn) == 0:
            for t in templates.all_templates():
                try:
                    parsed = worker.parse_strategy(t["code"])
                    db.create_strategy(conn, t["name"], t["code"], parsed.get("params", []))
                except Exception as e:
                    print(f"Seed template failed {t['name']}: {e}")
            conn.commit()
            print(f"Seeded {db.count_strategies(conn)} strategies")
    finally:
        conn.close()

if __name__ == "__main__":
    ensure_seed()
    port = int(os.environ.get("PORT", "5000"))
    print(f"Strategy Lab running at http://127.0.0.1:{port}")
    print("Online: full Lab. Offline: Pine converter still works (cached by sw.js).")
    # threaded=True so long backtests don't block UI
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)