// 퀀트 터미널 (TERMINAL-1) — vanilla JS, no external libraries.  Missing values are shown as "—", never 0.
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const STATUS_KO = { REAL: "실데이터", STALE: "지연·오래됨", UNAVAILABLE: "데이터 없음", FROZEN: "고정", EXPERIMENTAL: "실험" };
const state = { tab: "overview", ticker: null, range: "1y", loaded: {}, market: "US" };
try { if (localStorage.getItem("qse-market") === "KR") state.market = "KR"; } catch (e) { /* storage unavailable */ }
const KR_RE = /^[0-9][0-9A-Z]{5}$/;
const marketOf = (t) => (KR_RE.test(String(t).toUpperCase()) ? "KR" : "US");
const isKR = () => state.market === "KR";
const mq = (path) => `${path}${path.includes("?") ? "&" : "?"}market=${state.market}`;

// ------------------------------------------------------------------ helpers
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNum = (v) => typeof v === "number" && isFinite(v);
const DASH = '<span class="missing">—</span>';
function fmt(v, d = 2) { return isNum(v) ? v.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d }) : DASH; }
function pct(v, d = 2, sign = true) {
  if (!isNum(v)) return DASH;
  const cls = v > 0 ? "up" : v < 0 ? "down" : "flat";
  return `<span class="${cls} num">${sign && v > 0 ? "+" : ""}${v.toFixed(d)}%</span>`;
}
function big(v, unit = "USD") {
  if (!isNum(v)) return DASH;
  const a = Math.abs(v), s = v < 0 ? "-" : "", p = unit === "USD" ? "$" : unit === "KRW" ? "₩" : "";
  if (a >= 1e12) return `${s}${p}${(a / 1e12).toFixed(2)}조`;
  if (a >= 1e8) return `${s}${p}${(a / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: a >= 1e11 ? 0 : 1 })}억`;
  if (a >= 1e4) return `${s}${p}${(a / 1e4).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}만`;
  return `${s}${p}${a.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}`;
}
function badge(st) { return `<span class="badge ${esc(st)}">${esc(STATUS_KO[st] || st)}</span>`; }
const liveBadge = (on) => (on ? '<span class="badge live" title="정규장 진행 중: 마지막 일봉은 아직 확정되지 않았습니다">장중·미확정</span>' : "");
function when(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? esc(iso) : d.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}
function meta(source, fetched, extra = "") {
  return `<div class="meta">출처: ${esc(source)}${fetched ? ` · 받아온 시각 ${when(fetched)}` : ""}${extra ? " · " + extra : ""}</div>`;
}
async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({ error: "BAD_RESPONSE" }));
  if (!r.ok) throw new Error(j.error || `HTTP_${r.status}`);
  return j;
}
const ERR_KO = { INVALID_TICKER: "종목 코드 형식이 올바르지 않습니다.", WATCHLIST_FULL: "관심종목은 최대 100개입니다.",
  INTERNAL_ERROR: "서버 내부 오류가 발생했습니다.", INVALID_RANGE: "기간 값이 올바르지 않습니다." };
const errBox = (e) => `<div class="panel err">불러오지 못했습니다: ${esc(ERR_KO[e.message] || e.message)}</div>`;
const loading = '<div class="panel empty">불러오는 중…</div>';
function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

