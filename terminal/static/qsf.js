// QSF 1.1 score tab.  Every colour comes with a text label; score and confidence are always shown separately.
const QSF_ACTION_CLASS = { BUY: "act-buy", SELL: "act-sell", AVOID: "act-sell", REDUCE: "act-reduce", HOLD: "act-hold", WATCH: "act-hold", INSUFFICIENT_DATA: "act-hold", BLOCKED: "act-hold" };
const QSF_STRAT = { SWING: "스윙", LONG_TERM: "장기" };
const QSF_ENTRY = { ENTRY_NOW: "지금 진입 가능 구간", WAIT_FOR_PULLBACK: "눌림 대기", WAIT_FOR_BREAKOUT_CONFIRMATION: "돌파 확인 대기", WAIT_FOR_EARNINGS: "실적 발표 대기", OVERVALUED_AT_CURRENT_PRICE: "현재 가격 고평가", NO_VALID_ENTRY_SETUP: "유효한 진입 근거 없음" };
const QSF_CONF = { HIGH: "높음", MEDIUM: "보통", LOW: "낮음", INSUFFICIENT: "부족" };
const QSF_EXIT = { HOLD: "보유", HOLD_AND_REVIEW: "보유하며 재검토", PARTIAL_TAKE_PROFIT: "일부 차익 실현 검토", REDUCE: "비중 축소 검토", EXIT: "청산 검토", THESIS_INVALIDATED: "투자 논리 무효", TIME_STOP_REVIEW: "시간 손절 재평가" };
const qsfState = { get market() { return state.market; }, strategy: "SWING", detail: null, evals: {}, rankToken: 0 };

function qsfClass(a, score) {
  if (a === "AVOID" && score !== null && score >= 40) return "act-reduce";   // 40-54.99 is the orange band; red starts below 40
  return QSF_ACTION_CLASS[a] || "act-hold";
}
function qsfNum(v, d = 1) { return v === null || v === undefined ? '<span class="missing">없음</span>' : Number(v).toFixed(d); }
function qsfPrice(v, market) { return v === null || v === undefined ? '<span class="missing">없음</span>' : Number(v).toLocaleString("ko-KR", { maximumFractionDigits: market === "KR" ? 0 : 2 }); }
function qsfLabel(c) {
  return `<span class="qsf-act ${qsfClass(c.action, c.score)}"><i></i>${esc(c.action_label)}</span>`;
}
function qsfBar(v) {
  if (v === null || v === undefined) return '<span class="missing">데이터 없음</span>';
  const tone = v >= 70 ? "act-buy" : v >= 55 ? "act-hold" : v >= 40 ? "act-reduce" : "act-sell";
  return `<span class="qsf-bar ${tone}"><i style="width:${Math.max(2, Math.min(100, v))}%"></i></span> <b class="num">${v.toFixed(0)}</b>`;
}

async function renderQsf() {
  const el = $("#tab-qsf");
  el.innerHTML = `<div class="panel"><h2>종목 점수 (QSF 1.1)</h2>
    <div class="notice"><b>미국 S&P 500 과거 검증(2014~2026)에서 점수가 높을수록 수익이 좋다는 근거를 찾지 못했습니다. 한국은 검증하지 않았습니다. 참고용으로만 쓰세요.</b><br>모델 탭의 기준 모델(미국 종목에 순위를 매겨 상위 5개와 진입·손절 계획을 내는, 규칙이 고정된 모델)과 별개인 규칙 기반 점수이며, 두 결과를 합치지 않습니다. 가중치와 구간은 사전에 정한 연구 기본값입니다. 주문을 실행하지 않고, 투자 자문이 아닙니다.</div>
    <form id="qsfform" class="qsf-form">
      <input id="qsfticker" placeholder="${isKR() ? "종목코드 (예: 005930)" : "티커 (예: AAPL)"}" autocomplete="off" aria-label="종목">
      <button class="btn-primary">평가</button></form>
    <div id="qsfmsg" class="meta"></div></div>
    <div id="qsfdetail"></div><div id="qsfrank"></div><div id="qsfscreen"></div><div id="qsfvalid"></div>`;
  $("#qsfform").onsubmit = (e) => { e.preventDefault(); const t = $("#qsfticker").value.trim().toUpperCase(); if (t) { setMarket(marketOf(t)); qsfEvaluate(t, qsfState.market); } };
  qsfRank();
  qsfScreenBuild();
  qsfValidation();
  if (qsfState.detail && qsfState.detail.market === state.market) qsfDrawDetail(qsfState.detail);
}

