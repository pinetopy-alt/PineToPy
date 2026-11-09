/* Strategy Lab front end: shared helpers, Test, Data and History tabs. */
"use strict";

const S = {datasets: [], strategies: [], runs: [], run: null};
const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}
const fmt = (v, d = 3) => (v == null || !isFinite(v) ? "n/a" : Number(v).toFixed(d));
const sgn = (v, d = 3) => (v == null || !isFinite(v) ? "n/a" : (v >= 0 ? "+" : "") + Number(v).toFixed(d));
const cls = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
const pct = (v) => (v == null ? "n/a" : (v * 100).toFixed(0) + "%");
const day = (s) => (s ? String(s).slice(0, 10) : "");

async function api(path, opts = {}) {
  const o = Object.assign({method: "GET", headers: {}}, opts);
  if (o.method !== "GET") o.headers["X-Lab"] = "1";
  if (o.json !== undefined) {
    o.headers["Content-Type"] = "application/json";
    o.body = JSON.stringify(o.json);
    delete o.json;
  }
  let r;
  try {
    r = await fetch(path, o);
  } catch (e) {
    throw Object.assign(new Error("Cannot reach the Strategy Lab server. Is the terminal window still running?"), {data: {}});
  }
  let data = {};
  try { data = await r.json(); } catch (e) { /* not json */ }
  if (!r.ok) throw Object.assign(new Error(data.error || "Request failed (" + r.status + ")"), {data});
  return data;
}

let msgTimer = null;
function note(text, ok) {
  const m = $("msg");
  m.textContent = text;
  m.className = "msg" + (ok ? " ok" : "");
  m.hidden = !text;
  clearTimeout(msgTimer);
  if (text && ok) msgTimer = setTimeout(() => (m.hidden = true), 4000);
  if (text) window.scrollTo({top: 0, behavior: "smooth"});
}

/* ---------- tabs ---------- */
let TAB = "test";
function show(tab) {
  if (TAB === "replay" && tab !== "replay" && Replay) Replay.pause();
  TAB = tab;
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== "view-" + tab));
  $("msg").hidden = true;
  if (tab === "history") loadHistory();
  if (tab === "data") loadDatasets();
  if (tab === "replay" && Replay) Replay.enter();
  if (tab === "ide" && IDE) IDE.enter();
  if (tab === "test") { refreshStrategies(); }
}

/* ---------- charts ---------- */
function setupCanvas(cv) {
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = Math.max(1, Math.round(w * dpr));
  cv.height = Math.max(1, Math.round(h * dpr));
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  return {g, w, h};
}
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/* equity curve of the chosen setting: blue = in-sample, orange = out-of-sample */
function drawCurve(cv, curve, splitTradeNo) {
  const {g, w, h} = setupCanvas(cv);
  if (!curve || curve.length < 2) {
    g.fillStyle = css("--muted"); g.font = "13px system-ui"; g.fillText("Not enough trades to draw a curve", 14, 24);
    return;
  }
  const L = 46, R = 10, T = 12, B = 24;
  const pts = [[0, 0]].concat(curve.map((p) => [p[0], p[1]]));
  let lo = Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1]));
  if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
  const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
  const X = (n) => L + (n / pts[pts.length - 1][0]) * (w - L - R);
  const Y = (v) => T + (1 - (v - lo) / (hi - lo)) * (h - T - B);
  g.strokeStyle = css("--line"); g.fillStyle = css("--muted"); g.font = "11px system-ui"; g.lineWidth = 1;
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4, y = Y(v);
    g.beginPath(); g.moveTo(L, y); g.lineTo(w - R, y); g.stroke();
    g.fillText(v.toFixed(0) + "R", 4, y + 4);
  }
  g.strokeStyle = "#5d6b7d"; g.beginPath(); g.moveTo(L, Y(0)); g.lineTo(w - R, Y(0)); g.stroke();
  g.lineWidth = 1.8;
  for (let i = 1; i < pts.length; i++) {
    const oos = curve[i - 1][3] === 1;
    g.strokeStyle = oos ? css("--oos") : css("--accent");
    g.beginPath(); g.moveTo(X(pts[i - 1][0]), Y(pts[i - 1][1])); g.lineTo(X(pts[i][0]), Y(pts[i][1])); g.stroke();
  }
  if (splitTradeNo != null) {
    g.setLineDash([4, 4]); g.strokeStyle = "#8b97a5"; g.lineWidth = 1;
    g.beginPath(); g.moveTo(X(splitTradeNo), T); g.lineTo(X(splitTradeNo), h - B); g.stroke(); g.setLineDash([]);
  }
  g.fillStyle = css("--muted");
  g.fillText("trade 1", L, h - 8);
  const last = "trade " + pts[pts.length - 1][0];
  g.fillText(last, w - R - g.measureText(last).width, h - 8);
}

