/* Pine Script v5/v6 -> Strategy Lab Python. 100% offline, no server. */
"use strict";
const Pine = {
  convert(src) {
    const warnings = [];
    let code = String(src || "");
    if (!code.trim()) throw new Error("Paste some Pine Script first.");
    if (!/@version\s*=\s*[56]/.test(code)) warnings.push("No //@version=5 or 6 found - assuming v5/v6.");
    if (/request\.security|security\(/.test(code)) warnings.push("request.security() removed - Lab tests one symbol/timeframe only.");
    if (/strategy\.order|strategy\.close/.test(code)) warnings.push("Complex exits converted to fixed SL/TP only. Check sl/tp.");
    const params = {}; const varMap = {};
    const reInput = /(\w+)\s*=\s*input\.(int|float|bool)\s*\(\s*([^,\)]+)(?:\s*,\s*"([^"]*)")?[^)]*\)/g; let m;
    while ((m = reInput.exec(code)) !== null) {
      const [, name, type, defRaw, title] = m; const def = defRaw.trim();
      if (type === "bool") continue;
      const key = name.toLowerCase(); const isInt = type === "int";
      const dv = isInt ? parseInt(def, 10) : parseFloat(def); if (!isFinite(dv)) continue;
      const full = m[0]; const minM = /minval\s*=\s*([-\d.]+)/.exec(full); const maxM = /maxval\s*=\s*([-\d.]+)/.exec(full); const stepM = /step\s*=\s*([-\d.]+)/.exec(full);
      let grid = null;
      if (minM && maxM) { const mn = parseFloat(minM[1]), mx = parseFloat(maxM[1]); const st = stepM ? parseFloat(stepM[1]) : (isInt ? Math.max(1, Math.round((mx - mn) / 4)) : (mx - mn) / 4); const vals = new Set([dv]); for (let v = dv - st * 2; v <= dv + st * 2 + 1e-9; v += st) { const vv = isInt ? Math.round(v) : Math.round(v * 100) / 100; if (vv >= mn && vv <= mx) vals.add(vv); } grid = [...vals].sort((a, b) => a - b); }
      params[key] = { def: dv, min: minM ? parseFloat(minM[1]) : undefined, max: maxM ? parseFloat(maxM[1]) : undefined, step: stepM ? parseFloat(stepM[1]) : (isInt ? 1 : 0.1), grid, label: title || name };
      varMap[name] = `p["${key}"]`;
    }
    const reBool = /(\w+)\s*=\s*input\.bool\s*\(\s*(true|false)/gi;
    while ((m = reBool.exec(code)) !== null) varMap[m[1]] = m[2].toLowerCase() === "true" ? "True" : "False";
    let body = code.replace(/\/\/@version.*$/m, "").replace(/indicator\s*\(.*?\)|strategy\s*\(.*?\)/gs, "").replace(/^\s*\w+\s*=\s*input\.[^\n]+\n/gm, "").replace(/plot\s*\(.*?\)\s*\n?/g, "").replace(/plotshape\s*\(.*?\)\s*\n?/g, "").replace(/bgcolor\s*\(.*?\)\s*\n?/g, "").replace(/hline\s*\(.*?\)\s*\n?/g, "");
    let longCond = null, shortCond = null, slExpr = null, tpExpr = null;
    const entryRe = /strategy\.entry\s*\(\s*"([^"]+)"\s*,\s*strategy\.(long|short)[^)]*when\s*=\s*([^\)]+)\)/g;
    while ((m = entryRe.exec(body)) !== null) { if (m[2] === "long") longCond = m[3].trim(); else shortCond = m[3].trim(); }
    if (!longCond || !shortCond) { const ifRe = /if\s+([^\n]+)\n\s*strategy\.entry\s*\(\s*"([^"]+)"\s*,\s*strategy\.(long|short)/g; while ((m = ifRe.exec(body)) !== null) { if (m[3] === "long" && !longCond) longCond = m[1].trim(); if (m[3] === "short" && !shortCond) shortCond = m[1].trim(); } }
    const exitRe = /strategy\.exit\s*\([^)]*stop\s*=\s*([^,\)]+)[^)]*limit\s*=\s*([^,\)]+)/.exec(body); if (exitRe) { slExpr = exitRe[1].trim(); tpExpr = exitRe[2].trim(); }
    const exitRe2 = /strategy\.exit\s*\([^)]*loss\s*=\s*([^,\)]+)[^)]*profit\s*=\s*([^,\)]+)/.exec(body); if (!slExpr && exitRe2) { slExpr = exitRe2[1].trim(); tpExpr = exitRe2[2].trim(); }
    if (!longCond) { const mm = /longCondition\s*=\s*([^\n]+)/.exec(body); if (mm) longCond = mm[1].trim(); }
    if (!shortCond) { const mm = /shortCondition\s*=\s*([^\n]+)/.exec(body); if (mm) shortCond = mm[1].trim(); }
    if (!longCond && !shortCond) throw new Error("Could not find entry: need strategy.entry(..., when=...) or longCondition / shortCondition.");
    const translate = (expr) => {
      let s = expr.replace(/\/\/.*$/gm, "");
      s = s.replace(/\bta\.ema\s*\(/g, "ema(").replace(/\bta\.sma\s*\(/g, "sma(").replace(/\bta\.rsi\s*\(/g, "rsi(").replace(/\bta\.atr\s*\(/g, "atr(df, ").replace(/\bta\.highest\s*\(/g, "highest(").replace(/\bta\.lowest\s*\(/g, "lowest(").replace(/\bta\.crossover\s*\(/g, "crossover(").replace(/\bta\.crossunder\s*\(/g, "crossunder(");
      s = s.replace(/\bmath\.max\s*\(/g, "np.maximum(").replace(/\bmath\.min\s*\(/g, "np.minimum(").replace(/\bmath\.abs\s*\(/g, "np.abs(");
      s = s.replace(/\bclose\b/g, 'df["close"]').replace(/\bopen\b/g, 'df["open"]').replace(/\bhigh\b/g, 'df["high"]').replace(/\blow\b/g, 'df["low"]');
      s = s.replace(/\bnz\s*\(\s*([^,]+)\s*,\s*([^\)]+)\)/g, "($1).fillna($2)").replace(/\bna\s*\(\s*([^\)]+)\)/g, "pd.isna($1)");
      for (const [k, v] of Object.entries(varMap)) s = s.replace(new RegExp(`\\b${k}\\b`, "g"), v);
      s = s.replace(/\band\b/g, " & ").replace(/\bor\b/g, " | ").replace(/\bnot\b/g, " ~ ").replace(/:=/g, "=").replace(/\btrue\b/gi, "True").replace(/\bfalse\b/gi, "False");
      return s;
    };
    const lines = [];
    for (let raw of body.split("\n")) { const line = raw.trim(); if (!line || line.startsWith("//")) continue; if (/strategy\.(entry|exit|close|cancel|order)/.test(line)) continue; if (/^(longCondition|shortCondition)\s*=/.test(line)) continue; const am = /^([A-Za-z_]\w*)\s*=\s*(.+)$/.exec(line); if (am) { const [, name, expr] = am; if (name.startsWith("strategy")) continue; lines.push(`    ${name} = ${translate(expr)}`); } }
    let paramsPy = "";
    if (Object.keys(params).length) { paramsPy = "PARAMS = {\n" + Object.entries(params).map(([k, v]) => { let p = [`"default": ${v.def}`]; if (v.min !== undefined) p.push(`"min": ${v.min}`); if (v.max !== undefined) p.push(`"max": ${v.max}`); p.push(`"step": ${v.step}`); if (v.grid) p.push(`"grid": [${v.grid.join(", ")}]`); return `    "${k}": {${p.join(", ")}},`; }).join("\n") + "\n}\n"; }
    else { paramsPy = 'PARAMS = {\n    "length": {"default": 20, "min": 2, "max": 200, "grid": [10, 20, 40]},\n}\n'; warnings.push("No input.* found - added placeholder PARAMS."); }
    let slPy = "atr(df, 14) * 1.5"; let tpPy = "0";
    if (slExpr) { const t = translate(slExpr); slPy = (/p\[|atr|ema|sma/.test(slExpr) && !/df\["close"\]/.test(t)) ? t : `(df["close"] - (${t})).abs()`; }
    if (tpExpr) { const t = translate(tpExpr); tpPy = (/p\[|atr|ema|sma/.test(tpExpr) && !/df\["close"\]/.test(t)) ? t : `((${t}) - df["close"]).abs()`; }
    const longPy = translate(longCond); const shortPy = shortCond ? translate(shortCond) : "False";
    return { code: `# Converted from Pine Script - CHECK before trusting it.\n# Signal on bar close, entry at NEXT bar's open. One trade at a time.\n\n${paramsPy}MAX_HOLD = 48\nWARMUP = 100\n\n\ndef signals(df, p):\n    c = df["close"]\n${lines.length ? lines.join("\n") + "\n" : ""}    buy = (${longPy})\n    sell = (${shortPy})\n    stop = ${slPy}\n    return {"side": buy.astype(int) - sell.astype(int),\n            "sl": stop,\n            "tp": ${tpPy}}\n\n\ndef plots(df, p):\n    return {}\n`, warnings };
  }
};
const PineUI = {
  EXAMPLE: `//@version=5\nstrategy("EMA Cross")\nfast = input.int(10, "Fast")\nslow = input.int(50, "Slow")\nbuy = ta.crossover(ta.ema(close, fast), ta.ema(close, slow))\nsell = ta.crossunder(ta.ema(close, fast), ta.ema(close, slow))\nstrategy.entry("Long", strategy.long, when=buy)\nstrategy.entry("Short", strategy.short, when=sell)`,
  init() {
    const $ = (id) => document.getElementById(id);
    $("pine-convert").onclick = () => {
      try {
        const r = Pine.convert($("pine-in").value);
        $("pine-out").value = r.code;
        // save offline - survives refresh even offline
        try { localStorage.setItem("pine_in", $("pine-in").value); localStorage.setItem("pine_out", r.code); } catch (e) {}
        $("pine-warn").innerHTML = r.warnings.length ? r.warnings.map(w => `<div class="box bad" style="margin-top:10px">⚠ ${esc(w)}</div>`).join("") : `<div class="box ok" style="margin-top:10px">✓ Converted. Verify SL/TP before testing.</div>`;
        if (!$("pine-name").value) $("pine-name").value = "Pine Import";
      } catch (e) { $("pine-warn").innerHTML = `<div class="box bad" style="margin-top:10px">${esc(e.message)}</div>`; }
    };
    $("pine-example").onclick = () => { $("pine-in").value = this.EXAMPLE; $("pine-convert").click(); };
    $("pine-clear").onclick = () => { $("pine-in").value = ""; $("pine-out").value = ""; $("pine-warn").innerHTML = ""; };
    $("pine-copy").onclick = async () => { try { await navigator.clipboard.writeText($("pine-out").value); note("Copied.", true); } catch (e) { $("pine-out").select(); document.execCommand("copy"); note("Copied.", true); } };
    $("pine-download").onclick = () => { const b = new Blob([$("pine-out").value], { type: "text/plain" }); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = ($("pine-name").value || "strategy") + ".py"; a.click(); };
    $("pine-send").onclick = async () => {
      const code = $("pine-out").value.trim(); if (!code) return note("Convert first.");
      if (!navigator.onLine) return note("Offline: Copy or Download instead. Send needs server.");
      try { const s = await api("/api/strategies", { method: "POST", json: { name: $("pine-name").value || "Pine Import", code } }); await refreshStrategies(String(s.id)); await IDE.openStrategy(s.id); show("ide"); note("Sent to Strategies - press Check code.", true); } catch (e) { note(e.message); }
    };
    // restore offline draft
    try { const pi = localStorage.getItem("pine_in"); const po = localStorage.getItem("pine_out"); if (pi) $("pine-in").value = pi; if (po) $("pine-out").value = po; } catch (e) {}
  },
  enter() {}
};