async function qsfEvaluate(t, market) {
  $("#qsfmsg").textContent = `${t} 평가 중… (처음에는 공시를 읽느라 수십 초 걸릴 수 있습니다)`;
  try {
    const d = await api(`/api/qsf/evaluate?t=${encodeURIComponent(t)}&market=${market}`);
    $("#qsfmsg").textContent = d.status === "REAL" ? "" : `평가할 수 없습니다: ${d.reason}`;
    if (d.status === "REAL") { qsfState.detail = d; qsfDrawDetail(d); }
  } catch (e) { $("#qsfmsg").textContent = "평가 실패: " + e.message; }
}

const QSF_RISK_NOTE = "참고용 표시입니다. 점수와 순위에 반영되지 않으며, 이 종목을 피하면 수익이 난다는 검증은 아직 없습니다. 한국 시장 변동성 상위 20%입니다.";
const qsfRiskTag = () => `<span class="badge risk-note" title="${QSF_RISK_NOTE}">변동성 높음 · 참고</span>`;
const QSF_FILING_NOTE = "참고용 표시입니다. 점수와 순위에 반영되지 않습니다. 최근 252거래일 안의 첫 공시를 제목으로 읽었고, 취소 여부와 규모는 보지 않습니다. 과거 시험에서 자금조달 결정 종목의 평균 수익은 낮았지만, 앞으로의 자료로는 아직 확인되지 않았습니다. 자사주 묶음은 과거에도 시장을 이기지 못했습니다.";
const qsfFilingTags = (f) => !f ? "" : (f.financing ? ` <span class="badge risk-note" title="${QSF_FILING_NOTE}">자금조달 결정 · 참고</span>` : "") + (f.buyback ? ` <span class="badge" title="${QSF_FILING_NOTE}">자사주 취득 · 참고</span>` : "");
const QSF_RANK_NOTE = {
  NO_SCAN: "이 거래일의 전 종목 순위가 아직 없어 상대강도를 벤치마크 대비로 계산했습니다. 스캔이 끝나면 점수가 달라질 수 있습니다.",
  OUTSIDE_UNIVERSE: "스캔 대상이 아닌 종목입니다. 상대강도는 스캔 종목의 수익률 분포에 넣어 계산했습니다.",
  SHORT_HISTORY: "거래 이력이 6개월보다 짧아 상대강도를 벤치마크 대비로 계산했습니다.",
};
function qsfDrawDetail(d) {
  const p = d.p6_reference;
  $("#qsfdetail").innerHTML = `<div class="panel"><h2>${esc(d.ticker)} ${esc(d.name || "")} <span class="badge">${d.market === "US" ? "미국" : "한국"}</span>${d.high_risk ? " " + qsfRiskTag() : ""}${qsfFilingTags(d.filing_events)}</h2>
    ${d.high_risk ? `<div class="meta">${QSF_RISK_NOTE} 기준일 ${esc(d.high_risk.session)}.</div>` : ""}
    ${d.filing_events ? `<div class="meta">${QSF_FILING_NOTE} 기준일 ${esc(d.filing_events.session)}.</div>` : ""}
    ${QSF_RANK_NOTE[d.rank_basis] ? `<div class="meta">${QSF_RANK_NOTE[d.rank_basis]}</div>` : ""}
    ${p ? `<div class="meta">P6-11B 참고: ${p.status !== "REAL" ? "기록 없음" : p.in_top5 ? `최근 스캔 상위 5 (${p.rank}위)` : "최근 스캔 상위 5 아님"} · 별도 모델이며 점수에 합치지 않습니다.</div>` : ""}
    <h3>당일 점검 <span class="meta" style="margin:0">점수에 포함되지 않음</span></h3><div id="qsftoday"></div>
    <div class="qsf-cards">${Object.values(d.cards).map(qsfCard).join("")}</div></div>`;
  qsfToday($("#qsftoday"), d.ticker, d.market);
}