function setupCanvas(cv, h) {
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth || cv.parentElement.clientWidth;
  cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.height = h + "px";
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}
function spark(cv, vals) {
  const v = (vals || []).filter(isNum);
  if (v.length < 2) return;
  const { ctx, w, h } = setupCanvas(cv, cv.clientHeight || 28);
  const lo = Math.min(...v), hi = Math.max(...v), rg = hi - lo || 1;
  ctx.strokeStyle = cssVar(v[v.length - 1] >= v[0] ? "--up" : "--down"); ctx.lineWidth = 1.4;
  ctx.beginPath();
  v.forEach((x, i) => { const px = (i / (v.length - 1)) * w, py = h - 2 - ((x - lo) / rg) * (h - 4); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
  ctx.stroke();
}

// ------------------------------------------------------------------ tabs & routing
function show(tab, push = true) {
  state.tab = tab;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("on", s.id === "tab-" + tab));
  if (push) location.hash = tab === "stock" && state.ticker ? `stock/${state.ticker}` : tab;
  if (tab === "stock") return renderStock();
  if (!state.loaded[tab] || ALWAYS_FRESH.has(tab)) RENDER[tab]();
}
function paintMarket() {
  $("#market").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.m === state.market));
}
function setMarket(m, render = true) {
  if (m === state.market) return;
  state.market = m;
  try { localStorage.setItem("qse-market", m); } catch (e) { /* storage unavailable */ }
  paintMarket();
  state.loaded = {};
  redrawers.clear();
  document.querySelectorAll(".tab").forEach((s) => (s.innerHTML = ""));
  if (state.ticker && marketOf(state.ticker) !== m) state.ticker = null;
  if (render) show(state.tab);
}
function openTicker(t) {
  state.ticker = String(t).toUpperCase(); state.loaded.stock = null;
  setMarket(marketOf(state.ticker), false);
  show("stock");
  window.scrollTo(0, 0);
}
document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => show(b.dataset.tab)));
$("#market").onclick = (e) => { const b = e.target.closest("button"); if (b) setMarket(b.dataset.m); };
async function searchKr(q) {
  setMarket("KR", false);
  state.ticker = null; state.loaded.stock = "search";
  show("stock");
  const el = $("#tab-stock"); el.innerHTML = loading;
  try {
    const d = await api(`/api/kr/search?q=${encodeURIComponent(q)}`);
    if (d.items.length === 1 || (d.items[0] && d.items[0].name === q)) return openTicker(d.items[0].ticker);
    el.innerHTML = `<div class="panel"><h2>'${esc(q)}' 검색 결과</h2>${d.items.length ? `<div class="tbl-wrap"><table><tbody>${d.items.map((i) => `<tr class="click" data-ticker="${esc(i.ticker)}"><td class="l"><b>${esc(i.name)}</b></td><td class="l">${esc(i.ticker)}</td><td class="l">${esc(i.market || "")}</td></tr>`).join("")}</tbody></table></div>` : '<div class="empty">일치하는 상장 종목이 없습니다.</div>'}</div>`;
  } catch (err) { el.innerHTML = errBox(err); }
}
$("#search").onsubmit = (e) => {
  e.preventDefault(); const t = $("#q").value.trim(); if (!t) return;
  /[가-힣]/.test(t) ? searchKr(t) : openTicker(t);
  $("#q").value = ""; $("#q").blur();
};
document.addEventListener("click", (e) => { const el = e.target.closest("[data-ticker]"); if (el && !e.target.closest("button.x")) openTicker(el.dataset.ticker); });

// theme: auto (OS) → light → dark
const THEMES = ["auto", "light", "dark"];
function applyTheme(t) {
  if (t === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.dataset.theme = t;
  $("#theme").title = "화면 테마: " + { auto: "시스템", light: "밝게", dark: "어둡게" }[t];
  redrawAll();
}
let theme = "auto";
try { theme = localStorage.getItem("qse-theme") || "auto"; } catch (e) { /* storage unavailable */ }
$("#theme").onclick = () => { theme = THEMES[(THEMES.indexOf(theme) + 1) % 3]; try { localStorage.setItem("qse-theme", theme); } catch (e) {} applyTheme(theme); };
const redrawers = new Set();
function redrawAll() { redrawers.forEach((f) => f()); }
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redrawAll);
let rz; window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(redrawAll, 120); });

// ------------------------------------------------------------------ 시장 개요
async function renderOverview() {
  const el = $("#tab-overview"), m = state.market; el.innerHTML = loading;
  try {
    const d = await api(mq("/api/overview")); if (m !== state.market) return; state.loaded.overview = true;
    const live = d.groups.some((g) => g.items.some((i) => i.intraday));
    el.innerHTML = (live ? '<div class="notice">정규장이 진행 중입니다. 오늘 일봉은 지연된 장중 값이며 확정되지 않았습니다.</div>' : "") +
      d.groups.map((g) => `<div class="panel"><h2>${esc(g.title)}</h2><div class="grid">${g.items.map(card).join("")}</div></div>`).join("") +
      `<div class="panel">${meta(d.source, d.cache.fetched_at, badge(d.cache.status))}<div class="meta">${esc(d.basis)}</div></div>`;
    const draw = () => el.querySelectorAll("canvas[data-spark]").forEach((cv) => spark(cv, JSON.parse(cv.dataset.spark)));
    draw(); redrawers.add(draw);
  } catch (e) { el.innerHTML = errBox(e); }
}
function card(i) {
  const code = i.ticker || i.symbol, won = /\.K[SQ]$/.test(i.symbol);
  const tk = /^[A-Z]{1,5}$/.test(code) || KR_RE.test(code) ? `data-ticker="${esc(code)}"` : "";
  return `<div class="card" ${tk} title="${esc(i.symbol)}${i.date ? " · " + esc(i.date) : ""}">
    <div class="nm">${esc(i.name || i.symbol)} <span class="muted">${esc(code)}</span></div>
    <div class="row"><div><div class="px num">${fmt(i.close, won ? 0 : 2)}</div>
      <div>${pct(i.change_pct)} <span class="meta" style="margin:0">1개월 ${pct(i.change_1m_pct, 1)}</span></div></div>
      <canvas data-spark='${JSON.stringify(i.spark || [])}'></canvas></div>
    <div class="meta" style="margin-top:4px">${i.status !== "REAL" ? badge(i.status) + " " : ""}${liveBadge(i.intraday)} ${esc(i.date || "")}</div>
  </div>`;
}

