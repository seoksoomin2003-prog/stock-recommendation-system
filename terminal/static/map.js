// 시장 지도 탭: 업종별 히트맵(크기 = 시가총액, 색 = 등락 또는 점수).  읽기 전용.
"use strict";
const heat = { mode: "1d", strategy: "SWING", palette: "std", data: null, rects: [] };
try { const v = JSON.parse(localStorage.getItem("qse-heat-view") || "null"); if (v && v.mode) Object.assign(heat, { mode: v.mode, strategy: v.strategy || "SWING", palette: v.palette === "cb" ? "cb" : "std" }); } catch (e) { /* default view */ }
// 색각 친화 색 (6차 묶음 P3-7, 사용자 결정 2026-11-24): 오르면 파랑, 내리면 주황.  빨강·초록을 구별하기 어려운 사람도 읽습니다.
const HEAT_CB = { up: { light: "#1f5fd1", dark: "#5b9cff" }, down: { light: "#b35900", dark: "#f0a531" } };
function heatSide(up, dark) { return heat.palette === "cb" ? HEAT_CB[up ? "up" : "down"][dark ? "dark" : "light"] : cssVar(up ? "--up" : "--down"); }
const HEAT_MODES = { "1d": ["1일", 0.03], "5d": ["5일", 0.08], "1m": ["1개월", 0.15], score: ["QSF 점수", null] };

// Squarified treemap (Bruls et al.): rows of tiles kept close to square.  Items need .value > 0; returns {item, x, y, w, h}.
function squarify(items, x, y, w, h) {
  const out = [], total = items.reduce((s, i) => s + i.value, 0);
  if (!total || w <= 0 || h <= 0) return out;
  const scale = (w * h) / total, rest = items.map((i) => ({ item: i, area: i.value * scale })).sort((a, b) => b.area - a.area);
  let row = [], X = x, Y = y, W = w, H = h;
  const worst = (r, side) => { const s = r.reduce((a, b) => a + b.area, 0), mx = Math.max(...r.map((a) => a.area)), mn = Math.min(...r.map((a) => a.area)); return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn)); };
  const lay = (r) => {
    const s = r.reduce((a, b) => a + b.area, 0);
    if (W >= H) { const cw = s / H; let yy = Y; r.forEach((a) => { const ch = a.area / cw; out.push({ item: a.item, x: X, y: yy, w: cw, h: ch }); yy += ch; }); X += cw; W -= cw; }
    else { const ch = s / W; let xx = X; r.forEach((a) => { const cw = a.area / ch; out.push({ item: a.item, x: xx, y: Y, w: cw, h: ch }); xx += cw; }); Y += ch; H -= ch; }
  };
  while (rest.length) {
    const side = Math.min(W, H), next = rest[0];
    if (!row.length || worst([...row, next], side) <= worst(row, side)) { row.push(rest.shift()); }
    else { lay(row); row = []; }
  }
  if (row.length) lay(row);
  return out;
}
function rgbOf(c) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(c.trim());
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [128, 128, 128];
}
const mixRgb = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
const lumOf = ([r, g, b]) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
// Which theme is showing (the colour-blind pair has a shade per theme).  Read from the page's theme mark, not from a colour.
const heatDark = () => document.documentElement.dataset.theme === "dark";
// Score mode is one neutral ramp (stage 2, visualization spec section 8 item 8): blue is the falling colour on Korean screens.
function heatColor(it, T = vizTokens()) {
  const dark = heatDark(), mid = rgbOf(T.heatMid);
  if (heat.mode === "score") {
    if (!isNum(it.score)) return null;
    const t = Math.min(1, Math.max(0, (it.score - 40) / 40));                                 // 40 or lower at one end, 80 or higher at the other
    return mixRgb(rgbOf(T.heatLo), rgbOf(T.heatHi), t);
  }
  const v = it.change[heat.mode];
  if (!isNum(v)) return null;
  const t = Math.min(1, Math.abs(v) / HEAT_MODES[heat.mode][1]);
  return mixRgb(mid, rgbOf(heatSide(v >= 0, dark)), t);
}

