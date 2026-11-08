// 업종 순환 그래프(RRG 근사): 업종 ETF의 지수 대비 상대강도(가로)와 그 모멘텀(세로), 최근 8주 꼬리.  읽기 전용.
"use strict";
const RRG_Q = { LEADING: ["선도", "--s3"], WEAKENING: ["약화", "--s4"], LAGGING: ["침체", "--s8"], IMPROVING: ["개선", "--s1"] };
const rrg = { data: null, heads: [] };

async function renderRotation(box) {
  box.innerHTML = `<div class="panel"><h2>업종 순환 그래프</h2><canvas id="rrg-cv" class="chart" aria-label="업종 순환 그래프"></canvas>
    <div class="legend" id="rrg-legend"></div><div id="rrg-meta">${loading}</div></div>
    <div class="panel"><h2>업종 상대 성과 <span class="meta" style="margin:0">업종을 누르면 점수 상위 종목이 나옵니다</span></h2><div id="rrg-table"></div></div>
    <div class="panel" id="rrg-picks" hidden></div>`;
  const want = state.market;
  try {
    const d = await api(mq("/api/rotation"));
    if (want !== state.market) return;
    rrg.data = d; rrgDraw(); redrawers.add(rrgDraw); rrgTable(d);
    $("#rrg-meta").innerHTML = d.status === "REAL"
      ? meta(d.source, d.fetched_at, `기준 지수 ${esc(d.benchmark)} · 마지막 주 ${esc(d.as_of)} · ${esc(d.method)}${d.missing.length ? ` · 가격 없음: ${esc(d.missing.join(", "))}` : ""}`)
      : `<div class="empty">${badge("UNAVAILABLE")} 업종 가격을 받지 못했습니다.</div>`;
  } catch (e) { $("#rrg-meta").innerHTML = errBox(e); }
}
function rrgDraw() {
  const cv = $("#rrg-cv"), d = rrg.data;
  if (!cv || !cv.isConnected || !d || d.status !== "REAL") return;
  const size = Math.min(cv.parentElement.clientWidth, 640), { ctx, w, h } = setupCanvas(cv, window.innerWidth < 600 ? size : Math.min(560, size));
  let span = 2;
  d.funds.forEach((f) => f.tail.forEach((p) => { span = Math.max(span, Math.abs(p.ratio - 100), Math.abs(p.momentum - 100)); }));
  span *= 1.12;
  const pad = 28, x = (v) => pad + ((v - (100 - span)) / (2 * span)) * (w - 2 * pad), y = (v) => h - pad - ((v - (100 - span)) / (2 * span)) * (h - 2 * pad);
  const muted = cssVar("--muted"), ink = cssVar("--ink"), grid = cssVar("--grid"), panel = cssVar("--panel");
  ctx.fillStyle = panel; ctx.fillRect(0, 0, w, h);
  // quadrants: faint fill of each quadrant's colour, its name in a corner
  const cx = x(100), cy = y(100);
  [["IMPROVING", pad, pad, cx - pad, cy - pad], ["LEADING", cx, pad, w - pad - cx, cy - pad], ["LAGGING", pad, cy, cx - pad, h - pad - cy], ["WEAKENING", cx, cy, w - pad - cx, h - pad - cy]].forEach(([q, qx, qy, qw, qh]) => {
    ctx.globalAlpha = 0.07; ctx.fillStyle = cssVar(RRG_Q[q][1]); ctx.fillRect(qx, qy, qw, qh); ctx.globalAlpha = 1;
    ctx.fillStyle = muted; ctx.font = "600 12px -apple-system, sans-serif"; ctx.textBaseline = "top";
    ctx.textAlign = qx === pad ? "left" : "right"; ctx.fillText(RRG_Q[q][0], qx === pad ? qx + 6 : qx + qw - 6, qy === pad ? qy + 6 : qy + qh - 20);
  });
  ctx.textAlign = "left";
  ctx.strokeStyle = grid; ctx.lineWidth = 1; ctx.strokeRect(pad, pad, w - 2 * pad, h - 2 * pad);
  ctx.strokeStyle = muted; ctx.beginPath(); ctx.moveTo(cx, pad); ctx.lineTo(cx, h - pad); ctx.moveTo(pad, cy); ctx.lineTo(w - pad, cy); ctx.stroke();
  ctx.fillStyle = muted; ctx.font = "11px -apple-system, sans-serif"; ctx.textBaseline = "middle";
  ctx.textAlign = "center"; ctx.fillText("상대강도 비율 →", w / 2, h - 10);
  ctx.save(); ctx.translate(10, h / 2); ctx.rotate(-Math.PI / 2); ctx.fillText("모멘텀 →", 0, 0); ctx.restore(); ctx.textAlign = "left";
  rrg.heads = [];
  d.funds.forEach((f) => {
    ctx.strokeStyle = muted; ctx.lineWidth = 1.5; ctx.globalAlpha = 0.6; ctx.beginPath();
    f.tail.forEach((p, i) => (i ? ctx.lineTo(x(p.ratio), y(p.momentum)) : ctx.moveTo(x(p.ratio), y(p.momentum))));
    ctx.stroke(); ctx.globalAlpha = 1;
    f.tail.slice(0, -1).forEach((p) => { ctx.fillStyle = muted; ctx.beginPath(); ctx.arc(x(p.ratio), y(p.momentum), 2, 0, 7); ctx.fill(); });
    const last = f.tail[f.tail.length - 1], hx = x(last.ratio), hy = y(last.momentum);
    ctx.fillStyle = cssVar(RRG_Q[f.quadrant][1]); ctx.strokeStyle = panel; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(hx, hy, 5, 0, 7); ctx.fill(); ctx.stroke();
    rrg.heads.push({ f, hx, hy });
  });
  // names beside the dots, moved down a line while they would overlap a name already placed
  ctx.fillStyle = ink; ctx.font = "11px -apple-system, sans-serif";
  const placed = [];
  [...rrg.heads].sort((a, b) => a.hy - b.hy).forEach(({ f, hx, hy }) => {
    const tw = ctx.measureText(f.name).width, lx = hx + 8 > w - pad - tw ? hx - 8 - tw : hx + 8;
    let ly = hy;
    while (placed.some((q) => lx < q.x + q.w + 2 && q.x < lx + tw + 2 && Math.abs(q.y - ly) < 12)) ly += 12;
    placed.push({ x: lx, y: ly, w: tw });
    if (ly !== hy) { ctx.strokeStyle = muted; ctx.lineWidth = 0.8; ctx.beginPath(); ctx.moveTo(hx, hy); ctx.lineTo(lx + (lx > hx ? 0 : tw), ly); ctx.stroke(); }
    ctx.fillText(f.name, lx, ly);
  });
  $("#rrg-legend").innerHTML = Object.values(RRG_Q).map(([n, v]) => `<span><span class="swatch" style="background:${cssVar(v)};border-radius:50%"></span>${n}</span>`).join("")
    + "<span>· 회색 선은 최근 8주의 이동 경로, 점이 이번 주입니다. 보통 개선 → 선도 → 약화 → 침체 순으로 돕니다.</span>";
  cv.onmousemove = (e) => {
    const b = cv.getBoundingClientRect(), mx = e.clientX - b.left, my = e.clientY - b.top, tip = $("#tip");
    const hit = rrg.heads.find((q) => Math.hypot(q.hx - mx, q.hy - my) < 10);
    if (!hit) { tip.hidden = true; return; }
    const f = hit.f, p = f.tail[f.tail.length - 1]; tip.hidden = false;
    tip.innerHTML = `<b>${esc(f.name)}</b> ${esc(f.symbol.replace(".KS", ""))}<br>${RRG_Q[f.quadrant][0]} · 비율 ${fmt(p.ratio, 1)} · 모멘텀 ${fmt(p.momentum, 1)}<br>
      지수 대비 4주 ${pct(isNum(f.relative["4w"]) ? f.relative["4w"] * 100 : null, 1)} · 13주 ${pct(isNum(f.relative["13w"]) ? f.relative["13w"] * 100 : null, 1)}`;
    const tx = e.clientX + 14 + tip.offsetWidth > window.innerWidth ? e.clientX - tip.offsetWidth - 14 : e.clientX + 14;
    tip.style.left = tx + "px"; tip.style.top = e.clientY + 14 + "px";
  };
  cv.onmouseleave = () => ($("#tip").hidden = true);
  cv.onclick = (e) => {
    const b = cv.getBoundingClientRect(), hit = rrg.heads.find((q) => Math.hypot(q.hx - (e.clientX - b.left), q.hy - (e.clientY - b.top)) < 10);
    if (hit) { $("#tip").hidden = true; loadSectorPicks(hit.f); }
  };
}
function rrgTable(d) {
  if (d.status !== "REAL") { $("#rrg-table").innerHTML = ""; return; }
  const order = { LEADING: 0, IMPROVING: 1, WEAKENING: 2, LAGGING: 3 };
  const rows = [...d.funds].sort((a, b) => order[a.quadrant] - order[b.quadrant] || b.tail[b.tail.length - 1].ratio - a.tail[a.tail.length - 1].ratio);
  $("#rrg-table").innerHTML = `<div class="tbl-wrap"><table><thead><tr><th class="l">업종</th><th class="l">국면</th><th>상대강도 비율</th><th>모멘텀</th><th>지수 대비 4주</th><th>지수 대비 13주</th></tr></thead><tbody>
    ${rows.map((f) => { const p = f.tail[f.tail.length - 1]; return `<tr class="click${rrg.sel === f.symbol ? " me" : ""}" data-fund="${esc(f.symbol)}"><td class="l">${esc(f.name)} <span class="meta" style="margin:0">${esc(f.symbol.replace(".KS", ""))}</span></td>
      <td class="l"><span class="swatch" style="background:${cssVar(RRG_Q[f.quadrant][1])};border-radius:50%"></span>${RRG_Q[f.quadrant][0]}</td><td class="num">${fmt(p.ratio, 1)}</td><td class="num">${fmt(p.momentum, 1)}</td>
      <td class="num">${pct(isNum(f.relative["4w"]) ? f.relative["4w"] * 100 : null, 1)}</td><td class="num">${pct(isNum(f.relative["13w"]) ? f.relative["13w"] * 100 : null, 1)}</td></tr>`; }).join("")}</tbody></table></div>
    <div class="meta">업종 ETF의 가격 흐름을 지수와 비교한 것입니다. QSF 점수에 쓰이지 않으며, 검증된 매매 신호가 아닙니다.</div>`;
  $("#rrg-table").querySelectorAll("tr[data-fund]").forEach((tr) => (tr.onclick = () => loadSectorPicks(d.funds.find((f) => f.symbol === tr.dataset.fund))));
}
