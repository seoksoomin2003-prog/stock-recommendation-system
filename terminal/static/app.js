// 퀀트 터미널 (TERMINAL-1) — vanilla JS, no external libraries.  Missing values are shown as "—", never 0.
"use strict";
const $ = (s, el = document) => el.querySelector(s);
// 저장 키 이름 (5차 묶음 P3-6): 이 브라우저에 남기는 설정은 모두 qse-로 시작합니다.  옛 이름의 값은 한 번 옮기고 옛 키는 지웁니다.
const STORE_RENAMES = [["recentTickers", "qse-recent"], ["qsfView", "qse-qsf-view"], ["qsfFolds", "qse-qsf-folds"], ["heatView", "qse-heat-view"],
  ["chartAnalysis", "qse-chart"], ["compareTickers", "qse-compare"]];
try {
  for (const [old, now] of STORE_RENAMES) {
    const v = localStorage.getItem(old);
    if (v === null) continue;
    if (localStorage.getItem(now) === null) localStorage.setItem(now, v);
    localStorage.removeItem(old);
  }
} catch (e) { /* storage unavailable: defaults */ }
// 화면 너비 단계 (5차 묶음 P2-11): 폰 640px 이하 · 태블릿 641~1023 · 컴퓨터 1024~1599 · 넓은 화면 1600 이상.  JS는 이 한 곳에서 묻습니다.
const isPhone = () => window.matchMedia("(max-width: 640px)").matches;
// 바깥 주소 링크는 http(s)만 엽니다 (5차 묶음 P3-8).  다른 스킴이면 링크를 만들지 않습니다.
const safeUrl = (u) => (/^https?:\/\//i.test(String(u || "").trim()) ? String(u).trim() : "");
const STATUS_KO = { REAL: "실데이터", STALE: "지연·오래됨", UNAVAILABLE: "데이터 없음", FROZEN: "고정", EXPERIMENTAL: "실험" };
const state = { tab: "overview", ticker: null, card: null, range: "1y", loaded: {}, market: "US" };
try { const m = localStorage.getItem("qse-market"); if (m === "KR" || m === "COIN") state.market = m; } catch (e) { /* storage unavailable */ }
// 코인 시장은 주식 탭을 쓰지 않습니다: '오늘'과 '코인' 묶음만 보입니다.  주식 시장에서는 '코인' 묶음이 숨습니다.
const isCoin = () => state.market === "COIN";
const groupShown = (g) => (isCoin() ? g === "today" || g === "coin" : g !== "coin");
const ANY_MARKET = new Set(["account"]);        // 시장 스위치와 상관없이 열리는 탭: 통합 '내 계좌'는 세 계좌를 한꺼번에 봅니다
const KR_RE = /^[0-9][0-9A-Z]{5}$/;
const marketOf = (t) => (KR_RE.test(String(t).toUpperCase()) ? "KR" : "US");
const isKR = () => state.market === "KR";
const mq = (path) => `${path}${path.includes("?") ? "&" : "?"}market=${state.market}`;

let screenStamp = null, healthAt = 0;      // 화면 파일 표식과 마지막 확인 시각 (아래 loadHealth)
// ------------------------------------------------------------------ helpers
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNum = (v) => typeof v === "number" && isFinite(v);
const DASH = '<span class="missing">—</span>';
// A bar's open is drawn only when it lies inside the bar's own low-high range: Yahoo sends 0 for some Korean intraday bars
// (005930 on 2026-11-23), and a body drawn from 0 ran through the volume pane.  The stored bar is left as it came.
function goodOpen(b) { return isNum(b.open) && b.open > 0 && (!isNum(b.low) || b.open >= b.low) && (!isNum(b.high) || b.open <= b.high); }
// 종목 이름표 (4차 묶음 P2-10, 사용자 결정 2026-11-23): 한국 종목은 이름을 굵게 앞에, 6자리 코드는 흐리게 뒤에 둡니다.
// 미국 종목은 코드가 앞입니다.  이름이 없으면 코드만 씁니다.
const nameFirst = (t, name) => !!name && marketOf(t) === "KR";
function tickerLabel(t, name, attrs = "") {
  if (nameFirst(t, name)) return `<b${attrs}>${esc(name)}</b> <span class="meta m0">${esc(t)}</span>`;
  return `<b${attrs}>${esc(t)}</b>${name ? ` <span class="meta m0">${esc(name)}</span>` : ""}`;
}
const tickerText = (t, name) => (nameFirst(t, name) ? `${name} ${t}` : `${t}${name ? " " + name : ""}`);
// 시각은 한 형식으로 (4차 묶음 P3-11, 사용자 결정): 2026-11-23 12:23, 이 기기의 시각(한국에서는 한국 시각)입니다.
function stamp(v) {
  const d = v instanceof Date ? v : new Date(v);
  if (isNaN(d)) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function fmt(v, d = 2) { return isNum(v) ? v.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d }) : DASH; }