function qsfCard(c) {
  const h = c.holding, m = c.market, e = c.entry;
  // Only the card of a holding's own style carries c.position.
  const factors = c.factors.map((f) => `<tr><td class="l">${esc(f.factor)}</td><td class="num">${f.weight}</td><td class="num">${f.contribution === null ? "-" : f.contribution.toFixed(1)}</td>
    <td class="l" style="white-space:normal">${esc(f.explanation || f.reason || "")}${f.status === "STALE" ? " (오래된 데이터)" : ""}${f.status === "NOT_APPLICABLE" ? " (해당 없음)" : ""}</td></tr>`).join("");
  const horizon = c.strategy === "SWING"
    ? `<dt>예상 보유</dt><dd>약 ${h.expected_sessions}거래일 (범위 ${h.range_sessions[0]}~${h.range_sessions[1]}일)</dd>
       <dt>첫 재평가</dt><dd>${esc(h.first_review)} · 이후 ${h.review_every_sessions}거래일마다</dd>
       <dt>시간 재평가</dt><dd>${esc(h.time_stop_review)} (${esc(h.time_stop_note)})</dd>
       <dt>손절 기준</dt><dd>${qsfPrice(h.stop, m)} · ${esc(h.stop_method || "")}</dd>
       <dt>목표 기준</dt><dd>${qsfPrice(h.target, m)} · ${esc(h.target_method || "")}</dd>
       <dt>비용 반영 손익비</dt><dd>${qsfNum(h.reward_risk, 2)} <span class="meta" style="margin:0">${esc(h.cost_basis || "")}</span></dd>`
    : `<dt>예상 보유</dt><dd>${h.range_months[0]}~${h.range_months[1]}개월 (강제 종료일 없음)</dd>
       <dt>첫 재평가</dt><dd>${esc(h.first_review)}, 다음 ${esc(h.next_review)} · 분기마다</dd>
       <dt>점검 항목</dt><dd>${h.milestones.map(esc).join(" / ")}</dd>
       <dt>시나리오</dt><dd>${h.scenarios.status === "REAL" ? h.scenarios.cases.map((x) => `${esc(x.case)} ${qsfPrice(x.price, m)} (${esc(x.assumption)})`).join("<br>") : esc(h.scenarios.reason)}</dd>`;
  return `<article class="qsf-card"><header><div><div class="meta" style="margin:0">${QSF_STRAT[c.strategy]} · ${esc(c.profile)}${c.position ? " · <b>보유 중</b>" : ""}</div>
      <div class="qsf-score num">${c.score === null ? "-" : c.score.toFixed(1)}<small>/100</small></div></div>
      <div>${qsfLabel(c)}<div class="meta" style="margin:4px 0 0">구간: ${esc(c.band_label)}${c.diagnostic_only ? " · 진단용 점수" : ""}</div></div></header>
    <div class="qsf-meta"><span>신뢰도 <b>${QSF_CONF[c.confidence]}</b></span><span>데이터 반영률 <b>${(c.coverage * 100).toFixed(0)}%</b></span><span>시세 <b>${esc(c.data_date)}</b> ${qsfPrice(c.price, m)}</span><span>${esc(c.model_version)}</span></div>
    <p>${esc(c.why_summary)}</p>
    ${c.gates.length ? `<div class="notice"><b>위험 게이트 ${c.gates.length}건</b>: ${c.gates.map((g) => esc(g.text)).join(" ")} 점수는 진단용으로 남기지만 실행 대상이 아닙니다.</div>` : ""}
    <h3>영역별 점수</h3><div class="qsf-domains">${Object.values(c.domains).map((v) => `<div><span>${esc(v.label)} <small class="meta" style="margin:0">${v.max_points}점</small></span>${qsfBar(v.score_100)}</div>`).join("")}</div>
    <h3>진입</h3><p><b>${QSF_ENTRY[e.status]}</b>: ${esc(e.reason)}${e.zone ? ` 기준 구간 ${qsfPrice(e.zone.low, m)}~${qsfPrice(e.zone.high, m)}.` : ""}</p>
    ${c.exit ? `<h3>보유 종목 판단</h3><p><b>${QSF_EXIT[c.exit.action]}</b>: ${esc(c.exit.reason)}</p>` : ""}
    <h3>보유 계획 <span class="meta" style="margin:0">(가설)</span></h3><dl class="qsf-dl"><dt>진입 예정일</dt><dd>${esc(h.entry_date)}</dd>${horizon}
      <dt>무효화 조건</dt><dd>${h.invalidation.map(esc).join(" / ")}</dd><dt>이 기간의 이유</dt><dd>${h.why.map(esc).join(" / ")}</dd></dl>
    <h3>판단이 바뀌는 조건</h3><ul class="qsf-list">${c.what_would_change.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    ${c.stability && c.stability.status === "REAL" ? `<div class="meta">직전 기록 ${esc(c.stability.previous_date)} ${c.stability.previous_score.toFixed(1)}점 → 변화 ${c.stability.delta >= 0 ? "+" : ""}${c.stability.delta.toFixed(1)}점${c.stability.large ? " (큰 변화)" : ""}</div>` : ""}
    <details><summary>요인별 계산 (${c.factors.length}개)${c.missing.length ? ` · 빠진 요인 ${c.missing.length}개` : ""}</summary><div class="tbl-wrap"><table><thead><tr><th class="l">요인</th><th>배점</th><th>기여</th><th class="l">근거</th></tr></thead><tbody>${factors}</tbody></table></div></details>
    <div class="meta">${esc(c.not_advice)}</div></article>`;
}