// ------------------------------------------------------------------ 종목
async function renderStock() {
  const el = $("#tab-stock");
  if (!state.ticker) { el.innerHTML = `<div class="panel empty">위 검색창에 ${isKR() ? "종목 코드나 회사명을 입력하세요 (예: 005930, 삼성전자)." : "종목 코드를 입력하세요 (예: AAPL, MSFT, NVDA)."}</div>`; return; }
  if (state.loaded.stock === state.ticker) return;
  state.loaded.stock = state.ticker;
  const t = state.ticker;
  el.innerHTML = `<div class="panel" id="s-head">${loading}</div>
    <div class="panel"><h2>가격 차트 <span class="seg" id="rng">${["3mo", "1y", "5y"].map((r) => `<button data-r="${r}" class="${r === state.range ? "on" : ""}">${{ "3mo": "3개월", "1y": "1년", "5y": "5년" }[r]}</button>`).join("")}</span>
      <span class="legend"><span><i style="background:var(--sma20)"></i>20일선</span><span><i style="background:var(--sma50)"></i>50일선</span><span><i style="background:var(--sma200)"></i>200일선</span></span></h2>
      <div class="chart"><canvas id="pc"></canvas></div><div id="c-meta"></div></div>
    <div class="panel" id="s-fund">${loading}</div>
    <div class="panel" id="s-fil">${loading}</div>`;
  $("#rng").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; state.range = b.dataset.r; $("#rng").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); loadChart(t); };
  loadChart(t);
  api(`/api/company?t=${encodeURIComponent(t)}`).then((c) => { if (state.ticker === t) { renderProfile(c); renderFund(c.fundamentals); } })
    .catch((e) => { if (state.ticker === t) { $("#s-fund").innerHTML = `<span class="err">${esc(ERR_KO[e.message] || e.message)}</span>`; $("#s-head").innerHTML = `<div class="err">${esc(ERR_KO[e.message] || e.message)}</div>`; } });
  api(`/api/filings?t=${encodeURIComponent(t)}`).then((f) => state.ticker === t && renderFilings(f))
    .catch((e) => state.ticker === t && ($("#s-fil").innerHTML = `<span class="err">${esc(ERR_KO[e.message] || e.message)}</span>`));
}
let lastChart = null;
async function loadChart(t) {
  $("#c-meta").innerHTML = '<div class="meta">불러오는 중…</div>';
  try {
    const c = await api(`/api/chart?t=${encodeURIComponent(t)}&range=${state.range}`);
    if (state.ticker !== t) return;
    lastChart = c; drawPrice(); redrawers.add(drawPrice);
    const L = c.last || {};
    $("#c-meta").innerHTML = c.bars.length ? meta(c.source, c.cache.fetched_at, `${badge(c.status)} ${liveBadge(L.intraday)} 마지막 일봉 ${esc(L.date)}`) :
      `<div class="empty">${badge("UNAVAILABLE")} 가격 데이터를 받지 못했습니다. 종목 코드를 확인하세요.</div>`;
    state.lastQuote = L; renderHeadPrice();
  } catch (e) { $("#c-meta").innerHTML = `<span class="err">${esc(ERR_KO[e.message] || e.message)}</span>`; }
}
function renderHeadPrice() {
  const L = state.lastQuote, h = $("#s-price");
  if (!h || !L) return;
  const d = isKR() ? 0 : 2;
  h.innerHTML = `<span class="big num">${fmt(L.close, d)}</span> ${pct(L.change_pct)} ${liveBadge(L.intraday)}
    <span class="meta">52주 범위 ${fmt(L.low_52w, d)} – ${fmt(L.high_52w, d)} · 200일선 대비 ${pct(L.vs_sma200_pct, 1)}</span>`;
}
function renderProfile(c) {
  const p = c.profile.data || {};
  const kv = [["시가총액", big(p.marketCap, c.market === "KR" ? "KRW" : "USD")], ["PER(후행)", fmt(p.trailingPE, 1)], ["PER(예상)", fmt(p.forwardPE, 1)],
    ["PBR", fmt(p.priceToBook, 2)], ["배당수익률", isNum(p.dividendYield) ? `${fmt(p.dividendYield, 2)}%` : DASH],
    ["베타", fmt(p.beta, 2)], ["평균 거래량", big(p.averageVolume, "")], ["상장 주식수", big(p.sharesOutstanding, "")]];
  $("#s-head").innerHTML = `<div class="head"><h2 style="margin:0">${esc(p.longName || p.shortName || c.ticker)} <span class="meta" style="margin:0">${esc(c.ticker)} · ${esc(p.exchange || "")}</span></h2>
      <button class="ghost" id="addw">＋ 관심종목</button></div>
    <div class="head" id="s-price"></div>
    <div class="meta">${esc([p.sector, p.industry].filter(Boolean).join(" · "))}${p.website ? ` · <a href="${esc(p.website)}" target="_blank" rel="noopener noreferrer">웹사이트</a>` : ""}</div>
    <div class="kv">${kv.map(([k, v]) => `<div><span>${k}</span><b class="num">${v}</b></div>`).join("")}</div>
    ${p.longBusinessSummary ? `<div class="summary" id="sum" title="눌러서 펼치기">${esc(p.longBusinessSummary)}</div><div class="meta">사업 설명은 Yahoo 제공 영문 원문입니다.</div>` : ""}
    ${meta(c.profile.source, c.profile.fetched_at, badge(c.profile.status))}`;
  renderHeadPrice();
  const s = $("#sum"); if (s) s.onclick = () => s.classList.toggle("open");
  $("#addw").onclick = async () => { try { await api("/api/watchlist/add", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticker: c.ticker }) }); $("#addw").textContent = "✓ 추가됨"; state.loaded.watch = false; } catch (e) { alert(ERR_KO[e.message] || e.message); } };
}
function renderFund(f) {
  const el = $("#s-fund");
  if (!f || f.status === "UNAVAILABLE" || !f.years || !f.years.length) {
    el.innerHTML = `<h2>연간 재무 요약 ${badge("UNAVAILABLE")}</h2><div class="empty">${esc(f && f.reason || "재무 데이터가 없습니다.")}</div>`; return;
  }
  const cell = (r, y) => {
    const v = r.values[y];
    if (r.unit === "ratio") return isNum(v) ? (r.key === "debt_ratio" ? `${(v * 100).toFixed(0)}%` : pct(v * 100, 1, false)) : DASH;
    if (r.unit === "USD/shares") return isNum(v) ? `$${v.toFixed(2)}` : DASH;
    if (r.unit === "KRW/shares") return isNum(v) ? `${Math.round(v).toLocaleString("ko-KR")}원` : DASH;
    return big(v, r.unit === "KRW" ? "KRW" : "USD");
  };
  el.innerHTML = `<h2>연간 재무 요약 ${badge(f.status)}</h2>
    <div class="tbl-wrap"><table><thead><tr><th>항목 (회계연도 종료일)</th>${f.years.map((y) => `<th>${esc(y)}</th>`).join("")}</tr></thead>
    <tbody>${f.rows.map((r) => `<tr><td title="${esc(Object.values(r.concepts || {}).filter(Boolean)[0] || "")}">${esc(r.label)}</td>${f.years.map((y) => `<td class="num">${cell(r, y)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    <div class="meta">— 는 공시에 해당 항목이 없거나 형식이 달라 확인할 수 없는 값입니다 (0이 아닙니다). 금융업처럼 영업이익을 따로 보고하지 않는 업종은 비어 있을 수 있습니다.</div>
    ${meta(f.source, f.fetched_at, esc(f.note))}`;
}
const FORM_KO = { "10-K": "연간보고서", "10-Q": "분기보고서", "8-K": "주요사항", "4": "내부자 거래", "DEF 14A": "주총 위임장",
  "S-3": "증권신고", "SC 13G": "대량보유", "SC 13G/A": "대량보유 변경", "144": "매도 예정 신고", "11-K": "종업원 플랜" };
function renderFilings(f) {
  const el = $("#s-fil");
  const name = f.market === "KR" ? "DART" : "SEC";
  if (f.status === "UNAVAILABLE") { el.innerHTML = `<h2>최근 ${name} 공시 ${badge("UNAVAILABLE")}</h2><div class="empty">${esc(f.reason || "")}</div>`; return; }
  el.innerHTML = `<h2>최근 ${name} 공시 ${badge(f.status)}</h2><div class="tbl-wrap"><table><thead><tr><th>제출일</th><th class="l">양식</th><th class="l">설명</th><th class="l">원문</th></tr></thead>
    <tbody>${f.items.map((i) => `<tr><td>${esc(i.filing_date)}</td><td class="l"><b>${esc(i.form)}</b> <span class="meta" style="margin:0">${esc(FORM_KO[i.form] || "")}</span></td>
      <td class="l">${esc(i.description || "")}</td><td class="l">${i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">열기 ↗</a>` : DASH}</td></tr>`).join("")}</tbody></table></div>
    ${meta(f.source, f.fetched_at)}`;
}

// candle chart with SMA overlays, volume pane and crosshair tooltip
function drawPrice() {
  const cv = $("#pc"), c = lastChart;
  if (!cv || !c || !c.bars.length || !cv.isConnected) return;
  const H = window.innerWidth < 600 ? 300 : 420;
  const { ctx, w, h } = setupCanvas(cv, H);
  const bars = c.bars, n = bars.length, padR = 58, padT = 8, volH = Math.round(h * 0.18), gap = 18, priceH = h - volH - gap - padT - 18;
  const pw = w - padR, bw = pw / n;
  let lo = Infinity, hi = -Infinity, vmax = 0;
  bars.forEach((b) => { for (const k of ["low", "high", "close", "sma20", "sma50", "sma200"]) if (isNum(b[k])) { lo = Math.min(lo, b[k]); hi = Math.max(hi, b[k]); } if (isNum(b.volume)) vmax = Math.max(vmax, b.volume); });
  const pad = (hi - lo) * 0.04 || 1; lo -= pad; hi += pad;
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * priceH, x = (i) => i * bw + bw / 2;
  const grid = cssVar("--grid"), muted = cssVar("--muted"), up = cssVar("--up"), dn = cssVar("--down");
  ctx.font = "11px -apple-system, sans-serif"; ctx.textBaseline = "middle";
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4, yy = y(v);
    ctx.strokeStyle = grid; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(pw, yy); ctx.stroke();
    ctx.fillStyle = muted; ctx.fillText(v.toFixed(v >= 100 ? 0 : 2), pw + 6, yy);
  }
  // date labels
  ctx.textBaseline = "top"; ctx.textAlign = "center";
  const step = Math.max(1, Math.round(n / (w < 600 ? 4 : 7)));
  for (let i = step; i < n - step / 3; i += step) ctx.fillText(bars[i].date.slice(2, 7).replace("-", "."), x(i), h - 14);
  ctx.textAlign = "left";
  const candle = bw >= 1.8;
  bars.forEach((b, i) => {
    const o = isNum(b.open) ? b.open : b.close, col = b.close >= o ? up : dn;
    ctx.strokeStyle = col; ctx.fillStyle = col;
    if (candle && isNum(b.high) && isNum(b.low)) {
      ctx.beginPath(); ctx.moveTo(x(i), y(b.high)); ctx.lineTo(x(i), y(b.low)); ctx.stroke();
      const top = y(Math.max(o, b.close)), ht = Math.max(1, Math.abs(y(o) - y(b.close)));
      ctx.fillRect(x(i) - bw * 0.35, top, Math.max(1, bw * 0.7), ht);
    }
    if (isNum(b.volume) && vmax) { ctx.globalAlpha = 0.45; const vh = (b.volume / vmax) * volH; ctx.fillRect(i * bw + bw * 0.1, h - 18 - vh, Math.max(1, bw * 0.8), vh); ctx.globalAlpha = 1; }
  });
  if (!candle) line(ctx, bars.map((b) => b.close), x, y, cssVar("--ink"), 1.3);
  [["sma20", "--sma20"], ["sma50", "--sma50"], ["sma200", "--sma200"]].forEach(([k, v]) => line(ctx, bars.map((b) => b[k]), x, y, cssVar(v), 1.2));
  // crosshair
  cv.onmousemove = (e) => {
    const r = cv.getBoundingClientRect(), i = Math.min(n - 1, Math.max(0, Math.floor((e.clientX - r.left) / bw))), b = bars[i];
    const tip = $("#tip"); tip.hidden = false;
    tip.innerHTML = `<b>${esc(b.date)}</b><br>시 ${fmt(b.open)} 고 ${fmt(b.high)} 저 ${fmt(b.low)} 종 ${fmt(b.close)}<br>거래량 ${big(b.volume, "")}<br>
      <span style="color:var(--sma20)">20일</span> ${fmt(b.sma20)} · <span style="color:var(--sma50)">50일</span> ${fmt(b.sma50)} · <span style="color:var(--sma200)">200일</span> ${fmt(b.sma200)}`;
    const tx = e.clientX + 14 + tip.offsetWidth > window.innerWidth ? e.clientX - tip.offsetWidth - 14 : e.clientX + 14;
    tip.style.left = tx + "px"; tip.style.top = e.clientY + 14 + "px";
  };
  cv.onmouseleave = () => ($("#tip").hidden = true);
}
function line(ctx, vals, x, y, color, lw) {
  ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.beginPath(); let pen = false;
  vals.forEach((v, i) => { if (!isNum(v)) { pen = false; return; } pen ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v)); pen = true; });
  ctx.stroke();
}

// ------------------------------------------------------------------ 거시
async function renderMacro() {
  const el = $("#tab-macro"), mk = state.market; el.innerHTML = loading;
  try {
    const d = await api(mq("/api/macro")); if (mk !== state.market) return; state.loaded.macro = true;
    el.innerHTML = `${d.reason ? `<div class="notice">${esc(d.reason)}</div>` : ""}<div class="panel"><h2>${mk === "KR" ? "한국" : "미국"} 거시 지표</h2><div class="mgrid">${d.items.map((m) => `<div class="mcard">
      <div class="nm meta" style="margin:0">${esc(m.label)} <span>${esc(m.id)}</span> ${m.status !== "REAL" ? badge(m.status) : ""}</div>
      <div class="row" style="display:flex;justify-content:space-between;align-items:baseline;gap:8px"><span class="px num" style="font-size:20px;font-weight:650">${fmtMacro(m, m.value)}</span>
        <span class="meta" style="margin:0">${esc(m.date || "")}</span></div>
      <div class="meta" style="margin:0">직전 ${fmtMacro(m, m.previous)} · 1년 전 ${fmtMacro(m, m.value_1y_ago)}</div>
      <canvas data-m="${esc(m.id)}"></canvas></div>`).join("")}</div>
      <div class="meta">${mk === "KR" ? "소비자물가" : "CPI"}는 전년 동월 대비 상승률(%)로 계산해 표시합니다. 차트는 최근 약 260개 관측치입니다.</div>${meta(d.source)}</div>`;
    const draw = () => d.items.forEach((m) => { const cv = el.querySelector(`canvas[data-m="${m.id}"]`); if (cv && cv.isConnected) mini(cv, m.series); });
    draw(); redrawers.add(draw);
  } catch (e) { el.innerHTML = errBox(e); }
}
function fmtMacro(m, v) {
  if (!isNum(v)) return DASH;
  if (m.unit === "천 명") return Math.round(v).toLocaleString("ko-KR");
  if (m.unit === "원") return v.toLocaleString("ko-KR", { maximumFractionDigits: 1 });
  return `${v.toFixed(2)}${m.unit}`;
}
function mini(cv, series) {
  const pts = (series || []).filter((p) => isNum(p[1]));
  if (pts.length < 2) return;
  const { ctx, w, h } = setupCanvas(cv, 90);
  const v = pts.map((p) => p[1]), lo = Math.min(...v), hi = Math.max(...v), rg = hi - lo || 1;
  const x = (i) => (i / (pts.length - 1)) * (w - 2) + 1, y = (val) => 4 + (1 - (val - lo) / rg) * (h - 18);
  if (lo < 0 && hi > 0) { ctx.strokeStyle = cssVar("--line"); ctx.beginPath(); ctx.moveTo(0, y(0)); ctx.lineTo(w, y(0)); ctx.stroke(); }
  line(ctx, v, x, y, cssVar("--accent"), 1.5);
  ctx.fillStyle = cssVar("--muted"); ctx.font = "10px -apple-system, sans-serif"; ctx.textBaseline = "bottom";
  ctx.fillText(pts[0][0].slice(0, 7), 1, h); ctx.textAlign = "right"; ctx.fillText(pts[pts.length - 1][0].slice(0, 7), w - 1, h); ctx.textAlign = "left";
}

// ------------------------------------------------------------------ 관심종목
async function renderWatch() {
  const el = $("#tab-watch"), mk = state.market, d0 = mk === "KR" ? 0 : 2;
  if (!el.innerHTML) el.innerHTML = loading;
  try {
    const d = await api(mq("/api/watchlist")); if (mk !== state.market) return; state.loaded.watch = true;
    el.innerHTML = `<div class="panel"><h2>${mk === "KR" ? "한국" : "미국"} 관심종목 <span class="meta" style="margin:0">${d.tickers.length}개</span></h2>
      <form class="addrow" id="wadd"><input id="wq" placeholder="추가할 종목 코드" maxlength="15"><button type="submit">추가</button></form>
      ${d.items.length ? `<div class="tbl-wrap"><table><thead><tr><th>종목</th><th>종가</th><th>전일 대비</th><th>1개월</th><th class="l">추세(30일)</th><th class="l">스윙 점수</th><th class="l">장기 점수</th><th class="l">상태</th><th></th></tr></thead>
      <tbody>${d.items.map((i) => `<tr class="click" data-ticker="${esc(i.symbol)}"><td><b>${esc(i.symbol)}</b> ${i.name ? `<span class="meta" style="margin:0">${esc(i.name)}</span>` : ""}</td><td class="num">${fmt(i.close, d0)}</td><td>${pct(i.change_pct)}</td><td>${pct(i.change_1m_pct, 1)}</td>
        <td class="l"><canvas style="width:80px;height:24px" data-spark='${JSON.stringify(i.spark || [])}'></canvas></td><td class="l">${watchScore(i.qsf, "SWING")}</td><td class="l">${watchScore(i.qsf, "LONG_TERM")}</td><td class="l">${badge(i.status)} ${liveBadge(i.intraday)} <span class="meta">${esc(i.date || "")}</span></td>
        <td><button class="x" data-rm="${esc(i.symbol)}" title="삭제">✕</button></td></tr>`).join("")}</tbody></table></div>` : '<div class="empty">관심종목이 없습니다.</div>'}
      ${d.qsf_scan && d.qsf_scan.status === "REAL" ? `<div class="meta">점수는 ${esc(d.qsf_scan.session)} 거래일 스캔(${esc(d.qsf_scan.model_version)})에 기록된 값입니다. 스캔 대상이 아닌 종목은 비워 둡니다. 점수 탭에서 다시 계산할 수 있습니다.</div>` : ""}
      ${d.cache ? meta(d.source, d.cache.fetched_at) : ""}<div class="meta">관심종목은 이 Mac의 data/terminal/watchlist.json 에만 저장됩니다.</div></div>`;
    const draw = () => el.querySelectorAll("canvas[data-spark]").forEach((cv) => spark(cv, JSON.parse(cv.dataset.spark)));
    draw(); redrawers.add(draw);
    $("#wadd").onsubmit = (e) => { e.preventDefault(); watchOp("add", $("#wq").value); };
    el.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); watchOp("remove", b.dataset.rm); }));
  } catch (e) { el.innerHTML = errBox(e); }
}
// 스캔에 기록된 점수만 보여 줍니다. 여기서 계산하지 않습니다. 색은 점수 탭과 같은 기준이고 글자로도 적습니다.
function watchScore(q, strategy) {
  const c = q && q[strategy];
  if (!c || c.score === null || c.score === undefined) return '<span class="missing">스캔 밖</span>';
  const tone = typeof qsfClass === "function" ? qsfClass(c.action, c.score) : "act-hold";
  return `<b class="num">${Number(c.score).toFixed(1)}</b> <span class="qsf-act ${tone}"><i></i>${esc(c.action_label || c.action || "")}</span>`;
}
async function watchOp(op, t) {
  t = (t || "").trim(); if (!t) return;
  try { await api(`/api/watchlist/${op}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticker: t }) }); setMarket(marketOf(t.toUpperCase()), false); renderWatch(); }
  catch (e) { alert(ERR_KO[e.message] || e.message); }
}

