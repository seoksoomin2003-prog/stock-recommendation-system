// 다섯 투자자 엔진(버핏식·멍거식·그레이엄식·린치식·드러켄밀러식), 통합 투자위원회, 여섯 포트폴리오 (규칙 IC-1).
// 점수 카드에는 그 종목에 대한 다섯 의견과 위원회 판정이 나옵니다. 여섯 포트폴리오는 따로 있는 기능입니다:
// '포트폴리오 받아보기'(종목 카드)나 '여섯 포트폴리오 받아보기'(투자위원회 탭)를 눌렀을 때만 만듭니다.
// 실존 투자자의 의견이 아니라 알려진 원칙을 규칙으로 옮긴 것이고, 점수와 섞지 않으며 주문을 내지 않습니다.
const IC_REC_COLOR = { STRONG_BUY: "var(--up)", BUY: "var(--up)", CONDITIONAL_BUY: "var(--accent)", HOLD: "var(--muted)", WAIT: "var(--warn)", REDUCE: "var(--bad)", SELL: "var(--bad)", AVOID: "var(--bad)", INSUFFICIENT_DATA: "var(--muted)" };
const IC_VIEWS = { dash: "위원회 현황", ports: "여섯 포트폴리오", compare: "투자자 비교", perf: "모의 성과" };
const IC_COND = { buy: "매수", hold: "보유", add: "추가 매수", reduce: "축소", sell: "매도", invalidation: "생각이 틀렸다고 볼 때" };
const icState = { view: "dash", port: "COMMITTEE", ports: {}, market: null };

const icNum = (v, d = 0) => (v === null || v === undefined ? "–" : Number(v).toFixed(d));
const icPct = (v, d = 1) => (v === null || v === undefined ? "–" : (v * 100).toFixed(d) + "%");
const icBadge = (code, label) => `<span class="badge" style="color:${IC_REC_COLOR[code] || "var(--muted)"}">${esc(label || code)}</span>`;
const icList = (xs) => (xs && xs.length ? xs.map((x) => `<div class="meta" style="margin:3px 0">${esc(x)}</div>`).join("") : `<div class="meta" style="margin:3px 0">없음</div>`);
const icMarket = () => (state.market === "KR" ? "KR" : "US");