// ------------------------------------------------------------------ 순위: 상위 3개는 펼치고 나머지는 한 줄로
const QSF_TOP = 3;
const QSF_GATE = { EARNINGS_IMMINENT: "실적 발표 임박", SEVERE_EVENT: "중대 공시", SHORT_HISTORY: "거래 이력 짧음", NO_TRADING: "거래 없음" };
function qsfEval(t, market) {
  const k = `${market}|${t}`;
  if (!qsfState.evals[k]) {
    qsfState.evals[k] = api(`/api/qsf/evaluate?t=${encodeURIComponent(t)}&market=${market}`).catch((e) => { delete qsfState.evals[k]; throw e; });
  }
  return qsfState.evals[k];
}
function qsfScanNote(r, c) {
  if (c.score === null || r.score === null || Math.abs(c.score - r.score) < 0.05) return "";
  return `<div class="meta">순위표는 스캔 시점 ${r.score.toFixed(1)}점, 이 카드는 조회 시점 ${c.score.toFixed(1)}점입니다.</div>`;
}
async function qsfFillRow(box, r, market) {
  box.innerHTML = '<div class="meta">불러오는 중…</div>';
  try {
    const d = await qsfEval(r.ticker, market);
    if (!box.isConnected) return;
    if (d.status !== "REAL") { box.innerHTML = `<div class="empty">평가할 수 없습니다: ${esc(d.reason || "")}</div>`; return; }
    const c = d.cards[qsfState.strategy];
    box.innerHTML = `${qsfScanNote(r, c)}<div class="qsf-cards">${qsfCard(c)}</div>
      <details class="qsf-today-fold"><summary>당일 점검 (시세·공시·뉴스)</summary><div class="qsf-today-slot"></div></details>`;
    const fold = box.querySelector(".qsf-today-fold");
    fold.addEventListener("toggle", () => { if (fold.open && !fold.dataset.done) { fold.dataset.done = "1"; qsfToday(fold.querySelector(".qsf-today-slot"), r.ticker, market); } });
  } catch (e) { if (box.isConnected) box.innerHTML = `<div class="err">불러오지 못했습니다: ${esc(e.message)}</div>`; }
}
function qsfRowHtml(r) {
  const out = r.actionability !== "ACTIONABLE";
  return `<div class="qsf-item"><button type="button" class="qsf-row" data-qsf="${esc(r.ticker)}" aria-expanded="false">
      <span class="qr-rank num">${r.rank}</span>
      <span class="qr-name"><b>${esc(r.ticker)}</b> <span class="meta" style="margin:0">${esc(r.name || "")}</span>${r.high_risk ? " " + qsfRiskTag() : ""}${qsfFilingTags(r.filing_events)}</span>
      <span class="qr-score num">${qsfNum(r.score)}</span><span class="qr-act">${qsfLabel(r)}</span>
      <span class="qr-conf">신뢰도 ${QSF_CONF[r.confidence]}</span><span class="qr-entry">${QSF_ENTRY[r.entry_status] || ""}</span>
      <span class="qr-gate">${out ? `<span class="qr-out">상위 3 제외</span> ` : ""}${r.gates.map((g) => esc(QSF_GATE[g] || g)).join(", ")}</span>
    </button><div class="qsf-exp" hidden></div></div>`;
}
async function qsfRank() {
  const box = $("#qsfrank"); if (!box) return;
  const mk = state.market, token = ++qsfState.rankToken;
  const d = await api(`/api/qsf/latest?market=${mk}`).catch(() => null);
  if (token !== qsfState.rankToken || mk !== state.market) return;
  if (!d || d.status !== "REAL") { box.innerHTML = `<div class="panel"><h2>순위</h2><div class="empty">아직 스캔 기록이 없습니다. <code>python app.py qsf scan</code> 또는 매일 자동 실행 후 표시됩니다.</div></div>`; return; }
  const all = d.rows.filter((r) => r.strategy === qsfState.strategy).slice(0, 50).map((r, i) => ({ ...r, rank: i + 1 }));
  const top = all.filter((r) => r.actionability === "ACTIONABLE").slice(0, QSF_TOP);
  const rest = all.filter((r) => !top.includes(r));
  box.innerHTML = `<div class="panel"><h2>상위 ${top.length}개 <span class="badge">${esc(d.session)}</span>
      <select id="qsfstrat" aria-label="전략"><option value="SWING">스윙</option><option value="LONG_TERM">장기</option></select></h2>
    <div class="meta">점수순으로 보여 줄 뿐 수익이 더 좋다는 근거는 아닙니다. 위험 게이트에 걸렸거나 데이터가 부족한 종목은 상위 3개에서 뺍니다.</div>
    ${all.some((r) => r.high_risk) ? `<div class="meta">변동성 높음 · 참고: ${QSF_RISK_NOTE}</div>` : ""}
    ${all.some((r) => r.filing_events) ? `<div class="meta">공시 표시 · 참고: ${QSF_FILING_NOTE}</div>` : ""}
    ${top.map((r) => `<section class="qsf-top"><h3><span class="qr-rank num">${r.rank}위</span> ${esc(r.ticker)} <span class="meta" style="margin:0">${esc(r.name || "")}</span>${r.high_risk ? " " + qsfRiskTag() : ""}${qsfFilingTags(r.filing_events)}</h3><div class="qsf-top-body" data-top="${esc(r.ticker)}"></div></section>`).join("") || '<div class="empty">상위에 올릴 종목이 없습니다.</div>'}
    <h3 style="margin-top:18px">나머지 순위 <span class="meta" style="margin:0">눌러서 자세히</span></h3>
    <div class="qsf-rows">${rest.map(qsfRowHtml).join("")}</div>
    <div class="meta">${d.tickers}종목 평가 · 생성 ${esc((d.generated_at || "").slice(0, 16))} UTC</div></div>`;
  $("#qsfstrat").value = qsfState.strategy;
  $("#qsfstrat").onchange = (e) => { qsfState.strategy = e.target.value; qsfRank(); qsfScreenRun(true); };
  box.querySelectorAll(".qsf-row").forEach((btn) => {
    btn.onclick = () => {
      const panel = btn.nextElementSibling, open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", open ? "false" : "true");
      panel.hidden = open;
      if (!open && !panel.dataset.done) { panel.dataset.done = "1"; qsfFillRow(panel, rest.find((r) => r.ticker === btn.dataset.qsf), mk); }
    };
  });
  for (const r of top) {      // 공시를 처음 읽는 종목은 오래 걸리므로 한 번에 하나씩 채웁니다
    if (token !== qsfState.rankToken) return;
    const slot = box.querySelector(`[data-top="${CSS.escape(r.ticker)}"]`);
    if (slot) await qsfFillRow(slot, r, mk);
  }
}