function pct(v, d = 2, sign = true) {
  if (!isNum(v)) return DASH;
  const cls = v > 0 ? "up" : v < 0 ? "down" : "flat";
  return `<span class="${cls} num">${sign && v > 0 ? "+" : ""}${v.toFixed(d)}%</span>`;
}
function big(v, unit = "USD") {
  if (!isNum(v)) return DASH;
  const a = Math.abs(v), s = v < 0 ? "-" : "", p = unit === "USD" ? "$" : unit === "KRW" ? "₩" : "";
  // 4차 묶음 P2-5 (사용자 결정): 조·억 단위는 그대로, 쉼표를 넣고 소수 자리를 크기에 따라 정합니다 (₩1,124.6조, $3.52조, ₩8,350억).
  const n = (x, d) => x.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
  if (a >= 1e12) return `${s}${p}${n(a / 1e12, a >= 1e13 ? 1 : 2)}조`;
  if (a >= 1e8) return `${s}${p}${n(a / 1e8, a >= 1e11 ? 0 : 1)}억`;
  if (a >= 1e4) return `${s}${p}${n(a / 1e4, 1)}만`;
  return `${s}${p}${a.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}`;
}
// 서버가 쓴 문장 속 큰 금액(예: "20일 평균 거래대금 17,237,663,755달러")을 같은 조·억 표기로 바꿉니다.  1억 미만은 그대로.
function bigInText(s) {
  return String(s).replace(/(\d{1,3}(?:,\d{3})+)(?:\.\d+)?\s?(달러|원)/g, (all, num, unit) => {
    const v = Number(num.replace(/,/g, ""));
    return v >= 1e8 ? big(v, unit === "원" ? "KRW" : "USD") : all;
  });
}
// Yahoo's sector names in Korean; any other name (a Korean exchange industry, for one) is shown as it is.
const SECTOR_KO = { "Technology": "기술", "Financial Services": "금융", "Healthcare": "헬스케어", "Consumer Cyclical": "경기소비재", "Consumer Defensive": "필수소비재", "Industrials": "산업재", "Basic Materials": "소재", "Energy": "에너지", "Utilities": "유틸리티", "Real Estate": "부동산", "Communication Services": "커뮤니케이션" };
const sectorKo = (s) => SECTOR_KO[s] || s || "";
function badge(st) { return `<span class="badge ${esc(st)}">${esc(STATUS_KO[st] || st)}</span>`; }
const liveBadge = (on) => (on ? '<span class="badge live" title="정규장 진행 중: 마지막 일봉은 아직 확정되지 않았습니다">장중·미확정</span>' : "");
function when(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? esc(iso) : stamp(d);
}
function meta(source, fetched, extra = "") {
  return `<div class="meta">출처: ${esc(source)}${fetched ? ` · 받아온 시각 ${when(fetched)}` : ""}${extra ? " · " + extra : ""}</div>`;
}
// 화면 안 알림 (4차 묶음 P3-5): 브라우저 기본 경고창 대신 화면 아래에 잠깐 띄웁니다.  되돌릴 수 없는 동작의 확인(confirm)은 그대로입니다.
let toastTimer = null;
function notify(text, tone = "err") {
  const el = $("#toast");
  if (!el) return;
  el.className = `toast ${tone}`;
  el.setAttribute("role", tone === "err" ? "alert" : "status");
  el.innerHTML = `<span>${esc(text)}</span><button type="button" class="ghost">닫기</button>`;
  el.hidden = false;
  el.querySelector("button").onclick = () => { el.hidden = true; };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, tone === "err" ? 9000 : 5000);
}
// 서버가 응답하지 않으면 화면 위에 알린다.  요청 실패가 '기록 없음'으로 읽히지 않게 하려는 것이다.
let netTimer = null;
function netDown(down) {
  const bar = $("#netbar");
  if (!bar) return;
  if (!down) {
    const was = !bar.hidden;
    bar.hidden = true;
    if (netTimer) { clearInterval(netTimer); netTimer = null; }
    if (was) { state.loaded = {}; show(state.tab, false); loadHealth(); }      // 서버가 돌아왔다: 지금 탭을 다시 읽고, 화면이 업데이트됐는지도 본다
    return;
  }
  if (!bar.hidden) return;
  bar.hidden = false;
  bar.innerHTML = `<span>터미널 서버(${esc(location.host)})에 연결되지 않습니다. 지금 화면의 '기록 없음'이나 빈칸은 실제로 기록이 없다는 뜻이 아닐 수 있습니다. 서버가 응답하면 자동으로 다시 읽습니다.</span><button type="button" class="ghost" id="netretry">다시 시도</button>`;
  const ping = () => fetch("/api/automation/status", { cache: "no-store" }).then((r) => { if (r.ok) netDown(false); }).catch(() => {});
  $("#netretry").onclick = ping;
  netTimer = setInterval(ping, 5000);
}
async function api(path, opts) {
  let r;
  try { r = await fetch(path, opts); }
  catch (e) { netDown(true); throw new Error("SERVER_UNREACHABLE"); }
  if ($("#netbar") && !$("#netbar").hidden) netDown(false);
  const j = await r.json().catch(() => ({ error: "BAD_RESPONSE" }));
  if (r.status === 401 && j.error === "PHONE_NOT_PAIRED") { location.reload(); throw new Error("PHONE_NOT_PAIRED"); }      // this phone was disconnected: back to the pairing page
  if (!r.ok) throw new Error(j.error || `HTTP_${r.status}`);
  return j;
}
// What the server's error codes mean, in Korean.  A code that is not here is shown as it is, marked as a code.
const ERR_KO = { INVALID_TICKER: "종목 코드 형식이 올바르지 않습니다.", WATCHLIST_FULL: "관심종목은 최대 100개입니다.", SERVER_UNREACHABLE: "터미널 서버에 연결되지 않습니다.",
  INTERNAL_ERROR: "서버 내부 오류가 발생했습니다. 잠시 뒤 다시 해 보세요. 계속되면 터미널을 띄운 컴퓨터에서 프로그램을 껐다 켜세요(기록: data/terminal/logs/server_errors.log).", INVALID_RANGE: "기간 값이 올바르지 않습니다.",
  BAD_RESPONSE: "서버의 답을 읽지 못했습니다. 화면을 새로 고쳐 보세요.", BAD_JSON: "보낸 내용을 서버가 읽지 못했습니다. 화면을 새로 고친 뒤 다시 해 보세요.",
  BAD_LENGTH: "보낸 내용이 너무 길거나 길이가 맞지 않습니다.", METHOD_NOT_ALLOWED: "이 주소는 그 방식의 요청을 받지 않습니다.", NOT_FOUND: "그런 주소가 없습니다. 화면을 새로 고쳐 보세요.",
  FORBIDDEN_HOST: "이 주소로는 터미널을 열 수 없습니다. 터미널을 띄운 컴퓨터에서는 127.0.0.1 주소로, 휴대폰에서는 '폰 연결'에 보이는 주소로 여세요.",
  PHONE_MAC_ONLY: "이 동작은 터미널을 띄운 컴퓨터에서만 할 수 있습니다. 휴대폰에서는 모든 화면 보기와 거래 기록, 모의 매매 기록, 관심종목, 알림 조건, 질문하기가 됩니다.",
  PHONE_NOT_PAIRED: "이 기기의 연결이 끊겼습니다. 화면을 새로 고쳐 연결 코드를 다시 넣으세요.", PHONE_VIEW_OFF: "휴대폰 연결이 꺼져 있습니다. 먼저 켜세요.",
  PHONE_VIEW_UNAVAILABLE: "이 서버에서는 휴대폰 연결을 쓸 수 없습니다.", PHONE_CODE_WRONG: "코드가 맞지 않습니다.", PHONE_CODE_EXPIRED: "코드의 시간이 지났습니다. 새 코드를 만드세요.",
  PHONE_CODE_LOCKED: "틀린 횟수가 많아 이 코드는 더 쓸 수 없습니다. 새 코드를 만드세요.", PHONE_TOO_MANY: "연결된 기기가 이미 다섯 대입니다. 하나를 끊은 뒤 다시 하세요.", FORBIDDEN_ORIGIN: "다른 사이트에서 온 요청이라 받지 않았습니다.",
  FORBIDDEN_SITE: "다른 사이트에서 온 요청이라 받지 않았습니다.",
  INVALID_MARKET: "시장 값이 올바르지 않습니다(미국 또는 한국).", BAD_MARKET: "시장 값이 올바르지 않습니다(미국 또는 한국).",
  INVALID_STANCE: "성향 값이 올바르지 않습니다(방어적, 기본, 공격적).", INVALID_STRATEGY: "구분 값이 올바르지 않습니다(스윙 또는 장기).", BAD_STRATEGY: "구분 값이 올바르지 않습니다(스윙 또는 장기).",
  INVALID_DAYS: "기간(일수) 값이 올바르지 않습니다.", INVALID_SORT: "정렬 기준이 올바르지 않습니다.", INVALID_ORDER: "정렬 방향이 올바르지 않습니다.",
  INVALID_ACTION: "판단 조건 값이 올바르지 않습니다.", INVALID_CONFIDENCE: "신뢰도 조건 값이 올바르지 않습니다.", INVALID_ENTRY: "진입 상태 조건 값이 올바르지 않습니다.",
  INVALID_MIN_SCORE: "최소 점수가 숫자가 아니거나 0~100을 벗어났습니다.", INVALID_LIMIT: "줄 수 값이 올바르지 않습니다.", INVALID_OFFSET: "시작 위치 값이 올바르지 않습니다.",
  INVALID_ACTIONABLE: "'실행 가능만' 조건 값이 올바르지 않습니다.", INVALID_BUYBACK: "'자사주 매입' 조건 값이 올바르지 않습니다.",
  INVALID_NO_FINANCING: "'자금 조달 제외' 조건 값이 올바르지 않습니다.", INVALID_NO_HIGH_RISK: "'고위험 제외' 조건 값이 올바르지 않습니다.",
  BAD_TYPE: "조건의 종류를 고르세요.", BAD_VALUE: "값이 올바르지 않습니다.", TICKER_REQUIRED: "종목 코드가 필요합니다.", TOO_MANY_RULES: "알림 조건은 최대 200개입니다.",
  KEEP_AT_LEAST_ONE: "적어도 하나는 남겨 두어야 합니다.", TOO_FEW_SYMBOLS: "비교하려면 종목이 둘 이상 필요합니다.", NO_HOLDINGS: "보유 종목이 없습니다.",
  UNKNOWN_FUND: "목록에 없는 펀드입니다.", MISSING_FUNDS: "펀드 구성 자료가 없습니다.", FUND_MISMATCH: "받은 펀드 구성이 요청한 펀드와 다릅니다.", UNKNOWN_MODEL: "그런 모델이 없습니다.",
  UNKNOWN_SECURITY: "한국 거래소 종목 목록에서 찾을 수 없는 종목입니다.", MASTER_UNAVAILABLE: "한국 종목 목록을 받지 못했습니다. 잠시 뒤 다시 해 보세요.",
  NO_PRICE: "가격 이력을 받지 못했습니다.", SHORT_HISTORY: "거래 이력이 30거래일이 안 돼 점수를 내지 않습니다.", NO_NAME: "종목명을 찾지 못했습니다.",
  NO_LEDGER_SESSION: "그 날짜의 점수 기록이 없습니다.", NO_PRICES_FOR_DAY: "그날의 가격 자료가 아직 없습니다.", TOO_FEW_STOCKS: "그날 자료가 있는 종목이 너무 적어 계산하지 않았습니다.",
  TOO_FEW_SCORES: "그날 점수가 있는 종목이 너무 적어 계산하지 않았습니다.", ROWS_DIFFER: "기록의 줄이 서로 맞지 않습니다. 기록 파일을 확인해야 합니다.",
  ROWS_NOT_IN_ORDER: "기록의 줄 순서가 맞지 않습니다. 기록 파일을 확인해야 합니다.", FORMER_COMPOSITION: "예전 구성으로 만든 기록이라 지금 방식으로 읽지 않습니다.",
  TEST_DATA_IN_DEVELOPMENT: "시험용 자료가 섞여 있어 처리하지 않았습니다.", RSS_WITH_DTD: "뉴스 제공처의 답이 허용하지 않는 형식이라 읽지 않았습니다." };