// ---------------------------------------------------------------- 한 투자자의 카드
function icInvestorHtml(o) {
  const est = (x, unit) => (x && x.value !== null && x.value !== undefined ? `${unit === "점" ? icNum(x.value) + "점" : icPct(x.value)} <span class="meta" style="margin:0">(${esc(x.basis)})</span>` : `<span class="meta" style="margin:0">${esc((x && x.basis) || "계산하지 않음")}</span>`);
  const comps = Object.entries(o.components || {}).map(([k, v]) => `${esc(k)} ${icNum(v)}`).join(" · ");
  const alt = o.other_profile;
  const extra = [o.category_ko ? `회사의 종류: ${o.category_ko}` : "", o.profile ? `기준: ${o.profile}(포트폴리오와 기록은 이 기준)` : "", o.method || "",
    o.loss_risk && o.loss_risk.score !== null ? `영구 손실 위험 ${icNum(o.loss_risk.score)}/100 (질문 ${o.loss_risk.asked}개 중 ${o.loss_risk.answered}개에 답함)` : "",
    (o.regimes || []).length ? `시장 국면: ${o.regimes.map((r) => `${r.label}(확신 ${r.confidence})`).join(", ")}` : "",
    (o.regimes_not_told || []).length ? `읽지 못한 국면: ${o.regimes_not_told.join(", ")}` : ""].filter(Boolean);
  return `<div class="ic-card">
    <div><b>${esc(o.name)}</b> <span class="meta" style="margin:0">${esc(o.philosophy)}</span></div>
    <div style="margin:6px 0">${icBadge(o.recommendation, o.recommendation_ko)} <span class="num">점수 <b>${icNum(o.score)}</b> · 신뢰 ${icNum(o.confidence)}</span></div>
    <div class="ic-say">${esc(o.opinion)}</div>
    <div class="meta" style="margin:6px 0 0"><b style="color:var(--up)">근거</b> ${esc((o.positives || [])[0] || "없음")}</div>
    <div class="meta" style="margin:2px 0 0"><b style="color:var(--bad)">우려</b> ${esc((o.negatives || [])[0] || "없음")}</div>
    <div class="meta" style="margin:2px 0 0"><b>할 일</b> ${esc(o.action)}</div>
    ${alt ? `<div class="meta" style="margin:2px 0 0"><b>${esc(alt.profile)} 기준이라면</b> ${icBadge(alt.recommendation, alt.recommendation_ko)}${alt.same ? " 같은 판정" : ""}</div>` : ""}
    <details><summary>자세히</summary>
      ${alt ? `<div class="meta"><b>${esc(alt.profile)} 기준(비교용, 아무것도 바꾸지 않음)</b> ${esc(alt.opinion)} 매수 조건: ${esc(alt.buy)}</div>` : ""}
      <div class="meta">묻는 것: ${esc(o.question)} · 보는 기간: ${esc(o.horizon)}</div>
      <div class="meta">가격 판단: ${esc(o.valuation)}</div>
      <div class="meta">기대수익률: ${est(o.expected_return)} · 하방 위험: ${est(o.downside_risk, o.investor === "MUNGER" ? "점" : "")}</div>
      ${comps ? `<div class="meta">항목별 점수: ${comps}</div>` : ""}
      ${extra.map((x) => `<div class="meta">${esc(x)}</div>`).join("")}
      ${o.loss_risk && (o.loss_risk.ways || []).length ? `<div class="meta">거꾸로 따져 본 위험: ${o.loss_risk.ways.map((w) => `${esc(w.ask)} → ${esc(w.text)}`).join(" · ")}</div>` : ""}
      <div class="meta"><b>좋게 본 것</b> ${esc((o.positives || []).join(", ") || "없음")}</div>
      <div class="meta"><b>나쁘게 본 것</b> ${esc((o.negatives || []).join(", ") || "없음")}</div>
      ${Object.entries(IC_COND).map(([k, label]) => `<div class="meta"><b>${label} 조건</b> ${esc((o.conditions || {})[k] || "")}</div>`).join("")}
      ${(o.missing || []).length ? `<div class="meta"><b>읽지 못한 자료</b> ${esc(o.missing.join(", "))}</div>` : ""}
      <div class="meta">확인된 자료 비율 ${icPct(o.coverage, 0)}${o.suggested_weight ? ` · 이 관점의 포트폴리오에서 줄 비중 ${icPct(o.suggested_weight)}` : ""}</div>
    </details></div>`;
}

// ---------------------------------------------------------------- 위원회 판정
function icCommitteeHtml(c) {
  const s = c.scores || {}, L = c.score_labels || {};
  const order = ["attractiveness", "confidence", "agreement", "quality", "valuation", "growth", "regime", "downside", "data"];
  return `<div class="ic-committee">
    <div><b>통합 투자위원회</b> ${icBadge(c.decision, c.decision_ko)} <span class="meta" style="margin:0">다섯 의견을 평균하지 않고 규칙으로 정합니다 · 보는 기간: ${esc(c.horizon)}</span></div>
    <div class="ic-scores">${order.map((k) => `<span><i>${esc(L[k] || k)}</i><b class="num">${icNum(s[k])}</b></span>`).join("")}</div>
    <div class="ic-say">${esc(c.thesis)}</div>
    <div class="meta"><b>이렇게 정한 이유</b></div>${icList(c.reasons)}
    <div class="meta"><b style="color:var(--up)">가장 강한 찬성 논거</b> ${c.strongest_for ? `${esc(c.strongest_for.investor)}: ${esc(c.strongest_for.text)}` : "없음"}</div>
    <div class="meta"><b style="color:var(--bad)">가장 강한 반대 논거</b> ${c.strongest_against ? `${esc(c.strongest_against.investor)}: ${esc(c.strongest_against.text)}` : "없음"}</div>
    <details><summary>위원회 토론 자세히</summary>
      <div class="meta"><b>함께 좋게 본 것</b> ${esc(((c.agreement || {}).positives || []).join(", ") || "없음")}</div>
      <div class="meta"><b>함께 나쁘게 본 것</b> ${esc(((c.agreement || {}).negatives || []).join(", ") || "없음")}</div>
      <div class="meta"><b>의견이 갈린 곳</b></div>${icList((c.disagreements || []).map((d) => `[${d.kind_ko}] ${d.text}`))}
      <div class="meta"><b>따로 본 위험</b></div>${icList((c.material_risks || []).map((r) => `${r.level === "CRITICAL" ? "중대" : "주요"} · ${r.name}: ${r.text} (${r.raised_by}의 관심사)`))}
      <div class="meta"><b>들어갈 조건</b></div>${icList(c.entry_conditions)}
      <div class="meta"><b>나올 조건</b></div>${icList(c.exit_conditions)}
      ${(c.minority || []).length ? `<div class="meta"><b>따르지 않은 의견(그대로)</b></div>${icList(c.minority.map((m) => `${m.investor} '${m.recommendation_ko}': ${m.opinion}`))}` : ""}
    </details></div>`;
}