// ------------------------------------------------------------------ 스크리너
// 최신 스캔을 거르고 정렬할 뿐입니다. 점수를 다시 계산하지 않고, 서버가 거른 결과만 그립니다.
const QSF_SCREEN_COLS = [["score", "점수"], ["technical", "기술"], ["fundamental", "재무"], ["risk", "위험"], ["events", "이벤트"]];
const QSF_SCREEN_DOMAIN = { technical: "TECHNICAL", fundamental: "FUNDAMENTAL", risk: "RISK", events: "EVENTS" };
const QSF_SCREEN_PAGE = 100;
const qsfScreenState = { form: {}, sort: "score", order: "desc", shown: QSF_SCREEN_PAGE, token: 0, timer: null };

function qsfScreenQuery(limit, offset) {
  const f = qsfScreenState.form, p = new URLSearchParams({ market: state.market, strategy: qsfState.strategy, sort: qsfScreenState.sort, order: qsfScreenState.order, limit, offset });
  for (const k of ["q", "action", "entry", "confidence", "min_score", "min_technical", "min_fundamental", "min_risk"]) if (f[k]) p.set(k, f[k]);
  const flags = isKR() ? ["actionable", "no_financing", "no_high_risk", "buyback"] : ["actionable"];
  for (const k of flags) if (f[k]) p.set(k, "1");
  return p.toString();
}