// The sentence for a failed request: the code's Korean text, else the server's own sentence, else the code marked as one.
function errKo(e) {
  const m = (e && e.message) || String(e);
  if (ERR_KO[m]) return ERR_KO[m];
  const h = /^HTTP_(\d+)$/.exec(m);
  if (h) return `서버가 요청을 처리하지 못했습니다(HTTP ${h[1]}).`;
  return /^[A-Z][A-Z0-9_]+$/.test(m) ? `오류 코드 ${m}` : m;
}
// '쉽게 설명해줘': a stock card or a portfolio in everyday words.  terminal/plain.py writes the text; nothing is fetched here.
function plainBlock(doc) {
  if (!doc || !doc.parts) return "";
  const parts = doc.parts.map((p) => `<h4>${esc(p.h)}</h4><ul>${p.lines.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`).join("");
  const words = (doc.words || []).length ? `<h4>낱말 풀이</h4><dl>${doc.words.map((w) => `<dt>${esc(w.word)}</dt><dd>${esc(w.means)}</dd>`).join("")}</dl>` : "";
  return `<div class="plain"><button type="button" class="ghost plain-btn" aria-expanded="false">쉽게 설명해줘</button>
    <div class="plain-box" hidden><b>${esc(doc.title)}</b>${parts}${words}</div></div>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest ? e.target.closest(".plain-btn") : null;
  if (!b) return;
  const box = b.parentElement.querySelector(".plain-box");
  box.hidden = !box.hidden;
  b.setAttribute("aria-expanded", String(!box.hidden));
  b.textContent = box.hidden ? "쉽게 설명해줘" : "쉬운 설명 닫기";
});
const errBox = (e) => `<div class="panel err">불러오지 못했습니다: ${esc(errKo(e))}</div>`;
const loading = '<div class="panel empty">불러오는 중…</div>';
function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

function setupCanvas(cv, h) {
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth || cv.parentElement.clientWidth;
  cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.height = h + "px";
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  // 4차 묶음 P2-14: 화면 읽기 프로그램에 그림이라고 알리고, 이름이 없으면 그 패널의 제목을 이름으로 씁니다.  스파크라인은 숨깁니다.
  if (cv.getAttribute("aria-hidden") !== "true") {
    cv.setAttribute("role", "img");
    if (!cv.getAttribute("aria-label")) { const t = cv.closest(".panel") && cv.closest(".panel").querySelector("h2, h3"); cv.setAttribute("aria-label", t ? t.textContent.trim() : "차트"); }
  }
  return { ctx, w, h };
}
// 스파크라인 아래의 '그래프 폭': 그래프 기간 최저와 최고의 차이(%).  카드끼리 흔들림의 크기를 비교할 수 있게 합니다.
function sparkRange(vals) {
  const v = (vals || []).filter(isNum);
  if (v.length < 2) return "";
  const lo = Math.min(...v), hi = Math.max(...v);
  return lo > 0 ? `<span class="nw" title="그래프(최근 ${v.length}거래일 종가)의 최저와 최고의 차이입니다. 점선은 그래프 첫날 값입니다.">그래프 폭 ${((hi / lo - 1) * 100).toFixed(1)}%</span>` : "";
}
// 가격 축 눈금 (4차 묶음 P2-6): 1·2·2.5·5 × 10ⁿ 간격의 값에 천 단위 쉼표.  소수 자리는 간격에 맞춥니다.
function niceTicks(lo, hi, n = 5) {
  if (!(hi > lo) || !isFinite(lo) || !isFinite(hi)) return { ticks: [], digits: 0 };
  const raw = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(raw)), f = raw / mag;
  const m = f < 1.5 ? 1 : f < 2.25 ? 2 : f < 3.5 ? 2.5 : f < 7.5 ? 5 : 10, step = m * mag;      // the nearest nice step
  const ticks = [];
  for (let k = Math.ceil(lo / step - 1e-9); k * step <= hi + step * 1e-9; k++) ticks.push(Number((k * step).toPrecision(12)));
  const e = Math.floor(Math.log10(step) + 1e-9);
  return { ticks, digits: Math.max(0, -e + (Math.abs(step / 10 ** e - 2.5) < 1e-9 ? 1 : 0)) };
}
const tickLabel = (v, digits) => v.toLocaleString("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
function spark(cv, vals) {
  const v = (vals || []).filter(isNum);
  cv.setAttribute("aria-hidden", "true");
  if (v.length < 2) return;
  const { ctx, w, h } = setupCanvas(cv, cv.clientHeight || 28);
  const lo = Math.min(...v), hi = Math.max(...v), rg = hi - lo || 1;
  // 4차 묶음 P2-24: 첫날 값의 점선 기준선.  카드마다 최저~최고로 늘려 그리므로, 흔들림의 크기는 카드의 '그래프 폭'으로 읽습니다.
  const by = h - 2 - ((v[0] - lo) / rg) * (h - 4);
  ctx.save(); ctx.setLineDash([2, 3]); ctx.globalAlpha = 0.6; ctx.strokeStyle = cssVar("--muted"); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, by); ctx.lineTo(w, by); ctx.stroke(); ctx.restore();
  ctx.strokeStyle = cssVar(cv.hasAttribute("data-plain") ? "--ink" : v[v.length - 1] >= v[0] ? "--up" : "--down"); ctx.lineWidth = 1.4;
  ctx.beginPath();
  v.forEach((x, i) => { const px = (i / (v.length - 1)) * w, py = h - 2 - ((x - lo) / rg) * (h - 4); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
  ctx.stroke();
}

// ------------------------------------------------------------------ tabs & routing
// 탭은 여섯 묶음으로 나뉩니다.  윗줄은 묶음, 아랫줄은 그 묶음의 탭입니다(탭이 하나뿐인 묶음은 아랫줄을 숨깁니다).
const groupTab = {};          // 묶음마다 마지막으로 본 탭
function groupOf(tab) { const b = document.querySelector(`.tabs button[data-tab="${tab}"]`); return b ? b.dataset.group : null; }
function paintGroups(tab) {
  const g = groupOf(tab);
  if (!g) return;
  groupTab[g] = tab;
  document.querySelectorAll(".groups button").forEach((b) => { b.classList.toggle("on", b.dataset.group === g); b.toggleAttribute("aria-current", b.dataset.group === g); b.hidden = !groupShown(b.dataset.group); });
  const mine = [...document.querySelectorAll(".tabs button")].filter((b) => { b.hidden = b.dataset.group !== g || (!groupShown(g) && !ANY_MARKET.has(b.dataset.tab)); return !b.hidden; });
  document.querySelector(".tabs").hidden = mine.length < 2;
  paintBar(g);
}
// 폰 아래 막대 (3차 묶음 P1-11, 사용자 결정 2026-11-23): 640px 이하에서는 윗줄 묶음 대신 오늘·종목·점수·내 계좌·더보기를 화면 아래에
// 둡니다.  코인 시장에서는 종목·점수 자리에 코인이 옵니다.  더보기는 나머지 묶음(시장, 차트, 검증·기록)과 머리줄에서 뺀 단추를 엽니다.
const BAR_GROUPS = ["today", "stock", "score", "coin", "account"];
const MORE_ACTS = [["collect", "지금 수집"], ["phonebtn", "폰 연결"], ["cmdbtn", "명령창"], ["theme", "화면 테마"], ["keysbtn", "한 글자 단축키"]];
function paintBar(g) {
  const bar = $("#bottombar");
  if (!bar) return;
  bar.querySelectorAll("button[data-group]").forEach((b) => {
    const k = b.dataset.group;
    b.hidden = k !== "account" && !groupShown(k);                       // 내 계좌는 어느 시장에서나 열립니다(ANY_MARKET)
    b.classList.toggle("on", k === g);
    b.toggleAttribute("aria-current", k === g);
  });
  bar.querySelector("[data-more]").classList.toggle("on", !BAR_GROUPS.includes(g));
}
function moreClose() {
  const sh = $("#moresheet");
  if (!sh || sh.hidden) return;
  sh.hidden = true;
  $("#bottombar [data-more]").setAttribute("aria-expanded", "false");
}
function moreOpen() {
  const sh = $("#moresheet");
  const groups = [...document.querySelectorAll(".groups button")].filter((b) => !BAR_GROUPS.includes(b.dataset.group) && groupShown(b.dataset.group));
  const acts = MORE_ACTS.filter(([id]) => { const b = $("#" + id); return b && (!b.hidden || id === "keysbtn") && !(id === "collect" && document.documentElement.classList.contains("on-phone")); });
  sh.innerHTML = `<div class="ms-title">다른 묶음</div><div class="ms-row">${groups.map((b) => `<button type="button" data-group="${b.dataset.group}" class="${b.classList.contains("on") ? "on" : ""}">${esc(b.textContent)}</button>`).join("")
      || '<span class="meta m0">이 시장에는 다른 묶음이 없습니다.</span>'}</div>
    <div class="ms-title">도구</div><div class="ms-row">${acts.map(([id, label]) => `<button type="button" data-act="${id}">${esc(id === "phonebtn" || id === "keysbtn" ? $("#" + id).textContent : label)}</button>`).join("")}</div>`;
  sh.hidden = false;
  $("#bottombar [data-more]").setAttribute("aria-expanded", "true");
}
$("#bottombar").onclick = (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.hasAttribute("data-more")) return $("#moresheet").hidden ? moreOpen() : moreClose();
  moreClose();
  if (b.dataset.group === "account") show("account");                   // 머리줄의 '내 계좌'와 같은 통합 계좌
  else showGroup(b.dataset.group);
};
$("#moresheet").onclick = (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  moreClose();
  if (b.dataset.group) showGroup(b.dataset.group);
  else if (b.dataset.act) $("#" + b.dataset.act).click();                 // 머리줄 단추가 하는 일을 그대로 합니다
};
document.addEventListener("click", (e) => { if (!e.target.closest("#moresheet, #bottombar")) moreClose(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") moreClose(); });
// 컴퓨터에서는 묶음 줄이 머리줄 바로 아래에 붙어 따라옵니다.  머리줄 높이(수집 막대가 열리면 달라짐)를 재어 둡니다.
// --sticky-top: 표 머리 행이 붙을 높이 (4차 묶음 P3-3) = 머리줄 + 붙어 따라오는 묶음 줄
const setTopH = () => {
  const top = Math.round($(".top").getBoundingClientRect().height), g = $(".groups");
  const gh = g && getComputedStyle(g).position === "sticky" ? Math.round(g.getBoundingClientRect().height) : 0;
  document.documentElement.style.setProperty("--top-h", top + "px");
  document.documentElement.style.setProperty("--sticky-top", top + gh + "px");
};
setTopH();
window.addEventListener("resize", setTopH);
if (window.ResizeObserver) new ResizeObserver(setTopH).observe($(".top"));
function showGroup(g) {
  const first = document.querySelector(`.tabs button[data-group="${g}"]`);
  if (first) show(groupTab[g] || first.dataset.tab);
}
const tabScroll = {};        // 탭을 떠날 때의 스크롤 위치.  다시 그리지 않는 탭(RETURN)으로 돌아올 때 되돌립니다.
// 주소 표시줄에 적는 이름: 종목 화면은 stock/코드, 평가한 점수 카드가 있는 순위·카드 탭은 qsf/코드, 나머지는 탭 이름입니다.
function tabHash(tab) {
  if (tab === "stock" && state.ticker) return `stock/${state.ticker}`;
  if (tab === "qsf" && typeof qsfState !== "undefined" && qsfState.view && qsfState.view !== "rank") return `qsf:${qsfState.view}`;     // 보기 (6차 묶음 P2-18)
  if (tab === "qsf" && state.card && marketOf(state.card) === state.market) return `qsf/${state.card}`;
  return tab;
}
// 표가 많은 화면은 넓은 화면에서 1680px까지 씁니다 (5차 묶음 P2-11, 사용자 결정 2026-11-23).  나머지 화면은 1280px 그대로입니다.
const WIDE_TABS = new Set(["qsf", "committee", "portfolio", "watch", "lab", "model", "coin"]);
// 화면마다 h1 하나 (5차 묶음 P3-4): 화면 읽기 프로그램이 지금 어느 화면인지 읽습니다.  보이는 제목은 그대로입니다.
function paintTitle(tab) {
  const b = document.querySelector(`.tabs button[data-tab="${tab}"]`), name = b ? b.textContent.trim() : "";
  $("#pagetitle").textContent = name ? `${name} · 퀀트 터미널` : "퀀트 터미널";
  document.title = $("#pagetitle").textContent;
  document.querySelectorAll(".tabs button").forEach((x) => x.toggleAttribute("aria-current", x === b));
}
function show(tab, push = true) {
  if (!ANY_MARKET.has(tab) && !groupShown(groupOf(tab) || "today")) tab = isCoin() ? "coin" : "today";       // 지금 시장에 없는 탭이면 그 시장의 첫 화면으로
  if (tab !== state.tab) tabScroll[state.tab] = window.scrollY;
  state.tab = tab;
  paintColorRule();
  if (healthAt && Date.now() - healthAt > 30000) loadHealth();      // 탭을 옮길 때도 화면이 업데이트됐는지 확인합니다
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  paintGroups(tab);
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("on", s.id === "tab-" + tab));
  $("main").classList.toggle("wide", WIDE_TABS.has(tab));
  paintTitle(tab);
  if (push) location.hash = tabHash(tab);
  if (tab === "stock") { const r = renderStock(); redrawShown(tab); return r; }
  if (!state.loaded[tab] || ALWAYS_FRESH.has(tab)) return RENDER[tab]();
  redrawShown(tab);                                                  // 숨어 있는 동안 크기나 테마가 바뀌었으면 지금 다시 그립니다
  if (RETURN[tab]) RETURN[tab](tabScroll[tab] || 0);                 // 이미 그려 둔 탭: 다시 만들지 않고 돌아왔다고만 알립니다
}
// Price colours by market (user decision 2026-11-23): Korean red up / blue down on Korean screens; screens that mix markets keep the
// international pair.  Set before a tab draws, since the charts read the colours when they draw.
const INTL_COLOR_TABS = new Set(["account"]);
function paintColorRule() {
  if (state.market === "KR" && !INTL_COLOR_TABS.has(state.tab)) document.documentElement.dataset.color = "kr";
  else delete document.documentElement.dataset.color;
}
function paintMarket() {
  paintColorRule();
  $("#market").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.m === state.market));
  $("#q").placeholder = state.market === "COIN" ? "코인에 대해 묻기 (예: 비트코인, 코인 상위는?)" : "종목 코드 또는 회사명";
}
function setMarket(m, render = true) {
  if (m === state.market) return;
  state.market = m;
  try { localStorage.setItem("qse-market", m); } catch (e) { /* storage unavailable */ }
  paintMarket();
  state.loaded = {};
  redrawers.clear(); redrawLater.clear();
  document.querySelectorAll(".tab").forEach((s) => (s.innerHTML = ""));
  if (state.ticker && marketOf(state.ticker) !== m) state.ticker = null;
  if (render) show(state.tab);
}
// Recently opened stocks, on this browser only.  Shown as shortcuts on the empty stock tab.
// A ticker is stored only once it is known to exist: a scanned stock at once, any other after its chart came back with prices
// (loadChart).  A mistyped code is therefore never a shortcut or a default of the compare tab.
function recentTickers() { try { return JSON.parse(localStorage.getItem("qse-recent") || "[]").filter((x) => typeof x === "string"); } catch (e) { return []; } }
function rememberTicker(t) {
  try { localStorage.setItem("qse-recent", JSON.stringify([t, ...recentTickers().filter((x) => x !== t)].slice(0, 12))); } catch (e) { /* not remembered */ }
}
// Shortcuts saved before that guard came (2026-11-22) can hold a code that never existed, such as the mistyped 'APPL'.  Once per page,
// a shortcut outside the scanned stocks is asked for its chart; it is dropped only when the price source gave no prices for it while
// the same source, asked right after, did give fresh prices for a known stock.  Offline both come back empty, so nothing is dropped.
const PRUNE_PROBE = { US: "SPY", KR: "005930" };
const noPrices = (d) => !!d && d.status === "UNAVAILABLE" && !!d.cache && d.cache.error === "EMPTY_RESPONSE";
// The chart answer carries when its prices were fetched (fetched_at), not their age; server and page run on the same machine.
const freshPrices = (d) => !!d && d.status !== "UNAVAILABLE" && !!d.cache && d.cache.status === "REAL" && !!d.cache.fetched_at && Date.now() - Date.parse(d.cache.fetched_at) < 120000;
function forgetTicker(t) {
  try { localStorage.setItem("qse-recent", JSON.stringify(recentTickers().filter((x) => x !== t))); } catch (e) { /* not stored */ }
}
async function pruneRecentTickers() {
  const chart = (t) => api(`/api/chart?t=${encodeURIComponent(t)}&range=3mo`).catch(() => null);
  for (const t of recentTickers()) {
    const mk = marketOf(t);
    if (t.startsWith("^") || !PRUNE_PROBE[mk]) continue;
    const s = await api(`/api/symbols?q=${encodeURIComponent(t)}&market=${mk}`).catch(() => null);
    if (!s || (s.exact && String(s.exact.ticker).toUpperCase() === t)) continue;
    if (noPrices(await chart(t)) && freshPrices(await chart(PRUNE_PROBE[mk]))) forgetTicker(t);
  }
}
function tickerChips(list) { return list.map((t) => `<button type="button" class="chip" data-ticker="${esc(t)}">${esc(t)}</button>`).join(""); }
function openTicker(t) {
  state.ticker = String(t).toUpperCase(); state.loaded.stock = null;
  if (knownSymbols.has(state.ticker)) rememberTicker(state.ticker);
  setMarket(marketOf(state.ticker), false);
  show("stock");
  window.scrollTo(0, 0);
}
document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => show(b.dataset.tab)));
// 빈 화면의 '지금 수집' 단추는 머리줄의 같은 단추를 누릅니다 (4차 묶음 P2-17).
document.addEventListener("click", (e) => { const b = e.target.closest && e.target.closest(".collect-now"); if (b && $("#collect")) $("#collect").click(); });
document.querySelectorAll(".groups button").forEach((b) => (b.onclick = () => showGroup(b.dataset.group)));
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
// ------------------------------------------------------------------ 종목 찾기
// 스캔한 종목(S&P 500, 한국 시가총액 상위 300) 안에서 코드, 회사명, 비슷한 코드를 찾습니다 (/api/symbols).  서버는 저장해 둔 이름만 봅니다.
const MARKET_KO = { US: "미국", KR: "한국" };
const knownSymbols = new Set();           // 스캔 대상으로 확인된 종목 코드
const symbolCache = new Map();            // 같은 말을 다시 묻지 않습니다.  수집이 끝나면 비웁니다 (collect.js).
function symbolSuggest(text) {
  const q = String(text).trim().replace(/\s+/g, " "), mk = isKR() ? "KR" : "US", key = `${mk}|${q.toLowerCase()}`;
  if (!symbolCache.has(key)) {
    if (symbolCache.size > 200) symbolCache.clear();
    const p = api(`/api/symbols?q=${encodeURIComponent(q)}&market=${mk}`).then((d) => { [d.exact, ...(d.items || [])].forEach((i) => i && knownSymbols.add(String(i.ticker).toUpperCase())); return d; });
    p.catch(() => symbolCache.delete(key));
    symbolCache.set(key, p);
  }
  return symbolCache.get(key);
}
const symbolLabel = (i) => `<b>${esc(i.ticker)}</b> <span>${esc(i.name)}</span> <small>${esc(MARKET_KO[i.market] || i.market)}</small>`;
// 찾기 전과 같은 열기: 한글은 한국 상장 종목 전체에서 검색하고, 그 밖은 적은 코드 그대로 엽니다 (ETF와 지수는 스캔 밖에 있습니다).
const openTyped = (q) => (/[가-힣]/.test(q) ? searchKr(q) : openTicker(q));
// 적은 말이 스캔한 종목의 코드면 바로 열고, 아니면 가까운 종목을 먼저 묻습니다.  회사명(apple, 삼성전자)을 코드로 읽지 않게 합니다.
async function findSymbol(text) {
  const q = String(text).trim();
  if (!q) return;
  let d = null;
  try { d = await symbolSuggest(q); } catch (e) { /* 찾지 못하면 이전처럼 엽니다 */ }
  if (d && d.exact) return openTicker(d.exact.ticker);
  const items = (d && d.items) || [], same = items.filter((i) => String(i.name).toLowerCase() === q.toLowerCase());
  if (same.length === 1) return openTicker(same[0].ticker);          // 회사명을 끝까지 적었습니다
  if (!items.length) return openTyped(q);
  symbolChoices(q, items);
}
function symbolChoices(q, items) {
  if (isCoin()) setMarket(items[0].market === "KR" ? "KR" : "US", false);
  state.ticker = null; state.loaded.stock = "search";
  show("stock");
  $("#tab-stock").innerHTML = `<div class="panel"><h2>혹시 이 종목인가요?</h2>
    <div class="meta">입력: '${esc(q)}' · 코드가 같은 스캔 종목은 없습니다. 코드나 회사명이 가까운 종목은 아래와 같습니다.</div>
    <div class="sym-list">${items.map((i) => `<button type="button" class="sym-item" data-ticker="${esc(i.ticker)}">${symbolLabel(i)}</button>`).join("")}</div>
    <div class="sym-raw"><button type="button" class="ghost" id="sym-raw">'${esc(q)}' ${/[가-힣]/.test(q) ? "한국 상장 종목 전체에서 찾기" : "그대로 열기"}</button>
      <span class="meta">ETF나 지수처럼 스캔 대상이 아닌 종목도 종목 화면에서 볼 수 있습니다.</span></div></div>`;
  $("#sym-raw").onclick = () => openTyped(q);
  window.scrollTo(0, 0);
}
// 검색창 자동 완성: 치는 동안 최대 8개를 검색창 아래에 보여 줍니다.  ↑↓로 고르고 Enter로 열며, Esc나 바깥을 누르면 닫힙니다.
const sug = { box: document.createElement("div"), q: "", items: [], sel: -1, timer: null, token: 0 };
sug.box.id = "qsug"; sug.box.className = "sug"; sug.box.hidden = true; sug.box.setAttribute("role", "listbox"); sug.box.setAttribute("aria-label", "종목 제안");
$("#search").appendChild(sug.box);
function sugPaint() {
  sug.box.hidden = !sug.items.length;
  sug.box.innerHTML = sug.items.map((i, k) => `<button type="button" role="option" aria-selected="${k === sug.sel}" class="sug-item${k === sug.sel ? " on" : ""}" data-sym="${esc(i.ticker)}">${symbolLabel(i)}</button>`).join("");
}
function sugClose() { clearTimeout(sug.timer); sug.token++; sug.q = ""; sug.items = []; sug.sel = -1; sugPaint(); }
function sugPick(t) { sugClose(); $("#q").value = ""; $("#q").blur(); openTicker(t); }
async function sugLoad(q) {
  const token = ++sug.token;
  let d;
  try { d = await symbolSuggest(q); } catch (e) { return; }
  if (token !== sug.token || $("#q").value.trim() !== q) return;
  sug.q = q; sug.items = (d.items || []).slice(0, 8); sug.sel = -1; sugPaint();
}
$("#q").addEventListener("input", () => {
  const q = $("#q").value.trim();
  if (!q || isCoin()) return sugClose();
  clearTimeout(sug.timer);
  if (q === sug.q) return;                       // 한글 조합이 끝나며 같은 말로 다시 온 입력: 고른 줄을 그대로 둡니다
  sug.timer = setTimeout(() => sugLoad(q), 150);
});
$("#q").addEventListener("keydown", (e) => {
  const n = sug.items.length;
  if (e.key === "ArrowDown" && n) { sug.sel = Math.min(sug.sel + 1, n - 1); sugPaint(); e.preventDefault(); }
  else if (e.key === "ArrowUp" && n) { sug.sel = Math.max(sug.sel - 1, -1); sugPaint(); e.preventDefault(); }
  else if (e.key === "Enter" && !e.isComposing && sug.sel >= 0) { e.preventDefault(); sugPick(sug.items[sug.sel].ticker); }
  else if (e.key === "Escape") sugClose();
});
sug.box.addEventListener("click", (e) => { const b = e.target.closest("[data-sym]"); if (b) sugPick(b.dataset.sym); });
document.addEventListener("click", (e) => { if (!sug.box.hidden && !e.target.closest("#search")) sugClose(); });
$("#search").onsubmit = (e) => {
  e.preventDefault(); const t = $("#q").value.trim(); if (!t) return;
  if (isCoin()) { askAssistant(t); $("#q").value = ""; $("#q").blur(); return; }       // 코인 시장에서는 검색창이 비서에게 묻습니다
  sugClose();
  findSymbol(t);
  $("#q").value = ""; $("#q").blur();
};
// 열어 둔 종목을 다른 탭의 종목 칸에 미리 적어 둡니다.  제출하지 않고, 사용자가 적은 값은 건드리지 않습니다
// (비어 있거나, 앞서 여기서 적어 둔 값 그대로일 때만 적습니다).  화면의 시장과 종목의 시장이 같을 때만 합니다.
function prefillTicker(input) {
  if (!input || !state.ticker || marketOf(state.ticker) !== state.market) return;
  if (input.value && input.value !== input.dataset.prefill) return;
  input.value = state.ticker; input.dataset.prefill = state.ticker;
}
document.addEventListener("click", (e) => { const el = e.target.closest("[data-ticker]"); if (el && !e.target.closest("button.x")) openTicker(el.dataset.ticker); });
// 누르면 열리는 줄과 글자 (5차 묶음 P2-12, 사용자 결정 2026-11-23): 줄 어디를 눌러도 열리는 것은 그대로 두고, Tab으로 가서 Enter나
// 스페이스로도 열리게 합니다.  화면이 새로 그려질 때마다 표시를 붙입니다.  단추와 링크는 원래 키보드로 됩니다.
const KEYABLE = "tr.click, tr[data-coin], tr[data-fund], div.card[data-ticker], b[data-ticker], span[data-ticker], .fold > div > .panel > h2";
function markKeyable(root) {
  if (!root.querySelectorAll) return;
  const els = [...root.querySelectorAll(KEYABLE)];
  if (root.matches && root.matches(KEYABLE)) els.push(root);
  for (const el of els) {
    if (el.hasAttribute("tabindex")) continue;
    el.tabIndex = 0;
    if (el.tagName !== "TR") el.setAttribute("role", "button");      // 표의 줄은 줄로 남겨 둡니다(열 이름과 함께 읽힘)
  }
  els.filter((el) => el.tagName === "H2").forEach((h) => h.setAttribute("aria-expanded", h.closest(".fold").classList.contains("open")));
  const segs = [...root.querySelectorAll(".seg button")];
  if (root.matches && root.matches(".seg button")) segs.push(root);       // 단추만 새로 들어온 경우(seg 안을 다시 그림)도 표시합니다
  segs.forEach((b) => b.setAttribute("aria-pressed", b.classList.contains("on")));
}
new MutationObserver((list) => {
  for (const m of list) {
    if (m.type === "attributes") {
      const t = m.target;
      if (t.matches(".seg button")) t.setAttribute("aria-pressed", t.classList.contains("on"));
      else if (t.matches(".fold")) { const h = $(":scope > div > .panel > h2", t); if (h) h.setAttribute("aria-expanded", t.classList.contains("open")); }
    } else m.addedNodes.forEach((n) => n.nodeType === 1 && markKeyable(n));
  }
}).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
markKeyable(document.body);
document.addEventListener("keydown", (e) => {
  if ((e.key !== "Enter" && e.key !== " ") || e.isComposing || e.target.tabIndex !== 0 || !e.target.matches || !e.target.matches(KEYABLE)) return;
  e.preventDefault();
  e.target.click();
});

// theme: auto (OS) → light → dark.  The page always carries data-theme, so style.css keeps one copy of the dark colours (batch 5 P2-21);
// theme.js sets it before the first paint, and 'auto' follows the device setting when it changes.
const THEMES = ["auto", "light", "dark"];
const systemDark = () => !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
function applyTheme(t) {
  document.documentElement.dataset.theme = t === "dark" || (t === "auto" && systemDark()) ? "dark" : "light";
  document.documentElement.dataset.themeChoice = t;
  $("#theme").title = "화면 테마: " + { auto: "시스템", light: "밝게", dark: "어둡게" }[t];
  redrawAll();
}
let theme = "auto";
try { theme = localStorage.getItem("qse-theme") || "auto"; } catch (e) { /* storage unavailable */ }
$("#theme").onclick = () => { theme = THEMES[(THEMES.indexOf(theme) + 1) % 3]; try { localStorage.setItem("qse-theme", theme); } catch (e) {} applyTheme(theme); };
// 다시 그리기 (5차 묶음 P2-22): "탭:부분" 이름마다 함수 하나.  같은 탭을 다시 그려도 쌓이지 않습니다.  지금 보이는 탭만 바로
// 그리고, 숨은 탭은 표시만 해 두었다가 그 탭으로 돌아올 때 그립니다(숨은 캔버스는 폭이 0이라 그려도 소용이 없습니다).
const redrawers = new Map(), redrawLater = new Set();
function redrawOn(tab, part, fn) { redrawers.set(`${tab}:${part}`, fn); }
function redrawAll() {
  redrawers.forEach((f, k) => { if (k.startsWith(state.tab + ":")) f(); else redrawLater.add(k); });
}
function redrawShown(tab) {
  for (const k of [...redrawLater]) if (k.startsWith(tab + ":")) { redrawLater.delete(k); const f = redrawers.get(k); if (f) f(); }
}
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => (theme === "auto" ? applyTheme("auto") : redrawAll()));
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
    draw(); redrawOn("overview", "sparks", draw);
  } catch (e) { el.innerHTML = errBox(e); }
}
// 오르면 좋은지 나쁜지가 정해지지 않은 지표(변동성, 금리, 달러인덱스, 환율): 색 없이 부호만 씁니다 (6차 묶음 P2-8).
const NEUTRAL_TILE = /^(\^VIX|\^VXN|\^VKOSPI|\^TNX|\^IRX|\^FVX|\^TYX|DX-Y\.NYB|[A-Z]{3}=X)$/;
function pctPlain(v, d = 2) { return isNum(v) ? `<span class="flat num">${v > 0 ? "+" : ""}${v.toFixed(d)}%</span>` : DASH; }
function card(i) {
  const code = i.ticker || i.symbol, won = /\.K[SQ]$/.test(i.symbol), plain = NEUTRAL_TILE.test(i.symbol || ""), chg = plain ? pctPlain : pct;
  const tk = /^[A-Z]{1,5}$/.test(code) || KR_RE.test(code) ? `data-ticker="${esc(code)}"` : "";
  return `<div class="card" ${tk} title="${esc(i.symbol)}${i.date ? " · " + esc(i.date) : ""}">
    <div class="nm">${esc(i.name || i.symbol)} <span class="muted">${esc(code)}</span></div>
    <div class="row"><div><div class="px num">${fmt(i.close, won ? 0 : 2)}</div>
      <div class="chg"><span class="nw"><span class="meta m0">1일</span> ${chg(i.change_pct)}</span><span class="nw"><span class="meta m0">1개월</span> ${chg(i.change_1m_pct, 1)}</span></div></div>
      <canvas data-spark='${JSON.stringify(i.spark || [])}'${plain ? " data-plain" : ""}></canvas></div>
    <div class="meta mt-1">${i.status !== "REAL" ? badge(i.status) + " " : ""}${liveBadge(i.intraday)} ${esc(i.date || "")} ${sparkRange(i.spark)}</div>
  </div>`;
}

// ------------------------------------------------------------------ 종목
async function renderStock() {
  const el = $("#tab-stock");
  if (!state.ticker) {
    const mk = state.market, recent = recentTickers().filter((t) => marketOf(t) === mk);
    el.innerHTML = `<div class="panel"><div class="empty">위 검색창에 ${isKR() ? "종목 코드나 회사명을 입력하세요 (예: 005930, 삼성전자)." : "종목 코드를 입력하세요 (예: AAPL, MSFT, NVDA)."}</div>
      ${recent.length ? `<h3>최근 본 종목</h3><div class="chips">${tickerChips(recent)}</div>` : ""}<div id="s-watch"></div></div>`;
    api(mq("/api/watchlist")).then((d) => {
      const list = (d.tickers || []).filter((t) => !t.startsWith("^") && marketOf(t) === mk);
      const box = $("#s-watch");
      if (box && list.length && mk === state.market && !state.ticker) box.innerHTML = `<h3>관심종목</h3><div class="chips">${tickerChips(list)}</div>`;
    }).catch(() => {});
    return;
  }
  if (state.loaded.stock === state.ticker) return;
  state.loaded.stock = state.ticker;
  const t = state.ticker;
  el.innerHTML = `<div class="panel" id="s-head">${loading}</div>
    <div class="panel"><h2>가격 차트 <span class="seg" id="rng">${["3mo", "1y", "5y"].map((r) => `<button data-r="${r}" class="${r === state.range ? "on" : ""}">${{ "3mo": "3개월", "1y": "1년", "5y": "5년" }[r]}</button>`).join("")}</span>
      <span class="legend"><span><i style="background:var(--sma20)"></i>20일선</span><span><i style="background:var(--sma50)"></i>50일선</span><span><i style="background:var(--sma200)"></i>200일선</span></span></h2>
      <div class="chart"><canvas id="pc"></canvas></div><div id="c-meta"></div></div>
    <div class="panel" id="s-peers"></div>
    <div class="panel" id="s-fund">${loading}</div>
    <div class="panel" id="s-fil">${loading}</div>`;
  $("#rng").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; state.range = b.dataset.r; $("#rng").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); loadChart(t); };
  loadChart(t);
  if (typeof loadPeers === "function") loadPeers(t);
  api(`/api/company?t=${encodeURIComponent(t)}`).then((c) => { if (state.ticker === t) { renderProfile(c); renderFund(c.fundamentals); } })
    .catch((e) => { if (state.ticker === t) { $("#s-fund").innerHTML = `<span class="err">${esc(errKo(e))}</span>`; $("#s-head").innerHTML = `<div class="err">${esc(errKo(e))}</div>`; } });
  api(`/api/filings?t=${encodeURIComponent(t)}`).then((f) => state.ticker === t && renderFilings(f))
    .catch((e) => state.ticker === t && ($("#s-fil").innerHTML = `<span class="err">${esc(errKo(e))}</span>`));
}
let lastChart = null;
async function loadChart(t) {
  $("#c-meta").innerHTML = '<div class="meta">불러오는 중…</div>';
  try {
    const c = await api(`/api/chart?t=${encodeURIComponent(t)}&range=${state.range}`);
    if (c.status !== "UNAVAILABLE") rememberTicker(t);          // 가격이 온 종목만 '최근 본 종목'에 남깁니다
    if (state.ticker !== t) return;
    lastChart = c; drawPrice(); redrawOn("stock", "price", drawPrice);
    const L = c.last || {};
    $("#c-meta").innerHTML = c.bars.length ? meta(c.source, c.cache.fetched_at, `${badge(c.status)} ${liveBadge(L.intraday)} 마지막 일봉 ${esc(L.date)}`) :
      `<div class="empty">${badge("UNAVAILABLE")} 가격 데이터를 받지 못했습니다. 종목 코드를 확인하세요.</div>`;
    state.lastQuote = L; renderHeadPrice();
  } catch (e) { $("#c-meta").innerHTML = `<span class="err">${esc(errKo(e))}</span>`; }
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
    ["PBR", fmt(p.priceToBook, 2)], ["배당수익률", p.dividendYieldSuspect ? `<span class="flat" title="Yahoo가 준 값이 ${fmt(p.dividendYieldLimit, 0)}%를 넘어 틀린 기록으로 봅니다. 투자위원회 계산에도 쓰지 않습니다.">— (원자료 이상 ${fmt(p.dividendYield, 2)}%)</span>` : isNum(p.dividendYield) ? `${fmt(p.dividendYield, 2)}%` : DASH],
    ["베타", fmt(p.beta, 2)], ["평균 거래량", big(p.averageVolume, "")], ["상장 주식수", big(p.sharesOutstanding, "")]];
  $("#s-head").innerHTML = `<div class="head"><h2 class="m0">${esc(p.longName || p.shortName || c.ticker)} <span class="meta m0">${esc(c.ticker)} · ${esc(p.exchange || "")}</span></h2>
      <span><button class="ghost" id="addw">＋ 관심종목</button> <button class="ghost" id="addc" type="button">비교 차트</button> <button class="ghost" id="adda" type="button" title="이동평균·볼린저밴드·RSI·MACD와 고전 신호를 봅니다">차트분석</button> <button class="ghost" id="addq" type="button" title="순위·카드 탭에서 이 종목의 점수 카드를 엽니다">점수 카드</button></span></div>
    <div class="head" id="s-price"></div>
    <div class="meta">${esc([sectorKo(p.sector), p.industry].filter(Boolean).join(" · "))}${safeUrl(p.website) ? ` · <a href="${esc(safeUrl(p.website))}" target="_blank" rel="noopener noreferrer">웹사이트</a>` : ""}</div>
    <div class="kv">${kv.map(([k, v]) => `<div><span>${k}</span><b class="num">${v}</b></div>`).join("")}</div>
    ${p.longBusinessSummary ? `<details class="co-sum" id="sum"><summary>회사 설명 <span class="meta m0">Yahoo 영문 원문</span> <span class="co-lead" lang="en">${esc(p.longBusinessSummary)}</span></summary><div class="summary open" lang="en">${esc(p.longBusinessSummary)}</div></details>` : ""}
    ${meta(c.profile.source, c.profile.fetched_at, badge(c.profile.status))}`;
  renderHeadPrice();
  $("#addc").onclick = () => compareWith([c.ticker]);
  $("#adda").onclick = () => chartWith(c.ticker);
  $("#addq").onclick = () => { if (typeof qsfOpenCard === "function") qsfOpenCard(c.ticker); };
  $("#addw").onclick = async () => { try { await api("/api/watchlist/add", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticker: c.ticker }) }); $("#addw").textContent = "✓ 추가됨"; state.loaded.watch = false; } catch (e) { notify(errKo(e)); } };
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
    <tbody>${f.items.map((i) => `<tr><td>${esc(i.filing_date)}</td><td class="l"><b>${esc(i.form)}</b> <span class="meta m0">${esc(FORM_KO[i.form] || "")}</span></td>
      <td class="l">${esc(i.description || "")}</td><td class="l">${safeUrl(i.url) ? `<a href="${esc(safeUrl(i.url))}" target="_blank" rel="noopener noreferrer">열기 ↗</a>` : DASH}</td></tr>`).join("")}</tbody></table></div>
    ${meta(f.source, f.fetched_at)}`;
}