// 점수 카드 안: 다섯 의견과 위원회 판정, 그리고 '포트폴리오 받아보기' 버튼 (qsf.js가 부릅니다)
function icCardHtml(v, ticker, market) {
  if (!v) return "";
  if (v.status !== "OK") return `<div class="panel"><h3>다섯 투자자와 투자위원회</h3><div class="meta">${esc(v.reason || "판단할 자료가 없습니다.")}</div></div>`;
  return `<div class="panel"><h3>다섯 투자자와 투자위원회 <span class="meta" style="margin:0">알려진 원칙을 규칙으로 옮긴 참고 · 점수와 무관 · 주문 없음</span></h3>
    <div class="ic-grid">${v.investors.map(icInvestorHtml).join("")}</div>
    ${icCommitteeHtml(v.committee)}
    ${plainBlock(v.plain)}
    <div style="margin:10px 0 0"><button type="button" class="ic-place" data-t="${esc(ticker || v.ticker || "")}" data-m="${esc(market || v.market || "")}" title="여섯 포트폴리오를 지금 만들고 이 종목이 어디에 드는지 보여 줍니다. 누르기 전에는 만들지 않습니다.">포트폴리오 받아보기</button>
      <span class="meta" style="margin:0 0 0 8px">다섯 투자자와 위원회의 여섯 포트폴리오 · 누를 때 작성</span></div>
    <div class="ic-out"></div>
    <div class="meta">${esc(v.note || "")}${v.source === "EVALUATION" ? " 스캔 대상이 아닌 종목이라 방금 계산한 값으로 판단했습니다." : ""}</div></div>`;
}

function icPlaceHtml(d) {
  if (!d || d.status !== "OK") return `<div class="notice">${esc((d && d.reason) || "포트폴리오를 만들지 못했습니다.")}</div>`;
  const rows = d.places.map((p) => `<tr><td class="l"><b>${esc(p.name)}</b></td><td class="num">${p.in ? icPct(p.weight) : "없음"}</td><td class="num">${p.count}종목 · 현금 ${icPct(p.cash, 0)}</td><td class="l">${esc(p.why)}</td></tr>`).join("");
  return `<h3 style="margin-top:14px">여섯 포트폴리오에서 이 종목 <span class="meta" style="margin:0">${esc(d.session || "")} 기록으로 지금 작성</span></h3>
    <div class="tbl-wrap"><table><thead><tr><th class="l">포트폴리오</th><th>이 종목의 비중</th><th>포트폴리오</th><th class="l">이유</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="meta">전체 종목과 비중은 <a href="#committee">투자위원회 탭</a>의 '여섯 포트폴리오'에서 봅니다. 주문을 내지 않는 모의 포트폴리오입니다.</div>`;
}

async function icPlace(btn) {
  const out = btn.parentElement.parentElement.querySelector(".ic-out");
  if (!out || btn.disabled) return;
  btn.disabled = true; btn.textContent = "작성 중…";
  out.innerHTML = `<div class="meta">여섯 포트폴리오를 작성하고 있습니다…</div>`;
  try {
    const d = await api(`/api/committee/place?t=${encodeURIComponent(btn.dataset.t)}&market=${btn.dataset.m}`);
    out.innerHTML = icPlaceHtml(d);
    if (d.status === "OK") icState.ports[btn.dataset.m] = null;          // 탭의 포트폴리오는 그 탭의 버튼으로 따로 받습니다
    btn.textContent = "다시 받아보기";
  } catch (e) {
    out.innerHTML = `<div class="notice">포트폴리오를 만들지 못했습니다: ${esc(errKo(e))}</div>`;
    btn.textContent = "포트폴리오 받아보기";
  }
  btn.disabled = false;
}

