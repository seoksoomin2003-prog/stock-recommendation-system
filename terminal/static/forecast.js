// Forecast layer FC-1 on screen.  It shows stored records only: no range is computed here, every figure is about one stock,
// and none of them enters a score, a rank, a limit or an order plan.  Rules: reports/QSF_FORECAST_PROTOCOL.md.
const FC_HORIZONS = ["5", "20"];
const FC_THIRD = ["낮은", "중간", "높은"];
const FC_WHERE = ["50% 범위 폭 안쪽", "50% 범위 밖 · 80% 범위 안", "80% 범위 밖"];
const FC_PART = { all: "전체", early: "전반", late: "후반" };
const fcPct = (v, d = 1) => (isNum(v) ? (v * 100).toFixed(d) + "%" : DASH);
const fcSigned = (v, d = 1) => (isNum(v) ? (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%" : DASH);
const fcBand = (b) => `${(b[0] * 100).toFixed(0)}~${(b[1] * 100).toFixed(0)}%`;
const fcParts = (c) => (c ? ["all", "early", "late"].map((k) => fcPct(c[k])).join(" / ") : DASH);

// The verdict never stands alone: the badge says which check, the line beside it says what was measured.
function fcTestBadge(t) {
  if (!t) return '<span class="badge STALE">과거 점검 없음</span>';
  return t.verdict === "RANGE_CALIBRATED" ? '<span class="badge REAL">과거 점검 통과</span>' : '<span class="badge UNAVAILABLE">과거 점검 미달</span>';
}
function fcTestReason(t, bands) {
  if (!t) return "과거 점검 결과 파일이 없습니다. 범위가 맞는지 확인되지 않은 상태입니다.";
  const span = `${esc((t.first || "").slice(0, 4))}~${esc((t.last || "").slice(0, 4))}, 평가일 ${t.days}개`;
  if (!t.failed.length) return `과거 점검(${span}): 80% 범위는 ${fcBand(bands["80"])}, 50% 범위는 ${fcBand(bands["50"])} 띠 안에 전체·전반·후반이 모두 들었습니다(12개 조건 충족).`;
  return `과거 점검(${span}) 미달 항목: ` + t.failed.map((x) => `${x.horizon}거래일 ${x.level}% 범위 ${FC_PART[x.part] || esc(x.part)} ${fcPct(x.value)}(띠 ${fcBand(x.band)})`).join(", ") + ".";
}

// ------------------------------------------------------------------ one stock: its ranges as prices
// Stop and target come from the swing card.  They are placed by their distance from the card's own price, so a card one
// session newer than the record still compares like with like.
function fcLevels(cards) {
  const c = cards && cards.SWING, h = c && c.holding;
  if (!c || !h || !isNum(c.price) || c.price <= 0) return [];
  return [["손절 기준", h.stop, "fc-stop"], ["목표 기준", h.target, "fc-target"]].filter((x) => isNum(x[1]) && x[1] > 0)
    .map(([name, v, cls]) => ({ name, v, cls, log: Math.log(v / c.price), pct: v / c.price - 1 }));
}
function fcStrip(d, levels) {
  const hs = FC_HORIZONS.filter((h) => d.ranges[h]);
  if (!hs.length) return "";
  const span = Math.max(...hs.map((h) => d.ranges[h].log_half80), ...levels.map((l) => Math.abs(l.log))) * 1.12;
  const x = (lg) => 50 + (lg / span) * 50;
  const marks = levels.map((l) => `<i class="fc-mark ${l.cls}" style="left:${x(l.log).toFixed(2)}%"></i>`).join("");
  const rows = hs.map((h) => { const r = d.ranges[h];
    return `<div class="fc-row"><span class="fc-lab">${h}거래일 뒤</span><div class="fc-track">
      <i class="fc-b80" style="left:${x(-r.log_half80).toFixed(2)}%;width:${(x(r.log_half80) - x(-r.log_half80)).toFixed(2)}%"></i>
      <i class="fc-b50" style="left:${x(-r.log_half50).toFixed(2)}%;width:${(x(r.log_half50) - x(-r.log_half50)).toFixed(2)}%"></i>
      <i class="fc-mid"></i>${marks}</div></div>`; }).join("");
  const tags = levels.map((l) => `<span class="fc-tag" style="left:${Math.max(6, Math.min(94, x(l.log))).toFixed(2)}%">${l.name.slice(0, 2)}</span>`).join("");
  const label = hs.map((h) => `${h}거래일 뒤 80% 범위 ${fcSigned(-d.ranges[h].half_width80 / (1 + d.ranges[h].half_width80))}에서 ${fcSigned(d.ranges[h].half_width80)}`).join(", ");
  return `<div class="fc-strip" role="img" aria-label="${label}">
    ${levels.length ? `<div class="fc-row"><span class="fc-lab"></span><div class="fc-tags">${tags}</div></div>` : ""}
    ${rows}
    <div class="fc-row"><span class="fc-lab"></span><div class="fc-axis"><span>${fcSigned(Math.exp(-span) - 1, 0)}</span><span>기준 종가</span><span>${fcSigned(Math.exp(span) - 1, 0)}</span></div></div>
    <div class="fc-legend"><span><i class="fc-key fc-b50"></i>50% 범위</span><span><i class="fc-key fc-b80"></i>80% 범위</span>${levels.map((l) => `<span><i class="fc-key fc-line ${l.cls}"></i>스윙 ${l.name}</span>`).join("")}</div></div>`;
}
function fcLevelLines(d, levels) {
  const hs = FC_HORIZONS.filter((h) => d.ranges[h]);
  if (!levels.length || !hs.length) return "";
  const where = (l, h) => { const r = d.ranges[h], a = Math.abs(l.log); return a <= r.log_half50 ? 0 : a <= r.log_half80 ? 1 : 2; };
  const rows = levels.map((l) => `<tr><td class="l"><b>스윙 ${l.name}</b></td><td class="num">${qsfPrice(l.v, d.market)}</td><td class="num">${fcSigned(l.pct)}</td>${hs.map((h) => `<td class="l">${FC_WHERE[where(l, h)]}</td>`).join("")}</tr>`).join("");
  return `<div class="tbl-wrap"><table class="fc-table"><thead><tr><th class="l">스윙 카드의 기준</th><th>가격</th><th title="카드의 조회 시세 대비 거리">시세 대비</th>${hs.map((h) => `<th class="l">${h}거래일 범위에서</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
    <div class="meta">읽는 법(위·아래를 합친 크기 기준): '50% 범위 폭 안쪽'이면 그 거래일 수 뒤 종가가 이 거리보다 멀리 가 있을 경우가 절반을 넘고, '80% 범위 밖'이면 다섯 번에 한 번보다 적습니다. ${esc(d.path_note || "")} 손절·목표 기준과 주문 계획은 이 범위로 바뀌지 않습니다.</div>`;
}
function fcDirection(d) {
  const rows = Object.entries(d.direction || {}).filter(([, v]) => v).map(([s, v]) => `<li><b>${QSF_STRAT[s]} 점수 (${v.horizon}거래일)</b>:
    기대 초과 수익 ${fcSigned(v.alpha, 2)} · 대상 절반을 이길 확률 ${fcPct(v.p, 0)}. ${esc(v.reason)}
    <span class="meta" style="margin:0">가정(설명력 ${d.ic_assumed}이 있다면): ${fcSigned(v.alpha_assumed, 2)}, ${fcPct(v.p_assumed)} · 표준화 점수 ${isNum(v.z) ? (v.z > 0 ? "+" : "") + v.z.toFixed(2) : "없음"}. 가정이며 예측이 아닙니다.</span></li>`).join("");
  return rows ? `<details class="fc-fold"><summary>방향 쪽 숫자: 근거 기준으로 초과 수익 0, 확률 50%</summary><ul class="qsf-list">${rows}</ul></details>` : "";
}
function fcStockHtml(d, cards) {
  if (!d) return '<div class="empty">가격 범위를 불러오지 못했습니다.</div>';
  if (d.status === "NO_RECORD") return '<div class="meta">아직 기록이 없습니다. 다음 자동 실행에서 처음 기록합니다.</div>';
  if (d.status === "BROKEN") return '<div class="notice">기록 검사(해시 연결)에 실패해 보여 주지 않습니다.</div>';
  if (d.status === "NOT_IN_RECORD") return `<div class="meta">${esc(d.session)} 기록(${d.universe}종목)에 이 종목이 없어 범위가 없습니다. 범위는 그날 스캔에서 점수를 받은 종목만 기록합니다.</div>`;
  if (d.status !== "REAL") return "";
  const hs = FC_HORIZONS.filter((h) => d.ranges[h]);
  const head = `<div class="meta">${fcTestBadge(d.test)} 기준일 <b>${esc(d.session)}</b> 종가 <b>${qsfPrice(d.close, d.market)}</b>. 움직임의 크기이며 오를지 내릴지는 말하지 않습니다.</div>`;
  if (!hs.length) return head + '<div class="meta">가격 이력이 120거래일에 못 미쳐 범위를 내지 않았습니다. 비워 둔 것이며 0이 아닙니다.</div>' + fcDirection(d);
  const levels = fcLevels(cards), t = d.test;
  const cell = (r, key, hw) => `${qsfPrice(r[key][0], d.market)} ~ ${qsfPrice(r[key][1], d.market)} <span class="meta" style="margin:0">(${fcSigned(r[key][0] / d.close - 1)} ~ ${fcSigned(hw)})</span>`;
  const body = hs.map((h) => { const r = d.ranges[h], th = t && t.horizons[h];
    return `<tr><td class="l">${h}거래일 뒤</td><td class="l">${cell(r, "p50", r.half_width50)}</td><td class="l">${cell(r, "p80", r.half_width80)}</td>
      <td class="num">${th ? fcPct(th.cover50.all) : DASH}</td><td class="num">${th ? fcPct(th.cover80.all) : DASH}</td></tr>`; }).join("");
  const r0 = d.ranges[hs[0]], third = r0.vol_third;
  const bias = t ? `과거 점검에서 이 묶음의 80% 범위가 실제로 담은 비율은 ${hs.map((h) => `${fcPct(t.horizons[h].by_vol[d.ranges[h].vol_third])}(${h}거래일)`).join(", ")}입니다${third === 0 ? ": 범위가 조금 좁게 나오는 묶음" : third === 2 ? ": 범위가 조금 넓게 나오는 묶음" : ""}.` : "";
  return `${head}${fcStrip(d, levels)}
    <div class="tbl-wrap"><table class="fc-table"><thead><tr><th class="l">지평</th><th class="l">50% 범위 (종가 대비)</th><th class="l">80% 범위 (종가 대비)</th><th title="과거 점검에서 50% 범위가 실제로 담은 비율">과거 실제 (50%)</th><th title="과거 점검에서 80% 범위가 실제로 담은 비율">과거 실제 (80%)</th></tr></thead><tbody>${body}</tbody></table></div>
    <div class="meta">${fcTestReason(t, d.bands)} 이 종목은 기록일 ${r0.forecast}종목 중 변동성 <b>${FC_THIRD[third]}</b> 3분의 1입니다. ${bias}${t ? ` 시장이 급변한 평가일(${hs.map((h) => fcPct(t.horizons[h].stress_share)).join(", ")})에는 80% 범위가 종목 절반도 담지 못했습니다.` : ""}</div>
    ${fcLevelLines(d, levels)}${fcDirection(d)}`;
}
async function fcStock(box, t, market, cards) {
  if (!box) return;
  const d = await api(`/api/qsf/forecast-stock?t=${encodeURIComponent(t)}&market=${market}`).catch(() => null);
  if (!box.isConnected || !qsfState.detail || qsfState.detail.ticker !== t) return;
  box.innerHTML = fcStockHtml(d, cards);
}

// ------------------------------------------------------------------ tracking card: the stored check and the record so far
function fcTrackHtml(d, market) {
  const title = (b) => `<h2>예측 층 FC-1: 종목별 가격 범위 ${b || ""}</h2>`;
  const how = `<div class="meta">종목마다 5거래일·20거래일 뒤 종가가 들어갈 범위를 매일 적어 고치지 못하게 저장하고, 실제로 그 안에 들어왔는지 채점합니다. 움직임의 크기에 대한 예측이며 오를지 내릴지는 말하지 않습니다. 점수·순위·한도·주문 계획에 쓰이지 않습니다.</div>`;
  if (!d || d.status !== "REAL") return `<div class="panel">${title()}${how}<div class="meta">아직 기록이 없습니다. 다음 자동 실행에서 처음 기록합니다.</div></div>`;
  const t = d.test, f = d.followed || { ranges: {}, direction: {} }, td = d.today, name = market === "KR" ? "한국" : "미국";
  const trow = t ? FC_HORIZONS.filter((h) => t.horizons[h]).map((h) => { const x = t.horizons[h];
    return `<tr><td class="l">${h}거래일</td><td class="num">${fcParts(x.cover80)}</td><td class="num">${fcParts(x.cover50)}</td><td class="num">${x.by_vol.map((v) => fcPct(v)).join(" / ")}</td><td class="num">${fcPct(x.stress_share)}</td></tr>`; }).join("") : "";
  const rrow = FC_HORIZONS.map((h) => { const x = f.ranges[h] || {}, w = td && td.half_width[h], th = t && t.horizons[h], rd = x.reading;
    return `<tr><td class="l">${h}거래일</td><td class="num">${w ? "±" + fcPct(w.p80_median) : DASH}</td><td class="num">${th ? "±" + fcPct(th.half_width) : DASH}</td>
      <td class="num">${x.matured || 0} / ${d.read_at}</td><td class="num">${x.matured ? fcPct(x.cover80) : '<span class="missing">아직 없음</span>'}</td><td class="num">${x.matured ? fcPct(x.cover50) : '<span class="missing">아직 없음</span>'}</td>
      <td class="l">${rd ? `${rd.verdict === "RANGE_CALIBRATED" ? "띠 안" : "띠 밖"} (80%: ${fcParts(rd.cover80)}, 50%: ${fcParts(rd.cover50)})` : `끝난 기록일 ${d.read_at}개에서 한 번 읽음`}</td></tr>`; }).join("");
  const drow = Object.entries(d.direction_horizons).map(([s, h]) => { const x = f.direction[s] || {};
    return `<tr><td class="l">${QSF_STRAT[s]} (${h}거래일)</td><td class="num">${d.ic_evidence[s]}</td><td class="l" style="white-space:normal">${esc(d.ic_reason[s])}</td><td class="num">${x.matured || 0}</td>
      <td class="num">${x.matured ? [x.high, x.middle, x.low].map((v) => fcPct(v, 0)).join(" / ") : '<span class="missing">아직 없음</span>'}</td>
      <td class="num">${x.matured ? `${qsfNum(x.brier_assumed, 4)} / ${qsfNum(x.brier_half, 4)}` : '<span class="missing">아직 없음</span>'}</td></tr>`; }).join("");
  return `<div class="panel">${title(fcTestBadge(t))}${how}
    ${d.integrity !== "OK" ? '<div class="notice">기록 검사(해시 연결)에 실패했습니다. 아래 기록 수치를 믿지 마세요.</div>' : ""}
    <h3>과거 점검 (${name}, 한 번 실행)</h3>
    <div class="meta">${fcTestReason(t, d.bands)}</div>
    ${t ? `<div class="tbl-wrap"><table><thead><tr><th class="l">지평</th><th title="80% 범위가 실제로 담은 비율">80% 범위: 전체 / 전반 / 후반</th><th title="50% 범위가 실제로 담은 비율">50% 범위: 전체 / 전반 / 후반</th>
      <th title="그날 변동성이 낮은, 중간, 높은 3분의 1에서 80% 범위가 담은 비율">변동성 낮음 / 중간 / 높음</th><th title="80% 범위가 종목 절반도 담지 못한 평가일의 비율">한꺼번에 틀린 날</th></tr></thead><tbody>${trow}</tbody></table></div>
    <div class="meta">조용한 종목은 범위가 조금 좁고 요동치는 종목은 조금 넓게 나옵니다. 띠 안이지만 한쪽으로 치우친 오차이며 이 판에서는 고치지 않았습니다.</div>` : ""}
    <h3>앞으로의 기록 <span class="meta" style="margin:0">${esc(d.record.first || "")} ~ ${esc(d.record.last || "")} · 기록일 ${d.record.sessions}개${td ? ` · 최근 ${td.forecast} / ${td.universe}종목에 범위` : ""}</span></h3>
    <div class="tbl-wrap"><table><thead><tr><th class="l">지평</th><th title="최근 기록일 80% 범위 폭의 중간값">지금 80% 범위 폭</th><th title="과거 점검 구간의 중간값">과거 중간값</th><th title="지평이 끝나 채점할 수 있는 기록일">끝난 기록일</th><th>실제 포함률 (80%)</th><th>실제 포함률 (50%)</th><th class="l">판정</th></tr></thead><tbody>${rrow}</tbody></table></div>
    <div class="meta">지평이 끝난 날부터 포함률이 쌓입니다. 그 전의 수치는 판정이 아니며 어떤 점수에도 쓰지 않습니다.</div>
    <h3>방향 쪽 숫자 <span class="meta" style="margin:0">기록만 하고 판정하지 않음</span></h3>
    <div class="tbl-wrap"><table><thead><tr><th class="l">점수</th><th title="과거 시험이 기준을 통과했을 때만 0이 아닙니다">근거 기준 설명력</th><th class="l">0인 이유</th><th>끝난 기록일</th><th title="표준화 점수가 +1 이상, 사이, −1 이하인 종목이 대상 절반을 이긴 비율">점수 높음 / 중간 / 낮음이 이긴 비율</th><th title="낮을수록 좋습니다. 늘 50%라고 말하면 0.25입니다">확률 오차: 가정 / 50%</th></tr></thead><tbody>${drow}</tbody></table></div>
    <div class="meta">설명력이 0이면 기대 초과 수익은 0, 대상 절반을 이길 확률은 50%입니다. 함께 적는 가정 값(설명력 ${d.ic_assumed})은 "약한 설명력이 있다면"의 숫자이며 예측이 아닙니다. 이 표는 라이브 전향 평가가 기준을 통과했을 때만 바뀝니다.</div>
    <details class="fc-fold"><summary>알려진 한계 ${d.limits.length}가지</summary><ul class="qsf-list">${d.limits.map((x) => `<li>${esc(x)}</li>`).join("")}<li>${esc(d.path_note)}</li></ul></details>
    <div class="meta">규칙: <code>${esc(d.protocol)}</code></div></div>`;
}
async function fcTrack() {
  const box = $("#qsffcast"); if (!box) return;
  const market = qsfState.market;
  const d = await api(`/api/qsf/forecast?market=${market}`).catch(() => null);
  if (market !== qsfState.market || !box.isConnected) return;
  box.innerHTML = fcTrackHtml(d, market);
}