/* ---------- Test tab ---------- */
function dsLabel(d) {
  return d.symbol + " " + d.timeframe + " · " + day(d.first_bar) + " to " + day(d.last_bar) + " · " + d.bars.toLocaleString() + " bars";
}

async function refreshDatasets(keep) {
  S.datasets = await api("/api/datasets");
  const cur = keep || $("ds").value;
  $("ds").innerHTML = S.datasets.length
    ? S.datasets.map((d) => `<option value="${d.id}">${esc(dsLabel(d))}</option>`).join("")
    : '<option value="">No data yet: add some in the Data tab</option>';
  if (cur && S.datasets.some((d) => String(d.id) === String(cur))) $("ds").value = cur;
  applyCost();
}

async function refreshStrategies(keep) {
  S.strategies = await api("/api/strategies");
  const cur = keep || $("strat").value;
  $("strat").innerHTML = S.strategies.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join("");
  if (cur && S.strategies.some((s) => String(s.id) === String(cur))) $("strat").value = cur;
  renderParams();
}

function renderParams() {
  const s = S.strategies.find((x) => String(x.id) === $("strat").value);
  const box = $("params");
  if (!s || !s.params || !s.params.length) {
    box.innerHTML = '<div class="hint" style="margin-top:12px">This strategy has no adjustable settings.</div>';
    return;
  }
  box.innerHTML = '<h3 style="margin-top:16px">Settings</h3><div class="row2" style="margin-top:0">' + s.params.map((p) =>
    `<div><label for="p_${esc(p.key)}" style="margin-top:0">${esc(p.label)}</label>
     <input id="p_${esc(p.key)}" data-key="${esc(p.key)}" type="number" value="${p.default}"
       ${p.min != null ? `min="${p.min}"` : ""} ${p.max != null ? `max="${p.max}"` : ""} step="${p.step || "any"}"></div>`).join("") + "</div>" +
    '<div class="hint">Used by Quick test. Full validation tries every value in each setting\'s grid instead.</div>';
}

/* a sensible starting cost (spread + slippage, in price units) for each kind of symbol */
function defaultCost(sym) {
  sym = (sym || "").toUpperCase();
  if (sym.startsWith("XAU")) return 0.35;
  if (sym.startsWith("XAG")) return 0.03;
  if (sym.startsWith("BTC")) return 20;
  if (sym.startsWith("ETH")) return 1.5;
  if (/^(US30|US500|NAS|SPX|GER|DAX|UK100|DJ)/.test(sym)) return 2;
  if (/^[A-Z]{6}$/.test(sym)) return sym.endsWith("JPY") ? 0.015 : 0.00015;
  return null;
}
function applyCost() {
  const d = S.datasets.find((x) => String(x.id) === $("ds").value);
  const c = d ? defaultCost(d.symbol) : null;
  if (c != null && !$("cost").dataset.touched) $("cost").value = c;
}

function gatherParams() {
  const o = {};
  document.querySelectorAll("#params input[data-key]").forEach((i) => { if (i.value !== "") o[i.dataset.key] = Number(i.value); });
  return o;
}