// ---------------------------------------------------------------- 투자위원회 탭
function renderCommittee() {
  const el = $("#tab-committee");
  icState.market = icMarket();
  el.innerHTML = `<div class="panel"><h2>투자위원회 <span class="meta" style="margin:0">${icState.market === "KR" ? "한국" : "미국"} · 다섯 투자자 엔진과 통합 위원회 · 규칙 IC-1</span></h2>
    <div class="meta">버핏식·멍거식·그레이엄식·린치식·드러켄밀러식 다섯 규칙이 종목마다 따로 판단하고, 위원회가 그 다섯을 읽어 하나의 판정을 냅니다. 실존 투자자의 의견이 아니고, 수익으로 검증하지 않았으며, QSF 점수와 섞지 않고, 주문을 내지 않습니다.</div>
    <div class="qsf-nav"><span class="seg" id="icview" role="group" aria-label="보기">${Object.entries(IC_VIEWS).map(([k, v]) => `<button type="button" data-v="${k}">${v}</button>`).join("")}</span></div></div>
    <div id="icbody"></div>`;
  $("#icview").querySelectorAll("button").forEach((b) => (b.onclick = () => icSetView(b.dataset.v)));
  icSetView(icState.view);
}

function icSetView(v) {
  icState.view = IC_VIEWS[v] ? v : "dash";
  $("#icview").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.v === icState.view));
  ({ dash: icDash, ports: icPorts, compare: icCompare, perf: icPerf })[icState.view]();
}

function icOpenRows(box, mk) {
  box.querySelectorAll(".qs-open").forEach((b) => { b.onclick = () => qsfOpenCard(b.dataset.t); });
}
const icTicker = (t, name) => `<button type="button" class="qs-open" data-t="${esc(t)}"><b>${esc(t)}</b> <span class="meta" style="margin:0">${esc(name || "")}</span></button>`;

async function icDash() {
  const box = $("#icbody"), mk = icState.market;
  box.innerHTML = `<div class="panel"><div class="meta">불러오는 중…</div></div>`;
  let d;
  try { d = await api(`/api/committee/dashboard?market=${mk}`); } catch (e) { box.innerHTML = errBox(e); return; }
  if (icState.view !== "dash" || mk !== icState.market) return;
  if (d.status !== "OK") { box.innerHTML = `<div class="panel"><div class="empty">${esc(d.reason || "기록이 없습니다.")}</div></div>`; return; }
  const chips = (o) => Object.entries(o || {}).map(([k, n]) => `<span class="badge">${esc(k)} ${n}</span>`).join(" ") || "없음";
  const top = d.top.map((r) => `<tr><td class="l">${icTicker(r.ticker, r.name)}</td><td class="l">${esc(r.sector || "")}</td><td class="l">${esc(r.decision_ko)}</td><td class="num">${icNum(r.attractiveness)}</td><td class="num">${icNum(r.confidence)}</td>
    <td class="l">${esc((r.supporters || []).join(", "))}</td><td class="l">${r.strongest_for ? esc(r.strongest_for.text) : ""}</td><td class="l">${r.strongest_against ? esc(r.strongest_against.investor + ": " + r.strongest_against.text) : ""}</td></tr>`).join("");
  box.innerHTML = `<div class="panel"><h2>위원회 현황 <span class="meta" style="margin:0">${esc(d.session)} 기록 · ${d.judged}종목</span></h2>
      <div class="meta"><b>시장 상태</b> ${icNum(d.market_state)}/100 · 국면: ${(d.regimes || []).map((r) => `${esc(r.label)}(확신 ${r.confidence})`).join(", ") || "뚜렷한 국면 없음"} · 읽지 못한 국면: ${esc((d.regimes_not_told || []).join(", "))}</div>
      <div class="meta"><b>위원회 판정의 분포</b> ${chips(d.decisions)}</div>
      <div class="meta"><b>의견 일치(평균)</b> ${icNum(d.average_agreement)}/100 · <b>의견이 갈린 종류</b> ${chips(d.disagreements)}</div>
      <div class="meta"><b>자주 나온 위험</b> ${chips(d.risks)}</div></div>
    <div class="panel"><h2>위원회가 매수 조건으로 본 종목 <span class="meta" style="margin:0">${d.buy_count}종목 가운데 매력 순 ${d.top.length}종목 · 줄을 누르면 점수 카드</span></h2>
      ${top ? `<div class="tbl-wrap"><table><thead><tr><th class="l">종목</th><th class="l">업종</th><th class="l">판정</th><th>매력</th><th>신뢰</th><th class="l">찬성한 관점</th><th class="l">찬성 논거</th><th class="l">반대 논거</th></tr></thead><tbody>${top}</tbody></table></div>`
        : `<div class="empty">위원회가 매수 조건으로 본 종목이 없습니다. 억지로 채우지 않습니다.</div>`}
      <div class="meta">${esc(d.note)}</div></div>`;
  icOpenRows(box, mk);
}

