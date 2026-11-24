// 차트분석 탭 (CHART-1, 2026-11-23): 캔들·OHLC, 이동평균, 볼린저밴드, 거래량, RSI, MACD와 고전 신호.  읽기 전용이며 점수와 섞지 않는다.
// 계산은 서버(terminal/chart_analysis.py)가 하고, 이 파일은 그리기만 한다.  설정 숫자(기간·기준선)는 서버가 보낸 값을 쓴다.
"use strict";
const CHA_KEY = "qse-chart";
const CHA_RANGES = { "1d": "오늘(1분봉)", "3mo": "3개월", "6mo": "6개월", "1y": "1년", "3y": "3년", "5y": "5년", "10y": "10년" };
const CHA_TYPES = { candle: "캔들", ohlc: "OHLC", line: "선" };
const CHA_HOME = { US: ["^GSPC", "^IXIC"], KR: ["^KS11", "^KQ11"] };
// Each signal is marked on the pane of the indicator it comes from, so the price chart carries only the crossings and band breaks.
const CHA_ON_PRICE = new Set(["GOLDEN_CROSS", "DEAD_CROSS", "BB_UPPER", "BB_LOWER"]);
const cha = { ticker: {}, range: "1y", type: "candle", ma: {}, bb: true, sig: true, data: null, x: null, timer: null, tick: 0, busy: false };
// 장중에 차트가 움직이게 (2026-11-25): 30초마다 다시 받습니다.  장이 닫혀 있으면 5분마다 열렸는지만 봅니다.  가격이 몇 분 전 것인지는
// 서버가 마지막 1분봉 시각으로 재서 보내고, 화면은 그 문장을 그대로 보여 줍니다(늦은 가격을 지금 가격처럼 보이지 않게).
const CHA_REFRESH_MS = 30000, CHA_CLOSED_EVERY = 10;
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
  // 작업 화면 개편 6단계 (배치 명세 3.7): 맨 위 줄에 제목, 종목 칸과 바로가기; 가운데 칸에 기간·모양·이동평균과 네 칸 차트; 오른쪽 칸에
  // 지금 상태와 최근 신호.  한 칸이면 위 줄 → 차트 → 지금 상태 → 최근 신호(전과 같은 순서).
  el.innerHTML = ui.ws({ name: "chart", label: "지금 상태와 최근 신호",
    ctx: `<h2>차트분석 <span class="meta m0">${esc(chaName(t))}${chaName(t) !== t ? ` · ${esc(t)}` : ""}</span> <span id="cha-badge"></span></h2>
    <form id="cha-form" class="cmp-bar ws-tools" autocomplete="off"><input id="cha-q" maxlength="15" placeholder="${isKR() ? "종목 코드 (예: 005930)" : "종목 코드 (예: AAPL)"}" aria-label="차트로 볼 종목 코드">
      <button type="submit">보기</button>${chips.map((x) => `<button type="button" class="chip${x === t ? " on" : ""}" data-cha="${esc(x)}">${esc(chaName(x))}</button>`).join("")}</form>`,
    main: `<div class="panel"><div class="cha-ctl"><span class="seg" id="cha-rng">${Object.entries(CHA_RANGES).map(([r, n]) => `<button type="button" data-r="${r}" class="${r === cha.range ? "on" : ""}">${n}</button>`).join("")}</span>
      <span class="seg" id="cha-type">${Object.entries(CHA_TYPES).map(([k, n]) => `<button type="button" data-k="${k}" class="${k === cha.type ? "on" : ""}">${n}</button>`).join("")}</span>
      <label class="cha-opt"><input type="checkbox" id="cha-bb"${cha.bb ? " checked" : ""}> 볼린저밴드</label>
      <label class="cha-opt"><input type="checkbox" id="cha-sig"${cha.sig ? " checked" : ""}> 신호 표시</label></div>
    <div class="cha-ctl" id="cha-ma"></div>
    <div class="cha-stack" id="cha-stack" role="group" aria-label="${esc(chaName(t))} 차트 네 칸. 초점을 두고 ←/→로 날짜를 옮깁니다."><canvas id="cha-price" aria-label="가격 차트"></canvas><div class="cha-pane">거래량</div><canvas id="cha-vol" aria-label="거래량"></canvas>
      <div class="cha-pane" id="cha-rsi-h">RSI</div><canvas id="cha-rsi" aria-label="RSI"></canvas><div class="cha-pane" id="cha-macd-h">MACD</div><canvas id="cha-macd" aria-label="MACD"></canvas>
      <div class="cha-xline viz-xline" id="cha-x" hidden></div></div>
    <div class="legend" id="cha-legend"></div><div id="cha-meta"><div class="meta">불러오는 중…</div></div><div id="cha-twin"></div></div>`,
    right: `<div class="panel"><h2>지금 상태</h2><div class="notice" id="cha-caveat"></div><div id="cha-lines"></div></div>
    <div class="panel"><h2>최근 신호 <span class="meta m0" id="cha-sig-n"></span></h2><div id="cha-sigs"></div></div>` });
  $("#cha-form").onsubmit = (e) => { e.preventDefault(); const q = $("#cha-q").value.trim(); if (q) chartWith(q); };
  el.querySelectorAll("[data-cha]").forEach((b) => (b.onclick = () => chartWith(b.dataset.cha)));
  $("#cha-rng").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; cha.range = b.dataset.r; chaSave(); renderChart(); };
  $("#cha-type").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; cha.type = b.dataset.k; chaSave(); $("#cha-type").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); chaDraw(); };
  $("#cha-bb").onchange = (e) => { cha.bb = e.target.checked; chaSave(); chaDraw(); };
  $("#cha-sig").onchange = (e) => { cha.sig = e.target.checked; chaSave(); chaDraw(); };
  const minute = cha.range === "1d";
  // 1분봉에는 일봉 기준 지표가 없으므로 그 칸과 선택지를 숨깁니다(display: 클래스 규칙이 hidden 속성보다 앞섭니다).
  [$("#cha-ma"), $("#cha-rsi-h"), $("#cha-rsi"), $("#cha-macd-h"), $("#cha-macd"), $("#cha-bb").closest("label"), $("#cha-sig").closest("label")]
    .forEach((el) => (el.style.display = minute ? "none" : ""));
  const want = chaWant();
  cha.data = null; clearInterval(cha.timer);
  try {
    const d = await api(chaUrl(t, mk));
    if (want !== chaWant() || mk !== state.market || !$("#cha-stack")) return;
    if (d.status !== "UNAVAILABLE" && !t.startsWith("^")) rememberTicker(t);
    if (!minute) chaControls(d);
    chaTake(d); redrawOn("chart", "main", chaDraw); chaPoll();
  } catch (e) { $("#cha-meta").innerHTML = `<span class="err">${esc(errKo(e))}</span>`; }
}
const chaWant = () => `${chaTicker()}|${cha.range}|${(cha.ma[state.market] || []).join(",")}|${state.market}`;
function chaUrl(t, mk) {
  return cha.range === "1d" ? `/api/chart/intraday?t=${encodeURIComponent(t)}`
    : `/api/chart/analysis?t=${encodeURIComponent(t)}&range=${cha.range}${cha.ma[mk] ? `&ma=${cha.ma[mk].join(",")}` : ""}&live=1`;
}
function chaTake(d) {
  d.minute = cha.range === "1d";
  cha.data = d; chaDraw();
  d.minute ? chaTextMinute(d) : chaText(d);
}
const chaLiveOn = (d) => !!d && (d.minute ? d.live : !!(d.live_now && d.live_now.live));
// 한 타이머만 돕니다.  차트 탭이 아니거나 창이 가려져 있으면 받지 않고, 받는 사이 종목·기간이 바뀌었으면 버립니다.
function chaPoll() {
  clearInterval(cha.timer); cha.tick = 0;
  cha.timer = setInterval(async () => {
    cha.tick++;
    if (state.tab !== "chart" || document.hidden || !$("#cha-stack") || cha.busy || !cha.data) return;
    if (!chaLiveOn(cha.data) && cha.tick % CHA_CLOSED_EVERY) return;
    const mk = state.market, want = chaWant();
    cha.busy = true;
    try {
      const d = await api(chaUrl(chaTicker(), mk));
      if (want === chaWant() && $("#cha-stack")) chaTake(d);
    } catch (e) { /* 그려진 차트는 그대로 두고 다음 차례에 다시 받습니다 */ } finally { cha.busy = false; }
  }, CHA_REFRESH_MS);
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
  $("#cha-badge").innerHTML = d.status !== "REAL" || d.intraday ? `${d.status !== "REAL" ? badge(d.status) : ""} ${liveBadge(d.intraday)}` : "";      // header badge (visualization spec 1.8)
  if (d.status === "UNAVAILABLE" || !bars.length) {
    $("#cha-stack").hidden = true;
    $("#cha-meta").innerHTML = `<div class="empty">${badge("UNAVAILABLE")} 가격 자료를 받지 못했습니다. 종목 코드를 확인하세요.</div>`;
    $("#cha-lines").innerHTML = $("#cha-sigs").innerHTML = $("#cha-twin").innerHTML = ""; return;
  }
  const dg = isKR() ? 0 : 2, tail = bars.slice(-30).reverse();
  $("#cha-twin").innerHTML = vizTable([{ label: "날짜", cls: "l" }, { label: "시" }, { label: "고" }, { label: "저" }, { label: "종" }, { label: "거래량" }, { label: "RSI" }, { label: "MACD" }, { label: "시그널" }],
    tail.map((b) => `<tr><td class="l">${esc(b.date)}</td><td class="num">${goodOpen(b) || !isNum(b.open) ? fmt(b.open, dg) : DASH}</td><td class="num">${fmt(b.high, dg)}</td><td class="num">${fmt(b.low, dg)}</td><td class="num">${fmt(b.close, dg)}</td>
      <td class="num">${big(b.volume, "")}</td><td class="num">${fmt(b.rsi, 1)}</td><td class="num">${fmt(b.macd, 2)}</td><td class="num">${fmt(b.macd_signal, 2)}</td></tr>`),
    "최근 30거래일, 최신이 위입니다. 시가가 원자료 이상인 날은 비워 둡니다.");
  const short = d.short_history ? ` · 가격 기록이 고른 기간보다 짧아 있는 ${bars.length}거래일만 그렸습니다` : "";
  const lv = d.live_now ? ` · ${esc(d.live_now.note)}${d.live_now.live ? " 30초마다 다시 받습니다." : ""}` : "";
  $("#cha-meta").innerHTML = meta(d.source, d.cache.fetched_at, `${badge(d.status)} ${liveBadge(d.intraday)} ${esc(bars[0].date)} ~ ${esc(bars[bars.length - 1].date)}${short}${lv}`);
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
  if (cha.data && cha.data.minute) return chaDrawMinute();
  const d = cha.data, cv = $("#cha-price");
  if (!d || !cv || !cv.isConnected || !d.bars.length) return;
  const phone = isPhone(), bars = d.bars, n = bars.length, padR = 58;
  const narrow = !phone && isNarrow();      // heights per width step (visualization spec 1.10): 400/90/100/110, tablet 360/80/90/100, phone 300/70/80/90
  $("#cha-stack").hidden = false;
  const P = setupCanvas(cv, phone ? 300 : narrow ? 360 : 400), V = setupCanvas($("#cha-vol"), phone ? 70 : narrow ? 80 : 90), R = setupCanvas($("#cha-rsi"), phone ? 80 : narrow ? 90 : 100), M = setupCanvas($("#cha-macd"), phone ? 90 : narrow ? 100 : 110);
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
    else if (cha.type === "candle" && i === n - 1 && d.intraday) { ctx.lineWidth = 1.5; ctx.strokeRect(x(i) - bw * 0.35, py(Math.max(o, b.close)), Math.max(1, bw * 0.7), Math.max(1, Math.abs(py(o) - py(b.close)))); }   // today's bar is not final: hollow
    else if (cha.type === "candle") ctx.fillRect(x(i) - bw * 0.35, py(Math.max(o, b.close)), Math.max(1, bw * 0.7), Math.max(1, Math.abs(py(o) - py(b.close))));
    else { ctx.beginPath(); ctx.moveTo(x(i) - bw * 0.4, py(o)); ctx.lineTo(x(i), py(o)); ctx.moveTo(x(i), py(b.close)); ctx.lineTo(x(i) + bw * 0.4, py(b.close)); ctx.stroke(); }
  });
  if (d.intraday && wide) { const L = bars[n - 1]; ctx.save(); ctx.font = vizFont(10); ctx.fillStyle = T.warn; ctx.textAlign = "right"; ctx.textBaseline = "bottom";
    ctx.fillText("장중·미확정", Math.min(pw - 2, x(n - 1) + 4), Math.max(12, py(isNum(L.high) ? L.high : L.close) - 4)); ctx.restore(); }
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
  const vt = niceTicks(0, vmax || 1, 2), vtop = Math.max(vmax || 1, vt.ticks[vt.ticks.length - 1] || 0);
  const vy = (v) => V.h - 2 - (v / vtop) * (V.h - 8);
  chaGrid(V.ctx, pw, 0, vtop, vy, grid, muted, (v) => big(v, ""), 2, vt.ticks.filter((v) => v > 0));
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
  const mt = niceTicks(mlo - mpad, mhi + mpad, 2);       // two nice ticks and the zero line (drawn in --axis below)
  chaGrid(M.ctx, pw, mlo - mpad, mhi + mpad, my, grid, muted, (v) => tickLabel(v, mt.digits), 2, [...new Set([0, ...mt.ticks])]);
  M.ctx.strokeStyle = T.axis; M.ctx.lineWidth = 1; M.ctx.beginPath(); M.ctx.moveTo(0, my(0)); M.ctx.lineTo(pw, my(0)); M.ctx.stroke();
  bars.forEach((b, i) => { if (!isNum(b.macd_hist)) return; M.ctx.fillStyle = T.bar; M.ctx.globalAlpha = 0.45; const y0 = my(0), y1 = my(b.macd_hist); M.ctx.fillRect(i * bw + bw * 0.15, Math.min(y0, y1), Math.max(1, bw * 0.7), Math.max(1, Math.abs(y1 - y0))); M.ctx.globalAlpha = 1; });
  line(M.ctx, bars.map((b) => b.macd), x, my, ink, 1.3); line(M.ctx, bars.map((b) => b.macd_signal), x, my, chaMaColor(20, T), 1.3);
  if (cha.sig) d.signals.forEach((g) => { if (g.kind.startsWith("MACD_") && g.i >= 0 && g.i < n && isNum(bars[g.i].macd)) chaMark(M.ctx, x(g.i), my(bars[g.i].macd) + (g.side === "up" ? 8 : -8), g.side === "up", ink); });
  chaDates(M.ctx, bars, x, M.h - 14, M.w, muted);
  // legend
  $("#cha-legend").innerHTML = [...mas.map((k) => `<span><i style="background:${chaMaColor(k, T)}"></i>${k}일선</span>`),
    cha.bb ? `<span><i style="background:${muted}"></i>볼린저밴드(${s.bollinger.n}일, ±${s.bollinger.k}표준편차)</span>` : "",
    `<span><i style="background:${ink}"></i>거래량 ${s.volume.n}일 평균</span>`, `<span><i style="background:${ink}"></i>RSI·MACD선</span>`, `<span><i style="background:${chaMaColor(20, T)}"></i>MACD 시그널</span>`,
    cha.sig ? `<span><b>▲</b> 오름 쪽 · <b>▼</b> 내림 쪽 신호 · <b>●</b> 거래량 급증 (모두 검증 안 됨)</span>` : ""].join("");
  // names with a data summary (visualization spec 1.11), like the stock screen's price chart
  const b0 = bars[0], b1 = bars[n - 1], dg = isKR() ? 0 : 2, lastRsi = [...bars].reverse().find((b) => isNum(b.rsi));
  cv.setAttribute("aria-label", `${chaName(chaTicker())} 가격 차트: ${b0.date}부터 ${b1.date}까지, 종가 ${isNum(b0.close) ? tickLabel(b0.close, dg) : "없음"}에서 ${isNum(b1.close) ? tickLabel(b1.close, dg) : "없음"}${d.intraday ? " (마지막 일봉은 장중·미확정)" : ""}`);
  $("#cha-rsi").setAttribute("aria-label", `RSI: 마지막 값 ${lastRsi ? lastRsi.rsi.toFixed(1) : "없음"}`);
  chaHover(py, nt.digits);
}
// Grid lines and value ticks; the tick labels are right-aligned at the canvas's right edge, so the digits line up (stage 6).
function chaGrid(ctx, pw, lo, hi, y, grid, muted, label, rows = 4, at = null) {
  const right = ctx.canvas.clientWidth - 4;
  ctx.font = vizFont(11); ctx.textBaseline = "middle"; ctx.textAlign = "right"; ctx.lineWidth = 1;
  const vals = at || Array.from({ length: rows + 1 }, (_, k) => lo + ((hi - lo) * k) / rows);
  vals.forEach((v) => { const yy = y(v); ctx.strokeStyle = grid; ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(pw, yy); ctx.stroke(); ctx.fillStyle = muted; ctx.fillText(label(v), right, yy); });
  ctx.textAlign = "left";
}
function chaDates(ctx, bars, x, yy, w, muted) { vizDates(ctx, bars.map((b) => b.date), x, yy, w, muted); }
function chaMark(ctx, x, y, upSide, col) {
  ctx.fillStyle = col; ctx.beginPath();
  if (upSide) { ctx.moveTo(x, y - 5); ctx.lineTo(x - 4.5, y + 3); ctx.lineTo(x + 4.5, y + 3); } else { ctx.moveTo(x, y + 5); ctx.lineTo(x - 4.5, y - 3); ctx.lineTo(x + 4.5, y - 3); }
  ctx.closePath(); ctx.fill();
}
// One crosshair over the four panes: a thin line and the day's figures.  vizHover on the stack itself (stage 6): pointer, finger drag
// (touch-action: pan-y keeps the page scroll) and keyboard on the stack (←/→ a day, Shift ten, Home/End), the close in the price gutter.
function chaHover(py, digits) {
  const box = $("#cha-stack"), d = cha.data, g = cha.x;
  if (!box || !d || !g) return;
  const bars = d.bars, x = (i) => i * g.bw + g.bw / 2;
  vizHover(box, { host: box, count: g.n, xOf: x, indexAt: (px) => (px > g.pw ? -1 : Math.min(g.n - 1, Math.max(0, Math.floor(px / g.bw)))),
    yTag: (i) => (isNum(bars[i].close) ? { x: g.pw + 2, y: py(bars[i].close), text: tickLabel(bars[i].close, Math.max(digits, isKR() ? 0 : 2)) } : null),
    html: (i) => {
      const b = bars[i], dg = isKR() ? 0 : 2, sigs = d.signals.filter((s) => s.i === i);
      return `<b>${esc(b.date)}</b>${i === g.n - 1 && d.intraday ? " 장중·미확정" : ""}<br>시 ${goodOpen(b) || !isNum(b.open) ? fmt(b.open, dg) : "없음(원자료 이상)"} 고 ${fmt(b.high, dg)} 저 ${fmt(b.low, dg)} 종 ${fmt(b.close, dg)}<br>
      거래량 ${big(b.volume, "")}${isNum(b.volume) && isNum(b.vol_avg) && b.vol_avg ? ` (20일 평균의 ${(b.volume / b.vol_avg).toFixed(1)}배)` : ""}<br>
      ${(d.ma || []).map((k) => `<i class="key-line" style="background:${chaMaColor(k)}"></i>${k}일 ${fmt(b.ma[String(k)], dg)}`).join(" · ")}<br>
      볼린저 ${fmt(b.bb_low, dg)} ~ ${fmt(b.bb_up, dg)} · RSI ${fmt(b.rsi, 1)} · MACD ${fmt(b.macd, 2)} / 시그널 ${fmt(b.macd_signal, 2)}
      ${sigs.length ? `<br>${sigs.map((s) => `${s.side === "up" ? "▲" : s.side === "down" ? "▼" : "●"} ${esc(s.label)}`).join(" · ")}` : ""}`; } });
}
// ---------------------------------------------------------------- today's one-minute bars (2026-11-25)
// 가로축은 정규장 전체(미국 09:30~16:00, 한국 09:00~15:30)라서 장이 흐르는 만큼 왼쪽부터 채워집니다.  점선은 전일 종가입니다.
function chaTextMinute(d) {
  const L = d.last || {}, dg = isKR() ? 0 : 2, bars = d.bars || [];
  $("#cha-caveat").textContent = "1분봉은 차트를 읽는 참고 자료이며 점수와 섞지 않고, 매매 지시가 아닙니다. 지표·신호는 일봉 기준 규칙이라 1분봉에는 그리지 않습니다.";
  $("#cha-badge").innerHTML = `${d.status !== "REAL" ? badge(d.status) : ""}${d.live ? ` <span class="badge live" title="${esc(d.note)}">장중 · ${esc(String(Math.round(d.age_min)))}분 전 가격</span>` : ""}`;
  $("#cha-sig-n").textContent = "";
  $("#cha-sigs").innerHTML = '<div class="empty">1분봉에는 고전 신호를 표시하지 않습니다. 일봉 기간을 고르면 볼 수 있습니다.</div>';
  $("#cha-legend").innerHTML = bars.length ? `<span><i style="background:${cssVar("--muted")}"></i>점선: 전일 종가</span>` : "";
  if (d.status === "UNAVAILABLE" || !bars.length) {
    $("#cha-stack").hidden = true; $("#cha-twin").innerHTML = "";
    $("#cha-meta").innerHTML = `<div class="empty">${badge("UNAVAILABLE")} ${esc(d.note || "1분봉을 받지 못했습니다.")}</div>`;
    $("#cha-lines").innerHTML = ""; return;
  }
  $("#cha-meta").innerHTML = meta(d.source, d.cache.fetched_at, `${badge(d.status)} ${esc(d.session)} · ${esc(d.note)}${d.live ? " 30초마다 다시 받습니다." : ""}`);
  const chg = isNum(L.change_pct) ? `${L.change_pct >= 0 ? "+" : ""}${L.change_pct.toFixed(2)}%` : DASH;
  $("#cha-lines").innerHTML = `<p class="cha-line"><b>마지막 가격</b> ${fmt(L.close, dg)} (${esc(String(L.time).slice(11, 16))}${d.live ? "" : ", 장 마감 뒤"})</p>
    <p class="cha-line"><b>전일 종가 대비</b> ${chg}${isNum(L.prev_close) ? ` · 전일 종가 ${fmt(L.prev_close, dg)}` : ""}</p>
    <p class="cha-line"><b>오늘</b> 시 ${fmt(L.open, dg)} · 고 ${fmt(L.high, dg)} · 저 ${fmt(L.low, dg)}</p>
    <p class="cha-line"><b>거래량</b> ${big(L.volume, "")} <span class="meta m0">(1분봉 합계라 거래소 집계와 다를 수 있음)</span></p>
    <div class="meta">${esc(d.note)}</div>`;
  const tail = bars.slice(-30).reverse();
  $("#cha-twin").innerHTML = vizTable([{ label: "시각", cls: "l" }, { label: "시" }, { label: "고" }, { label: "저" }, { label: "종" }, { label: "거래량" }],
    tail.map((b) => `<tr><td class="l">${esc(b.time.slice(11, 16))}</td><td class="num">${fmt(b.open, dg)}</td><td class="num">${fmt(b.high, dg)}</td><td class="num">${fmt(b.low, dg)}</td><td class="num">${fmt(b.close, dg)}</td><td class="num">${big(b.volume, "")}</td></tr>`),
    "최근 30개 1분봉, 최신이 위입니다.");
}
function chaDrawMinute() {
  const d = cha.data, cv = $("#cha-price");
  if (!d || !cv || !cv.isConnected || !d.bars.length) return;
  const phone = isPhone(), narrow = !phone && isNarrow(), bars = d.bars, n = bars.length, padR = 58, slots = d.slots || n;
  $("#cha-stack").hidden = false;
  const P = setupCanvas(cv, phone ? 300 : narrow ? 360 : 400), V = setupCanvas($("#cha-vol"), phone ? 70 : narrow ? 80 : 90);
  const pw = P.w - padR, bw = pw / slots, x = (m) => m * bw + bw / 2, xi = (i) => x(bars[i].m);
  cha.x = { bw, pw, n };
  const T = vizTokens(), grid = T.grid, muted = T.tick, up = T.up, dn = T.down, ink = T.ink, ctx = P.ctx, dg = isKR() ? 0 : 2;
  const prev = d.last && isNum(d.last.prev_close) ? d.last.prev_close : null;
  let lo = Infinity, hi = -Infinity;
  bars.forEach((b) => [b.low, b.high, b.close].forEach((v) => { if (isNum(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
  if (prev !== null) { lo = Math.min(lo, prev); hi = Math.max(hi, prev); }
  const pad = (hi - lo) * 0.05 || Math.abs(hi) * 0.002 || 1; lo -= pad; hi += pad;
  const ph = P.h - 22, py = (v) => 6 + (1 - (v - lo) / (hi - lo)) * (ph - 6);
  const nt = niceTicks(lo, hi);
  chaGrid(ctx, pw, lo, hi, py, grid, muted, (v) => tickLabel(v, nt.digits), 4, nt.ticks);
  chaClock(ctx, d, x, P.h - 14, muted);
  if (prev !== null) { ctx.save(); ctx.strokeStyle = muted; ctx.setLineDash([4, 3]); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, py(prev)); ctx.lineTo(pw, py(prev)); ctx.stroke(); ctx.restore(); }
  if (cha.type === "line" || bw < 2.2) {
    ctx.strokeStyle = ink; ctx.lineWidth = 1.4; ctx.beginPath(); bars.forEach((b, i) => (i ? ctx.lineTo(xi(i), py(b.close)) : ctx.moveTo(xi(i), py(b.close)))); ctx.stroke();
  } else bars.forEach((b, i) => {
    const o = isNum(b.open) ? b.open : b.close, col = b.close >= o ? up : dn, hv = isNum(b.high) ? b.high : Math.max(o, b.close), lv = isNum(b.low) ? b.low : Math.min(o, b.close);
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(xi(i), py(hv)); ctx.lineTo(xi(i), py(lv)); ctx.stroke();
    if (cha.type === "candle") ctx.fillRect(xi(i) - bw * 0.35, py(Math.max(o, b.close)), Math.max(1, bw * 0.7), Math.max(1, Math.abs(py(o) - py(b.close))));
    else { ctx.beginPath(); ctx.moveTo(xi(i) - bw * 0.4, py(o)); ctx.lineTo(xi(i), py(o)); ctx.moveTo(xi(i), py(b.close)); ctx.lineTo(xi(i) + bw * 0.4, py(b.close)); ctx.stroke(); }
  });
  const L = bars[n - 1];
  vizEndTags(ctx, [{ y: py(L.close), color: ink, label: tickLabel(L.close, Math.max(nt.digits, dg)), dot: [xi(n - 1), py(L.close)] }], pw + 4, 12, ph - 6, { box: true, T });
  let vmax = 0; bars.forEach((b) => { if (isNum(b.volume)) vmax = Math.max(vmax, b.volume); });
  const vt = niceTicks(0, vmax || 1, 2), vtop = Math.max(vmax || 1, vt.ticks[vt.ticks.length - 1] || 0), vy = (v) => V.h - 2 - (v / vtop) * (V.h - 8);
  chaGrid(V.ctx, pw, 0, vtop, vy, grid, muted, (v) => big(v, ""), 2, vt.ticks.filter((v) => v > 0));
  bars.forEach((b) => { if (!isNum(b.volume)) return; const o = isNum(b.open) ? b.open : b.close; V.ctx.fillStyle = b.close >= o ? up : dn; V.ctx.globalAlpha = 0.5;
    V.ctx.fillRect(b.m * bw + bw * 0.1, vy(b.volume), Math.max(1, bw * 0.8), V.h - 2 - vy(b.volume)); V.ctx.globalAlpha = 1; });
  cv.setAttribute("aria-label", `${chaName(chaTicker())} ${d.session} 1분봉: 마지막 ${L.time.slice(11, 16)} ${tickLabel(L.close, dg)}${prev !== null ? `, 전일 종가 ${tickLabel(prev, dg)}` : ""}. ${d.note}`);
  const box = $("#cha-stack");
  vizHover(box, { host: box, count: n, xOf: xi,
    indexAt: (px) => { if (px > pw) return -1; const m = Math.floor(px / bw); let k = 0; for (let i = 1; i < n; i++) if (Math.abs(bars[i].m - m) < Math.abs(bars[k].m - m)) k = i; return k; },
    yTag: (i) => ({ x: pw + 2, y: py(bars[i].close), text: tickLabel(bars[i].close, Math.max(nt.digits, dg)) }),
    html: (i) => { const b = bars[i]; return `<b>${esc(b.time.slice(11, 16))}</b><br>시 ${fmt(b.open, dg)} 고 ${fmt(b.high, dg)} 저 ${fmt(b.low, dg)} 종 ${fmt(b.close, dg)}<br>거래량 ${big(b.volume, "")}`; } });
}
// The session's hour marks under the minute chart (10:00, 11:00, ...).
function chaClock(ctx, d, x, yy, color) {
  const [h0, m0] = d.open_hm || [9, 30], start = h0 * 60 + m0;
  ctx.save(); ctx.textBaseline = "top"; ctx.textAlign = "center"; ctx.fillStyle = color; ctx.font = vizFont(11);
  for (let m = (60 - (start % 60)) % 60; m < d.slots; m += 60) if (m > 10 && m < d.slots - 10) ctx.fillText(`${String(Math.floor((start + m) / 60)).padStart(2, "0")}:${String((start + m) % 60).padStart(2, "0")}`, x(m), yy);
  ctx.restore();
}
RENDER.chart = renderChart;