function table(headers, rows, hl) {
  return '<table><thead><tr>' + headers.map((h, i) => `<th${i === 0 ? ' class="l"' : ""}>${h}</th>`).join("") + "</tr></thead><tbody>" +
    rows.map((r, k) => `<tr${hl === k ? ' class="hl"' : ""}>` + r.map((c) => `<td>${c}</td>`).join("") + "</tr>").join("") + "</tbody></table>";
}

function renderRun(run) {
  S.run = run;
  const r = run.result, ch = r.chosen;
  const vc = r.verdict === "CANDIDATE EDGE" ? "v-good" : r.mode === "quick" ? "v-neutral" : "v-bad";
  const nIS = r.curve.filter((p) => p[3] === 0).length;
  let h = `<div class="verdict ${vc}"><span>${esc(r.verdict)}</span><small>Run #${run.id} · ${esc(run.strategy_name || "")} · ${esc(run.dataset_name || "")} · out-of-sample starts ${esc(day(r.split_at))}</small></div>`;
  if (r.lookahead && !r.lookahead.ok) {
    h += `<div class="box bad" style="margin-top:12px"><b>This strategy peeks at the future.</b> ${esc(r.lookahead.detail)}</div>`;
  }
  h += '<div class="card" style="margin-top:16px"><h3>Chosen settings</h3><div class="note" style="margin:0 0 10px">' +
    Object.entries(ch.params).map(([k, v]) => `<b>${esc(k)}</b> = ${esc(v)}`).join(" · ") + "</div>" +
    table(["", "Trades", "Expectancy (R)", "Win rate", "Profit factor", "Total (R)", "Max drawdown (R)"], [
      ["In-sample", ch.is.n, `<span class="${cls(ch.is.exp)}">${sgn(ch.is.exp)}</span>`, pct(ch.is.win), fmt(ch.is.pf, 2), sgn(ch.is.tot, 1), fmt(ch.is.dd, 1)],
      ["<b>Out-of-sample</b>", ch.oos.n, `<span class="${cls(ch.oos.exp)}"><b>${sgn(ch.oos.exp)}</b></span>`, pct(ch.oos.win), fmt(ch.oos.pf, 2), sgn(ch.oos.tot, 1), fmt(ch.oos.dd, 1)],
    ]) + "</div>";

  if (r.checks) {
    h += '<div class="card"><h3>Checks (all must pass)</h3><ul class="checks">' + r.checks.map((c) =>
      `<li><span class="ic ${c.pass ? "pos" : "neg"}">${c.pass ? "✓" : "✗"}</span><span>${esc(c.name)}</span><span class="d">${esc(c.detail)}</span></li>`).join("") + "</ul>";
    const b = r.robustness;
    h += `<div class="note">Tested ${b.settings_tested} settings. In-sample: ${pct(b.pos_is)} profitable. Out-of-sample: ${pct(b.pos_oos)} profitable, median ${sgn(b.median_oos_exp)}R.</div></div>`;
  }
  h += '<div class="card"><h3>Equity curve (R, after costs)</h3><canvas id="curve"></canvas>' +
    `<div class="legend"><span><i style="background:var(--accent)"></i>In-sample (seen while choosing settings)</span><span><i style="background:var(--oos)"></i>Out-of-sample (unseen: this is the honest part)</span></div>` +
    `<div class="actions" style="margin-top:12px"><button class="btn sm" type="button" id="watch">▶ Watch it live (Visual)</button> <a class="btn ghost sm" style="text-decoration:none" href="/api/runs/${run.id}/trades.csv">Download trades (CSV)</a></div></div>`;
  if (r.grid && r.grid.length) {
    const keys = Object.keys(r.grid[0].params).filter((k) => new Set(r.grid.map((g) => g.params[k])).size > 1);
    const top = r.grid.slice(0, 15);
    h += '<div class="card"><h3>Settings tried (best in-sample first)</h3><div class="scroll">' +
      table(keys.map(esc).concat(["IS trades", "IS exp", "OOS trades", "OOS exp"]), top.map((g) =>
        keys.map((k) => g.params[k]).concat([g.is.n, sgn(g.is.exp), g.oos.n, `<span class="${cls(g.oos.exp)}">${sgn(g.oos.exp)}</span>`])), 0) +
      "</div>" + (r.grid.length > top.length ? `<div class="note">Showing 15 of ${r.grid.length}.</div>` : "") + "</div>";
  }
  if (run.log) h += `<div class="card"><h3>Strategy console</h3><pre class="log">${esc(run.log)}</pre></div>`;
  $("result").innerHTML = h;
  drawCurve($("curve"), r.curve, nIS || null);
  $("watch").onclick = () => Replay.open(run.id);
}