function icPortHtml(p) {
  const rows = p.holdings.map((r) => `<tr><td class="l">${icTicker(r.ticker, r.name)}</td><td class="l">${esc(r.sector || "")}${r.category ? ` · ${esc(r.category)}` : ""}</td><td class="num"><b>${icPct(r.weight)}</b>${r.overweight ? ' <span class="badge risk-note" title="한 종목 한도의 1.5배 이상입니다. 알리기만 하고 그대로 둡니다.">비중 과다</span>' : ""}</td>
    <td class="l">${icBadge(r.recommendation, r.recommendation_ko)}</td><td class="num">${icNum(r.score)}</td><td class="num">${icNum(r.confidence)}</td><td class="l">${esc(r.status)}</td>
    <td class="l"><details><summary>${esc(r.thesis || "")}</summary><div class="meta">들어갈 조건: ${esc(r.entry || "")}</div><div class="meta">나올 조건: ${esc(r.exit || "")}</div>
      <div class="meta">비중을 정한 방법: ${esc(r.sizing)}${r.supporters ? ` · 찬성한 관점: ${esc(r.supporters.join(", ") || "없음")}` : ""}${r.volatility ? ` · 변동성 ${icPct(r.volatility, 0)}` : ""}</div>
      <div class="meta">기준일 ${esc(r.as_of || "")}</div></details></td></tr>`).join("");
  const sectors = Object.entries(p.sectors || {}).map(([k, w]) => `${esc(k)} ${icPct(w, 0)}`).join(" · ");
  // 예외 두 가지(2026-11-23): 비중 과다는 알리기만 하고 그대로 두며, 치명적 훼손은 여섯 포트폴리오 모두에서 전부 뺍니다
  const interrupts = (p.fatal || []).map((n) => `<div class="notice"><b>치명적 훼손으로 전량 제외</b> ${esc(n.name)}(${esc(n.ticker)}): ${esc(n.why)}. 빠진 비중 ${icPct(n.weight)}는 현금으로 둡니다.</div>`).join("")
    + (p.overweight || []).map((n) => `<div class="notice"><b>비중 과다 알림${n.new ? " · 오늘 처음" : ""}</b> ${esc(n.text)}</div>`).join("");
  return `<div class="panel"><h2>${esc(p.name)} <span class="meta" style="margin:0">${esc(p.objective)}</span></h2>
    ${plainBlock(p.plain)}
    ${interrupts}
    <div class="ic-scores"><span><i>종목 수</i><b class="num">${p.count}</b></span><span><i>투자 비중</i><b class="num">${icPct(p.invested, 0)}</b></span><span><i>현금</i><b class="num">${icPct(p.cash, 0)}</b></span>
      <span><i>가장 큰 종목</i><b class="num">${icPct(p.largest)}</b></span><span><i>집중도(HHI)</i><b class="num">${icNum(p.concentration, 3)}</b></span><span><i>이번 교체</i><b class="num">${icPct(p.turnover, 0)}</b></span></div>
    <div class="meta"><b>비중 규칙</b> ${esc(p.sizing)} · 최대 ${p.limits.max}종목, 한 업종 ${p.limits.per_sector}종목, 한 종목 ${icPct(p.limits.per_stock, 0)}까지 · 후보 ${p.candidates}종목 중 한도로 빠진 종목 ${p.left_out_by_limits}</div>
    <div class="meta"><b>보유 중인 종목</b>의 비중은 가격에 따라 저절로 변합니다(한도로 되돌리지 않습니다). 한도의 1.5배 이상이 되면 알리고, 심각 공시가 뜨거나 멍거식 영구 손실 위험이 50 이상이면 전부 뺍니다.</div>
    ${(p.cash_reasons || []).map((x) => `<div class="meta"><b>현금</b> ${esc(x)}</div>`).join("")}
    ${sectors ? `<div class="meta"><b>업종</b> ${sectors}</div>` : ""}
    ${rows ? `<div class="tbl-wrap"><table><thead><tr><th class="l">종목</th><th class="l">업종</th><th>비중</th><th class="l">판정</th><th>점수</th><th>신뢰</th><th class="l">상태</th><th class="l">논지(누르면 조건)</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="empty">담은 종목이 없습니다. 전부 현금입니다.</div>`}
    ${(p.exits || []).length ? `<div class="meta"><b>이번에 나간 종목</b></div>${icList(p.exits.map((x) => `${x.name}(${x.ticker}): ${x.why}`))}` : ""}
    ${(p.moves_together || []).length ? `<div class="meta"><b>함께 움직여 빠진 종목</b> ${p.moves_together.map((x) => `${esc(x.ticker)}(${esc(x.with)}와 상관 ${x.correlation})`).join(", ")}</div>` : ""}
  </div>`;
}