// candle chart with SMA overlays, volume pane and crosshair tooltip
function drawPrice() {
  const cv = $("#pc"), c = lastChart;
  if (!cv || !c || !c.bars.length || !cv.isConnected) return;
  const H = isPhone() ? 300 : 420;
  const { ctx, w, h } = setupCanvas(cv, H);
  const bars = c.bars, n = bars.length, padR = 58, padT = 8, volH = Math.round(h * 0.18), gap = 18, priceH = h - volH - gap - padT - 18;
  const pw = w - padR, bw = pw / n;
  let lo = Infinity, hi = -Infinity, vmax = 0;
  bars.forEach((b) => { for (const k of ["low", "high", "close", "sma20", "sma50", "sma200"]) if (isNum(b[k])) { lo = Math.min(lo, b[k]); hi = Math.max(hi, b[k]); } if (isNum(b.volume)) vmax = Math.max(vmax, b.volume); });
  const pad = (hi - lo) * 0.04 || 1; lo -= pad; hi += pad;
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * priceH, x = (i) => i * bw + bw / 2;
  const grid = cssVar("--grid"), muted = cssVar("--muted"), up = cssVar("--up"), dn = cssVar("--down");
  ctx.font = "11px -apple-system, sans-serif"; ctx.textBaseline = "middle";
  const nt = niceTicks(lo, hi);
  nt.ticks.forEach((v) => {
    const yy = y(v);
    ctx.strokeStyle = grid; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(pw, yy); ctx.stroke();
    ctx.fillStyle = muted; ctx.fillText(tickLabel(v, nt.digits), pw + 6, yy);
  });
  const b0 = bars[0], b1 = bars[n - 1], px = (v) => (isNum(v) ? v.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) : "없음");
  cv.setAttribute("aria-label", `${tickerText(state.ticker || "", "")} 가격 차트: ${b0.date}부터 ${b1.date}까지, 종가 ${px(b0.close)}에서 ${px(b1.close)}`);
  // date labels
  ctx.textBaseline = "top"; ctx.textAlign = "center";
  const step = Math.max(1, Math.round(n / (w < 600 ? 4 : 7)));
  for (let i = step; i < n - step / 3; i += step) ctx.fillText(bars[i].date.slice(2, 7).replace("-", "."), x(i), h - 14);
  ctx.textAlign = "left";
  const candle = bw >= 1.8;
  bars.forEach((b, i) => {
    const okOpen = goodOpen(b), o = okOpen ? b.open : b.close, col = !okOpen && isNum(b.open) ? muted : b.close >= o ? up : dn;
    ctx.strokeStyle = col; ctx.fillStyle = col;
    if (candle && isNum(b.high) && isNum(b.low)) {
      ctx.beginPath(); ctx.moveTo(x(i), y(b.high)); ctx.lineTo(x(i), y(b.low)); ctx.stroke();
      const top = y(Math.max(o, b.close)), ht = Math.max(1, Math.abs(y(o) - y(b.close)));
      if (okOpen) ctx.fillRect(x(i) - bw * 0.35, top, Math.max(1, bw * 0.7), ht);
    }
    if (isNum(b.volume) && vmax) { ctx.globalAlpha = 0.45; const vh = (b.volume / vmax) * volH; ctx.fillRect(i * bw + bw * 0.1, h - 18 - vh, Math.max(1, bw * 0.8), vh); ctx.globalAlpha = 1; }
  });
  if (!candle) line(ctx, bars.map((b) => b.close), x, y, cssVar("--ink"), 1.3);
  [["sma20", "--sma20"], ["sma50", "--sma50"], ["sma200", "--sma200"]].forEach(([k, v]) => line(ctx, bars.map((b) => b[k]), x, y, cssVar(v), 1.2));
  // crosshair
  cv.onmousemove = (e) => {
    const r = cv.getBoundingClientRect(), i = Math.min(n - 1, Math.max(0, Math.floor((e.clientX - r.left) / bw))), b = bars[i];
    const tip = $("#tip"); tip.hidden = false;
    tip.innerHTML = `<b>${esc(b.date)}</b><br>시 ${goodOpen(b) || !isNum(b.open) ? fmt(b.open) : "없음(원자료 이상)"} 고 ${fmt(b.high)} 저 ${fmt(b.low)} 종 ${fmt(b.close)}<br>거래량 ${big(b.volume, "")}<br>
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
    el.innerHTML = `${d.reason ? `<div class="notice">${esc(d.reason)}</div>` : ""}<div class="panel" id="econcal"></div><div class="panel"><h2>${mk === "KR" ? "한국" : "미국"} 거시 지표</h2><div class="mgrid">${d.items.map((m) => `<div class="mcard">
      <div class="nm meta m0">${esc(m.label)} <span>${esc(m.id)}</span> ${m.status !== "REAL" ? badge(m.status) : ""}</div>
      <div class="row" style="display:flex;justify-content:space-between;align-items:baseline;gap:8px"><span class="px num" style="font-size:20px;font-weight:650">${fmtMacro(m, m.value)}</span>
        <span class="meta m0">${esc(m.date || "")}</span></div>
      <div class="meta m0">직전 ${fmtMacro(m, m.previous)} · 1년 전 ${fmtMacro(m, m.value_1y_ago)}</div>
      <canvas data-m="${esc(m.id)}"></canvas></div>`).join("")}</div>
      <div class="meta">${mk === "KR" ? "소비자물가" : "CPI"}는 전년 동월 대비 상승률(%)로 계산해 표시합니다. 차트는 최근 약 260개 관측치입니다.</div>${meta(d.source)}</div>`;
    const draw = () => d.items.forEach((m) => { const cv = el.querySelector(`canvas[data-m="${m.id}"]`); if (cv && cv.isConnected) mini(cv, m.series); });
    draw(); redrawOn("macro", "minis", draw);
    if (typeof loadCalendar === "function") loadCalendar($("#econcal"));
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
    el.innerHTML = `<div class="panel"><h2>${mk === "KR" ? "한국" : "미국"} 관심종목 <span class="meta m0">${d.tickers.length}개</span></h2>
      <form class="addrow" id="wadd"><input id="wq" placeholder="추가할 종목 코드" maxlength="15"><button type="submit">추가</button></form>
      ${d.items.length ? `<div class="tbl-wrap"><table><thead><tr><th>종목</th><th>종가</th><th>전일 대비</th><th>1개월</th><th class="l">추세(30일)</th><th class="l">스윙 점수</th><th class="l">장기 점수</th><th class="l">상태</th><th></th></tr></thead>
      <tbody>${d.items.map((i) => `<tr class="click" data-ticker="${esc(i.symbol)}"><td><b>${esc(i.symbol)}</b> ${i.name ? `<span class="meta m0">${esc(i.name)}</span>` : ""}</td><td class="num">${fmt(i.close, d0)}</td><td>${pct(i.change_pct)}</td><td>${pct(i.change_1m_pct, 1)}</td>
        <td class="l"><canvas style="width:80px;height:24px" data-spark='${JSON.stringify(i.spark || [])}'></canvas></td><td class="l">${watchScore(i.qsf, "SWING", d.qsf_scan)}</td><td class="l">${watchScore(i.qsf, "LONG_TERM", d.qsf_scan)}</td><td class="l">${badge(i.status)} ${liveBadge(i.intraday)} <span class="meta">${esc(i.date || "")}</span></td>
        <td><button class="x" data-rm="${esc(i.symbol)}" title="삭제">✕</button></td></tr>`).join("")}</tbody></table></div>` : '<div class="empty">관심종목이 없습니다.</div>'}
      ${d.qsf_scan && d.qsf_scan.status === "REAL" ? `<div class="meta">점수는 ${esc(d.qsf_scan.session)} 거래일 스캔(${esc(d.qsf_scan.model_version)})에 기록된 값입니다. 스캔 대상이 아닌 종목은 비워 둡니다. 순위·카드 탭에서 다시 계산할 수 있습니다.</div>` : ""}
      ${d.cache ? meta(d.source, d.cache.fetched_at) : ""}<div class="meta">관심종목은 이 Mac의 data/terminal/watchlist.json 에만 저장됩니다.</div></div>`;
    const draw = () => el.querySelectorAll("canvas[data-spark]").forEach((cv) => spark(cv, JSON.parse(cv.dataset.spark)));
    draw(); redrawOn("watch", "sparks", draw);
    $("#wadd").onsubmit = (e) => { e.preventDefault(); watchOp("add", $("#wq").value); };
    el.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); watchOp("remove", b.dataset.rm); }));
  } catch (e) { el.innerHTML = errBox(e); }
}
// 스캔에 기록된 점수만 보여 줍니다. 여기서 계산하지 않습니다. 색은 순위·카드 탭과 같은 기준이고 글자로도 적습니다.
function watchScore(q, strategy, scan) {
  if (!scan || scan.status !== "REAL") return '<span class="missing">스캔 없음</span>';
  const c = q && q[strategy];
  if (!c || c.score === null || c.score === undefined) return '<span class="missing">스캔 밖</span>';
  const tone = typeof qsfClass === "function" ? qsfClass(c.action, c.score) : "act-hold";
  return `<b class="num">${Number(c.score).toFixed(1)}</b> <span class="qsf-act ${tone}"><i></i>${esc(c.action_label || c.action || "")}</span>`;
}
async function watchOp(op, t) {
  t = (t || "").trim(); if (!t) return;
  try { await api(`/api/watchlist/${op}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticker: t }) }); setMarket(marketOf(t.toUpperCase()), false); renderWatch(); }
  catch (e) { notify(errKo(e)); }
}

