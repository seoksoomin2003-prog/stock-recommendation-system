// 비교 탭: 여러 종목과 지수를 같은 출발점(0%)에서 배당 포함 수익률로 겹쳐 본다.  읽기 전용.
"use strict";
const CMP_KEY = "compareTickers";
const CMP_INDEX = { "^GSPC": "S&P 500", "^IXIC": "나스닥 종합", "^KS11": "코스피", "^KQ11": "코스닥" };
const cmp = { list: null, slots: {}, range: "1y", data: null };

function cmpDefault() {
  const mine = recentTickers().filter((t) => marketOf(t) === state.market);
  return (isKR() ? ["^KS11", ...mine] : ["SPY", ...mine]).slice(0, 3);
}
function cmpInit() {
  if (cmp.list) return;
  try { const v = JSON.parse(localStorage.getItem(CMP_KEY) || "null"); if (Array.isArray(v) && v.length) cmp.list = v.filter((s) => typeof s === "string").slice(0, 8); } catch (e) { /* storage unavailable */ }
  cmp.list = cmp.list || cmpDefault();
  cmp.list.forEach(cmpSlot);
}
// A colour belongs to its stock for as long as it is on the chart: removing one never repaints the others.
function cmpSlot(t) {
  if (cmp.slots[t] === undefined) { const used = new Set(Object.values(cmp.slots)); cmp.slots[t] = [0, 1, 2, 3, 4, 5, 6, 7].find((i) => !used.has(i)); }
  return cmp.slots[t];
}
const cmpColor = (t) => cssVar(`--s${cmpSlot(t) + 1}`);
const cmpName = (t) => CMP_INDEX[t] || t;
function cmpSave() { try { localStorage.setItem(CMP_KEY, JSON.stringify(cmp.list)); } catch (e) { /* not remembered */ } }
function cmpAdd(t) {
  t = String(t).trim().toUpperCase();
  if (!t || cmp.list.includes(t)) return;
  if (cmp.list.length >= 8) { alert("비교는 최대 8개까지입니다."); return; }
  cmp.list.push(t); cmpSlot(t); cmpSave();
}
function cmpRemove(t) { cmp.list = cmp.list.filter((x) => x !== t); delete cmp.slots[t]; cmpSave(); }
function compareWith(list) {
  cmpInit(); list.forEach(cmpAdd);
  state.loaded.compare = null; show("compare");
}