function qsfScreenBuild() {
  const box = $("#qsfscreen"); if (!box) return;
  const f = qsfScreenState.form;
  const num = (k, label) => `<label>${label}<input type="number" name="${k}" min="0" max="100" step="1" value="${esc(f[k] || "")}" inputmode="numeric"></label>`;
  const opt = (k, v, label) => `<option value="${v}"${(f[k] || "") === v ? " selected" : ""}>${label}</option>`;
  const check = (k, label) => `<label class="qs-check"><input type="checkbox" name="${k}"${f[k] ? " checked" : ""}> ${label}</label>`;
  box.innerHTML = `<div class="panel"><h2>스크리너 <span class="meta" id="qsfscreencount" style="margin:0"></span></h2>
    <div class="meta">최신 스캔의 전 종목을 거르고 정렬합니다. 점수를 바꾸지 않으며, 걸러 낸 목록이 수익이 더 좋다는 근거는 아닙니다. 물어본 값이 없는 종목은 0점으로 치지 않고 빼서 따로 셉니다.</div>
    <form id="qsfscreenform" class="qs-form" autocomplete="off">
      <label class="qs-wide">검색<input type="search" name="q" maxlength="40" placeholder="코드 또는 이름" value="${esc(f.q || "")}"></label>
      <label>판단<select name="action">${opt("action", "", "전체")}${opt("action", "BUY", "매수 후보")}${opt("action", "WATCH", "관찰")}${opt("action", "AVOID", "회피")}</select></label>
      <label>진입<select name="entry">${opt("entry", "", "전체")}${Object.keys(QSF_ENTRY).map((k) => opt("entry", k, esc(QSF_ENTRY[k]))).join("")}</select></label>
      <label>신뢰도<select name="confidence">${opt("confidence", "", "전체")}${opt("confidence", "MEDIUM", "보통 이상")}${opt("confidence", "HIGH", "높음")}</select></label>
      ${num("min_score", "점수 이상")}${num("min_technical", "기술 이상")}${num("min_fundamental", "재무 이상")}${num("min_risk", "위험 이상")}
      <div class="qs-checks">${check("actionable", "게이트 통과만")}${isKR() ? check("no_financing", "자금조달 결정 제외") + check("no_high_risk", "변동성 높음 제외") + check("buyback", "자사주 취득만") : ""}</div>
      <div class="qs-actions"><button type="button" id="qsfscreenreset">초기화</button><button type="button" id="qsfscreencsv">CSV 저장</button></div>
    </form>
    ${isKR() ? `<div class="meta">공시 표시 · 참고: ${QSF_FILING_NOTE}</div>` : ""}
    <div id="qsfscreenbody"></div></div>`;
  const form = $("#qsfscreenform");
  const read = () => { const out = {}; for (const el of form.elements) { if (!el.name) continue; if (el.type === "checkbox") { if (el.checked) out[el.name] = true; } else if (el.value !== "") out[el.name] = el.value; } return out; };
  const changed = () => { clearTimeout(qsfScreenState.timer); qsfScreenState.timer = setTimeout(() => { qsfScreenState.form = read(); qsfScreenRun(true); }, 250); };
  form.oninput = changed;
  form.onsubmit = (e) => { e.preventDefault(); changed(); };
  $("#qsfscreenreset").onclick = () => { qsfScreenState.form = {}; qsfScreenBuild(); };
  $("#qsfscreencsv").onclick = qsfScreenCsv;
  qsfScreenRun(true);
}

async function qsfScreenRun(fresh) {
  const body = $("#qsfscreenbody"); if (!body) return;
  if (fresh) qsfScreenState.shown = QSF_SCREEN_PAGE;
  const token = ++qsfScreenState.token, mk = state.market;
  let d;
  try { d = await api(`/api/qsf/screen?${qsfScreenQuery(qsfScreenState.shown, 0)}`); }
  catch (e) { if (token === qsfScreenState.token) body.innerHTML = `<div class="empty">조건을 읽지 못했습니다: ${esc(e.message)}</div>`; return; }
  if (token !== qsfScreenState.token || mk !== state.market) return;
  if (d.status !== "REAL") { $("#qsfscreencount").textContent = ""; body.innerHTML = `<div class="empty">아직 스캔 기록이 없습니다.</div>`; return; }
  $("#qsfscreencount").textContent = `${QSF_STRAT[d.strategy]} ${d.total}개 중 ${d.matched}개 · 기준 ${d.session}${d.missing_value ? ` · 값이 없어 뺀 종목 ${d.missing_value}개` : ""}`;
  if (!d.matched) { body.innerHTML = `<div class="empty">조건에 맞는 종목이 없습니다.</div>`; return; }
  const head = QSF_SCREEN_COLS.map(([k, label]) => { const on = qsfScreenState.sort === k;
    return `<th aria-sort="${on ? (qsfScreenState.order === "desc" ? "descending" : "ascending") : "none"}"><button type="button" class="qs-sort" data-sort="${k}">${label}${on ? (qsfScreenState.order === "desc" ? " ▼" : " ▲") : ""}</button></th>`; }).join("");
  const rows = d.rows.map((r) => `<tr><td class="l"><button type="button" class="qs-open" data-t="${esc(r.ticker)}"><b>${esc(r.ticker)}</b> <span class="meta" style="margin:0">${esc(r.name || "")}</span></button>${r.high_risk ? " " + qsfRiskTag() : ""}${qsfFilingTags(r.filing_events)}</td>
      <td class="num">${qsfNum(r.score)}</td>${Object.values(QSF_SCREEN_DOMAIN).map((k) => `<td class="num">${qsfNum((r.domains || {})[k], 0)}</td>`).join("")}
      <td class="l">${qsfLabel(r)}</td><td class="l">${esc(QSF_CONF[r.confidence] || "")}</td><td class="l">${esc(QSF_ENTRY[r.entry_status] || "")}${r.gates.length ? `<div class="meta" style="margin:0">${r.gates.map((g) => esc(QSF_GATE[g] || g)).join(", ")}</div>` : ""}</td></tr>`).join("");
  body.innerHTML = `<div class="tbl-wrap"><table class="qs-table"><thead><tr><th class="l">종목</th>${head}<th class="l">판단</th><th class="l">신뢰도</th><th class="l">진입과 게이트</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${d.matched > d.rows.length ? `<button type="button" id="qsfscreenmore" style="margin-top:10px">${d.matched - d.rows.length}개 더 보기</button>` : ""}`;
  body.querySelectorAll(".qs-sort").forEach((b) => { b.onclick = () => { const k = b.dataset.sort;
    qsfScreenState.order = qsfScreenState.sort === k && qsfScreenState.order === "desc" ? "asc" : "desc"; qsfScreenState.sort = k; qsfScreenRun(false); }; });
  body.querySelectorAll(".qs-open").forEach((b) => { b.onclick = () => { qsfEvaluate(b.dataset.t, mk); $("#qsfmsg").scrollIntoView({ block: "start" }); }; });
  const more = $("#qsfscreenmore");
  if (more) more.onclick = () => { qsfScreenState.shown += QSF_SCREEN_PAGE; qsfScreenRun(false); };
}