function icPortsDraw(d, mk) {
  const box = $("#icbody");
  const tabs = d.portfolios.map((p) => `<button type="button" data-p="${p.key}">${esc(p.name.replace(" 포트폴리오", ""))} <span class="meta" style="margin:0">${p.count}</span></button>`).join("");
  const over = (d.overlap || []).filter((o) => o.count).map((o) => `${esc(o.a.replace(" 포트폴리오", ""))}–${esc(o.b.replace(" 포트폴리오", ""))} ${o.count}종목`).join(" · ");
  box.innerHTML = `<div class="panel"><h2>여섯 포트폴리오 <span class="meta" style="margin:0">${esc(d.session)} 기록으로 작성 · 모의(주문 없음)</span>
      <button type="button" class="ghost" id="icportsget">다시 받아보기</button></h2>
      <div class="meta">${esc(d.made)}</div>
      <div class="meta"><b>겹치는 종목</b> ${over || "여섯 포트폴리오 사이에 겹치는 종목이 없습니다"}</div>
      <div class="qsf-nav"><span class="seg" id="icporttabs" role="group" aria-label="포트폴리오">${tabs}</span></div></div>
    <div id="icport"></div><div class="panel"><div class="meta">${esc(d.note)}</div></div>`;
  const show = (key) => {
    icState.port = key;
    $("#icporttabs").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.p === key));
    $("#icport").innerHTML = icPortHtml(d.portfolios.find((p) => p.key === key) || d.portfolios[0]);
    icOpenRows($("#icport"), mk);
  };
  $("#icporttabs").querySelectorAll("button").forEach((b) => (b.onclick = () => show(b.dataset.p)));
  $("#icportsget").onclick = () => icPortsGet();
  show(d.portfolios.some((p) => p.key === icState.port) ? icState.port : "COMMITTEE");
}

// 여섯 포트폴리오는 이 버튼을 눌렀을 때만 만듭니다. 탭을 여는 것만으로는 만들지 않습니다.
async function icPortsGet() {
  const box = $("#icbody"), mk = icState.market;
  box.innerHTML = `<div class="panel"><div class="meta">여섯 포트폴리오를 작성하고 있습니다…</div></div>`;
  let d;
  try { d = await api(`/api/committee/portfolios?market=${mk}`); } catch (e) { box.innerHTML = errBox(e); return; }
  if (d.status !== "OK") { box.innerHTML = `<div class="panel"><div class="empty">${esc(d.reason || "만들지 못했습니다.")}</div></div>`; return; }
  icState.ports[mk] = d;
  if (icState.view === "ports" && mk === icState.market) icPortsDraw(d, mk);
}