async function renderCompare() {
  cmpInit();
  state.loaded.compare = true;
  const el = $("#tab-compare");
  el.innerHTML = `<div class="panel"><h2>수익률 비교 <span class="seg" id="cmp-rng">${["3mo", "1y", "5y"].map((r) => `<button data-r="${r}" class="${r === cmp.range ? "on" : ""}">${{ "3mo": "3개월", "1y": "1년", "5y": "5년" }[r]}</button>`).join("")}</span></h2>
    <div class="cmp-bar" id="cmp-chips"></div>
    <form id="cmp-add" class="cmp-bar" autocomplete="off"><input id="cmp-q" maxlength="15" placeholder="종목 코드 추가 (예: NVDA, 005930)" aria-label="비교할 종목 코드">
      <button type="submit">추가</button>
      <span class="meta" style="margin:0">지수: ${Object.entries(CMP_INDEX).map(([s, n]) => `<button type="button" class="chip" data-add="${esc(s)}">${esc(n)}</button>`).join(" ")}</span></form>
    <canvas id="cmp-cv" class="chart" aria-label="수익률 비교 차트"></canvas><div class="legend" id="cmp-legend"></div><div id="cmp-meta"></div></div>
    <div class="panel"><h2>기간 성과</h2><div id="cmp-stats"></div></div>
    <div class="panel"><h2>일간 수익률 상관계수</h2><div id="cmp-corr"></div></div>`;
  $("#cmp-rng").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; cmp.range = b.dataset.r; renderCompare(); };
  $("#cmp-add").onsubmit = (e) => { e.preventDefault(); cmpAdd($("#cmp-q").value); renderCompare(); };
  el.querySelectorAll("[data-add]").forEach((b) => (b.onclick = () => { cmpAdd(b.dataset.add); renderCompare(); }));
  cmpChips();
  if (!cmp.list.length) { $("#cmp-meta").innerHTML = '<div class="empty">비교할 종목을 추가하세요.</div>'; return; }
  $("#cmp-meta").innerHTML = '<div class="meta">불러오는 중…</div>';
  const want = cmp.list.join(",") + "|" + cmp.range;
  try {
    const d = await api(`/api/compare?t=${encodeURIComponent(cmp.list.join(","))}&range=${cmp.range}`);
    if (want !== cmp.list.join(",") + "|" + cmp.range) return;
    cmp.data = d; cmpDraw(); redrawers.add(cmpDraw); cmpTables(d);
    const miss = d.missing && d.missing.length ? ` · <span class="err">가격 없음: ${esc(d.missing.join(", "))}</span>` : "";
    $("#cmp-meta").innerHTML = d.status === "REAL"
      ? meta(d.source, d.fetched_at, `${esc(d.dates[0])} ~ ${esc(d.dates[d.dates.length - 1])} · ${esc(d.basis)}${d.mixed_markets ? " 미국과 한국을 섞으면 두 시장이 모두 연 날만 남습니다." : ""}${miss}`)
      : `<div class="empty">${badge("UNAVAILABLE")} 비교할 가격을 받지 못했습니다.${miss}</div>`;
  } catch (e) { $("#cmp-meta").innerHTML = `<span class="err">${esc(ERR_KO[e.message] || e.message)}</span>`; }
}
function cmpChips() {
  const box = $("#cmp-chips");
  box.innerHTML = cmp.list.map((t) => `<span class="chip"><span class="swatch" style="background:${cmpColor(t)}"></span>${esc(cmpName(t))}<button type="button" class="x" data-rm="${esc(t)}" aria-label="${esc(cmpName(t))} 빼기">×</button></span>`).join("")
    || '<span class="meta" style="margin:0">아직 없습니다.</span>';
  box.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => { cmpRemove(b.dataset.rm); renderCompare(); }));
}
function cmpDraw() {
  const cv = $("#cmp-cv"), d = cmp.data;
  if (!cv || !cv.isConnected || !d || d.status !== "REAL") return;
  const H = window.innerWidth < 600 ? 280 : 380, { ctx, w, h } = setupCanvas(cv, H);
  const n = d.dates.length, labels = d.series.length <= 4, padR = labels ? 92 : 52, padT = 10, padB = 20, pw = w - padR, ph = h - padT - padB;
  let lo = 0, hi = 0;
  d.series.forEach((s) => s.points.forEach((v) => { lo = Math.min(lo, v); hi = Math.max(hi, v); }));
  const pad = (hi - lo) * 0.06 || 0.01; lo -= pad; hi += pad;
  const x = (i) => (n > 1 ? (i / (n - 1)) * pw : 0), y = (v) => padT + (1 - (v - lo) / (hi - lo)) * ph;
  const grid = cssVar("--grid"), muted = cssVar("--muted"), ink = cssVar("--ink");
  ctx.font = "11px -apple-system, sans-serif"; ctx.textBaseline = "middle";
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4, yy = y(v);
    ctx.strokeStyle = grid; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(pw, yy); ctx.stroke();
    ctx.fillStyle = muted; ctx.fillText(`${(v * 100).toFixed(0)}%`, pw + 6, yy);
  }
  ctx.strokeStyle = muted; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, y(0)); ctx.lineTo(pw, y(0)); ctx.stroke();
  ctx.textBaseline = "top"; ctx.textAlign = "center"; ctx.fillStyle = muted;
  const step = Math.max(1, Math.round(n / (w < 600 ? 4 : 7)));
  for (let i = step; i < n - step / 3; i += step) ctx.fillText(d.dates[i].slice(2, 7).replace("-", "."), x(i), h - 14);
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  d.series.forEach((s) => line(ctx, s.points, x, y, cmpColor(s.ticker), 2));
  if (labels) {      // direct labels at the line ends, nudged apart, in text ink beside a colour mark
    const ends = d.series.map((s) => ({ s, yy: y(s.points[n - 1]) })).sort((a, b) => a.yy - b.yy);
    for (let i = 1; i < ends.length; i++) ends[i].yy = Math.max(ends[i].yy, ends[i - 1].yy + 14);
    ends.forEach(({ s, yy }) => {
      ctx.fillStyle = cmpColor(s.ticker); ctx.fillRect(pw + 36, yy - 4, 8, 8);
      ctx.fillStyle = ink; ctx.fillText(cmpName(s.ticker).slice(0, 7), pw + 48, yy);
    });
  }
  $("#cmp-legend").innerHTML = d.series.map((s) => `<span><span class="swatch" style="background:${cmpColor(s.ticker)}"></span>${esc(cmpName(s.ticker))} ${pct(s.total_return * 100, 1)}</span>`).join("");
  cv.onmousemove = (e) => {
    const r = cv.getBoundingClientRect(), i = Math.min(n - 1, Math.max(0, Math.round(((e.clientX - r.left) / pw) * (n - 1))));
    const rows = d.series.map((s) => [s, s.points[i]]).sort((a, b) => b[1] - a[1]);
    const tip = $("#tip"); tip.hidden = false;
    tip.innerHTML = `<b>${esc(d.dates[i])}</b><br>${rows.map(([s, v]) => `<span class="swatch" style="background:${cmpColor(s.ticker)}"></span>${esc(cmpName(s.ticker))} ${pct(v * 100, 1)}`).join("<br>")}`;
    const tx = e.clientX + 14 + tip.offsetWidth > window.innerWidth ? e.clientX - tip.offsetWidth - 14 : e.clientX + 14;
    tip.style.left = tx + "px"; tip.style.top = e.clientY + 14 + "px";
  };
  cv.onmouseleave = () => ($("#tip").hidden = true);
}
function cmpTables(d) {
  if (d.status !== "REAL") { $("#cmp-stats").innerHTML = $("#cmp-corr").innerHTML = ""; return; }
  const yrs = (d.dates.length - 1) / 252;
  $("#cmp-stats").innerHTML = `<div class="tbl-wrap"><table><thead><tr><th class="l">종목</th><th>기간 수익률</th><th>연환산</th><th>연 변동성</th><th>최대 낙폭</th></tr></thead><tbody>
    ${d.series.map((s) => `<tr${s.ticker in CMP_INDEX ? "" : ` class="click" data-ticker="${esc(s.ticker)}"`}><td class="l"><span class="swatch" style="background:${cmpColor(s.ticker)}"></span>${esc(cmpName(s.ticker))}</td>
      <td class="num">${pct(s.total_return * 100, 1)}</td><td class="num">${yrs >= 0.9 ? pct((Math.pow(1 + s.total_return, 1 / yrs) - 1) * 100, 1) : DASH}</td>
      <td class="num">${isNum(s.volatility) ? (s.volatility * 100).toFixed(1) + "%" : DASH}</td><td class="num">${pct(s.max_drawdown * 100, 1)}</td></tr>`).join("")}</tbody></table></div>
    <div class="meta">연환산은 1년 가까이 되는 기간에만 표시합니다. 과거 성과이며 앞으로의 수익을 뜻하지 않습니다.</div>`;
  const head = d.series.map((s) => `<th>${esc(cmpName(s.ticker).slice(0, 8))}</th>`).join("");
  $("#cmp-corr").innerHTML = d.series.length < 2 ? '<div class="empty">두 개 이상일 때 보입니다.</div>' : `<div class="tbl-wrap"><table><thead><tr><th class="l"></th>${head}</tr></thead><tbody>
    ${d.series.map((s, i) => `<tr><td class="l">${esc(cmpName(s.ticker))}</td>${d.correlation[i].map((v, j) => `<td class="num">${i === j ? DASH : fmt(v, 2)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    <div class="meta">1에 가까울수록 같이 움직였고, 0 근처면 따로 움직였습니다. 같은 날 수익률끼리 비교합니다.</div>`;
}
RENDER.compare = renderCompare;
