/* Pine Script v5/v6 -> Strategy Lab Python. Pure frontend, no server change. */
"use strict";

const Pine = {
  convert(src) {
    const warnings = [];
    let code = String(src || "");
    if (!code.trim()) throw new Error("Paste some Pine Script first.");
    if (!/@version\s*=\s*[56]/.test(code)) warnings.push("No //@version=5 or 6 found - assuming v5/v6.");
    if (/request\.security|request\.ticker|security\(/.test(code)) warnings.push("request.security() removed - Lab tests one symbol/timeframe only. Delete that line or it will use the current chart data.");
    if (/strategy\.order|strategy\.close|strategy\.exit.*profit|strategy\.exit.*loss/.test(code)) warnings.push("Complex exits converted to fixed SL/TP only. Check sl/tp in output.");

    // --- PARAMS from input.* ---
    const params = {};
    // input.int(20, "Length", minval=2, maxval=200) / input.float / input.bool
    const reInput = /(\w+)\s*=\s*input\.(int|float|bool)\s*\(\s*([^,\)]+)(?:\s*,\s*"([^"]*)")?[^)]*\)/g;
    let m;
    const varMap = {}; // pine var -> p["key"]
    while ((m = reInput.exec(code)) !== null) {
      const [, name, type, defRaw, title] = m;
      const def = defRaw.trim();
      if (type === "bool") continue; // handled as 0/1 below
      const key = name.toLowerCase();
      const isInt = type === "int";
      const dv = isInt ? parseInt(def, 10) : parseFloat(def);
      if (!isFinite(dv)) continue;
      // try to find minval/maxval
      const full = m[0];
      const minM = /minval\s*=\s*([-\d.]+)/.exec(full);
      const maxM = /maxval\s*=\s*([-\d.]+)/.exec(full);
      const stepM = /step\s*=\s*([-\d.]+)/.exec(full);
      // grid: default +- 2 steps, clamped
      let grid = null;
      if (minM && maxM) {
        const mn = parseFloat(minM[1]), mx = parseFloat(maxM[1]);
        const st = stepM ? parseFloat(stepM[1]) : (isInt ? Math.max(1, Math.round((mx - mn) / 4)) : (mx - mn) / 4);
        const vals = new Set([dv]);
        for (let v = dv - st * 2; v <= dv + st * 2 + 1e-9; v += st) {
          const vv = isInt ? Math.round(v) : Math.round(v * 100) / 100;
          if (vv >= mn && vv <= mx) vals.add(vv);
        }
        grid = [...vals].sort((a, b) => a - b);
      }
      params[key] = { def: dv, min: minM ? parseFloat(minM[1]) : undefined, max: maxM ? parseFloat(maxM[1]) : undefined, step: stepM ? parseFloat(stepM[1]) : (isInt ? 1 : 0.1), grid, label: title || name, isInt };
      varMap[name] = `p["${key}"]`;
    }
    // bool inputs -> keep as pine var, map to (p value 0/1) - simpler: leave as True/False literal
    const reBool = /(\w+)\s*=\s*input\.bool\s*\(\s*(true|false)/gi;
    while ((m = reBool.exec(code)) !== null) varMap[m[1]] = m[2].toLowerCase() === "true" ? "True" : "False";

    // --- strip header / strategy / plot / inputs ---
    let body = code
      .replace(/\/\/@version.*$/m, "")
      .replace(/indicator\s*\(.*?\)|strategy\s*\(.*?\)/gs, "")
      .replace(/^\s*\w+\s*=\s*input\.[^\n]+\n/gm, "")
      .replace(/plot\s*\(.*?\)\s*\n?/g, "")
      .replace(/plotshape\s*\(.*?\)\s*\n?/g, "")
      .replace(/plotchar\s*\(.*?\)\s*\n?/g, "")
      .replace(/bgcolor\s*\(.*?\)\s*\n?/g, "")
      .replace(/hline\s*\(.*?\)\s*\n?/g, "");

    // --- extract long/short conditions + SL/TP ---
    let longCond = null, shortCond = null, slExpr = null, tpExpr = null;
    // strategy.entry("Long", strategy.long, when=cond)
    const entryRe = /strategy\.entry\s*\(\s*"([^"]+)"\s*,\s*strategy\.(long|short)[^)]*when\s*=\s*([^\)]+)\)/g;
    while ((m = entryRe.exec(body)) !== null) {
      const dir = m[2];
      if (dir === "long") longCond = m[3].trim(); else shortCond = m[3].trim();
    }
    // fallback: if strategy.entry("Long", ...) without when, look for preceding if
    if (!longCond || !shortCond) {
      const ifRe = /if\s+([^\n]+)\n\s*strategy\.entry\s*\(\s*"([^"]+)"\s*,\s*strategy\.(long|short)/g;
      while ((m = ifRe.exec(body)) !== null) {
        if (m[3] === "long" && !longCond) longCond = m[1].trim();
        if (m[3] === "short" && !shortCond) shortCond = m[1].trim();
      }
    }
    // strategy.exit with stop/limit
    const exitRe = /strategy\.exit\s*\([^)]*stop\s*=\s*([^,\)]+)[^)]*limit\s*=\s*([^,\)]+)/.exec(body);
    if (exitRe) { slExpr = exitRe[1].trim(); tpExpr = exitRe[2].trim(); }
    const exitRe2 = /strategy\.exit\s*\([^)]*loss\s*=\s*([^,\)]+)[^)]*profit\s*=\s*([^,\)]+)/.exec(body);
    if (!slExpr && exitRe2) { slExpr = exitRe2[1].trim(); tpExpr = exitRe2[2].trim(); }

    // If no strategy.entry, try longCondition / shortCondition vars
    if (!longCond) { const mm = /longCondition\s*=\s*([^\n]+)/.exec(body); if (mm) longCond = mm[1].trim(); }
    if (!shortCond) { const mm = /shortCondition\s*=\s*([^\n]+)/.exec(body); if (mm) shortCond = mm[1].trim(); }
    if (!longCond && !shortCond) throw new Error("Could not find entry: need strategy.entry(..., when=...) or longCondition / shortCondition. Add a when= condition.");

    // --- translate expression Pine -> Python ---
    const translate = (expr) => {
      let s = expr;
      // strings / comments out
      s = s.replace(/\/\/.*$/gm, "");
      // ta.* helpers -> Lab helpers
      s = s.replace(/\bta\.ema\s*\(/g, "ema(").replace(/\bta\.sma\s*\(/g, "sma(")
           .replace(/\bta\.rsi\s*\(/g, "rsi(").replace(/\bta\.atr\s*\(/g, "atr(df, ")
           .replace(/\bta\.highest\s*\(/g, "highest(").replace(/\bta\.lowest\s*\(/g, "lowest(")
           .replace(/\bta\.crossover\s*\(/g, "crossover(").replace(/\bta\.crossunder\s*\(/g, "crossunder(")
           .replace(/\bta\.barssince\s*\(/g, "barssince(") // flagged below
           .replace(/\bta\.valuewhen\s*\(/g, "valuewhen(");
      if (/barssince|valuewhen/.test(s)) warnings.push("ta.barssince / ta.valuewhen has no direct Lab equivalent - check the generated code, it may need manual fix.");
      // math
      s = s.replace(/\bmath\.max\s*\(/g, "np.maximum(").replace(/\bmath\.min\s*\(/g, "np.minimum(")
           .replace(/\bmath\.abs\s*\(/g, "np.abs(");
      // series: close/open/high/low/volume -> df["..."]
      s = s.replace(/\bclose\b/g, 'df["close"]').replace(/\bopen\b/g, 'df["open"]')
           .replace(/\bhigh\b/g, 'df["high"]').replace(/\blow\b/g, 'df["low"]');
      // nz(x, y) -> fillna, na(x) -> isna
      s = s.replace(/\bnz\s*\(\s*([^,]+)\s*,\s*([^\)]+)\)/g, "($1).fillna($2)")
           .replace(/\bna\s*\(\s*([^\)]+)\)/g, "pd.isna($1)");
      // input vars -> p["key"]
      for (const [k, v] of Object.entries(varMap)) s = s.replace(new RegExp(`\\b${k}\\b`, "g"), v);
      // Pine operators: and/or/not, == stays, := -> =
      s = s.replace(/\band\b/g, " & ").replace(/\bor\b/g, " | ").replace(/\bnot\b/g, " ~ ")
           .replace(/:=/g, "=").replace(/\btrue\b/gi, "True").replace(/\bfalse\b/gi, "False");
      // Pine ternary a ? b : c -> np.where - leave for manual check if present
      if (s.includes(" ? ")) warnings.push("Ternary ? : found - converted code uses Python if/else, verify it.");
      return s;
    };

    // --- build indicator lines: keep assignments that are not entries/exits ---
    const lines = [];
    for (let raw of body.split("\n")) {
      const line = raw.trim();
      if (!line || line.startsWith("//")) continue;
      if (/strategy\.(entry|exit|close|cancel|order)/.test(line)) continue;
      if (/^(longCondition|shortCondition)\s*=/.test(line)) continue;
      if (/^(if|else)/.test(line) && /strategy\.entry/.test(line)) continue;
      // assignment: name = expr
      const am = /^([A-Za-z_]\w*)\s*=\s*(.+)$/.exec(line);
      if (am) {
        const [, name, expr] = am;
        // skip strategy.* vars
        if (name.startsWith("strategy")) continue;
        const t = translate(expr);
        // atr(df, 14) fix: ta.atr(14) -> atr(df, 14) already, but atr(df, df) guard
        lines.push(`    ${name} = ${t}`);
      }
    }

    // --- PARAMS block ---
    let paramsPy = "";
    if (Object.keys(params).length) {
      paramsPy = "PARAMS = {\n" + Object.entries(params).map(([k, v]) => {
        let parts = [`"default": ${v.def}`];
        if (v.min !== undefined) parts.push(`"min": ${v.min}`);
        if (v.max !== undefined) parts.push(`"max": ${v.max}`);
        parts.push(`"step": ${v.step}`);
        if (v.grid) parts.push(`"grid": [${v.grid.join(", ")}]`);
        return `    "${k}": {${parts.join(", ")}},`;
      }).join("\n") + "\n}\n";
    } else {
      paramsPy = 'PARAMS = {\n    "length": {"default": 20, "min": 2, "max": 200, "grid": [10, 20, 40]},\n}\n';
      warnings.push("No input.* found - added a placeholder PARAMS. Edit it to match your strategy.");
    }

    // --- SL / TP ---
    let slPy = "atr(df, 14) * 1.5";
    let tpPy = "0";
    if (slExpr) {
      // stop = close - sl  OR  stop price -> distance = abs(close - stop)
      const t = translate(slExpr);
      slPy = `(df["close"] - (${t})).abs()`;
      // if user used loss in points: strategy.exit(loss=...) is already distance if it looks like p["x"] * atr
      if (/p\[|atr|ema|sma/.test(slExpr) && !/df\["close"\]/.test(t)) slPy = t;
    }
    if (tpExpr) {
      const t = translate(tpExpr);
      tpPy = `((${t}) - df["close"]).abs()`;
      if (/p\[|atr|ema|sma/.test(tpExpr) && !/df\["close"\]/.test(t)) tpPy = t;
    }

    const longPy = translate(longCond);
    const shortPy = shortCond ? translate(shortCond) : "False";

    const out = `# Converted from Pine Script - CHECK before trusting it.
# Signal on bar close, entry at NEXT bar's open. One trade at a time.
# Original entry logic preserved below. Verify SL/TP - Pine exits are complex.

${paramsPy}MAX_HOLD = 48
WARMUP = 100

def signals(df, p):
    c = df["close"]
${lines.length ? lines.join("\n") + "\n" : ""}    buy = (${longPy})
    sell = (${shortPy})
    stop = ${slPy}
    return {"side": buy.astype(int) - sell.astype(int),
            "sl": stop,
            "tp": ${tpPy}}

def plots(df, p):
    return {}
`;
    return { code: out, warnings };
  }
};