// ------------------------------------------------------------------ 모델 (읽기 전용)
const REC_KO = { "REAL RECOMMENDATION": "모델 정상 실행", "PARTIAL RECOMMENDATION": "모델 일부만 실행", "NO VALID RECOMMENDATION": "모델 결과 없음" };
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
  const nextScan = mk === "KR" ? "다음 일일 작업의 스캔부터 이 금액을 씁니다. 지금 바로 돌리려면 옆의 '스캔 실행'을 누르세요." : "다음 일일 작업의 스캔부터 이 금액을 씁니다.";
  const refresh = (msg) => {
    const typed = parse(), base = typed === null ? (isNum(b.capital) ? b.capital : null) : typed;
    el.querySelectorAll("[data-cap-amount]").forEach((c) => { const w = parseFloat(c.dataset.w); c.innerHTML = base && !isNaN(base) && !isNaN(w) ? money(w * base) : DASH; });
    el.querySelectorAll("[data-cap-shares]").forEach((c) => { const w = parseFloat(c.dataset.w), p = parseFloat(c.dataset.close); c.innerHTML = base && !isNaN(base) && !isNaN(w) && p > 0 ? Math.floor(w * base / p).toLocaleString("ko-KR") : DASH; });
    const parts = [];
    if (msg) parts.push(msg);
    if (Number.isNaN(typed)) parts.push("0보다 큰 숫자로 입력하세요.");
    else if (typed !== saved) parts.push("저장 전 미리보기입니다.");
    else if (saved === null) parts.push(cap.invalid ? "저장된 값을 읽을 수 없습니다. 다시 입력하세요." : mk === "KR" ? "저장된 자본금이 없어 한국 모델 스캔을 건너뜁니다." : "자본금이 없어 P6-11B 스캔을 건너뜁니다.");
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
    } catch (e) { refresh(esc(errKo(e))); }
  };
  refresh();
  // The Korean model scan is a hand-run command, not a step of the daily job; this button starts that same command.
  const runBtn = $("#capRun"), runNote = $("#capRunNote");
  if (!runBtn) return;
  const hhmm = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }); };
  let timer = null, wasRunning = false;
  const show = (s, fresh) => {
    clearTimeout(timer);
    if (!runBtn.isConnected) return;                    // the tab was drawn again: that drawing has its own watcher
    runBtn.disabled = s.status === "RUNNING";
    if (s.status === "RUNNING") {
      runNote.innerHTML = `${s.by === "DAILY_JOB" ? "일일 작업이 한국 스캔을 실행하는 중입니다" : "한국 스캔을 실행하는 중입니다"} (시작 ${hhmm(s.started_at)}). 그날 첫 실행은 약 2,500종목의 시세를 받아 40분쯤 걸릴 수 있습니다. 이 화면을 닫아도 계속 실행됩니다.`;
      timer = setTimeout(poll, 10000);
    } else if (s.status === "DONE") {
      runNote.innerHTML = `마지막 스캔 실행: ${hhmm(s.started_at)} 시작, 완료 (${esc(REC_KO[s.run.recommendation_status] || s.run.recommendation_status || "")}, 기준 거래일 ${esc(s.run.latest_session || "")}).`;
      if (fresh) RENDER.model();
    } else if (s.status === "FAILED") {
      runNote.innerHTML = `마지막 스캔 실행(${hhmm(s.started_at)} 시작)이 결과를 남기지 못하고 끝났습니다. 실행 기록: <code>${esc(s.log)}</code>`;
    } else runNote.innerHTML = "";
  };
  const poll = async () => {
    try { const s = await api("/api/model/scan"); const fresh = wasRunning && s.status === "DONE"; wasRunning = s.status === "RUNNING"; show(s, fresh); }
    catch (e) { if (runBtn.isConnected) timer = setTimeout(poll, 10000); }
  };
  runBtn.onclick = async () => {
    if (saved === null || parse() !== saved) { refresh("먼저 금액을 저장하세요. 스캔은 저장된 금액으로 실행합니다."); return; }
    try {
      const r = await api("/api/model/scan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ market: "KR" }) });
      if (r.status === "NO_CAPITAL") { refresh("먼저 금액을 저장하세요. 스캔은 저장된 금액으로 실행합니다."); return; }
      wasRunning = true;
      show({ status: "RUNNING", started_at: r.started_at, by: r.by }, false);
    } catch (e) { runNote.innerHTML = esc(errKo(e)); }
  };
  poll();
}
async function renderModel() {
  const el = $("#tab-model"), mk = state.market; el.innerHTML = loading;
  try {
    const [d, cap] = await Promise.all([api(mq("/api/model")), api(mq("/api/capital"))]); if (mk !== state.market) return; state.loaded.model = true;
    const b = d.baseline, t = d.tracking;
    el.innerHTML = `<div class="panel"><h2>${esc(b.name)} ${badge(b.status || "FROZEN")} <span class="meta m0">${esc(b.role)}</span></h2>
      <div class="form" style="margin:8px 0 12px"><label>투자 자본금 (${esc(cap.currency)})<input id="capInput" inputmode="decimal" autocomplete="off" value="${isNum(cap.amount) ? cap.amount : ""}" placeholder="금액 입력"></label><button id="capSave">저장</button>${mk === "KR" ? '<button id="capRun" type="button" title="저장된 금액으로 한국 모델 스캔을 실행합니다">스캔 실행</button>' : ""}<div class="wide meta m0" id="capNote"></div><div class="wide meta m0" id="capRunNote"></div></div>
      ${b.newer_empty_scan ? `<div class="notice">더 최근 스캔(${when(b.newer_empty_scan.executed_at)}, 기준 거래일 ${esc(b.newer_empty_scan.latest_session || "")})은 그날 시세가 아직 다 나오지 않아 채점한 종목이 없었습니다. 아래는 그 전의 마지막 유효 결과입니다.</div>` : ""}
      ${b.run_id ? `<div class="kv"><div><span>최근 전체 스캔</span><b>${when(b.executed_at)}</b></div>${b.latest_session ? `<div><span>기준 거래일</span><b>${esc(b.latest_session)}</b></div>` : ""}<div><span>결과</span><b>${esc(REC_KO[b.recommendation_status] || b.recommendation_status)}</b></div>
        <div><span>시장 국면</span><b>${esc(REGIME_KO[b.regime] || b.regime || "—")}</b></div><div><span>기준 자본</span><b class="num">${isNum(b.capital) ? b.capital.toLocaleString("ko-KR") + " " + esc(b.currency || "") : DASH}</b></div></div>
      <h3>모델 상위 종목</h3><div class="tbl-wrap"><table><thead><tr><th>순위</th><th class="l">종목</th><th class="l">섹터</th><th>기준가</th><th title="모델이 순위를 매기는 데 쓰는 값입니다. 수익률이 아닙니다.">${mk === "KR" ? "모델 점수(순위용)" : "모델 알파(순위용)"}</th><th>목표 비중</th><th>목표 금액</th><th>주수</th><th>손절가</th><th>보유 기간</th></tr></thead>
      <tbody>${(b.top5 || []).map((r) => `<tr class="click" data-ticker="${esc(r.ticker)}"><td>${esc(r.recommendation_rank)}</td><td class="l"><b>${esc(r.ticker)}</b> <span class="meta m0">${esc(r.name || "")}</span></td>
        <td class="l">${esc(sectorKo(r.sector))}</td><td class="num">${fmt(r.close, mk === "KR" ? 0 : 2)}</td><td class="num">${fmt(r.alpha, 3)}</td><td class="num">${isNum(r.target_weight) ? (r.target_weight * 100).toFixed(1) + "%" : DASH}</td>
        <td class="num" data-cap-amount data-w="${isNum(r.target_weight) ? r.target_weight : ""}">${DASH}</td><td class="num" data-cap-shares data-w="${isNum(r.target_weight) ? r.target_weight : ""}" data-close="${isNum(r.close) ? r.close : ""}">${DASH}</td>
        <td class="num">${fmt(r.hard_stop)}</td><td>${isNum(r.horizon_days) ? r.horizon_days + "거래일" : DASH}</td></tr>`).join("") || '<tr><td colspan="10" class="empty">추천 종목 없음</td></tr>'}</tbody></table></div>
      <div class="meta"><span class="tech-id">실행 ID ${esc(b.run_id)}</span> · 읽기 전용 표시입니다. 이 화면은 모델을 실행하거나 변경하지 않습니다.</div>` : '<div class="empty">기록된 전체 스캔이 없습니다.</div>'}</div>
      <div class="panel"><h2>전향적 추적 ${badge(t.status)}</h2>${t.status === "REAL" ? `<div class="kv"><div><span>기록된 실행</span><b>${esc(t.runs)}</b></div><div><span>관찰 건수</span><b>${esc(t.observations)}</b></div>${t.excluded_runs ? `<div title="같은 거래일을 두 번 스캔한 기록입니다. 지우지 않고 집계에서만 뺍니다."><span>집계 제외 (중복 스캔)</span><b>실행 ${esc(t.excluded_runs)}개 · ${esc(t.excluded_observations)}건</b></div>` : ""}
        <div><span>최근 갱신</span><b>${esc(t.latest_update || "—")}</b></div></div>
        ${t.outcome_states ? `<div class="kv">${Object.entries(t.outcome_states).map(([k, v]) => `<div><span>${esc(outKo(k))}</span><b>${esc(v)}</b></div>`).join("")}</div>` : ""}
        <div class="meta">표본이 충분히 쌓이기 전에는 성과를 판단할 수 없습니다.</div>` : `<div class="empty">추적 데이터를 읽지 못했습니다. ${esc(t.error ? errKo({ message: t.error }) : "")}</div>`}</div>
      <div class="panel"><h2>도전자 모델</h2><div class="empty">${esc(d.challenger_note)}</div></div>`;
    wireCapital(el, cap, b, mk);
  } catch (e) { el.innerHTML = errBox(e); }
}

