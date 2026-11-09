"""Runs user strategy code in its own process so a crash or endless loop cannot hurt the app.
Reads one JSON request on stdin, writes one JSON line on stdout. print() output from the
strategy goes to stderr and is shown to you in the app as the strategy console."""
import json
import os
import sqlite3
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_out = sys.stdout
sys.stdout = sys.stderr

import numpy as np  # noqa: E402

import engine  # noqa: E402
import library  # noqa: E402


def user_error(e):
    line = None
    for f in reversed(traceback.extract_tb(e.__traceback__)):
        if f.filename == "<strategy>":
            line = f.lineno
            break
    msg = str(e) if isinstance(e, ValueError) else "%s: %s" % (type(e).__name__, e)
    if isinstance(e, SyntaxError):
        line, msg = e.lineno, "SyntaxError: %s" % e.msg
    return {"ok": False, "error": msg, "line": line}


def r7(x):
    return None if x is None or not np.isfinite(x) else float("%.7g" % x)


def handle(req):
    op = req["op"]
    strat = engine.Strategy(req["code"])
    if op == "inspect":
        return {"ok": True, "params": strat.defs, "max_hold": strat.max_hold, "warmup": strat.warmup,
                "has_plots": callable(strat.ns.get("plots"))}

    con = sqlite3.connect(req["db"], timeout=60)
    if op == "check":
        df = library.load_df(con, req["dataset_id"], limit=req.get("max_bars", 4000)) if req.get("dataset_id") else None
        out = {"ok": True, "params": strat.defs, "max_hold": strat.max_hold, "warmup": strat.warmup,
               "has_plots": callable(strat.ns.get("plots")), "ran": False}
        if df is None:
            return out
        if len(df) <= strat.warmup + 20:
            raise ValueError("WARMUP (%d) is too large for the %d bars used in the check" % (strat.warmup, len(df)))
        p = engine.clean_params(strat, {})
        side, sl, tp = strat.get_signals(df, p)
        trades = engine.simulate(df, side, sl, tp, 0.0, int(p.get("max_hold", strat.max_hold)), strat.warmup)
        out.update(ran=True, bars=len(df), n_signals=int(((side != 0) & (sl > 0))[strat.warmup:].sum()),
                   n_trades=len(trades), lookahead=engine.lookahead_check(strat, df, p, side, sl))
        return out

    df = library.load_df(con, req["dataset_id"])
    params = engine.clean_params(strat, req.get("params") or {})
    if op == "run":
        fn = engine.validate if req.get("mode") == "validate" else engine.quick
        return {"ok": True, "result": fn(df, strat, params, float(req["cost"]), float(req["split"]))}
    if op == "plots":
        fn = strat.ns.get("plots")
        series = {}
        if callable(fn):
            for name, s in list(fn(df, params).items())[:6]:
                a = np.asarray(s, dtype=float)
                if a.shape == (len(df),):
                    series[str(name)[:30]] = [r7(v) for v in a]
        return {"ok": True, "series": series}
    raise ValueError("Unknown operation")


def main():
    try:
        out = handle(json.loads(sys.stdin.read()))
    except Exception as e:  # user code errors are reported, never raised
        out = user_error(e)
    _out.write(json.dumps(engine.sanitize(out)) + "\n")
    _out.flush()


if __name__ == "__main__":
    main()