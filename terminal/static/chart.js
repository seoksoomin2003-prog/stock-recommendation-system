// 차트분석 탭 (CHART-1, 2026-11-23): 캔들·OHLC, 이동평균, 볼린저밴드, 거래량, RSI, MACD와 고전 신호.  읽기 전용이며 점수와 섞지 않는다.
// 계산은 서버(terminal/chart_analysis.py)가 하고, 이 파일은 그리기만 한다.  설정 숫자(기간·기준선)는 서버가 보낸 값을 쓴다.
"use strict";
const CHA_KEY = "qse-chart";
const CHA_RANGES = { "3mo": "3개월", "6mo": "6개월", "1y": "1년", "3y": "3년", "5y": "5년", "10y": "10년" };
const CHA_TYPES = { candle: "캔들", ohlc: "OHLC", line: "선" };
const CHA_HOME = { US: ["^GSPC", "^IXIC"], KR: ["^KS11", "^KQ11"] };
// Each signal is marked on the pane of the indicator it comes from, so the price chart carries only the crossings and band breaks.
const CHA_ON_PRICE = new Set(["GOLDEN_CROSS", "DEAD_CROSS", "BB_UPPER", "BB_LOWER"]);
const cha = { ticker: {}, range: "1y", type: "candle", ma: {}, bb: true, sig: true, data: null, x: null };
try {
  const v = JSON.parse(localStorage.getItem(CHA_KEY) || "null");
  if (v && typeof v === "object") {
    if (CHA_RANGES[v.range]) cha.range = v.range;
    if (CHA_TYPES[v.type]) cha.type = v.type;
    if (v.ma && typeof v.ma === "object") for (const m of ["US", "KR"]) if (Array.isArray(v.ma[m])) cha.ma[m] = v.ma[m].filter((n) => Number.isInteger(n));
    if (v.ticker && typeof v.ticker === "object") for (const m of ["US", "KR"]) if (typeof v.ticker[m] === "string") cha.ticker[m] = v.ticker[m];
    cha.bb = v.bb !== false; cha.sig = v.sig !== false;
  }
} catch (e) { /* storage unavailable: defaults */ }
function chaSave() {
  try { localStorage.setItem(CHA_KEY, JSON.stringify({ range: cha.range, type: cha.type, ma: cha.ma, bb: cha.bb, sig: cha.sig, ticker: cha.ticker })); } catch (e) { /* not remembered */ }
}
const chaName = (t) => (typeof CMP_INDEX !== "undefined" && CMP_INDEX[t]) || t;
// Per-market MA colours (visualization spec 2.3: Korean screens move 50 to aqua and 120 to grey) come from the tokens.
const chaMaColor = (n, T) => (T ? T.ma[n] : cssVar(`--ma${n}`)) || (T ? T.muted : cssVar("--muted"));
function chaTicker() {
  const mk = state.market;
  if (cha.ticker[mk]) return cha.ticker[mk];
  if (state.ticker && marketOf(state.ticker) === mk) return state.ticker;
  return recentTickers().find((t) => marketOf(t) === mk) || CHA_HOME[mk][0];
}
// 종목 화면의 '차트분석' 단추와 명령창이 쓴다.
function chartWith(t) {
  t = String(t).trim().toUpperCase();
  cha.ticker[t.startsWith("^") ? state.market : marketOf(t)] = t; chaSave();
  state.loaded.chart = null; show("chart");
}

