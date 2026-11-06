// QSF 1.1 score tab.  Every colour comes with a text label; score and confidence are always shown separately.
const QSF_ACTION_CLASS = { BUY: "act-buy", SELL: "act-sell", AVOID: "act-sell", REDUCE: "act-reduce", HOLD: "act-hold", WATCH: "act-hold", INSUFFICIENT_DATA: "act-hold", BLOCKED: "act-hold" };
const QSF_STRAT = { SWING: "스윙", LONG_TERM: "장기" };
const QSF_ENTRY = { ENTRY_NOW: "지금 진입 가능 구간", WAIT_FOR_PULLBACK: "눌림 대기", WAIT_FOR_BREAKOUT_CONFIRMATION: "돌파 확인 대기", WAIT_FOR_EARNINGS: "실적 발표 대기", OVERVALUED_AT_CURRENT_PRICE: "현재 가격 고평가", NO_VALID_ENTRY_SETUP: "유효한 진입 근거 없음" };
const QSF_CONF = { HIGH: "높음", MEDIUM: "보통", LOW: "낮음", INSUFFICIENT: "부족" };
const QSF_EXIT = { HOLD: "보유", HOLD_AND_REVIEW: "보유하며 재검토", PARTIAL_TAKE_PROFIT: "일부 차익 실현 검토", REDUCE: "비중 축소 검토", EXIT: "청산 검토", THESIS_INVALIDATED: "투자 논리 무효", TIME_STOP_REVIEW: "시간 손절 재평가" };
const qsfState = { get market() { return state.market; }, strategy: "SWING", detail: null };

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
    <div id="qsfdetail"></div><div id="qsfrank"></div><div id="qsfvalid"></div>`;
  $("#qsfform").onsubmit = (e) => { e.preventDefault(); const t = $("#qsfticker").value.trim().toUpperCase(); if (t) { setMarket(marketOf(t)); qsfEvaluate(t, qsfState.market); } };
  qsfRank();
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

function qsfDrawDetail(d) {
  const p = d.p6_reference;
  $("#qsfdetail").innerHTML = `<div class="panel"><h2>${esc(d.ticker)} ${esc(d.name || "")} <span class="badge">${d.market === "US" ? "미국" : "한국"}</span></h2>
    ${p ? `<div class="meta">P6-11B 참고: ${p.status !== "REAL" ? "기록 없음" : p.in_top5 ? `최근 스캔 상위 5 (${p.rank}위)` : "최근 스캔 상위 5 아님"} · 별도 모델이며 점수에 합치지 않습니다.</div>` : ""}
    <div class="qsf-cards">${Object.values(d.cards).map(qsfCard).join("")}</div></div>`;
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

async function qsfRank() {
  const box = $("#qsfrank"); if (!box) return;
  const mk = state.market;
  const d = await api(`/api/qsf/latest?market=${mk}`).catch(() => null);
  if (mk !== state.market) return;
  if (!d || d.status !== "REAL") { box.innerHTML = `<div class="panel"><h2>순위</h2><div class="empty">아직 스캔 기록이 없습니다. <code>python app.py qsf scan</code> 또는 매일 자동 실행 후 표시됩니다.</div></div>`; return; }
  const rows = d.rows.filter((r) => r.strategy === qsfState.strategy).slice(0, 50);
  box.innerHTML = `<div class="panel"><h2>순위 <span class="badge">${esc(d.session)}</span>
      <select id="qsfstrat" aria-label="전략"><option value="SWING">스윙</option><option value="LONG_TERM">장기</option></select></h2>
    <div class="tbl-wrap"><table><thead><tr><th class="l">종목</th><th>점수</th><th class="l">판정</th><th>신뢰도</th><th>반영률</th><th class="l">진입</th><th class="l">게이트</th></tr></thead>
    <tbody>${rows.map((r) => `<tr class="click" data-qsf="${esc(r.ticker)}"><td class="l"><b>${esc(r.ticker)}</b> <span class="meta" style="margin:0">${esc(r.name || "")}</span></td><td class="num">${qsfNum(r.score)}</td><td class="l">${qsfLabel(r)}</td><td>${QSF_CONF[r.confidence]}</td><td class="num">${(r.coverage * 100).toFixed(0)}%</td><td class="l">${QSF_ENTRY[r.entry_status] || ""}</td><td class="l">${r.gates.length ? r.gates.map(esc).join(", ") : "없음"}</td></tr>`).join("")}</tbody></table></div>
    <div class="meta">${d.tickers}종목 평가 · 생성 ${esc((d.generated_at || "").slice(0, 16))} UTC</div></div>`;
  $("#qsfstrat").value = qsfState.strategy;
  $("#qsfstrat").onchange = (e) => { qsfState.strategy = e.target.value; qsfRank(); };
  box.querySelectorAll("[data-qsf]").forEach((tr) => { tr.onclick = () => { qsfEvaluate(tr.dataset.qsf, qsfState.market); window.scrollTo(0, 0); }; });
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