// ------------------------------------------------------------------ 모델 (읽기 전용)
const REC_KO = { "REAL RECOMMENDATION": "정상 추천", "PARTIAL RECOMMENDATION": "부분 추천", "NO VALID RECOMMENDATION": "유효 추천 없음" };
const REGIME_KO = { BULL: "상승장", BEAR: "하락장", SIDEWAYS: "횡보장", RISK_OFF: "위험 회피", RISK_ON: "위험 선호" };
const OUT_KO = { PENDING_ENTRY: "진입 대기", PENDING_OUTCOME: "보유 중(결과 대기)", COMPLETED_OUTCOME: "완료", INCOMPLETE: "데이터 불완전",
  VALID_PROSPECTIVE: "유효", PRE_FIX_EXCLUDED: "수정 전 제외", DATA_INVALID: "데이터 무효" };
const outKo = (k) => String(k).split("/").map((x) => OUT_KO[x] || x).join(" · ");
// Amounts follow the box as typed; the list itself comes from the recorded scan and changes only at the next scan.
function wireCapital(el, cap, b, mk) {
  const input = $("#capInput"), note = $("#capNote");
  let saved = isNum(cap.amount) ? cap.amount : null;
  const money = (v) => mk === "KR" ? `${Math.round(v).toLocaleString("ko-KR")}원` : `$${Math.round(v).toLocaleString("en-US")}`;
  const parse = () => { const t = input.value.replace(/[,_$\s]/g, ""); if (!t) return null; const v = Number(t); return Number.isFinite(v) && v > 0 ? v : NaN; };
  const nextScan = mk === "KR" ? "한국 스캔은 일일 작업에 없으니 <code>python app.py --market KR scan</code>으로 실행하세요." : "다음 일일 작업의 스캔부터 이 금액을 씁니다.";
  const refresh = (msg) => {
    const typed = parse(), base = typed === null ? (isNum(b.capital) ? b.capital : null) : typed;
    el.querySelectorAll("[data-cap-amount]").forEach((c) => { const w = parseFloat(c.dataset.w); c.innerHTML = base && !isNaN(base) && !isNaN(w) ? money(w * base) : DASH; });
    el.querySelectorAll("[data-cap-shares]").forEach((c) => { const w = parseFloat(c.dataset.w), p = parseFloat(c.dataset.close); c.innerHTML = base && !isNaN(base) && !isNaN(w) && p > 0 ? Math.floor(w * base / p).toLocaleString("ko-KR") : DASH; });
    const parts = [];
    if (msg) parts.push(msg);
    if (Number.isNaN(typed)) parts.push("0보다 큰 숫자로 입력하세요.");
    else if (typed !== saved) parts.push("저장 전 미리보기입니다.");
    else if (saved === null) parts.push(cap.invalid ? "저장된 값을 읽을 수 없습니다. 다시 입력하세요." : "자본금이 없어 P6-11B 스캔을 건너뜁니다.");
    if (!Number.isNaN(typed) && base && isNum(b.capital) && base !== b.capital) parts.push(`금액과 주수만 환산했습니다. 추천 종목은 스캔 당시 자본 ${money(b.capital)} 기준이라 다음 스캔에서 달라질 수 있습니다.`);
    note.innerHTML = parts.join(" ");
  };
  input.oninput = () => refresh();
  $("#capSave").onclick = async () => {
    if (Number.isNaN(parse())) return refresh();
    try {
      const r = await api("/api/capital", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ market: mk, amount: parse() === null ? "" : parse() }) });
      saved = isNum(r.amount) ? r.amount : null;
      refresh(saved === null ? "지웠습니다." : `저장했습니다. ${nextScan}`);
    } catch (e) { refresh(esc(ERR_KO[e.message] || e.message)); }
  };
  refresh();
}
async function renderModel() {
  const el = $("#tab-model"), mk = state.market; el.innerHTML = loading;
  try {
    const [d, cap] = await Promise.all([api(mq("/api/model")), api(mq("/api/capital"))]); if (mk !== state.market) return; state.loaded.model = true;
    const b = d.baseline, t = d.tracking;
    el.innerHTML = `<div class="panel"><h2>${esc(b.name)} ${badge(b.status || "FROZEN")} <span class="meta" style="margin:0">${esc(b.role)}</span></h2>
      <div class="form" style="margin:8px 0 12px"><label>투자 자본금 (${esc(cap.currency)})<input id="capInput" inputmode="decimal" autocomplete="off" value="${isNum(cap.amount) ? cap.amount : ""}" placeholder="금액 입력"></label><button id="capSave">저장</button><div class="wide meta" id="capNote" style="margin:0"></div></div>
      ${b.run_id ? `<div class="kv"><div><span>최근 전체 스캔</span><b>${when(b.executed_at)}</b></div><div><span>결과</span><b>${esc(REC_KO[b.recommendation_status] || b.recommendation_status)}</b></div>
        <div><span>시장 국면</span><b>${esc(REGIME_KO[b.regime] || b.regime || "—")}</b></div><div><span>기준 자본</span><b class="num">${isNum(b.capital) ? b.capital.toLocaleString("ko-KR") + " " + esc(b.currency || "") : DASH}</b></div></div>
      <h3>추천 상위 종목</h3><div class="tbl-wrap"><table><thead><tr><th>순위</th><th class="l">종목</th><th class="l">섹터</th><th>기준가</th><th>${mk === "KR" ? "점수" : "알파"}</th><th>목표 비중</th><th>목표 금액</th><th>주수</th><th>손절가</th><th>보유 기간</th></tr></thead>
      <tbody>${(b.top5 || []).map((r) => `<tr class="click" data-ticker="${esc(r.ticker)}"><td>${esc(r.recommendation_rank)}</td><td class="l"><b>${esc(r.ticker)}</b> <span class="meta" style="margin:0">${esc(r.name || "")}</span></td>
        <td class="l">${esc(r.sector || "")}</td><td class="num">${fmt(r.close, mk === "KR" ? 0 : 2)}</td><td class="num">${fmt(r.alpha, 3)}</td><td class="num">${isNum(r.target_weight) ? (r.target_weight * 100).toFixed(1) + "%" : DASH}</td>
        <td class="num" data-cap-amount data-w="${isNum(r.target_weight) ? r.target_weight : ""}">${DASH}</td><td class="num" data-cap-shares data-w="${isNum(r.target_weight) ? r.target_weight : ""}" data-close="${isNum(r.close) ? r.close : ""}">${DASH}</td>
        <td class="num">${fmt(r.hard_stop)}</td><td>${isNum(r.horizon_days) ? r.horizon_days + "거래일" : DASH}</td></tr>`).join("") || '<tr><td colspan="10" class="empty">추천 종목 없음</td></tr>'}</tbody></table></div>
      <div class="meta">실행 ID ${esc(b.run_id)} · 읽기 전용 표시입니다. 이 화면은 모델을 실행하거나 변경하지 않습니다.</div>` : '<div class="empty">기록된 전체 스캔이 없습니다.</div>'}</div>
      <div class="panel"><h2>전향적 추적 ${badge(t.status)}</h2>${t.status === "REAL" ? `<div class="kv"><div><span>기록된 실행</span><b>${esc(t.runs)}</b></div><div><span>관찰 건수</span><b>${esc(t.observations)}</b></div>
        <div><span>최근 갱신</span><b>${esc(t.latest_update || "—")}</b></div></div>
        ${t.outcome_states ? `<div class="kv">${Object.entries(t.outcome_states).map(([k, v]) => `<div><span>${esc(outKo(k))}</span><b>${esc(v)}</b></div>`).join("")}</div>` : ""}
        <div class="meta">표본이 충분히 쌓이기 전에는 성과를 판단할 수 없습니다.</div>` : `<div class="empty">추적 데이터를 읽지 못했습니다 (${esc(t.error || "")}).</div>`}</div>
      <div class="panel"><h2>도전자 모델</h2><div class="empty">${esc(d.challenger_note)}</div></div>`;
    wireCapital(el, cap, b, mk);
  } catch (e) { el.innerHTML = errBox(e); }
}

const ALWAYS_FRESH = new Set(["watch", "portfolio", "assist", "model"]);
const RENDER = { overview: renderOverview, macro: renderMacro, watch: renderWatch, model: renderModel, stock: renderStock };

// ------------------------------------------------------------------ boot
applyTheme(theme);
paintMarket();
api("/api/health").then((h) => ($("#health").textContent = `· ${h.version} · SEC ${h.sec === "CONFIGURED" ? "연결 설정됨" : "미설정"} · ECOS ${h.ecos === "CONFIGURED" ? "연결 설정됨" : "미설정"}`)).catch(() => {});
let booted = false;
function fromHash() {
  const [tab, tk] = location.hash.replace(/^#/, "").split("/");
  if (booted && tab === state.tab && (tab !== "stock" || (tk || "").toUpperCase() === state.ticker)) return;
  booted = true;
  if (tab === "stock" && tk) { state.ticker = decodeURIComponent(tk).toUpperCase(); state.loaded.stock = null; setMarket(marketOf(state.ticker), false); }
  show(RENDER[tab] ? tab : "overview", false);
}
window.addEventListener("hashchange", fromHash);
window.addEventListener("DOMContentLoaded", fromHash);   // after every script (portfolio.js) has registered