function icPorts() {
  const mk = icState.market, kept = icState.ports[mk];
  if (kept) { icPortsDraw(kept, mk); return; }
  $("#icbody").innerHTML = `<div class="panel"><h2>여섯 포트폴리오</h2>
    <div class="meta">버핏식(오래 가져갈 좋은 사업), 멍거식(탁월한 사업 몇 개), 그레이엄식(싸고 튼튼한 종목을 넓게), 린치식(성장에 비해 값이 적당한 종목), 드러켄밀러식(시장·이익·추세가 맞는 곳), 투자위원회(위험을 따져 합친 것).
      여섯은 서로 다른 규칙으로 종목을 고르고 비중을 정합니다. 조건을 채운 종목이 없으면 현금으로 둡니다.</div>
    <div style="margin:12px 0"><button type="button" class="btn-primary" id="icportsget">여섯 포트폴리오 받아보기</button>
      <span class="meta" style="margin:0 0 0 8px">누르면 지금 기록으로 작성합니다. 누르기 전에는 만들지 않습니다.</span></div>
    <div class="meta">주문을 내지 않는 모의 포트폴리오입니다. 금액과 수량은 계산하지 않습니다.</div></div>`;
  $("#icportsget").onclick = () => icPortsGet();
}

async function icCompare(asked) {
  const box = $("#icbody"), mk = icState.market;
  box.innerHTML = `<div class="panel"><div class="meta">불러오는 중…</div></div>`;
  let d;
  try { d = await api(`/api/committee/compare?market=${mk}${asked ? `&t=${encodeURIComponent(asked)}` : ""}`); } catch (e) { box.innerHTML = errBox(e); return; }
  if (icState.view !== "compare" || mk !== icState.market) return;
  if (d.status !== "OK") { box.innerHTML = `<div class="panel"><div class="empty">${esc(d.reason || "기록이 없습니다.")}</div></div>`; return; }
  const names = d.rows.length ? d.rows[0].views.map((v) => v.name) : Object.keys(d.tally);
  const rows = d.rows.map((r) => `<tr><td class="l">${icTicker(r.ticker, r.name)}</td>${r.views.map((v) => `<td class="l" title="${esc(v.valuation)} · ${esc(v.horizon)}">${icBadge(v.recommendation, v.recommendation_ko)} <span class="num">${icNum(v.score)}</span></td>`).join("")}
    <td class="l"><b>${esc(r.committee)}</b></td><td class="num">${icNum(r.attractiveness)}</td><td class="num">${icNum(r.agreement)}</td><td class="num">${icNum(r.growth)}</td><td class="num">${icNum(r.downside)}</td></tr>`).join("");
  const tally = Object.entries(d.tally).map(([n, o]) => `<div class="meta"><b>${esc(n)}</b> ${Object.entries(o).sort((a, b) => b[1] - a[1]).map(([k, c]) => `${esc(k)} ${c}`).join(" · ")}</div>`).join("");
  box.innerHTML = `<div class="panel"><h2>투자자 비교 <span class="meta" style="margin:0">${esc(d.session)} 기록 · ${d.asked ? "고른 종목" : "위원회 매력 상위 20종목"}</span></h2>
      <form id="iccmpform" class="search" style="margin:0 0 8px"><input id="iccmpq" placeholder="${mk === "KR" ? "005930, 000660" : "AAPL, NVDA, MSFT"}" value="${esc(asked || "")}" aria-label="비교할 종목 코드(쉼표로 구분)"><button>비교</button></form>
      ${(d.not_found || []).length ? `<div class="notice">스캔 기록에 없는 종목: ${esc(d.not_found.join(", "))}</div>` : ""}
      <div class="tbl-wrap"><table><thead><tr><th class="l">종목</th>${names.map((n) => `<th class="l">${esc(n)}</th>`).join("")}<th class="l">위원회</th><th>매력</th><th>일치</th><th>성장</th><th>하방 위험</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="meta">칸에 마우스를 올리면 그 관점의 가격 판단과 보는 기간이 나옵니다. 숫자는 그 관점의 점수(0~100)입니다.</div></div>
    <div class="panel"><h2>관점마다 판정이 어떻게 갈리나 <span class="meta" style="margin:0">${d.judged}종목</span></h2>${tally}<div class="meta">${esc(d.note)}</div></div>`;
  $("#iccmpform").onsubmit = (e) => { e.preventDefault(); icCompare($("#iccmpq").value.trim().toUpperCase()); };
  icOpenRows(box, mk);
}

