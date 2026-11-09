# PineToPy - Streamlit version
# Works on Streamlit Cloud - no Flask needed
import re
import streamlit as st

st.set_page_config(page_title="Pine → Py", page_icon="🌲", layout="wide")

# ---------- CONVERTER (same logic as pine.js, ported to Python) ----------
def translate(expr, var_map):
    s = expr
    s = re.sub(r"//.*", "", s)
    s = s.replace("ta.ema(", "ema(").replace("ta.sma(", "sma(").replace("ta.rsi(", "rsi(")
    s = s.replace("ta.atr(", "atr(df, ").replace("ta.highest(", "highest(").replace("ta.lowest(", "lowest(")
    s = s.replace("ta.crossover(", "crossover(").replace("ta.crossunder(", "crossunder(")
    s = s.replace("math.max(", "np.maximum(").replace("math.min(", "np.minimum(").replace("math.abs(", "np.abs(")
    s = re.sub(r"\bclose\b", 'df["close"]', s)
    s = re.sub(r"\bopen\b", 'df["open"]', s)
    s = re.sub(r"\bhigh\b", 'df["high"]', s)
    s = re.sub(r"\blow\b", 'df["low"]', s)
    s = re.sub(r"\bnz\s*\(\s*([^,]+)\s*,\s*([^\)]+)\)", r"(\1).fillna(\2)", s)
    s = re.sub(r"\bna\s*\(\s*([^\)]+)\)", r"pd.isna(\1)", s)
    for k, v in var_map.items():
        s = re.sub(rf"\b{k}\b", v, s)
    s = re.sub(r"\band\b", " & ", s)
    s = re.sub(r"\bor\b", " | ", s)
    s = re.sub(r"\bnot\b", " ~ ", s)
    s = s.replace(":=", "=")
    s = re.sub(r"\btrue\b", "True", s, flags=re.I)
    s = re.sub(r"\bfalse\b", "False", s, flags=re.I)
    return s