async function renderChart() {
  state.loaded.chart = true;
  const el = $("#tab-chart"), mk = state.market, t = chaTicker();
  const chips = [...CHA_HOME[mk], ...recentTickers().filter((x) => marketOf(x) === mk).slice(0, 6)];
  el.innerHTML = `<div class="panel"><h2>차트분석 <span class="meta m0">${esc(chaName(t))}${chaName(t) !== t ? ` · ${esc(t)}` : ""}</span></h2>
    <form id="cha-form" class="cmp-bar" autocomplete="off"><input id="cha-q" maxlength="15" placeholder="${isKR() ? "종목 코드 (예: 005930)" : "종목 코드 (예: AAPL)"}" aria-label="차트로 볼 종목 코드">
      <button type="submit">보기</button>${chips.map((x) => `<button type="button" class="chip${x === t ? " on" : ""}" data-cha="${esc(x)}">${esc(chaName(x))}</button>`).join("")}</form>
    <div class="cha-ctl"><span class="seg" id="cha-rng">${Object.entries(CHA_RANGES).map(([r, n]) => `<button type="button" data-r="${r}" class="${r === cha.range ? "on" : ""}">${n}</button>`).join("")}</span>
      <span class="seg" id="cha-type">${Object.entries(CHA_TYPES).map(([k, n]) => `<button type="button" data-k="${k}" class="${k === cha.type ? "on" : ""}">${n}</button>`).join("")}</span>
      <label class="cha-opt"><input type="checkbox" id="cha-bb"${cha.bb ? " checked" : ""}> 볼린저밴드</label>
      <label class="cha-opt"><input type="checkbox" id="cha-sig"${cha.sig ? " checked" : ""}> 신호 표시</label></div>
    <div class="cha-ctl" id="cha-ma"></div>
    <div class="cha-stack" id="cha-stack"><canvas id="cha-price" aria-label="가격 차트"></canvas><div class="cha-pane">거래량</div><canvas id="cha-vol" aria-label="거래량"></canvas>
      <div class="cha-pane" id="cha-rsi-h">RSI</div><canvas id="cha-rsi" aria-label="RSI"></canvas><div class="cha-pane" id="cha-macd-h">MACD</div><canvas id="cha-macd" aria-label="MACD"></canvas>
      <div class="cha-xline" id="cha-x" hidden></div></div>
    <div class="legend" id="cha-legend"></div><div id="cha-meta"><div class="meta">불러오는 중…</div></div></div>
    <div class="panel"><h2>지금 상태</h2><div class="notice" id="cha-caveat"></div><div id="cha-lines"></div></div>
    <div class="panel"><h2>최근 신호 <span class="meta m0" id="cha-sig-n"></span></h2><div id="cha-sigs"></div></div>`;
  $("#cha-form").onsubmit = (e) => { e.preventDefault(); const q = $("#cha-q").value.trim(); if (q) chartWith(q); };
  el.querySelectorAll("[data-cha]").forEach((b) => (b.onclick = () => chartWith(b.dataset.cha)));
  $("#cha-rng").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; cha.range = b.dataset.r; chaSave(); renderChart(); };
  $("#cha-type").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; cha.type = b.dataset.k; chaSave(); $("#cha-type").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); chaDraw(); };
  $("#cha-bb").onchange = (e) => { cha.bb = e.target.checked; chaSave(); chaDraw(); };
  $("#cha-sig").onchange = (e) => { cha.sig = e.target.checked; chaSave(); chaDraw(); };
  const want = `${t}|${cha.range}|${(cha.ma[mk] || []).join(",")}`;
  try {
    const d = await api(`/api/chart/analysis?t=${encodeURIComponent(t)}&range=${cha.range}${cha.ma[mk] ? `&ma=${cha.ma[mk].join(",")}` : ""}`);
    if (want !== `${chaTicker()}|${cha.range}|${(cha.ma[mk] || []).join(",")}` || mk !== state.market || !$("#cha-stack")) return;
    cha.data = d;
    if (d.status !== "UNAVAILABLE" && !t.startsWith("^")) rememberTicker(t);
    chaControls(d); chaDraw(); redrawOn("chart", "main", chaDraw); chaText(d);
  } catch (e) { $("#cha-meta").innerHTML = `<span class="err">${esc(errKo(e))}</span>`; }
}
function chaControls(d) {
  const s = d.settings, mk = state.market, on = new Set(d.ma || []);
  $("#cha-ma").innerHTML = `<span class="meta m0">이동평균</span>${s.ma_choices.map((n) => `<label class="cha-opt"><input type="checkbox" data-ma="${n}"${on.has(n) ? " checked" : ""}>
    <span class="swatch" style="background:${chaMaColor(n)}"></span>${n}일</label>`).join("")}
    <button type="button" class="ghost" id="cha-ma-def">기본(${s.ma_default[mk].join("·")})</button><span class="meta m0">최대 ${s.ma_max}개</span>`;
  $("#cha-ma").querySelectorAll("[data-ma]").forEach((b) => (b.onchange = () => {
    const got = [...$("#cha-ma").querySelectorAll("[data-ma]:checked")].map((x) => +x.dataset.ma);
    if (got.length > s.ma_max) { b.checked = false; notify(`이동평균은 한 번에 ${s.ma_max}개까지 그립니다.`, "info"); return; }
    cha.ma[mk] = got; chaSave(); renderChart();
  }));
  $("#cha-ma-def").onclick = () => { delete cha.ma[mk]; chaSave(); renderChart(); };
  $("#cha-rsi-h").textContent = `RSI(${s.rsi.n}, 와일더 방식) · 기준선 ${s.rsi.low}/${s.rsi.high}`;
  $("#cha-macd-h").textContent = `MACD(${s.macd.join(", ")}) · 선, 시그널, 막대`;
}
function chaText(d) {
  const s = d.settings, bars = d.bars;
  $("#cha-caveat").textContent = s.caveat;
  if (d.status === "UNAVAILABLE" || !bars.length) {
    $("#cha-meta").innerHTML = `<div class="empty">${badge("UNAVAILABLE")} 가격 자료를 받지 못했습니다. 종목 코드를 확인하세요.</div>`;
    $("#cha-lines").innerHTML = $("#cha-sigs").innerHTML = ""; return;
  }
  const short = d.short_history ? ` · 가격 기록이 고른 기간보다 짧아 있는 ${bars.length}거래일만 그렸습니다` : "";
  $("#cha-meta").innerHTML = meta(d.source, d.cache.fetched_at, `${badge(d.status)} ${liveBadge(d.intraday)} ${esc(bars[0].date)} ~ ${esc(bars[bars.length - 1].date)}${short}`);
  $("#cha-lines").innerHTML = `${d.lines.map((l) => `<p class="cha-line"><b>${esc(l.name)}</b> ${esc(l.text)}</p>`).join("")}
    <div class="meta">마지막 일봉(${esc(bars[bars.length - 1].date)}) 기준입니다. 골든·데드크로스는 ${esc(s.cross_pair[state.market].join("일선과 "))}일선으로 봅니다(이동평균 선택과 상관없음).</div>`;
  const sig = d.signals.slice().reverse();
  $("#cha-sig-n").textContent = `이 기간 ${d.signal_count}건`;
  const row = (g) => `<tr><td>${esc(g.date)}</td><td class="l" title="${esc(g.text)}"><span aria-hidden="true">${g.side === "up" ? "▲" : g.side === "down" ? "▼" : "●"}</span> ${esc(g.label)}</td>
    <td class="num">${fmt(g.close, isKR() ? 0 : 2)}</td></tr>`;
  const head = '<thead><tr><th>날짜</th><th class="l">신호</th><th>그날 종가</th></tr></thead>';
  const kinds = [...new Map(d.signals.map((g) => [g.kind, g])).values()];
  $("#cha-sigs").innerHTML = !sig.length ? '<div class="empty">이 기간에 고전 신호가 없었습니다.</div>' :
    `<div class="tbl-wrap"><table>${head}<tbody>${sig.slice(0, 20).map(row).join("")}</tbody></table></div>
    ${sig.length > 20 ? `<details><summary class="meta">나머지 ${sig.length - 20}건 보기</summary><div class="tbl-wrap"><table>${head}<tbody>${sig.slice(20).map(row).join("")}</tbody></table></div></details>` : ""}
    <details open><summary class="meta">신호의 관습적인 뜻</summary>${kinds.map((g) => `<p class="cha-line"><b>${esc(g.label)}</b> ${esc(g.text)}</p>`).join("")}</details>
    <div class="meta">▲는 관습적으로 오름 쪽, ▼는 내림 쪽으로 읽는 신호입니다. 차트에서는 이동평균 교차와 볼린저 띠 이탈은 가격에, RSI·MACD 신호는 각 칸에, 거래량 급증은 거래량 칸에 찍힙니다. 신호 뒤 가격이 어떻게 됐는지는 계산하지 않았습니다(한 종목의 적은 표본은 우연이 크게 섞입니다). 이 표의 어떤 줄도 점수나 매매 계획에 쓰이지 않습니다.</div>`;
}