async function icPerf() {
  const box = $("#icbody"), mk = icState.market;
  box.innerHTML = `<div class="panel"><div class="meta">불러오는 중…</div></div>`;
  let d;
  try { d = await api(`/api/committee/performance?market=${mk}`); } catch (e) { box.innerHTML = errBox(e); return; }
  if (icState.view !== "perf" || mk !== icState.market) return;
  const rd = d.reading || {};
  const reading = `<div class="meta"><b>한 번의 읽기</b> ${esc(rd.rule || "")} ${rd.verdict ? `읽은 결과: <b>${esc(rd.verdict)}</b>` : `앞으로 약 ${rd.left}거래일.`} 규칙: ${esc(rd.protocol || "")}</div>${(rd.reasons || []).map((x) => `<div class="meta">${esc(x)}</div>`).join("")}`;
  const head = `<h2>여섯 포트폴리오의 모의 성과 <span class="badge" style="color:var(--warn)">모의 기록</span></h2>
    <div class="meta">${esc(d.kind_ko)} · ${esc(d.not_this)}</div><div class="meta">${esc(d.method)} 거래 비용은 편도 ${icPct(d.one_way_cost, 2)}로 계산합니다. 비교 지수: ${esc(d.benchmark)}.</div>`;
  if (d.status !== "OK") {
    box.innerHTML = `<div class="panel">${head}<div class="empty">${esc(d.reason || "기록이 없습니다.")}</div>
      <div class="meta">매일 작업이 그날의 여섯 포트폴리오를 한 줄씩 기록합니다. 기록 ${d.records}거래일${d.first_session ? `(${esc(d.first_session)} ~ ${esc(d.last_session)})` : ""}.</div>${reading}</div>`;
    return;
  }
  const rows = Object.entries(d.portfolios).map(([k, s]) => `<tr><td class="l"><b>${esc((d.names || {})[k] || k)}</b></td><td class="num">${s.days}</td><td class="num">${icPct(s.total_return, 2)}</td><td class="num">${icPct(s.benchmark_return, 2)}</td>
    <td class="num">${icPct(s.max_drawdown, 2)}</td><td class="num">${icPct(s.win_rate, 0)}</td><td class="num">${icPct(s.cagr, 1)}</td><td class="num">${icPct(s.volatility, 1)}</td><td class="num">${icNum(s.sharpe, 2)}</td><td class="num">${icNum(s.sortino, 2)}</td>
    <td class="num">${icNum(s.calmar, 2)}</td><td class="num">${icPct(s.alpha, 1)}</td><td class="num">${icNum(s.beta, 2)}</td><td class="num">${icPct(s.turnover_per_day, 1)}</td><td class="num">${icNum(s.average_holding_sessions, 1)}</td><td class="num">${icPct(s.cost_total, 2)}</td></tr>`).join("");
  const first = Object.values(d.portfolios)[0] || {};
  box.innerHTML = `<div class="panel">${head}
    <div class="tbl-wrap"><table><thead><tr><th class="l">포트폴리오</th><th>거래일</th><th>수익</th><th>지수</th><th>최대 낙폭</th><th>오른 날</th><th>연환산</th><th>변동성</th><th>샤프</th><th>소르티노</th><th>칼마</th><th>알파</th><th>베타</th><th>하루 교체</th><th>평균 보유일</th><th>비용 합</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${first.ratios ? `<div class="meta">${esc(first.ratios)}</div>` : ""}
    <div class="meta">기록 ${d.records}거래일(${esc(d.first_session)} ~ ${esc(d.last_session)}). 표본이 짧을 때의 수익은 우연과 구별되지 않습니다. 이 성과를 보고 규칙을 고치지 않습니다.</div>${reading}</div>`;
}

RENDER.committee = renderCommittee;
document.addEventListener("click", (e) => { const b = e.target.closest && e.target.closest(".ic-place"); if (b) icPlace(b); });