const ALWAYS_FRESH = new Set(["watch", "account", "portfolio", "assist", "paper", "model"]);      // 오늘 탭은 RETURN으로 돌아옵니다 (assistant.js)
const RENDER = { overview: renderOverview, macro: renderMacro, watch: renderWatch, model: renderModel, stock: renderStock };
const RETURN = {};          // 다시 그리지 않고 돌아온 탭이 할 일 (탭 이름 -> 함수(떠날 때의 스크롤 위치)).  순위·카드 탭이 씁니다 (qsf.js).

// ------------------------------------------------------------------ boot
applyTheme(theme);
paintMarket();
// 열어 둔 화면은 서버가 업데이트돼도 옛 파일 그대로입니다. 서버가 알려 주는 화면 파일 표식이 처음 받은 것과 달라지면 알립니다.
function screenChanged() {
  const bar = $("#verbar");
  if (!bar || !bar.hidden) return;
  bar.hidden = false;
  bar.innerHTML = `<span>프로그램 화면이 업데이트되었습니다. 새로고침해야 새 탭과 기능이 보입니다.</span><button type="button" id="verreload">새로고침</button>`;
  $("#verreload").onclick = () => location.reload();
}
function loadHealth() {
  healthAt = Date.now();
  api("/api/health").then((h) => {
    if (h.screen) { if (screenStamp === null) screenStamp = h.screen; else if (h.screen !== screenStamp) screenChanged(); }
    const e = h.server_errors || {}, el = $("#health");
    el.textContent = `· ${h.version} · SEC ${h.sec === "CONFIGURED" ? "연결 설정됨" : "미설정"} · ECOS ${h.ecos === "CONFIGURED" ? "연결 설정됨" : "미설정"}` +
      (e.count ? ` · 서버 오류 ${e.count}건` : "");
    el.title = e.count && e.last ? `마지막 오류 ${e.last.at} ${e.last.path} (${e.last.type}). 자세한 내용: data/terminal/logs/server_errors.log` : "";
  }).catch(() => {});
}
loadHealth();
setTimeout(() => pruneRecentTickers().catch(() => {}), 3000);      // 첫 화면을 그린 뒤에
setInterval(loadHealth, 5 * 60 * 1000);
document.addEventListener("visibilitychange", () => { if (!document.hidden && Date.now() - healthAt > 30000) loadHealth(); });
let booted = false;
// #탭, #stock/코드, #qsf/코드(순위·카드 탭의 오늘 순위 보기에서 그 종목을 평가)를 읽습니다.  모르는 이름은 첫 화면으로 갑니다.
const HASH_TICKER = /^[0-9A-Z^][0-9A-Z.\-]{0,11}$/;
function fromHash() {
  const [head, tk] = location.hash.replace(/^#/, "").split("/"), [tab, view] = head.split(":");
  const card = tab === "qsf" && HASH_TICKER.test((tk || "").toUpperCase()) ? tk.toUpperCase() : null;
  // #qsf:exec 처럼 순위·카드 탭의 보기가 붙은 주소 (6차 묶음 P2-18): 같은 탭이면 보기만 바꿉니다.
  if (tab === "qsf" && !card && typeof qsfState !== "undefined") {
    const v = QSF_VIEWS[view] ? view : "rank";
    if (booted && state.tab === "qsf") { if (v !== qsfState.view) qsfSetView(v); return; }
    qsfState.view = v;
  }
  // 화면이 이미 그 주소대로면 다시 그리지 않습니다.  종목이 없는 #stock도 같다고 봅니다: 다시 그리면 방금 띄운 '혹시 이 종목인가요?' 목록이 지워집니다.
  if (booted && tab === state.tab && (tab !== "stock" || (tk || "").toUpperCase() === (state.ticker || "")) && (!card || card === state.card)) return;
  booted = true;
  if (tab === "stock" && tk) { state.ticker = decodeURIComponent(tk).toUpperCase(); state.loaded.stock = null; setMarket(marketOf(state.ticker), false); }
  if (card && typeof qsfOpenCard === "function") return qsfOpenCard(card, false);
  show(RENDER[tab] ? tab : RENDER.today ? "today" : "overview", false);
}
window.addEventListener("hashchange", fromHash);
window.addEventListener("DOMContentLoaded", fromHash);   // after every script (portfolio.js) has registered