async function doRun(ev) {
  ev.preventDefault();
  if (!$("ds").value) return note("Add price data first (Data tab).");
  const btn = $("run");
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = "Running… large tests can take a few minutes";
  note("");
  try {
    const run = await api("/api/runs", {method: "POST", json: {
      dataset_id: Number($("ds").value), strategy_id: Number($("strat").value), params: gatherParams(),
      mode: document.querySelector("input[name=mode]:checked").value,
      cost: Number($("cost").value), split: Number($("split").value) / 100}});
    renderRun(run);
  } catch (e) {
    let t = e.message;
    if (e.data && e.data.line) t += "\n(line " + e.data.line + " of your strategy)";
    if (e.data && e.data.log) t += "\n\n" + e.data.log;
    note(t);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

/* ---------- History ---------- */
async function loadHistory() {
  S.runs = await api("/api/runs");
  const box = $("history");
  if (!S.runs.length) { box.innerHTML = '<div class="empty">No tests yet.</div>'; return; }
  box.innerHTML = table(["#", "When", "Strategy", "Data", "Mode", "Verdict", "OOS trades", "OOS exp (R)", ""], S.runs.map((r) => [
    r.id, esc(String(r.created_at).slice(0, 16)), esc(r.strategy_name || "Trend Pullback"), esc(r.dataset_name || "(deleted)"), esc(r.mode),
    `<span class="pill ${r.verdict === "CANDIDATE EDGE" ? "v-good" : r.verdict.startsWith("SINGLE") ? "v-neutral" : "v-bad"}">${esc(r.verdict)}</span>`,
    r.oos_n, `<span class="${cls(r.oos_exp)}">${sgn(r.oos_exp)}</span>`,
    `<button class="btn ghost sm" data-open="${r.id}">Open</button> <button class="btn ghost sm" data-watch="${r.id}">▶ Visual</button> <button class="btn ghost sm danger" data-del="${r.id}">✕</button>`]));
  box.querySelectorAll("[data-open]").forEach((b) => (b.onclick = async () => {
    try { const run = await api("/api/runs/" + b.dataset.open); show("test"); renderRun(run); } catch (e) { note(e.message); }
  }));
  box.querySelectorAll("[data-watch]").forEach((b) => (b.onclick = () => Replay.open(Number(b.dataset.watch))));
  box.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => {
    if (!confirm("Delete test #" + b.dataset.del + "?")) return;
    try { await api("/api/runs/" + b.dataset.del, {method: "DELETE"}); loadHistory(); } catch (e) { note(e.message); }
  }));
}

/* ---------- Data library ---------- */
function coverageBars(meta) {
  const c = meta && meta.coverage ? Object.entries(meta.coverage) : [];
  if (!c.length) return "";
  const max = Math.max(...c.map((x) => x[1]));
  return '<div class="cov">' + c.map(([y, n]) => `<div class="cb" style="height:${Math.max(8, (n / max) * 100)}%" title="${y}: ${n.toLocaleString()} bars"></div>`).join("") + "</div>" +
    `<div class="hint">${c[0][0]} – ${c[c.length - 1][0]}</div>`;
}

