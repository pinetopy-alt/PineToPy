"""Strategy Lab engine: data helpers, indicator helpers, strategy loader, simulator, validation."""
import itertools
import os
import re

import numpy as np
import pandas as pd

OHLC = ("open", "high", "low", "close")
TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400, "W1": 604800}
MAX_COMBOS = 500
TS_FMT = "%Y-%m-%d %H:%M:%S"


def fmt_ts(ts):
    return pd.Timestamp(ts).strftime(TS_FMT)


# ---------------- data ----------------
def load_csv(path):
    """Load an OHLC csv (MT5 export or generic time,open,high,low,close)."""
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [str(c).strip("<>").strip().lower() for c in df.columns]
    missing = [k for k in OHLC if k not in df.columns]
    if missing:
        raise ValueError("CSV is missing columns: " + ", ".join(missing))
    if "date" in df.columns and "time" in df.columns:
        ts = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), errors="coerce")
    else:
        tcol = next((c for c in ("time", "datetime", "timestamp", "date") if c in df.columns), None)
        if tcol is None:
            raise ValueError("CSV needs a date/time column")
        ts = pd.to_datetime(df[tcol], errors="coerce")
    out = pd.DataFrame({k: pd.to_numeric(df[k], errors="coerce") for k in OHLC})
    out.index = ts
    out = out[out.index.notna()].dropna()
    out = out[~out.index.duplicated()].sort_index()
    if len(out) < 500:
        raise ValueError("Need at least 500 bars of data (got %d)" % len(out))
    return out


def detect_timeframe(df):
    d = np.diff(df.index.values).astype("timedelta64[s]").astype(np.int64)
    d = d[d > 0]
    if not len(d):
        raise ValueError("Could not read the bar spacing from this file")
    vals, counts = np.unique(d, return_counts=True)
    sec = int(vals[counts.argmax()])
    for name, s in TF_SECONDS.items():
        if s == sec:
            return name
    raise ValueError("Unsupported timeframe: most bars are %d seconds apart (supported: %s)"
                     % (sec, ", ".join(TF_SECONDS)))


def _tokens(name):
    base = re.sub(r"\.(csv|txt)$", "", os.path.basename(str(name)).strip(), flags=re.I)
    return [t for t in re.split(r"[_,\s\-]+", base) if t]


def guess_symbol(name):
    toks = _tokens(name)
    if not toks:
        return None
    s = re.sub(r"[^A-Za-z0-9#.]", "", toks[0]).upper()
    return s if re.fullmatch(r"[A-Z0-9#.]{2,20}", s) else None


def guess_timeframe(name):
    return next((t.upper() for t in _tokens(name)[1:] if t.upper() in TF_SECONDS), None)


def synthetic(n=20000, seed=0, start=1900.0):
    """Random-walk candles. Any strategy that 'works' here is fooling itself."""
    rng = np.random.default_rng(seed)
    vol = np.clip(1.5 * np.exp(0.3 * np.cumsum(rng.normal(0, 0.02, n))), 0.5, 5.0)
    close = start + np.cumsum(rng.normal(0, 1, n) * vol)
    open_ = np.r_[start, close[:-1]]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.6, n)) * vol
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.6, n)) * vol
    idx = pd.date_range("2022-01-01", periods=n, freq="h")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


# ---------------- helpers available inside strategy code ----------------
def ema(s, n):
    return s.ewm(span=int(n), adjust=False).mean()


def sma(s, n):
    return s.rolling(int(n)).mean()


def atr(df, n=14):
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(int(n)).mean()


def rsi(s, n=14):
    delta = s.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    out = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    return out.where(dn != 0, 100.0)


def highest(s, n):
    return s.rolling(int(n)).max()


def lowest(s, n):
    return s.rolling(int(n)).min()


def _pair(a, b):
    like = a if isinstance(a, pd.Series) else b
    mk = lambda x: x if isinstance(x, pd.Series) else pd.Series(x, index=like.index)
    return mk(a), mk(b)


def crossover(a, b):
    a, b = _pair(a, b)
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossunder(a, b):
    a, b = _pair(a, b)
    return (a < b) & (a.shift(1) >= b.shift(1))


HELPERS = {f.__name__: f for f in (ema, sma, atr, rsi, highest, lowest, crossover, crossunder)}