// 등락 보기에서는 스윙·장기 점수 단추를 쓰지 않으므로 흐리게 두고 이유를 적습니다 (P3-7).  색 선택은 점수 보기에서 쓰지 않습니다.
function heatIdle() {
  const st = $("#heat-strat"), pal = $("#heat-pal"), score = heat.mode === "score";
  if (st) { st.classList.toggle("idle", !score); st.title = score ? "" : "등락 보기에서는 쓰지 않습니다. 점수 보기를 고르면 이 점수로 칠합니다."; }
  if (pal) pal.classList.toggle("idle", score);
}
async function renderMap() {
  state.loaded.map = true;
  const el = $("#tab-map");
  el.innerHTML = `<div class="panel"><h2>시장 히트맵 <span class="seg" id="heat-mode">${Object.entries(HEAT_MODES).map(([k, [n]]) => `<button data-k="${k}" class="${k === heat.mode ? "on" : ""}">${n}</button>`).join("")}</span>
      <span class="seg" id="heat-strat">${[["SWING", "스윙"], ["LONG_TERM", "장기"]].map(([k, n]) => `<button data-k="${k}" class="${k === heat.strategy ? "on" : ""}">${n} 점수</button>`).join("")}</span>
      <span class="seg" id="heat-pal" title="${isKR() ? "색: 기본은 한국 색(빨강 오름·파랑 내림)이고, 이미 색각 친화입니다. 파랑·주황은 미국 화면용 색이라 여기서 고르면 파랑이 오름을 뜻합니다." : "색: 기본은 시장의 상승·하락 색, 파랑·주황은 색각 친화 색입니다"}">${[["std", "기본 색"], ["cb", "파랑·주황"]].map(([k, n]) => `<button data-k="${k}" class="${k === heat.palette ? "on" : ""}">${n}</button>`).join("")}</span></h2>
    <canvas id="heat-cv" class="chart" aria-label="시장 히트맵"></canvas><div class="legend" id="heat-legend"></div><div id="heat-meta">${loading}</div></div>
    <div id="map-more"></div>`;
  const pick = (id, key) => ($(id).onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return; heat[key] = b.dataset.k;
    try { localStorage.setItem("qse-heat-view", JSON.stringify({ mode: heat.mode, strategy: heat.strategy, palette: heat.palette })); } catch (err) { /* not remembered */ }
    $(id).querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    heatIdle();
    key === "strategy" ? loadHeat() : heatDraw();
  });
  pick("#heat-mode", "mode"); pick("#heat-strat", "strategy"); pick("#heat-pal", "palette");
  heatIdle();
  loadHeat();
  if (typeof renderRotation === "function") renderRotation($("#map-more"));
}
async function loadHeat() {
  const want = state.market + heat.strategy;
  try {
    const d = await api(mq(`/api/qsf/heatmap?strategy=${heat.strategy}`));
    if (want !== state.market + heat.strategy) return;
    heat.data = d; heatDraw(); redrawOn("map", "heat", heatDraw);
    $("#heat-meta").innerHTML = d.status === "REAL"
      ? meta(d.source, null, `스캔 거래일 ${esc(d.session)} · ${esc(d.model_version || "")} · ${esc(d.basis)}${d.without_cap.length ? ` · 시가총액 없음: ${esc(d.without_cap.join(", "))}` : ""}`)
      : `<div class="empty">${badge("UNAVAILABLE")} 스캔 결과가 없습니다.</div>`;
  } catch (e) { $("#heat-meta").innerHTML = errBox(e); }
}
function heatDraw() {
  const cv = $("#heat-cv"), d = heat.data;
  if (!cv || !cv.isConnected || !d || d.status !== "REAL") return;
  const H = isPhone() ? 520 : 620, { ctx, w, h } = setupCanvas(cv, H);
  const groups = {};
  d.items.filter((i) => isNum(i.market_cap)).forEach((i) => { const k = i.sector || "업종 없음"; (groups[k] = groups[k] || []).push(i); });
  const sectors = Object.entries(groups).map(([name, its]) => ({ name, its, value: its.reduce((s, i) => s + i.market_cap, 0) }));
  const T = vizTokens(), panel = T.surface, ink = T.ink, muted = T.tick;
  ctx.fillStyle = panel; ctx.fillRect(0, 0, w, h);
  heat.rects = [];
  ctx.font = vizFont(11); ctx.textBaseline = "top";
  squarify(sectors, 0, 0, w, h).forEach((s) => {
    const head = s.h > 40 && s.w > 50 ? 14 : 0;
    if (head) { ctx.fillStyle = muted; ctx.fillText(sectorKo(s.item.name).slice(0, Math.max(3, Math.floor(s.w / 7))), s.x + 3, s.y + 1); }
    squarify(s.item.its.map((i) => ({ ...i, value: i.market_cap })), s.x, s.y + head, s.w, s.h - head).forEach((r) => {
      const col = heatColor(r.item, T);
      ctx.fillStyle = col ? `rgb(${col.join(",")})` : T.missing;
      ctx.fillRect(r.x + 1, r.y + 1, Math.max(0, r.w - 2), Math.max(0, r.h - 2));          // a 2px surface gap between tiles
      if (!col && r.w > 4 && r.h > 4) { ctx.strokeStyle = T.missingEdge; ctx.lineWidth = 1; ctx.strokeRect(r.x + 1.5, r.y + 1.5, r.w - 3, r.h - 3); }   // no value: an empty tile, never a low score or a flat 0%
      heat.rects.push(r);
      if (r.w > 34 && r.h > 18) {
        ctx.fillStyle = col && lumOf(col) < 0.55 ? "#ffffff" : col ? "#14171c" : ink;
        const label = isKR() ? (r.item.name || r.item.ticker) : r.item.ticker;
        ctx.font = vizFont(r.w > 90 && r.h > 40 ? 12 : 10, r.w > 90 && r.h > 40 ? 600 : 400);
        ctx.fillText(label.slice(0, Math.max(2, Math.floor(r.w / (isKR() ? 11 : 7)))), r.x + 4, r.y + 4);
        const v = heat.mode === "score" ? r.item.score : r.item.change[heat.mode];
        if (r.h > 34 && isNum(v)) ctx.fillText(heat.mode === "score" ? v.toFixed(0) : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`, r.x + 4, r.y + 19);
      }
    });
    ctx.strokeStyle = panel; ctx.lineWidth = 2; ctx.strokeRect(s.x, s.y, s.w, s.h);
  });
  const span = HEAT_MODES[heat.mode][1];
  // legend: a gradient key with plain text (stage 2, visualization spec section 8 item 16): no text in a series colour
  const none = '<span><i class="heat-none"></i>테두리만 있는 칸은 값 없음</span>';
  $("#heat-legend").innerHTML = heat.mode === "score"
    ? `<span>타일 크기: 시가총액 · 색: ${heat.strategy === "SWING" ? "스윙" : "장기"} 점수 40 이하<i class="heat-key seq"></i>80 이상</span>${none}`
    : `<span>타일 크기: 시가총액 · 색: ${HEAT_MODES[heat.mode][0]} 등락 −${(span * 100).toFixed(0)}%<i class="heat-key chg" style="--hk-down:${heatSide(false, heatDark())};--hk-up:${heatSide(true, heatDark())}"></i>+${(span * 100).toFixed(0)}% (가운데 회색은 0, 그 너머는 같은 색)</span>${none}`;
  cv.onmousemove = (e) => {
    const b = cv.getBoundingClientRect(), mx = e.clientX - b.left, my = e.clientY - b.top;
    const r = heat.rects.find((q) => mx >= q.x && mx < q.x + q.w && my >= q.y && my < q.y + q.h), tip = $("#tip");
    if (!r) { tip.hidden = true; cv.style.cursor = ""; return; }
    const i = r.item; cv.style.cursor = "pointer"; tip.hidden = false;
    tip.innerHTML = `<b>${esc(i.name || i.ticker)}</b> ${esc(i.ticker)}<br>${esc(sectorKo(i.sector))}<br>시가총액 ${big(i.market_cap, isKR() ? "KRW" : "USD")}<br>
      1일 ${pct(isNum(i.change["1d"]) ? i.change["1d"] * 100 : null, 2)} · 5일 ${pct(isNum(i.change["5d"]) ? i.change["5d"] * 100 : null, 1)} · 1개월 ${pct(isNum(i.change["1m"]) ? i.change["1m"] * 100 : null, 1)}<br>
      ${heat.strategy === "SWING" ? "스윙" : "장기"} 점수 ${fmt(i.score, 1)} · ${esc(i.band_label || "")}`;
    const tx = e.clientX + 14 + tip.offsetWidth > window.innerWidth ? e.clientX - tip.offsetWidth - 14 : e.clientX + 14;
    tip.style.left = tx + "px"; tip.style.top = e.clientY + 14 + "px";
  };
  cv.onmouseleave = () => { $("#tip").hidden = true; };
  cv.onclick = (e) => {
    const b = cv.getBoundingClientRect(), mx = e.clientX - b.left, my = e.clientY - b.top;
    const r = heat.rects.find((q) => mx >= q.x && mx < q.x + q.w && my >= q.y && my < q.y + q.h);
    if (r) { $("#tip").hidden = true; openTicker(r.item.ticker); }
  };
}
RENDER.map = renderMap;