async function loadDatasets() {
  await refreshDatasets();
  const box = $("datasets");
  if (!S.datasets.length) { box.innerHTML = '<div class="empty">No data yet. Upload a CSV on the left.</div>'; return; }
  box.innerHTML = table(["Symbol", "Timeframe", "From", "To", "Bars", "Bars per year", "Largest gap", ""], S.datasets.map((d) => {
    const m = d.meta || {};
    const gap = m.gap_days != null && m.gap_days > 5 ? `<span class="neg" title="${esc(m.gap_from)} to ${esc(m.gap_to)}">${m.gap_days} days</span>` : (m.gap_days != null ? m.gap_days + " days" : "");
    return [`<b>${esc(d.symbol)}</b>${d.kind === "synthetic" ? ' <span class="pill v-neutral">random</span>' : ""}`, esc(d.timeframe), esc(day(d.first_bar)), esc(day(d.last_bar)),
      d.bars.toLocaleString(), coverageBars(m), gap, `<button class="btn ghost sm danger" data-dds="${d.id}">Delete</button>`];
  }));
  box.querySelectorAll("[data-dds]").forEach((b) => (b.onclick = async () => {
    if (!confirm("Delete this data? Your saved test results stay, but cannot be replayed.")) return;
    try { await api("/api/datasets/" + b.dataset.dds, {method: "DELETE"}); loadDatasets(); } catch (e) { note(e.message); }
  }));
}

async function doUpload(ev) {
  ev.preventDefault();
  const files = Array.from($("up-file").files);
  const out = $("upmsg");
  out.innerHTML = "";
  const btn = ev.submitter || ev.target.querySelector("button[type=submit]");
  btn.disabled = true;
  for (const f of files) {
    const line = document.createElement("div");
    line.textContent = "Uploading " + f.name + "…";
    out.appendChild(line);
    const fd = new FormData();
    fd.append("file", f);
    fd.append("symbol", $("up-symbol").value);
    fd.append("timeframe", $("up-tf").value);
    try {
      const r = await api("/api/datasets", {method: "POST", body: fd});
      line.innerHTML = `<span class="pos">✓</span> ${esc(f.name)} → <b>${esc(r.symbol)} ${esc(r.timeframe)}</b>: ` +
        (r.merged ? `${r.added.toLocaleString()} new bars added (now ${r.total.toLocaleString()})` : `${r.total.toLocaleString()} bars saved`);
    } catch (e) {
      line.innerHTML = `<span class="neg">✗</span> ${esc(f.name)}: ${esc(e.message)}`;
    }
  }
  btn.disabled = false;
  $("up-file").value = "";
  loadDatasets();
}

async function addSynthetic() {
  const seed = 1 + Math.floor(Math.random() * 9999);
  try {
    const r = await api("/api/datasets/synthetic", {method: "POST", json: {seed}});
    note("Added " + r.symbol + " (" + r.total.toLocaleString() + " random bars).", true);
    loadDatasets();
  } catch (e) { note(e.message); }
}

/* ---------- boot ---------- */
async function boot() {
  document.querySelectorAll("nav button").forEach((b) => (b.onclick = () => show(b.dataset.tab)));
  $("form").onsubmit = doRun;
  $("strat").onchange = renderParams;
  $("ds").onchange = applyCost;
  $("cost").oninput = () => ($("cost").dataset.touched = "1");
  $("split").oninput = () => ($("splitv").textContent = $("split").value);
  $("upload").onsubmit = doUpload;
  $("synth").onclick = addSynthetic;
  $("edit-code").onclick = async (e) => { e.preventDefault(); await IDE.openStrategy(Number($("strat").value)); show("ide"); };
  window.addEventListener("resize", () => {
    if (S.run && TAB === "test" && $("curve")) drawCurve($("curve"), S.run.result.curve, S.run.result.curve.filter((p) => p[3] === 0).length || null);
    if (TAB === "replay" && Replay) Replay.draw();
  });
  IDE.init();
  Replay.init();
  try {
    await refreshDatasets();
    await refreshStrategies();
  } catch (e) { note(e.message); }
}