# ---------------- strategy loader ----------------
def _param_defs(raw):
    if not isinstance(raw, dict):
        raise ValueError("PARAMS must be a dict like {'length': {'default': 20}}")
    out = []
    for key, d in raw.items():
        if not isinstance(d, dict) or "default" not in d:
            raise ValueError("PARAMS['%s'] needs a 'default' value" % key)
        dv = d["default"]
        if isinstance(dv, bool) or not isinstance(dv, (int, float)):
            raise ValueError("PARAMS['%s']['default'] must be a number" % key)
        typ = "int" if isinstance(dv, int) else "float"
        cast = int if typ == "int" else float
        grid = d.get("grid")
        if grid is not None:
            grid = [cast(g) for g in grid]
        out.append({"key": str(key), "label": str(key).replace("_", " ").capitalize(), "type": typ,
                    "default": dv, "min": d.get("min"), "max": d.get("max"),
                    "step": d.get("step", 1 if typ == "int" else 0.1), "grid": grid})
    return out


class Strategy:
    """Wraps user code. The code must define signals(df, p) and may define PARAMS, MAX_HOLD,
    WARMUP, valid(p) and plots(df, p)."""

    def __init__(self, code):
        ns = {"__name__": "strategy", "np": np, "pd": pd}
        ns.update(HELPERS)
        exec(compile(code, "<strategy>", "exec"), ns)
        if not callable(ns.get("signals")):
            raise ValueError("Your code must define a function signals(df, p)")
        self.ns = ns
        self.defs = _param_defs(ns.get("PARAMS") or {})
        self.max_hold = int(ns.get("MAX_HOLD", 48))
        self.warmup = int(ns.get("WARMUP", 100))
        if self.max_hold < 1 or self.warmup < 0:
            raise ValueError("MAX_HOLD must be 1 or more and WARMUP 0 or more")

    def valid(self, p):
        fn = self.ns.get("valid")
        return True if not callable(fn) else bool(fn(p))

    def get_signals(self, df, p):
        out = self.ns["signals"](df, p)
        if not isinstance(out, (dict, pd.DataFrame)):
            raise ValueError("signals() must return a dict with 'side' and 'sl' (and optionally 'tp')")
        n = len(df)

        def arr(name, required):
            if name not in out:
                if required:
                    raise ValueError("signals() result is missing '%s'" % name)
                return np.zeros(n)
            a = np.asarray(out[name], dtype=float)
            if a.ndim == 0:
                a = np.full(n, float(a))
            if a.shape != (n,):
                raise ValueError("'%s' needs one value per bar (%d), got shape %s" % (name, n, a.shape))
            return np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)

        return np.sign(arr("side", True)), arr("sl", True), arr("tp", False)

    def run(self, df, p, cost):
        side, sl, tp = self.get_signals(df, p)
        return simulate(df, side, sl, tp, cost, int(p.get("max_hold", self.max_hold)), self.warmup)


def clean_params(strat, raw):
    out = {}
    for d in strat.defs:
        v = raw.get(d["key"], d["default"])
        try:
            v = int(float(v)) if d["type"] == "int" else float(v)
        except (TypeError, ValueError):
            raise ValueError("%s must be a number" % d["label"])
        if not np.isfinite(v):
            raise ValueError("%s must be a finite number" % d["label"])
        if d["min"] is not None and v < d["min"] or d["max"] is not None and v > d["max"]:
            raise ValueError("%s must be between %s and %s" % (d["label"], d["min"], d["max"]))
        out[d["key"]] = v
    if not strat.valid(out):
        raise ValueError("These settings are rejected by the strategy's valid() rule")
    return out


# ---------------- simulator ----------------
def simulate(df, side, sl, tp, cost, max_hold, warmup):
    """Signal on bar close, entry at the NEXT bar's open, stop and optional target, one trade at a
    time. If stop and target are both hit inside one bar the stop is assumed first (conservative).
    r = profit in multiples of the risk (entry to stop distance), after costs."""
    o, h, l, c = (df[k].to_numpy() for k in OHLC)
    n = len(df)
    idx = np.flatnonzero((side != 0) & (sl > 0))
    idx = idx[(idx >= warmup) & (idx < n - 1)]
    trades, pos = [], 0
    while pos < len(idx):
        i, s = int(idx[pos]), int(side[idx[pos]])
        entry, risk = o[i + 1], sl[i]
        stop = entry - s * risk
        target = entry + s * tp[i] if tp[i] > 0 else None
        j = min(i + max_hold, n - 1)
        exit_px = c[j]
        for k in range(i + 1, min(i + 1 + max_hold, n)):
            if s == 1:
                if l[k] <= stop:
                    exit_px, j = stop, k
                    break
                if target is not None and h[k] >= target:
                    exit_px, j = target, k
                    break
            else:
                if h[k] >= stop:
                    exit_px, j = stop, k
                    break
                if target is not None and l[k] <= target:
                    exit_px, j = target, k
                    break
        r = ((exit_px - entry) * s - cost) / risk
        trades.append({"i": i + 1, "j": j, "side": s, "entry": float(entry), "exit": float(exit_px),
                       "r": float(r), "sl": float(stop), "tp": None if target is None else float(target)})
        pos = int(np.searchsorted(idx, j, side="right"))
    return trades