// ---------------------------------------------------------------- drawing
function chaDraw() {
  const d = cha.data, cv = $("#cha-price");
  if (!d || !cv || !cv.isConnected || !d.bars.length) return;
  const phone = isPhone(), bars = d.bars, n = bars.length, padR = 58;
  const P = setupCanvas(cv, phone ? 300 : 400), V = setupCanvas($("#cha-vol"), phone ? 70 : 90), R = setupCanvas($("#cha-rsi"), phone ? 80 : 100), M = setupCanvas($("#cha-macd"), phone ? 90 : 110);
  const pw = P.w - padR, bw = pw / n, x = (i) => i * bw + bw / 2;
  cha.x = { bw, pw, n };
  // colours through vizTokens (stage 2).  Signals are untested classic rules, not price moves: ink triangles, the shape gives the side;
  // the RSI and MACD lines are ink (the accent is not a data series); the MACD bars are the neutral bar colour, their side is the sign.
  const T = vizTokens(), grid = T.grid, muted = T.tick, up = T.up, dn = T.down, ink = T.ink;
  const mas = (d.ma || []).map(String);
  // price pane
  let lo = Infinity, hi = -Infinity;
  bars.forEach((b) => {
    const vals = [b.low, b.high, b.close, ...mas.map((k) => b.ma[k])];
    if (cha.bb) vals.push(b.bb_up, b.bb_low);
    vals.forEach((v) => { if (isNum(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } });
  });
  const pad = (hi - lo) * 0.05 || 1; lo -= pad; hi += pad;
  const ph = P.h - 22, py = (v) => 6 + (1 - (v - lo) / (hi - lo)) * (ph - 6);
  const nt = niceTicks(lo, hi);
  chaGrid(P.ctx, pw, lo, hi, py, grid, muted, (v) => tickLabel(v, nt.digits), 4, nt.ticks);
  chaDates(P.ctx, bars, x, P.h - 14, P.w, muted);
  const ctx = P.ctx;
  if (cha.bb) {
    ctx.fillStyle = muted; ctx.globalAlpha = 0.09; ctx.beginPath(); let started = false, back = [];
    bars.forEach((b, i) => { if (!isNum(b.bb_up) || !isNum(b.bb_low)) return; started ? ctx.lineTo(x(i), py(b.bb_up)) : ctx.moveTo(x(i), py(b.bb_up)); started = true; back.push(i); });
    back.reverse().forEach((i) => ctx.lineTo(x(i), py(bars[i].bb_low)));
    if (started) ctx.fill();
    ctx.globalAlpha = 1; ctx.setLineDash([4, 3]);
    line(ctx, bars.map((b) => b.bb_up), x, py, muted, 1); line(ctx, bars.map((b) => b.bb_low), x, py, muted, 1); line(ctx, bars.map((b) => b.bb_mid), x, py, muted, 0.8);
    ctx.setLineDash([]);
  }
  const wide = bw >= 2.2;
  if (cha.type === "line" || !wide) line(ctx, bars.map((b) => b.close), x, py, ink, 1.4);
  else bars.forEach((b, i) => {
    const okOpen = goodOpen(b), o = okOpen ? b.open : b.close, col = !okOpen && isNum(b.open) ? muted : b.close >= o ? up : dn, hiv = isNum(b.high) ? b.high : Math.max(o, b.close), lov = isNum(b.low) ? b.low : Math.min(o, b.close);
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x(i), py(hiv)); ctx.lineTo(x(i), py(lov)); ctx.stroke();
    if (!okOpen) { /* no trustworthy open: the high-low line only */ }
    else if (cha.type === "candle") ctx.fillRect(x(i) - bw * 0.35, py(Math.max(o, b.close)), Math.max(1, bw * 0.7), Math.max(1, Math.abs(py(o) - py(b.close))));
    else { ctx.beginPath(); ctx.moveTo(x(i) - bw * 0.4, py(o)); ctx.lineTo(x(i), py(o)); ctx.moveTo(x(i), py(b.close)); ctx.lineTo(x(i) + bw * 0.4, py(b.close)); ctx.stroke(); }
  });
  mas.forEach((k) => line(ctx, bars.map((b) => b.ma[k]), x, py, chaMaColor(k, T), 1.4));
  vizEndTags(ctx, mas.map((k) => { let i = n - 1; while (i >= 0 && !isNum(bars[i].ma[k])) i--; return i < 0 ? null : { y: py(bars[i].ma[k]), color: chaMaColor(k, T), label: k, dot: [x(i), py(bars[i].ma[k])] }; }).filter(Boolean),
    pw + 4, 12, ph - 6, { box: true, T });
  if (cha.sig) d.signals.forEach((g) => {
    if (!CHA_ON_PRICE.has(g.kind) || (!cha.bb && g.kind.startsWith("BB_")) || g.i < 0 || g.i >= n) return;      // band breaks go with the band
    const b = bars[g.i], upSide = g.side === "up", yy = upSide ? py(isNum(b.low) ? b.low : b.close) + 9 : py(isNum(b.high) ? b.high : b.close) - 9;
    chaMark(ctx, x(g.i), yy, upSide, ink);
  });
  // volume pane
  let vmax = 0; bars.forEach((b) => { if (isNum(b.volume)) vmax = Math.max(vmax, b.volume); });
  const vy = (v) => V.h - 2 - (v / (vmax || 1)) * (V.h - 8);
  chaGrid(V.ctx, pw, 0, vmax || 1, vy, grid, muted, (v) => big(v, ""), 2);
  bars.forEach((b, i) => {
    if (!isNum(b.volume)) return;
    const o = isNum(b.open) ? b.open : b.close; V.ctx.fillStyle = b.close >= o ? up : dn; V.ctx.globalAlpha = 0.5;
    V.ctx.fillRect(i * bw + bw * 0.1, vy(b.volume), Math.max(1, bw * 0.8), V.h - 2 - vy(b.volume)); V.ctx.globalAlpha = 1;
  });
  line(V.ctx, bars.map((b) => b.vol_avg), x, vy, ink, 1.2);
  if (cha.sig) d.signals.forEach((g) => { if (g.kind === "VOLUME_SPIKE" && g.i >= 0 && g.i < n) { V.ctx.fillStyle = ink; V.ctx.strokeStyle = T.surface; V.ctx.lineWidth = 2; V.ctx.beginPath(); V.ctx.arc(x(g.i), Math.max(6, vy(bars[g.i].volume) - 6), 4, 0, Math.PI * 2); V.ctx.fill(); V.ctx.stroke(); } });
  // RSI pane
  const s = d.settings, ry = (v) => 3 + (1 - v / 100) * (R.h - 6);
  R.ctx.fillStyle = muted; R.ctx.globalAlpha = 0.07; R.ctx.fillRect(0, ry(s.rsi.high), pw, ry(s.rsi.low) - ry(s.rsi.high)); R.ctx.globalAlpha = 1;
  chaGrid(R.ctx, pw, 0, 100, ry, grid, muted, (v) => v.toFixed(0), 0, [s.rsi.low, 50, s.rsi.high]);
  line(R.ctx, bars.map((b) => b.rsi), x, ry, ink, 1.4);
  if (cha.sig) d.signals.forEach((g) => { if (g.kind.startsWith("RSI_") && g.i >= 0 && g.i < n && isNum(bars[g.i].rsi)) chaMark(R.ctx, x(g.i), ry(bars[g.i].rsi) + (g.side === "up" ? 8 : -8), g.side === "up", ink); });
  // MACD pane
  let mlo = 0, mhi = 0; bars.forEach((b) => [b.macd, b.macd_signal, b.macd_hist].forEach((v) => { if (isNum(v)) { mlo = Math.min(mlo, v); mhi = Math.max(mhi, v); } }));
  const mpad = (mhi - mlo) * 0.08 || 1, my = (v) => 4 + (1 - (v - (mlo - mpad)) / (mhi - mlo + 2 * mpad)) * (M.h - 22);
  chaGrid(M.ctx, pw, mlo - mpad, mhi + mpad, my, grid, muted, (v) => v.toLocaleString("ko-KR", { maximumFractionDigits: Math.abs(v) >= 10 ? 0 : 2 }), 2, [0]);
  bars.forEach((b, i) => { if (!isNum(b.macd_hist)) return; M.ctx.fillStyle = T.bar; M.ctx.globalAlpha = 0.45; const y0 = my(0), y1 = my(b.macd_hist); M.ctx.fillRect(i * bw + bw * 0.15, Math.min(y0, y1), Math.max(1, bw * 0.7), Math.max(1, Math.abs(y1 - y0))); M.ctx.globalAlpha = 1; });
  line(M.ctx, bars.map((b) => b.macd), x, my, ink, 1.3); line(M.ctx, bars.map((b) => b.macd_signal), x, my, chaMaColor(20, T), 1.3);
  if (cha.sig) d.signals.forEach((g) => { if (g.kind.startsWith("MACD_") && g.i >= 0 && g.i < n && isNum(bars[g.i].macd)) chaMark(M.ctx, x(g.i), my(bars[g.i].macd) + (g.side === "up" ? 8 : -8), g.side === "up", ink); });
  chaDates(M.ctx, bars, x, M.h - 14, M.w, muted);
  // legend
  $("#cha-legend").innerHTML = [...mas.map((k) => `<span><i style="background:${chaMaColor(k, T)}"></i>${k}일선</span>`),
    cha.bb ? `<span><i style="background:${muted}"></i>볼린저밴드(${s.bollinger.n}일, ±${s.bollinger.k}표준편차)</span>` : "",
    `<span><i style="background:${ink}"></i>거래량 ${s.volume.n}일 평균</span>`, `<span><i style="background:${ink}"></i>RSI·MACD선</span>`, `<span><i style="background:${chaMaColor(20, T)}"></i>MACD 시그널</span>`,
    cha.sig ? `<span><b>▲</b> 오름 쪽 · <b>▼</b> 내림 쪽 신호 · <b>●</b> 거래량 급증 (모두 검증 안 됨)</span>` : ""].join("");
  chaHover();
}
function chaGrid(ctx, pw, lo, hi, y, grid, muted, label, rows = 4, at = null) {
  ctx.font = vizFont(11); ctx.textBaseline = "middle"; ctx.textAlign = "left"; ctx.lineWidth = 1;
  const vals = at || Array.from({ length: rows + 1 }, (_, k) => lo + ((hi - lo) * k) / rows);
  vals.forEach((v) => { const yy = y(v); ctx.strokeStyle = grid; ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(pw, yy); ctx.stroke(); ctx.fillStyle = muted; ctx.fillText(label(v), pw + 6, yy); });
}
function chaDates(ctx, bars, x, yy, w, muted) { vizDates(ctx, bars.map((b) => b.date), x, yy, w, muted); }
function chaMark(ctx, x, y, upSide, col) {
  ctx.fillStyle = col; ctx.beginPath();
  if (upSide) { ctx.moveTo(x, y - 5); ctx.lineTo(x - 4.5, y + 3); ctx.lineTo(x + 4.5, y + 3); } else { ctx.moveTo(x, y + 5); ctx.lineTo(x - 4.5, y - 3); ctx.lineTo(x + 4.5, y - 3); }
  ctx.closePath(); ctx.fill();
}
// One crosshair over the four panes: a thin line and the day's figures.  Pointer events, so a finger drag on a phone works too.
function chaHover() {
  const box = $("#cha-stack"), xl = $("#cha-x"), d = cha.data;
  if (!box || !d) return;
  const at = (e) => {
    const r = $("#cha-price").getBoundingClientRect(), g = cha.x;
    if (!g || e.clientX - r.left > g.pw) return hide();
    const i = Math.min(g.n - 1, Math.max(0, Math.floor((e.clientX - r.left) / g.bw))), b = d.bars[i];
    xl.hidden = false; xl.style.left = (i * g.bw + g.bw / 2) + "px";
    const dg = isKR() ? 0 : 2, sigs = d.signals.filter((s) => s.i === i);
    const tip = $("#tip"); tip.hidden = false;
    tip.innerHTML = `<b>${esc(b.date)}</b><br>시 ${fmt(b.open, dg)} 고 ${fmt(b.high, dg)} 저 ${fmt(b.low, dg)} 종 ${fmt(b.close, dg)}<br>
      거래량 ${big(b.volume, "")}${isNum(b.volume) && isNum(b.vol_avg) && b.vol_avg ? ` (20일 평균의 ${(b.volume / b.vol_avg).toFixed(1)}배)` : ""}<br>
      ${(d.ma || []).map((k) => `<i class="key-line" style="background:${chaMaColor(k)}"></i>${k}일 ${fmt(b.ma[String(k)], dg)}`).join(" · ")}<br>
      볼린저 ${fmt(b.bb_low, dg)} ~ ${fmt(b.bb_up, dg)} · RSI ${fmt(b.rsi, 1)} · MACD ${fmt(b.macd, 2)} / 시그널 ${fmt(b.macd_signal, 2)}
      ${sigs.length ? `<br>${sigs.map((s) => `${s.side === "up" ? "▲" : s.side === "down" ? "▼" : "●"} ${esc(s.label)}`).join(" · ")}` : ""}`;
    const tx = e.clientX + 14 + tip.offsetWidth > window.innerWidth ? e.clientX - tip.offsetWidth - 14 : e.clientX + 14;
    tip.style.left = Math.max(4, tx) + "px"; tip.style.top = e.clientY + 14 + "px";
  };
  const hide = () => { xl.hidden = true; $("#tip").hidden = true; };
  box.onpointermove = at; box.onpointerdown = at; box.onpointerleave = hide;
}
RENDER.chart = renderChart;