def convert(src):
    warnings = []
    code = src or ""
    if not code.strip():
        raise ValueError("Paste some Pine Script first.")
    if not re.search(r"@version\s*=\s*[56]", code):
        warnings.append("No //@version=5 or 6 found - assuming v5/v6.")
    if "request.security" in code or "security(" in code:
        warnings.append("request.security() removed - Lab tests one symbol/timeframe only.")
    if "strategy.order" in code or "strategy.close" in code:
        warnings.append("Complex exits converted to fixed SL/TP only. Check sl/tp.")

    params = {}
    var_map = {}
    for m in re.finditer(r"(\w+)\s*=\s*input\.(int|float|bool)\s*\(\s*([^,\)]+)(?:\s*,\s*\"([^\"]*)\")?[^)]*\)", code):
        name, typ, def_raw, title = m.groups()
        if typ == "bool":
            continue
        is_int = typ == "int"
        try:
            dv = int(def_raw.strip()) if is_int else float(def_raw.strip())
        except:
            continue
        full = m.group(0)
        min_m = re.search(r"minval\s*=\s*([-\d.]+)", full)
        max_m = re.search(r"maxval\s*=\s*([-\d.]+)", full)
        step_m = re.search(r"step\s*=\s*([-\d.]+)", full)
        grid = None
        if min_m and max_m:
            mn, mx = float(min_m.group(1)), float(max_m.group(1))
            st = float(step_m.group(1)) if step_m else (max(1, round((mx-mn)/4)) if is_int else (mx-mn)/4)
            vals = set([dv])
            v = dv - st*2
            while v <= dv + st*2 + 1e-9:
                vv = round(v) if is_int else round(v*100)/100
                if mn <= vv <= mx:
                    vals.add(vv)
                v += st
            grid = sorted(vals)
        key = name.lower()
        params[key] = {"def": dv, "min": float(min_m.group(1)) if min_m else None,
                       "max": float(max_m.group(1)) if max_m else None,
                       "step": float(step_m.group(1)) if step_m else (1 if is_int else 0.1),
                       "grid": grid, "label": title or name}
        var_map[name] = f'p["{key}"]'

    for m in re.finditer(r"(\w+)\s*=\s*input\.bool\s*\(\s*(true|false)", code, re.I):
        var_map[m.group(1)] = "True" if m.group(2).lower() == "true" else "False"

    body = re.sub(r"//@version.*", "", code)
    body = re.sub(r"indicator\s*\(.*?\)|strategy\s*\(.*?\)", "", body, flags=re.S)
    body = re.sub(r"^\s*\w+\s*=\s*input\.[^\n]+\n", "", body, flags=re.M)
    body = re.sub(r"plot\s*\(.*?\)\s*\n?", "", body)
    body = re.sub(r"plotshape\s*\(.*?\)\s*\n?", "", body)
    body = re.sub(r"bgcolor\s*\(.*?\)\s*\n?", "", body)
    body = re.sub(r"hline\s*\(.*?\)\s*\n?", "", body)

    long_cond = short_cond = sl_expr = tp_expr = None
    for m in re.finditer(r'strategy\.entry\s*\(\s*"([^"]+)"\s*,\s*strategy\.(long|short)[^)]*when\s*=\s*([^\)]+)\)', body):
        if m.group(2) == "long":
            long_cond = m.group(3).strip()
        else:
            short_cond = m.group(3).strip()
    if not long_cond or not short_cond:
        for m in re.finditer(r"if\s+([^\n]+)\n\s*strategy\.entry\s*\(\s*\"([^\"]+)\"\s*,\s*strategy\.(long|short)", body):
            if m.group(3) == "long" and not long_cond:
                long_cond = m.group(1).strip()
            if m.group(3) == "short" and not short_cond:
                short_cond = m.group(1).strip()
    m = re.search(r"strategy\.exit\s*\([^)]*stop\s*=\s*([^,\)]+)[^)]*limit\s*=\s*([^,\)]+)", body)
    if m:
        sl_expr, tp_expr = m.group(1).strip(), m.group(2).strip()
    if not sl_expr:
        m = re.search(r"strategy\.exit\s*\([^)]*loss\s*=\s*([^,\)]+)[^)]*profit\s*=\s*([^,\)]+)", body)
        if m:
            sl_expr, tp_expr = m.group(1).strip(), m.group(2).strip()
    if not long_cond:
        m = re.search(r"longCondition\s*=\s*([^\n]+)", body)
        if m: long_cond = m.group(1).strip()
    if not short_cond:
        m = re.search(r"shortCondition\s*=\s*([^\n]+)", body)
        if m: short_cond = m.group(1).strip()
    if not long_cond and not short_cond:
        raise ValueError("Could not find entry: need strategy.entry(..., when=...) or longCondition / shortCondition.")

    lines = []
    for raw in body.split("\n"):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if re.search(r"strategy\.(entry|exit|close|cancel|order)", line):
            continue
        if re.match(r"^(longCondition|shortCondition)\s*=", line):
            continue
        am = re.match(r"^([A-Za-z_]\w*)\s*=\s*(.+)$", line)
        if am:
            name, expr = am.groups()
            if name.startswith("strategy"):
                continue
            lines.append(f"    {name} = {translate(expr, var_map)}")

    if params:
        params_py = "PARAMS = {\n"
        for k, v in params.items():
            parts = [f'"default": {v["def"]}']
            if v["min"] is not None: parts.append(f'"min": {v["min"]}')
            if v["max"] is not None: parts.append(f'"max": {v["max"]}')
            parts.append(f'"step": {v["step"]}')
            if v["grid"]: parts.append(f'"grid": {v["grid"]}')
            params_py += f'    "{k}": {{{", ".join(parts)}}},\n'
        params_py += "}\n"
    else:
        params_py = 'PARAMS = {\n    "length": {"default": 20, "min": 2, "max": 200, "grid": [10, 20, 40]},\n}\n'
        warnings.append("No input.* found - added placeholder PARAMS.")

    sl_py = "atr(df, 14) * 1.5"
    tp_py = "0"
    if sl_expr:
        t = translate(sl_expr, var_map)
        sl_py = t if ("p[" in sl_expr or "atr" in sl_expr) and 'df["close"]' not in t else f'(df["close"] - ({t})).abs()'
    if tp_expr:
        t = translate(tp_expr, var_map)
        tp_py = t if ("p[" in tp_expr or "atr" in tp_expr) and 'df["close"]' not in t else f'(({t}) - df["close"]).abs()'

    long_py = translate(long_cond, var_map)
    short_py = translate(short_cond, var_map) if short_cond else "False"

    out = f"""# Converted from Pine Script - CHECK before trusting it.
# Signal on bar close, entry at NEXT bar's open. One trade at a time.

{params_py}MAX_HOLD = 48
WARMUP = 100

def signals(df, p):
    c = df["close"]
"""
    if lines:
        out += "\n".join(lines) + "\n"
    out += f"""    buy = ({long_py})
    sell = ({short_py})
    stop = {sl_py}
    return {{"side": buy.astype(int) - sell.astype(int),
            "sl": stop,
            "tp": {tp_py}}}

def plots(df, p):
    return {{}}
"""
    return out, warnings

EXAMPLE = """//@version=5
strategy("EMA Cross")
fast = input.int(10, "Fast")
slow = input.int(50, "Slow")
buy = ta.crossover(ta.ema(close, fast), ta.ema(close, slow))
sell = ta.crossunder(ta.ema(close, fast), ta.ema(close, slow))
strategy.entry("Long", strategy.long, when=buy)
strategy.entry("Short", strategy.short, when=sell)"""

# ---------- UI ----------
st.title("🌲 Pine → Py")
st.caption("Paste Pine Script v5/v6 → get Strategy Lab Python. Works on phone + PC.")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Pine Script")
    if st.button("Load example"):
        st.session_state["pine_in"] = EXAMPLE
    pine_in = st.text_area("Pine", value=st.session_state.get("pine_in", EXAMPLE), height=420, label_visibility="collapsed")
    convert_btn = st.button("Convert → Python", type="primary", use_container_width=True)
    st.session_state["pine_in"] = pine_in

with col2:
    st.subheader("Lab Python")
    out = st.session_state.get("pine_out", "")
    st.text_area("Python", value=out, height=420, label_visibility="collapsed", key="pine_out_display")
    if out:
        st.download_button("Download .py", out, file_name="strategy.py", mime="text/plain", use_container_width=True)
    st.caption("Copy from above → paste into Lab Strategies → Check code → Test it.")

if convert_btn:
    try:
        code, warns = convert(pine_in)
        st.session_state["pine_out"] = code
        for w in warns:
            st.warning(f"⚠ {w}")
        st.success("✓ Converted. Verify SL/TP before testing.")
        st.rerun()
    except Exception as e:
        st.error(str(e))