def lookahead_check(strat, df, p, side, sl):
    """Re-run signals() with the future hidden at random cut points. If an earlier bar's signal
    changes, the code is peeking at the future and any result is fake."""
    n, lo = len(df), strat.warmup + 50
    if n < lo + 60:
        return {"ok": True, "detail": "Too little data to run the no-peeking test"}
    rng = np.random.default_rng(7)
    try:
        for k in sorted({int(x) for x in rng.integers(lo, n - 5, size=3)}):
            side2, sl2, _ = strat.get_signals(df.iloc[:k], p)
            w = slice(strat.warmup, k)
            diff = np.flatnonzero(side[w] != side2[w])
            if len(diff):
                b = int(diff[0]) + strat.warmup
                return {"ok": False, "detail": "The signal on bar %d (%s) changes when later bars are hidden. "
                        "Your code uses future data (look for shift(-1), whole-series max/min/mean, or centered windows)."
                        % (b, fmt_ts(df.index[b]))}
            m = side[w] != 0
            if not np.allclose(sl[w][m], sl2[w][m], rtol=1e-6, atol=1e-9):
                return {"ok": False, "detail": "The stop distance changes when later bars are hidden. Your code uses future data."}
    except Exception as e:
        return {"ok": False, "detail": "signals() failed on shortened data (%s: %s)" % (type(e).__name__, e)}
    return {"ok": True, "detail": "Signals identical with the future hidden (3 random cut points)"}


# ---------------- statistics ----------------
def stats(rs):
    rs = np.asarray(rs, dtype=float)
    n = len(rs)
    if n == 0:
        return {"n": 0, "exp": 0.0, "pf": 0.0, "win": 0.0, "tot": 0.0, "dd": 0.0}
    gains, losses = rs[rs > 0].sum(), -rs[rs < 0].sum()
    eq = np.cumsum(rs)
    dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    return {"n": n, "exp": rs.mean(), "pf": (gains / losses if losses > 0 else np.inf),
            "win": (rs > 0).mean(), "tot": eq[-1], "dd": dd}


def boot_p(rs, n_boot=5000, seed=1):
    """Bootstrap estimate of P(true expectancy <= 0)."""
    rs = np.asarray(rs, dtype=float)
    if len(rs) < 5:
        return 1.0
    rng = np.random.default_rng(seed)
    return float((rng.choice(rs, (n_boot, len(rs))).mean(axis=1) <= 0).mean())


def sanitize(o):
    """Make results JSON-safe (numpy types, inf/nan -> None)."""
    if isinstance(o, dict):
        return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    if isinstance(o, (float, np.floating)):
        v = float(o)
        return v if np.isfinite(v) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def _split(trades, cut):
    return [t["r"] for t in trades if t["i"] < cut], [t["r"] for t in trades if t["i"] >= cut]


def _curve(trades, df, cut):
    eq, pts = 0.0, []
    for n, t in enumerate(trades, 1):
        eq += t["r"]
        pts.append([n, round(eq, 4), fmt_ts(df.index[t["i"]])[:16], int(t["i"] >= cut)])
    return pts


def _trade_rows(trades, df, cut):
    return [[fmt_ts(df.index[t["i"]]), fmt_ts(df.index[t["j"]]), t["side"], t["entry"], t["exit"], t["r"],
             "oos" if t["i"] >= cut else "is", t["sl"], t["tp"]] for t in trades]


