// Agent 8 scratch: render one stock's score-tab detail with the program's own screen scripts (qsf.js, committee.js,
// forecast.js) and count what the user sees.  Reads only files; no network.  Usage: node count_card.js <repo> <evaluate.json> <forecast.json> <history.json>
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");
const [repo, evalFile, fcFile, histFile] = process.argv.slice(2);
const read = (f) => JSON.parse(fs.readFileSync(f, "utf8"));
const boxes = {};
const box = (sel) => (boxes[sel] = boxes[sel] || { innerHTML: "", isConnected: true, hidden: false, dataset: {}, querySelector: () => ({}), querySelectorAll: () => [], addEventListener() {}, classList: { toggle() {} }, setAttribute() {} });
const files = { forecast: read(fcFile), history: read(histFile) };
const ctx = {
  console, isFinite, Number, Math, JSON, Object, Array, String, Date, Promise, Set, Map, encodeURIComponent, CSS: { escape: (s) => s },
  localStorage: { getItem: () => null, setItem() {} },
  document: { addEventListener() {}, querySelectorAll: () => [], querySelector: () => null },
  window: { scrollTo() {}, innerWidth: 1200 }, location: { hash: "" },
  state: { market: "US", tab: "qsf", loaded: {}, card: null }, RENDER: {}, RETURN: {}, ALWAYS_FRESH: new Set(),
  $: (sel) => box(sel),
  api: (p) => p.includes("/api/qsf/forecast-stock") ? Promise.resolve(files.forecast) : p.includes("/api/qsf/history") ? Promise.resolve(files.history) : Promise.reject(new Error("NOT_FETCHED_BY_THIS_SCRIPT")),
};
// helpers copied in meaning from app.js (app.js itself wires the DOM at load, so it is not loaded here)
vm.createContext(ctx);
vm.runInContext(`
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const isNum = (v) => typeof v === "number" && isFinite(v);
  const DASH = '<span class="missing">—</span>';
  function fmt(v, d = 2) { return isNum(v) ? v.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d }) : DASH; }
  function pct(v, d = 2, sign = true) { if (!isNum(v)) return DASH; const cls = v > 0 ? "up" : v < 0 ? "down" : "flat"; return '<span class="' + cls + ' num">' + (sign && v > 0 ? "+" : "") + v.toFixed(d) + '%</span>'; }
  function when(iso) { return iso || "—"; }
  const ERR_KO = {}; const isKR = () => state.market === "KR"; const marketOf = () => state.market; const redrawers = new Set();
  const sectorKo = (s) => s || ""; const meta = () => ""; const badge = (s) => String(s); const big = (v) => String(v); const cssVar = () => ""; function setupCanvas() { return {}; }
  const loading = ""; const errBox = (e) => ""; function tabHash() { return ""; } function prefillTicker() {} function show() {} function setMarket() {}
`, ctx);
for (const f of ["qsf.js", "committee.js", "forecast.js"]) vm.runInContext(fs.readFileSync(path.join(repo, "terminal/static", f), "utf8"), ctx, { filename: f });

const d = read(evalFile);
ctx.state.market = d.market;
ctx.__d = d;
vm.runInContext(`qsfState.detail = __d; qsfDrawDetail(__d);`, ctx);

const strip = (h) => h.replace(/<[^>]+>/g, " ").replace(/&[a-z#0-9]+;/g, " ").replace(/\s+/g, " ").trim();
// what is visible before any click: the body of a closed <details> is hidden, its <summary> stays
function closeFolds(h) {
  let prev;
  do { prev = h; h = h.replace(/<details(?![^>]*\sopen)[^>]*>\s*(<summary>[\s\S]*?<\/summary>)(?:(?!<details)[\s\S])*?<\/details>/g, "$1"); } while (h !== prev);
  return h;
}
function count(h) {
  const text = strip(h);
  const dates = (text.match(/\d{4}-\d{2}-\d{2}/g) || []).length;
  const nums = (text.replace(/\d{4}-\d{2}-\d{2}/g, " ").match(/[-+−]?\d[\d,]*(?:\.\d+)?%?/g) || []).length;
  return { chars: text.length, numbers_not_dates: nums, dates, badges: (h.match(/class="badge/g) || []).length, action_pills: (h.match(/class="qsf-act/g) || []).length,
    notice_boxes: (h.match(/class="notice/g) || []).length, grey_meta_lines: (h.match(/class="meta"/g) || []).length, bars: (h.match(/class="qsf-bar/g) || []).length,
    tables: (h.match(/<table/g) || []).length, folds: (h.match(/<details/g) || []).length, buttons: (h.match(/<button/g) || []).length,
    honesty_phrases: (text.match(/참고|점수에 포함되지 않|점수 미반영|점수와 무관|검증|근거|가설|자문이 아닙|주문/g) || []).length };
}
setTimeout(() => {       // let the forecast and history promises fill their boxes
  const main = boxes["#qsfdetail"].innerHTML, fc = (boxes["#qsffc"] || {}).innerHTML || "", hist = (boxes["#qsfhistory"] || {}).innerHTML || "";
  const full = main.replace('<div id="qsffc"><div class="meta">불러오는 중…</div></div>', `<div id="qsffc">${fc}</div>`).replace('<div id="qsfhistory"></div>', `<div id="qsfhistory">${hist}</div>`);
  const out = { ticker: d.ticker, market: d.market, note: "the same-day panel (/api/today: quote, filings, news) is NOT included; it was not fetched",
    everything_including_folded: count(full), visible_before_any_click: count(closeFolds(full)) };
  const cards = [...main.matchAll(/<article class="qsf-card">[\s\S]*?<\/article>/g)].map((m) => m[0]);
  out.one_score_card_visible = cards.map((c) => count(closeFolds(c)));
  out.one_score_card_everything = cards.map((c) => count(c));
  const ic = main.match(/<div class="panel"><h3>다섯 투자자와 투자위원회[\s\S]*?<div class="ic-out"><\/div>/);
  if (ic) { out.committee_block_visible = count(closeFolds(ic[0])); out.committee_block_everything = count(ic[0]); }
  out.forecast_block_visible = count(closeFolds(fc)); out.forecast_block_everything = count(fc);
  console.log(JSON.stringify(out, null, 1));
  fs.writeFileSync(path.join(path.dirname(evalFile), `rendered_${d.ticker}.html`), full);
  fs.writeFileSync(path.join(path.dirname(evalFile), `rendered_${d.ticker}_visible.txt`), strip(closeFolds(full)));
}, 200);