// 스프레드시트가 값의 첫 글자를 수식으로 읽지 못하게 앞에 작은따옴표를 붙입니다.
function qsfCsvCell(v) {
  if (v === null || v === undefined) return "";
  const s = typeof v === "number" ? String(v) : String(v).replace(/^[=+\-@\t\r]/, (c) => "'" + c);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

async function qsfScreenCsv() {
  const msg = $("#qsfscreencount");
  let d;
  try { d = await api(`/api/qsf/screen?${qsfScreenQuery(2000, 0)}`); } catch (e) { msg.textContent = "저장 실패: " + e.message; return; }
  if (d.status !== "REAL") { msg.textContent = "저장할 스캔 기록이 없습니다."; return; }
  const round = (v) => (typeof v === "number" ? Math.round(v * 10) / 10 : v);
  const lines = [["기준일", "전략", "코드", "이름", "점수", "기술", "재무", "위험", "이벤트", "판단", "신뢰도", "진입", "게이트", "가격", "자금조달 결정", "자사주 취득", "변동성 높음"].join(",")];
  for (const r of d.rows) {
    const dom = r.domains || {}, mark = r.filing_events;
    const marks = d.market === "KR" ? [mark && mark.financing ? "예" : "", mark && mark.buyback ? "예" : "", r.high_risk ? "예" : ""] : ["", "", ""];
    lines.push([d.session, QSF_STRAT[d.strategy], r.ticker, r.name, round(r.score), round(dom.TECHNICAL), round(dom.FUNDAMENTAL), round(dom.RISK), round(dom.EVENTS), r.action_label, QSF_CONF[r.confidence], QSF_ENTRY[r.entry_status], r.gates.map((g) => QSF_GATE[g] || g).join(" / "), r.price, ...marks].map(qsfCsvCell).join(","));
  }
  const url = URL.createObjectURL(new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url; a.download = `screen_${d.market}_${d.strategy}_${d.session}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ------------------------------------------------------------------ 당일 점검
async function qsfToday(el, t, market) {
  el.innerHTML = '<div class="meta">당일 시세·공시·뉴스를 불러오는 중…</div>';
  try {
    const d = await api(`/api/today?t=${encodeURIComponent(t)}&market=${market}`);
    if (el.isConnected) el.innerHTML = qsfTodayHtml(d);
  } catch (e) {
    if (!el.isConnected) return;
    const offline = e instanceof TypeError;      // fetch rejects this way when the local server does not answer
    el.innerHTML = `<div class="err">${offline ? "터미널 서버가 응답하지 않아 당일 점검을 불러오지 못했습니다. 서버가 켜져 있는지 확인한 뒤 다시 시도하세요." : `당일 점검을 불러오지 못했습니다: ${esc(ERR_KO[e.message] || e.message)}`}</div>
      <button type="button" class="qsf-retry" style="margin-top:6px">다시 시도</button>`;
    el.querySelector(".qsf-retry").onclick = () => qsfToday(el, t, market);
  }
}
function qsfTodayHtml(d) {
  const q = d.quote, m = d.market, f = d.filings, n = d.news;
  const quote = q.status === "UNAVAILABLE" ? '<div class="empty">시세를 받지 못했습니다.</div>' : `<div class="kv">
      <div><span>${q.intraday ? "현재가 (지연, 장중)" : `종가 (${esc(q.date)})`}</span><b class="num">${qsfPrice(q.price, m)}</b></div>
      <div><span>전 거래일 대비</span><b>${pct(q.change_pct)}</b></div>
      <div><span>시가 갭</span><b>${pct(q.gap_pct)}</b></div>
      <div><span>같은 날 시장${d.bench ? ` (${esc(d.bench.name)})` : ""}</span><b>${d.bench ? pct(d.bench.change_pct) : DASH}</b></div>
      <div><span>거래량 / ${isNum(q.volume_ratio) ? "20일 평균 대비" : q.intraday ? "장중 누적" : "평균 대비"}</span><b class="num">${isNum(q.volume) ? q.volume.toLocaleString("ko-KR") : DASH}${isNum(q.volume_ratio) ? ` (${q.volume_ratio.toFixed(1)}배)` : ""}</b></div></div>
    <div class="meta">점수 기준일은 ${esc(d.score_session || "확인 불가")}입니다.${q.intraday ? " 오늘 움직임은 점수에 반영되지 않았습니다." : ""}${q.status === "STALE" ? " 시세가 오래되었습니다." : ""}${q.behind_market ? ` <b>시세 제공처의 이 종목 자료가 시장(${esc(q.market_date)})보다 ${q.behind_market}거래일 늦습니다.</b>` : ""}</div>`;
  const warn = d.events_status !== "REAL" ? '<div class="meta">공시 경고를 확인하지 못했습니다.</div>'
    : d.warnings.length ? `<ul class="rec-alerts">${d.warnings.map((w) => `<li class="${esc(w.level)}">${esc(w.date)} ${esc(w.label)}</li>`).join("")}</ul>`
    : '<div class="meta">점수 기준일 이후 새로 확인된 공시 경고는 없습니다.</div>';
  const filings = f.items && f.items.length ? `<ul class="qsf-list">${f.items.map((x) => `<li>${esc(x.filing_date || "")} ${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.form || "공시")}</a>` : esc(x.form || "공시")}${x.description ? ` <span class="meta" style="margin:0">${esc(x.description)}</span>` : ""}</li>`).join("")}</ul>`
    : `<div class="meta">${f.status === "UNAVAILABLE" ? `공시를 받지 못했습니다${f.reason ? `: ${esc(f.reason)}` : ""}` : "점수 기준일 이후 공시가 없습니다."}</div>`;
  const news = n.status === "UNAVAILABLE" ? `<div class="meta">뉴스를 받지 못했습니다${n.error === "NO_NAME" ? " (종목명을 찾지 못함)" : ""}.</div>`
    : n.items.length ? `${n.status === "STALE" ? '<div class="meta">새 뉴스를 받지 못해 이전에 받은 목록을 보여 줍니다.</div>' : ""}<ul class="qsf-news">${n.items.map((x) => `<li><a href="${esc(x.link)}" target="_blank" rel="noopener noreferrer">${esc(x.title)}</a><span class="meta" style="margin:0">${esc(x.source || "")} · ${x.published ? when(x.published) : "시각 없음"}</span></li>`).join("")}</ul><div class="meta">출처: ${esc(n.provider || "")} · 받아온 시각 ${when(n.fetched_at)}</div>`
    : '<div class="meta">최근 뉴스가 없습니다.</div>';
  return `<div class="qsf-today"><h3>시세</h3>${quote}<h3>공시 경고</h3>${warn}<h3>최근 공시</h3>${filings}<h3>뉴스 제목</h3>${news}<div class="meta">${esc(d.note)}</div></div>`;
}

async function qsfValidation() {
  const box = $("#qsfvalid"); if (!box) return;
  const d = await api("/api/qsf/validation").catch(() => null);
  if (!d) return;
  const rows = Object.entries(d.cohorts).map(([k, c]) => { const first = Object.values(c.horizons)[0];
    return `<tr><td class="l"><b>${esc(k)}</b></td><td class="num">${c.snapshots}</td><td class="num">${c.sessions}</td><td class="num">${first.independent_samples.toFixed(1)}</td><td class="l">${esc(first.verdict)}</td></tr>`; }).join("");
  box.innerHTML = `<div class="panel"><h2>전향 검증 ${d.integrity.status === "OK" ? badge("REAL") : badge("UNAVAILABLE")}</h2>
    <div class="tbl-wrap"><table><thead><tr><th class="l">코호트</th><th>기록</th><th>거래일</th><th>독립 표본(최단 기간)</th><th class="l">판단</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="meta">코호트를 합치지 않습니다. 독립 표본 12개 전에는 점수가 수익을 예측한다고 판단하지 않습니다. 상세: <code>python app.py qsf validate</code></div></div>`;
}

RENDER.qsf = renderQsf;