# ---------------- runs ----------------
def quick(df, strat, params, cost, split):
    """One settings set, in-sample vs out-of-sample. Informational only, not proof."""
    cut = int(len(df) * split)
    side, sl, tp = strat.get_signals(df, params)
    trades = simulate(df, side, sl, tp, cost, int(params.get("max_hold", strat.max_hold)), strat.warmup)
    is_r, oos_r = _split(trades, cut)
    return {
        "mode": "quick", "verdict": "SINGLE TEST (NOT PROOF)",
        "split_at": fmt_ts(df.index[cut]), "bars": len(df),
        "lookahead": lookahead_check(strat, df, params, side, sl),
        "chosen": {"params": params, "is": stats(is_r), "oos": stats(oos_r)},
        "curve": _curve(trades, df, cut), "trades": _trade_rows(trades, df, cut),
    }


def validate(df, strat, base, cost, split, min_is_trades=30):
    """Search the PARAMS grids on in-sample data only, test the winner once out-of-sample,
    and judge it with strict checks."""
    cut = int(len(df) * split)
    axes = {}
    for d in strat.defs:
        vals = [base[d["key"]]]
        if d["grid"]:
            vals = sorted(set(d["grid"] + vals))
        axes[d["key"]] = vals
    total = int(np.prod([len(v) for v in axes.values()])) if axes else 1
    if total > MAX_COMBOS:
        raise ValueError("Too many setting combinations (%d, limit %d). Remove some grid values." % (total, MAX_COMBOS))
    keys, rows = list(axes), []
    for combo in itertools.product(*axes.values()):
        p = dict(zip(keys, combo))
        if not strat.valid(p):
            continue
        trades = strat.run(df, p, cost)
        is_r, oos_r = _split(trades, cut)
        rows.append({"params": p, "is": stats(is_r), "oos": stats(oos_r), "trades": trades, "oos_r": oos_r})

    eligible = [r for r in rows if r["is"]["n"] >= min_is_trades]
    if not eligible:
        raise ValueError("Not enough in-sample trades (need %d+). Use more data or looser settings." % min_is_trades)
    best = max(eligible, key=lambda r: r["is"]["exp"])
    s_is, s_oos = best["is"], best["oos"]

    pos_is = float(np.mean([r["is"]["exp"] > 0 for r in eligible]))
    el_oos = [r for r in eligible if r["oos"]["n"] >= 20]
    pos_oos = float(np.mean([r["oos"]["exp"] > 0 for r in el_oos])) if el_oos else 0.0
    med_oos = float(np.median([r["oos"]["exp"] for r in el_oos])) if el_oos else 0.0
    p = boot_p(best["oos_r"])
    side, sl, _ = strat.get_signals(df, best["params"])
    look = lookahead_check(strat, df, best["params"], side, sl)

    def chk(name, ok, detail):
        return {"name": name, "pass": bool(ok), "detail": detail}

    checks = [
        chk("No peeking: signals use only past data", look["ok"], "clean" if look["ok"] else "FAILED"),
        chk("At least 100 out-of-sample trades", s_oos["n"] >= 100, "%d trades" % s_oos["n"]),
        chk("Out-of-sample expectancy above +0.05R after costs", s_oos["exp"] > 0.05, "%+.3fR" % s_oos["exp"]),
        chk("Out-of-sample profit factor at least 1.15", s_oos["pf"] >= 1.15,
            "n/a" if not np.isfinite(s_oos["pf"]) else "%.2f" % s_oos["pf"]),
        chk("Bootstrap chance the edge is zero or negative under 1%", p < 0.01, "%.1f%%" % (p * 100)),
        chk("Robust: 60%+ of ALL tested settings profitable out-of-sample", pos_oos >= 0.60, "%.0f%%" % (pos_oos * 100)),
        chk("No collapse: out-of-sample expectancy at least 40% of in-sample", s_oos["exp"] >= 0.4 * s_is["exp"],
            "%+.3fR vs %+.3fR" % (s_oos["exp"], s_is["exp"])),
    ]
    ok = all(c["pass"] for c in checks)
    grid = sorted(({"params": r["params"], "is": r["is"], "oos": r["oos"]} for r in rows),
                  key=lambda r: r["is"]["exp"], reverse=True)
    return {
        "mode": "validate", "verdict": "CANDIDATE EDGE" if ok else "NO PROVEN EDGE",
        "split_at": fmt_ts(df.index[cut]), "bars": len(df), "lookahead": look,
        "chosen": {"params": best["params"], "is": s_is, "oos": s_oos},
        "checks": checks,
        "robustness": {"settings_tested": len(rows), "pos_is": pos_is, "pos_oos": pos_oos,
                       "median_oos_exp": med_oos, "boot_p": p},
        "grid": grid, "curve": _curve(best["trades"], df, cut), "trades": _trade_rows(best["trades"], df, cut),
    }