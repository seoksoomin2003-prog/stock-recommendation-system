// QSF score tab.  Every colour comes with a text label; score and confidence are always shown separately.
const QSF_ACTION_CLASS = { BUY: "act-buy", SELL: "act-sell", AVOID: "act-sell", REDUCE: "act-reduce", HOLD: "act-hold", WATCH: "act-hold", INSUFFICIENT_DATA: "act-hold", BLOCKED: "act-hold" };
const QSF_STRAT = { SWING: "스윙", LONG_TERM: "장기" };
const QSF_ENTRY = { ENTRY_NOW: "지금 진입 가능 구간", WAIT_FOR_PULLBACK: "눌림 대기", WAIT_FOR_BREAKOUT_CONFIRMATION: "돌파 확인 대기", WAIT_FOR_EARNINGS: "실적 발표 대기", OVERVALUED_AT_CURRENT_PRICE: "현재 가격 고평가", NO_VALID_ENTRY_SETUP: "유효한 진입 근거 없음" };
// A long-term card's ENTRY_NOW says only that no rule blocks entry: 61% of US long cards carried it, so it is not a timing signal
// and is not named like one (user decision 2026-11-23).  The swing one has passed a reward-to-risk test and keeps its name.
const qsfEntry = (status, strategy) => (status === "ENTRY_NOW" && strategy === "LONG_TERM" ? "진입을 막는 조건 없음" : QSF_ENTRY[status] || "");
// A scored factor without data: the score is computed from the rest, which the rank alone does not show.
const qsfMissTag = (r) => (!r.missing_factors ? "" : ` <span class="badge info" title="점수에 드는 요인 가운데 ${r.missing_factors}개는 자료가 없어 나머지로만 계산했습니다.${r.band_held_back ? " 없는 부분을 '보통'으로 치면 구간이 내려가, 더 낮은 구간으로 보여 줍니다." : ""} 자료가 없다는 것은 좋다는 뜻이 아닙니다.">자료 없는 요인 ${r.missing_factors}</span>`);
const QSF_CONF = { HIGH: "높음", MEDIUM: "보통", LOW: "낮음", INSUFFICIENT: "부족" };
const QSF_EXIT = { HOLD: "보유", HOLD_AND_REVIEW: "보유하며 재검토", PARTIAL_TAKE_PROFIT: "일부 차익 실현 검토", REDUCE: "비중 축소 검토", EXIT: "청산 검토", THESIS_INVALIDATED: "투자 논리 무효", TIME_STOP_REVIEW: "시간 손절 재평가" };
const qsfState = { get market() { return state.market; }, strategy: "SWING", view: (() => { try { return localStorage.getItem("qsfView") || "rank"; } catch (e) { return "rank"; } })(), fresh: {}, detail: null, evals: {}, rankToken: 0, evalToken: 0 };

function qsfClass(a, score) {
  if (a === "AVOID" && score !== null && score >= 40) return "act-reduce";   // 40-54.99 is the orange band; red starts below 40
  return QSF_ACTION_CLASS[a] || "act-hold";
}
// Tables show whole scores (UI batch 1, user decision 2026-11-23); the stored score, the sort and the band edges are unchanged.
// Within one point of a band edge a mark says the band can turn on a small move; the edges come from the server, not this file.
function qsfInt(v) { return isNum(v) ? Number(v).toFixed(0) : DASH; }
function qsfNear(score, edges) {
  if (!isNum(score) || !Array.isArray(edges)) return "";
  const e = edges.find((x) => Math.abs(score - x) <= 1);
  return isNum(e) ? ` <span class="badge near-edge" title="점수 ${Number(score).toFixed(1)}점이 구간 경계 ${e}점에서 1점 안입니다. 작은 변화로 구간이 바뀔 수 있습니다.">경계 근처</span>` : "";
}
function qsfNum(v, d = 1) { return v === null || v === undefined ? DASH : Number(v).toFixed(d); }
function qsfPrice(v, market) { return v === null || v === undefined ? DASH : Number(v).toLocaleString("ko-KR", { maximumFractionDigits: market === "KR" ? 0 : 2 }); }
function qsfLabel(c) {
  return `<span class="qsf-act ${qsfClass(c.action, c.score)}"><i></i>${esc(c.action_label)}</span>`;
}
// 시장 상태: 어떤 점수에도 들어가지 않는 값(QSF-1.4.0). 종목 카드, 순위, 주문 계획이 같은 줄을 쓴다.
const QSF_STATE_FACTOR = { vix_regime: "VIX", vix_term: "VIX 기간 구조", credit_spread: "하이일드 스프레드", index_trend_breadth: "지수 추세·시장 폭", vkospi_regime: "VKOSPI",
  index_trend: "지수 추세", breadth: "시장 폭", usdkrw_regime: "원/달러", credit_liquidity: "신용 스프레드" };
function qsfMarketState(ms) {
  if (!ms || ms.score_100 === null || ms.score_100 === undefined) return `<div class="qsf-state meta"><b>시장 상태</b>: 자료 없음 · 종목 점수에는 들어가지 않습니다.${ms && ms.size_factor < 1 ? ` <span class="badge risk-note">읽을 수 없어 나쁜 날로 취급 · 새 주문 크기 ${(ms.size_factor * 100).toFixed(0)}%</span>` : ""}</div>`;
  const bad = ms.state !== "FAVOURABLE";
  const parts = (ms.factors || []).map((f) => `${QSF_STATE_FACTOR[f.factor] || esc(f.factor)} ${f.normalized === null || f.normalized === undefined ? "없음" : (f.normalized * 100).toFixed(0)}`).join(" · ");
  const cut = bad && ms.size_factor < 1 ? ` <span class="badge risk-note">새 주문 크기 ${(ms.size_factor * 100).toFixed(0)}%</span>` : "";
  return `<div class="qsf-state my-2"><div><b>시장 상태</b> <b class="num">${ms.score_100.toFixed(0)}</b><small>/100</small> <span class="badge${bad ? " risk-note" : ""}">${esc(ms.label)}</span>${cut}
    <span class="meta m0">점수 미반영 · ${ms.mid} 미만이면 나쁨${ms.state === "UNKNOWN" ? " · 요인의 절반 이상이 비어 이 값은 읽지 않습니다" : ""}${ms.session ? ` · ${esc(ms.session)} 기록` : ""}</span></div>
    ${parts ? `<div class="meta mt-1">요인(0~100): ${parts}</div>` : ""}<div class="meta mt-1">${esc(ms.note || "")}</div></div>`;
}
// 점수 탭 머리의 한 줄 상태 띠(2차 묶음 P1-8, 사용자 결정 2026-11-23).  시장 상태의 짧은 글: 띠와 주문 계획이 씁니다.
// 나쁜 날의 '새 주문 크기' 경고는 펼치지 않아도 같은 크기로 보입니다.  전체 설명(qsfMarketState)은 띠를 펼친 곳 한 군데에만 둡니다.
function qsfStateShort(ms) {
  if (!ms || ms.status === "UNAVAILABLE") return "시장 상태 읽지 못함";
  const cut = isNum(ms.size_factor) && ms.size_factor < 1 ? ` <span class="badge risk-note">새 주문 크기 ${(ms.size_factor * 100).toFixed(0)}%</span>` : "";
  if (!isNum(ms.score_100)) return `시장 상태 자료 없음${cut ? ` · 나쁜 날로 취급${cut}` : ""}`;
  const bad = ms.state !== "FAVOURABLE";
  return `시장 상태 <b class="num">${ms.score_100.toFixed(0)}</b>/100 <span class="badge${bad ? " risk-note" : ""}">${esc(ms.label)}</span>${bad ? cut : ""}`;
}
async function qsfStrip() {
  const mk = state.market, full = $("#qsfstatefull"), short = $("#qsfstripstate");
  const ms = await api(`/api/qsf/market-state?market=${mk}`).catch(() => null);
  if (mk !== state.market || !full || !full.isConnected) return;
  short.innerHTML = qsfStateShort(ms && ms.status === "REAL" ? ms : null);
  full.innerHTML = ms && ms.status === "REAL" ? qsfMarketState(ms) : '<div class="meta">시장 상태를 불러오지 못했습니다.</div>';
}
function qsfBar(v) {
  if (v === null || v === undefined) return '<span class="missing">데이터 없음</span>';
  const tone = v >= 70 ? "act-buy" : v >= 55 ? "act-hold" : v >= 40 ? "act-reduce" : "act-sell";
  return `<span class="qsf-bar ${tone}"><i style="width:${Math.max(2, Math.min(100, v))}%"></i></span> <b class="num">${v.toFixed(0)}</b>`;
}

// The score tab shows one part at a time; the choice is remembered on this browser only.
const QSF_VIEWS = { rank: "오늘 순위", screen: "스크리너", exec: "주문 계획·모의 장부", track: "추적·검증" };
function qsfSetView(v) {
  if (!QSF_VIEWS[v]) v = "rank";
  qsfState.view = v;
  document.querySelectorAll("#tab-qsf [data-view]").forEach((el) => { el.hidden = el.dataset.view !== v; });
  document.querySelectorAll("#qsfview button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
  try { localStorage.setItem("qsfView", v); } catch (e) { /* private mode: the view is simply not remembered */ }
  qsfLoadView(v);
}
// A view is fetched when first shown, and again after the market or strategy changes; hidden views cost nothing.
const QSF_LOADERS = {
  rank: () => { qsfRank(); qsfCap(); qsfChanges(); },
  screen: () => ($("#qsfscreenform") ? qsfScreenRun(true) : qsfScreenBuild()),
  exec: () => { qsfPlan(); qsfPaper(); },
  track: () => { qsfReadings(); qsfTop3(); fcTrack(); qsfMethod(); qsfRegime(); qsfLookahead(); qsfValidation(); },
};
function qsfLoadView(v) {
  if (qsfState.fresh[v]) return;
  qsfState.fresh[v] = true;
  QSF_LOADERS[v]();
}
function qsfMarkStrategy() { document.querySelectorAll("#qsfstratseg button").forEach((b) => b.classList.toggle("on", b.dataset.s === qsfState.strategy)); }
function qsfSetStrategy(s) {
  if (s === qsfState.strategy) return;
  qsfState.strategy = s; qsfMarkStrategy();
  qsfState.fresh = {};
  qsfLoadView(qsfState.view);
}

// 최신 스캔 응답(/api/qsf/latest)은 시장마다 5분 동안 기억합니다.  스윙·장기 두 순위가 한 응답에 들어 있어 전환할 때 다시 받지 않습니다.
// 수집이 끝나거나 '화면 새로 고침'을 누르면 버립니다 (collect.js).
const QSF_LATEST_TTL_MS = 5 * 60 * 1000;
const qsfLatestCache = {};          // 시장 -> { at, promise }
function qsfLatest(mk) {
  const hit = qsfLatestCache[mk];
  if (hit && Date.now() - hit.at < QSF_LATEST_TTL_MS) return hit.promise;
  const entry = { at: Date.now(), promise: api(`/api/qsf/latest?market=${mk}`) };
  const forget = () => { if (qsfLatestCache[mk] === entry) delete qsfLatestCache[mk]; };
  entry.promise.then((d) => { if (!d || d.status !== "REAL") forget(); }, forget);          // 실패와 '기록 없음'은 기억하지 않습니다
  qsfLatestCache[mk] = entry;
  return entry.promise;
}
function qsfDropLatest() { Object.keys(qsfLatestCache).forEach((k) => delete qsfLatestCache[k]); }

// What the stored one-run historical checks said, next to the score.  Numbers come from report files; nothing is computed here.
const QSF_STRATEGY_NAME = { SWING: "스윙", LONG_TERM: "장기" };
function qsfWhyHtml(r) {
  const why = r.why || [];
  if (!why.length) return "";
  const p1 = (v) => (isNum(v) ? pct(v * 100, 1) : DASH), n3 = (v) => (isNum(v) ? (v > 0 ? "+" : "") + v.toFixed(3) : DASH), share = (v) => (isNum(v) ? (v * 100).toFixed(1) + "%" : DASH);
  const checks = (r.checks || []).map((c) => `<tr><td class="l">${esc(c.label)}</td><td class="l">${esc(c.need)}</td><td class="l">${esc(c.value)}</td><td class="l">${c.passed ? "충족" : "<b>미달</b>"}</td></tr>`).join("");
  const domains = (r.domains || []).map((x) => `<tr><td class="l">${esc(x.name)}</td><td>${share(x.pair_win)}</td><td>${isNum(x.t) ? x.t.toFixed(2) : DASH}</td><td>${n3(x.early_ic)}</td><td>${n3(x.late_ic)}</td></tr>`).join("");
  const bands = (r.bands || []).map((x) => `<tr><td class="l">${esc(x.band)}점</td><td>${isNum(x.n) ? x.n.toLocaleString() : DASH}</td><td>${p1(x.vs_average)}</td><td>${p1(x.vs_index_net)}</td><td>${share(x.beat_average_rate)}</td></tr>`).join("");
  return `<tr class="qsf-why"><td colspan="7" class="l"><div>${why.slice(0, 2).map(esc).join(" ")}</div>
    <details><summary>판정 근거 자세히 (다섯 조건 중 ${r.checks_passed}개 충족)</summary>
      ${why.length > 2 ? `<ul>${why.slice(2).map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
      <div class="tbl-wrap"><table><thead><tr><th class="l">사전에 정한 조건</th><th class="l">기준</th><th class="l">실제 (전반 / 후반)</th><th class="l">결과</th></tr></thead><tbody>${checks}</tbody></table></div>
      ${domains ? `<div class="meta">영역 하나만으로 같은 시험을 본 결과입니다. 판정에는 쓰지 않습니다. t값이 2.24보다 작으면 우연과 구별되지 않습니다(겹치는 표본에서는 그보다 높아야 합니다: 앞으로의 판정은 표본 구조에 맞춘 기준을 씁니다).</div>
      <div class="tbl-wrap"><table><thead><tr><th class="l">영역</th><th>높은 점수가 이긴 비율</th><th>t값</th><th>전반 IC</th><th>후반 IC</th></tr></thead><tbody>${domains}</tbody></table></div>` : ""}
      ${bands ? `<div class="meta">${esc(r.band_note || "")}</div>
      <div class="tbl-wrap"><table><thead><tr><th class="l">점수 구간</th><th>건수</th><th>같은 날 평균 대비</th><th>지수 대비</th><th>평균을 이긴 비율</th></tr></thead><tbody>${bands}</tbody></table></div>` : ""}
    </details></td></tr>`;
}
function qsfForwardHtml(f) {
  const s = f && f.strategies;
  if (!s || !s.SWING || !s.LONG_TERM) return "";
  const one = (name, c) => `${name}은 ${c.horizon}거래일 보유가 끝난 날이 ${c.needed}개가 되는 ${esc(c.expected || "시점")}`;
  return `<div class="meta"><b>이 판정을 바꿀 수 있는 것은 앞으로의 기록뿐입니다.</b> ${esc(f.first)} 거래일부터 매일 점수를 고정해 기록하고 있고 지금 ${s.SWING.recorded}거래일이 쌓였습니다.
    ${one("스윙", s.SWING)}, ${one("장기", s.LONG_TERM)}에 같은 조건으로 한 번 판정합니다. 지난 구간을 기준이나 구성을 바꿔 가며 다시 시험하지는 않습니다. 결과가 좋아 보일 때까지 고치면 그 수치는 근거가 되지 못합니다.</div>`;
}
function qsfRecordHtml(d) {
  if (!d || d.status !== "REAL") return "";
  const p1 = (v) => (isNum(v) ? pct(v * 100, 1) : DASH);
  const span = (r) => (r.first && r.last ? `${r.first.slice(0, 7)} ~ ${r.last.slice(0, 7)}` : "");
  const win = (r) => (isNum(r.pair_win) ? (r.pair_win * 100).toFixed(1) + "%" + (r.pair_win_range ? `<div class="meta m0">${(r.pair_win_range[0] * 100).toFixed(1)}~${(r.pair_win_range[1] * 100).toFixed(1)}%</div>` : "") : DASH);
  const fifths = (r) => (isNum(r.top_fifth_excess) || isNum(r.bottom_fifth_excess) || !isNum(r.spread_net) ? `<td>${p1(r.top_fifth_excess)}</td><td>${p1(r.bottom_fifth_excess)}</td>`
    : `<td colspan="2" title="상위 20%에서 하위 20%를 뺀 수익, 비용 차감 후">차이 ${p1(r.spread_net)}</td>`);
  const rows = d.rows.map((r) => `<tr><td class="l">${QSF_STRATEGY_NAME[r.strategy] || esc(r.strategy)} · ${r.horizon}거래일${r.superseded ? " (이전 구성)" : ""}<div class="meta m0">${esc([r.universe, span(r)].filter(Boolean).join(" · "))}</div></td>
    <td>${win(r)}</td>${fifths(r)}
    <td>${p1(r.buy_excess)}</td><td${r.not_stored_note ? ` title="${esc(r.not_stored_note)}"` : ""}>${isNum(r.universe_return) && isNum(r.market_return) ? `${p1(r.universe_return)} / ${p1(r.market_return)}` : DASH}</td>
    <td class="l">${esc(r.reading_label)}${r.beats_market === false ? " · 시장은 못 이김" : ""}</td></tr>${qsfWhyHtml(r)}`).join("");
  return `<details class="qsf-record"><summary>과거 성적: 이 점수를 얼마나 믿을 수 있나 <span class="fold-hint">표 보기</span></summary>
    <div class="tbl-wrap"><table class="qs-table"><thead><tr><th class="l">점수 · 보유 기간</th><th title="임의의 두 종목 중 점수가 높은 쪽의 수익이 더 좋았던 비율. 50%면 동전 던지기입니다. 아래 작은 숫자는 오차 범위(약 95%)입니다.">높은 점수가 이긴 비율</th>
      <th title="같은 날 스캔한 종목 평균 대비">상위 20%</th><th title="같은 날 스캔한 종목 평균 대비">하위 20%</th><th title="같은 날 스캔한 종목 평균 대비">70점 이상</th>
      <th title="스캔한 종목 전체의 평균 수익과 같은 기간 시장 수익">대상 평균 / 시장</th><th class="l">판정</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${qsfForwardHtml(d.forward)}
    <div class="meta">${esc(d.what)}. ${d.caveats.map(esc).join(" ")} 출처: ${[d.source, ...(d.more_sources || [])].map(esc).join(", ")}</div></details>`;
}
async function qsfLoadRecord() {
  const el = $("#qsfrecord");
  if (!el) return;
  try {
    el.innerHTML = qsfRecordHtml(await api(`/api/qsf/track-record?market=${isKR() ? "KR" : "US"}`));
  } catch (e) {
    el.innerHTML = "";
  }
}

// 긴 화면은 제목만 보이고, 제목을 누르면 펼쳐집니다.  펼친 것은 이 브라우저가 기억합니다.  처음에는 판정 일정만 펼쳐 둡니다.
const QSF_FOLD_OPEN = ["readings"];
function qsfFoldState() { try { const v = JSON.parse(localStorage.getItem("qsfFolds") || "null"); return Array.isArray(v) ? v : QSF_FOLD_OPEN; } catch (e) { return QSF_FOLD_OPEN; } }
function qsfFolds(el) {
  const open = new Set(qsfFoldState());
  el.querySelectorAll(".fold").forEach((f) => f.classList.toggle("open", open.has(f.dataset.fold)));
  el.onclick = (e) => {
    const h = e.target.closest(".fold > div > .panel > h2");
    if (!h || e.target.closest("button, a, input, select")) return;
    const f = h.closest(".fold");
    f.classList.toggle("open");
    try { localStorage.setItem("qsfFolds", JSON.stringify([...el.querySelectorAll(".fold.open")].map((x) => x.dataset.fold))); } catch (err) { /* private mode: not remembered */ }
    if (f.classList.contains("open")) redrawAll();          // 접힌 동안 그리지 못한 그래프를 지금 그립니다
  };
}

// 열어 둔 카드(2차 묶음 P1-9, 사용자 결정 2026-11-23): '닫기'를 누르거나 메뉴로 점수 탭에 돌아오면 한 줄로 접힙니다.
// 카드 링크(qsfOpenCard)와 뒤로·앞으로(#qsf/코드)는 그대로 엽니다.  접으면 주소도 #qsf로 바꿉니다(기록은 늘리지 않음).
function qsfFoldCard() {
  const d = qsfState.detail, box = $("#qsfdetail"), was = qsfState.cardOpen;
  qsfState.cardOpen = false;
  if (!box) return was;
  if (!d || d.market !== state.market) { box.innerHTML = ""; return was; }
  box.innerHTML = `<div class="qsf-reopen"><button type="button" class="ghost">${esc(tickerText(d.ticker, d.name || ""))} 카드 다시 열기</button></div>`;
  box.querySelector("button").onclick = () => { state.card = d.ticker; history.replaceState(null, "", "#" + tabHash("qsf")); qsfDrawDetail(d); };
  if (state.card) { state.card = null; if (state.tab === "qsf") history.replaceState(null, "", "#qsf"); }
  return was;
}

// keep: 성향을 바꾸거나 새 스캔으로 다시 그릴 때는 열어 둔 카드를 그대로 둡니다.  메뉴로 들어오면(keep 없음) 접습니다.
async function renderQsf(keep = false) {
  const el = $("#tab-qsf"), wasOpen = qsfState.cardOpen;
  el.innerHTML = `<details class="qsf-strip" id="qsfstrip"><summary><span class="qsf-strip-items"><span id="qsfstripstate">시장 상태 불러오는 중…</span><span id="qsfstripstance"></span>
      <b>점수 검증: 높은 점수의 수익 근거 아직 없음 · 참고용</b></span> <span class="fold-hint">자세히</span></summary>
    <div id="qsfstatefull"></div>
    <div class="notice qsf-caveat"><b>점수가 높다고 수익이 더 좋았다는 근거는 아직 확인되지 않았습니다. 참고용으로만 쓰세요.</b><br>
    <b>미국 S&P 500 과거 검증(2014~2026)에서 점수가 높을수록 수익이 좋다는 근거를 찾지 못했습니다. 한국 스캔 대상은 2026-11-11부터 시가총액 상위 300종목입니다. 이 대상 안에서 점수는 과거 시험(2019~2026)의 기준에 못 미쳤고(장기 점수는 순위와 약한 양의 관계, 상위 종목은 시장 수준), 이전 대상(거래대금 상위 300)에서는 장기 점수가 한 구간에서만 순위를 설명했으며 그 대상 자체가 시장보다 크게 부진했습니다. 한국 스윙 점수는 2026-11-11에 차트 항목을 뺀 새 구성이라 과거 성적이 없습니다. 2026-11-16부터 네 점수 모두 시장 국면을 빼고 '시장 상태'로 따로 보여 줍니다(종목 순위는 거의 그대로이고 매수 후보 수가 달라집니다). 참고용으로만 쓰세요.</b><br>모델 탭의 기준 모델(미국 종목에 순위를 매겨 상위 5개와 진입·손절 계획을 내는, 규칙이 고정된 모델)과 별개인 규칙 기반 점수이며, 두 결과를 합치지 않습니다. 가중치와 구간은 사전에 정한 연구 기본값입니다. 주문을 실행하지 않고, 투자 자문이 아닙니다.</div>
    <div id="qsfrecord"></div>
    <div id="qsfstance"></div></details>
    <div class="qsf-nav">
      <span class="seg" id="qsfview" role="group" aria-label="보기">${Object.entries(QSF_VIEWS).map(([k, v]) => `<button type="button" data-v="${k}">${v}</button>`).join("")}</span>
      <span class="seg" id="qsfstratseg" role="group" aria-label="전략"><button type="button" data-s="SWING">스윙</button><button type="button" data-s="LONG_TERM">장기</button></span>
    </div>
    <div data-view="rank"><form id="qsfform" class="qsf-form">
      <input id="qsfticker" placeholder="${isKR() ? "종목코드 (예: 005930)" : "티커 (예: AAPL)"}" autocomplete="off" aria-label="종목">
      <button class="btn-primary">평가</button></form><div id="qsfmsg" class="meta"></div><div id="qsfdetail"></div><div id="qsfrank"></div><div class="fold" data-fold="cap"><div id="qsfcap"></div></div><div class="fold" data-fold="changes"><div id="qsfchanges"></div></div></div>
    <div data-view="screen"><div id="qsfscreen"></div></div>
    <div data-view="exec"><div id="qsfplan"></div><div id="qsfpaper"></div></div>
    <div data-view="track"><div class="fold" data-fold="readings"><div id="qsfreadings"></div></div><div class="fold" data-fold="top3"><div id="qsftop3"></div></div><div class="fold" data-fold="fcast"><div id="qsffcast"></div></div>
      <div class="fold" data-fold="method"><div id="qsfmethod"></div></div><div class="fold" data-fold="regime"><div id="qsfregime"></div></div><div class="fold" data-fold="look"><div id="qsflook"></div></div>
      <div class="fold" data-fold="valid"><div id="qsfvalid"></div></div></div>`;
  qsfFolds(el);
  $("#qsfview").querySelectorAll("button").forEach((b) => (b.onclick = () => qsfSetView(b.dataset.v)));
  $("#qsfstratseg").querySelectorAll("button").forEach((b) => (b.onclick = () => qsfSetStrategy(b.dataset.s)));
  qsfState.fresh = {};
  qsfLoadRecord();
  qsfStrip();
  qsfStanceDraw();
  qsfMarkStrategy();
  qsfSetView(qsfState.view);
  $("#qsfform").onsubmit = (e) => { e.preventDefault(); const t = $("#qsfticker").value.trim().toUpperCase(); if (t) { setMarket(marketOf(t)); qsfSetView("rank"); qsfEvaluate(t, qsfState.market); } };
  if (qsfState.opening) qsfState.cardOpen = false;          // 카드 링크로 왔습니다: qsfEvaluate가 곧 그립니다
  else if (keep && wasOpen && qsfState.detail && qsfState.detail.market === state.market) qsfDrawDetail(qsfState.detail);
  else qsfFoldCard();
  prefillTicker($("#qsfticker"));
  state.loaded.qsf = true;          // 같은 시장에서 돌아오면 다시 만들지 않습니다 (qsfReturn).  시장이 바뀌면 setMarket이 지웁니다.
}

// 같은 시장에서 점수 탭으로 돌아왔습니다.  화면을 다시 만들지 않아 펼친 줄, 평가한 카드, 스크롤 위치가 그대로입니다.
// 계좌를 읽는 주문 계획·모의 장부만 다시 읽고, 그 사이 새 스캔이 기록됐으면 그때 한 번 다시 그립니다.
function qsfReturn(scrollY) {
  const folded = !qsfState.opening && qsfFoldCard();
  window.scrollTo(0, folded ? 0 : scrollY);          // 카드를 접어 페이지가 짧아졌으면 맨 위에서 시작합니다
  prefillTicker($("#qsfticker"));
  qsfState.fresh.exec = false;
  if (qsfState.view === "exec") qsfLoadView("exec");
  const mk = state.market, shown = (qsfState.scanMark || {})[mk];
  if (shown === undefined) return;
  qsfLatest(mk).then((d) => {
    if (mk === state.market && state.tab === "qsf" && d && d.status === "REAL" && `${d.session}|${d.generated_at}` !== shown) renderQsf(true);
  }).catch(() => {});
}
RETURN.qsf = qsfReturn;

// 평가한 카드는 주소에 #qsf/코드로 남습니다.  뒤로·앞으로와 새로 고침이 같은 카드로 돌아옵니다 (app.js fromHash).
async function qsfEvaluate(t, market, push = true) {
  const token = ++qsfState.evalToken;
  state.card = t;
  if (push && state.tab === "qsf") location.hash = tabHash("qsf");
  $("#qsfmsg").textContent = `${t} 평가 중… (처음에는 공시를 읽느라 수십 초 걸릴 수 있습니다)`;
  try {
    const d = await api(`/api/qsf/evaluate?t=${encodeURIComponent(t)}&market=${market}`);
    if (token !== qsfState.evalToken || !$("#qsfmsg")) return;          // 그 사이 다른 종목을 평가했습니다
    $("#qsfmsg").textContent = d.status === "REAL" ? "" : `평가할 수 없습니다: ${d.reason}`;
    if (d.status === "REAL") { qsfState.detail = d; if (d.market === state.market) qsfDrawDetail(d); }
  } catch (e) { if (token === qsfState.evalToken && $("#qsfmsg")) $("#qsfmsg").textContent = "평가 실패: " + errKo(e); }
}
// 종목 화면의 '점수 카드' 버튼과 #qsf/코드 주소가 부릅니다: 점수 탭의 오늘 순위 보기에서 그 종목을 평가합니다.
function qsfOpenCard(ticker, push = true) {
  const t = String(ticker).toUpperCase();
  setMarket(marketOf(t), false);
  const kept = !push && state.loaded.qsf && state.card === t && qsfState.detail && qsfState.detail.ticker === t && qsfState.detail.market === state.market;
  state.card = t;
  qsfState.opening = true;
  try { show("qsf", push); } finally { qsfState.opening = false; }
  if (kept) return;                 // 뒤로·앞으로로 같은 카드에 돌아왔습니다: 다시 평가하지 않고 그대로 둡니다
  qsfSetView("rank");
  qsfEvaluate(t, state.market, push);
  window.scrollTo(0, 0);
}

const QSF_RISK_NOTE = "참고용 표시입니다. 점수와 순위에 반영되지 않으며, 이 종목을 피하면 수익이 난다는 검증은 아직 없습니다. 한국 시장 변동성 상위 20%입니다.";
const QSF_DEAL_NOTE = "SEC에 인수·합병 절차 공시가 있는 종목입니다. 인수 가격이 정해지면 주가가 그 값에 묶여 더 오를 여지가 작고, 거래가 깨지면 크게 내릴 수 있습니다. 인수하는 쪽이 낸 공시일 수도 있습니다. 점수에는 들어가지 않습니다.";
const qsfDealTag = (d) => !d ? "" : ` <span class="badge risk-note" title="${QSF_DEAL_NOTE} ${esc(d.label || "")}(${esc(d.form || "")}, ${esc(d.date || "")})">합병 절차 공시 · 참고</span>`;
const qsfRiskTag = () => `<span class="badge risk-note" title="${QSF_RISK_NOTE}">변동성 높음 · 참고</span>`;
const QSF_FILING_NOTE = "참고용 표시입니다. 점수와 순위에 반영되지 않습니다. 최근 252거래일 안의 첫 공시를 제목으로 읽었고, 취소 여부와 규모는 보지 않습니다. 과거 시험에서 자금조달 결정 종목의 평균 수익은 낮았지만, 앞으로의 자료로는 아직 확인되지 않았습니다. 자사주 묶음은 과거에도 시장을 이기지 못했습니다.";
const qsfFilingTags = (f) => !f ? "" : (f.financing ? ` <span class="badge risk-note" title="${QSF_FILING_NOTE}">자금조달 결정 · 참고</span>` : "") + (f.buyback ? ` <span class="badge" title="${QSF_FILING_NOTE}">자사주 취득 · 참고</span>` : "");
const QSF_RANK_NOTE = {
  NO_SCAN: "이 거래일의 전 종목 순위가 아직 없어 상대강도를 벤치마크 대비로 계산했습니다. 스캔이 끝나면 점수가 달라질 수 있습니다.",
  OUTSIDE_UNIVERSE: "스캔 대상이 아닌 종목입니다. 상대강도는 스캔 종목의 수익률 분포에 넣어 계산했습니다.",
  SHORT_HISTORY: "거래 이력이 6개월보다 짧아 상대강도를 벤치마크 대비로 계산했습니다.",
};
// 시세 이력 점검: 점수를 계산한 일봉을 KRX 공식 자료(한국) 또는 거래일 달력(미국)과 맞춰 본 결과입니다. 점수에는 넣지 않습니다.
const QSF_AUDIT_NOTE = "점수는 이 시세로 계산됐습니다. 표시된 날은 고치지 않았으므로 1년 수익률·변동성 같은 값에 영향을 줄 수 있습니다. 한국 일봉은 KRX 공식 자료로 다시 만들며(QSF-1.1.8), 남는 표시는 KRX가 아직 내지 않은 최근 날이나 KRX에 없는 종목입니다.";
function qsfAuditLine(a) {
  if (!a) return "";
  const prov = a.last_bar_provisional ? " 마지막 날 일봉이 아직 확정되지 않았습니다(고가·저가가 시가·종가를 감싸지 않음)." : "";
  if (a.level === "ok") return `<div class="meta">시세 이력 점검(${esc(a.session)}): 문제 없음.${prov} ${esc(a.source)}.</div>`;
  const ex = (a.examples || []).map((e) => `${esc(e.date)}${e.yahoo_pct !== undefined ? ` (${e.yahoo_pct}% / KRX ${e.krx_pct}%)` : e.krx_pct !== undefined ? ` (KRX ${e.krx_pct}%)` : ""}`).join(", ");
  return `<div class="notice">시세 이력 점검(${esc(a.session)}): ${esc(a.text)}${ex ? ` 예: ${ex}.` : ""}${prov} ${QSF_AUDIT_NOTE} <span class="meta m0">${esc(a.source)}</span></div>`;
}
const qsfAuditTag = (a) => (a && a.level !== "ok" ? ` <span class="badge risk-note" title="${esc(a.text)}">시세 이력 확인 필요</span>` : "");
function qsfRiskGradeLine(g) {
  if (!g) return "";
  const pc = (v, n = 1) => (isNum(v) ? (v * 100).toFixed(n) + "%" : DASH), t = g.test || {};
  return `<div class="meta"><b>위험 등급 ${esc(g.name || g.grade)}</b> (위험 점수 ${isNum(g.score) ? g.score.toFixed(0) : DASH} / 100, 높을수록 위험)${g.top_fifth ? ' · <b>스캔 대상 안에서 위험 상위 20%</b>' : " · 스캔 대상 안에서 위험 상위 20% 아님"}. 기준일 ${esc(g.session)}.
    수익이 아니라 앞으로 20거래일의 흔들림과 큰 손실을 가늠하는 참고값이며 점수와 순위에 반영되지 않습니다.
    과거 시험(${esc((t.first || "").slice(0, 4))}~${esc((t.last || "").slice(0, 4))}, 시가총액 상위 300): 위험 점수가 높은 쪽이 실제로 더 흔들린 비율 ${pc(t.pair_win, 0)}, 20거래일 뒤 −15% 이하로 끝난 비율은 위험 상위 20%가 ${pc(t.loss_top)}(전체 ${pc(t.loss_all)}),
    평균 최대 낙폭은 위험 상위 20%가 ${pc(t.drawdown_top)}(하위 20%는 ${pc(t.drawdown_bottom)}). 이미 본 구간의 시험입니다.</div>`;
}
// 3차 묶음 P1-12 (사용자 결정 2026-11-23): 카드와 종목 상세의 묶음은 모두 접고 근거만 펼칩니다.  누가 펼치거나 접으면
// 묶음 종류마다(근거, 계획, 요인 계산, 위원회, 가격 범위, 이력과 기술 정보) 이 브라우저에 기억합니다.  내용과 계산은 그대로입니다.
const QSF_FOLD_KEY = "qse-fold-";
function qsfFoldOpen(key, dflt) {
  try { const v = localStorage.getItem(QSF_FOLD_KEY + key); return v === null ? dflt : v === "1"; } catch (e) { return dflt; }
}
function qsfFold(key, title, body, dflt = false, id = "") {
  return `<details class="qsf-sec" data-fold="${key}"${id ? ` id="${id}"` : ""}${qsfFoldOpen(key, dflt) ? " open" : ""}><summary>${title}</summary><div class="qsf-sec-body">${body}</div></details>`;
}
// toggle은 위로 번지지 않아 문서에서 잡는 단계(capture)로 받습니다.
document.addEventListener("toggle", (ev) => {
  const el = ev.target;
  if (!el || !el.dataset || !el.dataset.fold || !el.isConnected) return;
  try { localStorage.setItem(QSF_FOLD_KEY + el.dataset.fold, el.open ? "1" : "0"); } catch (e) { /* 저장 못 해도 화면은 그대로 */ }
}, true);
// 접힌 묶음의 자료는 처음 펼칠 때 한 번 읽습니다.  이미 펼쳐 둔 묶음이면 바로 읽습니다.
function qsfOnOpen(el, load) {
  if (!el) return;
  if (el.open) { load(); return; }
  const once = () => { if (el.open) { el.removeEventListener("toggle", once); load(); } };
  el.addEventListener("toggle", once);
}
function qsfDrawDetail(d) {
  const p = d.p6_reference;
  $("#qsfdetail").innerHTML = `<div class="panel"><h2>${nameFirst(d.ticker, d.name) ? `${esc(d.name)} <span class="meta m0">${esc(d.ticker)}</span>` : `${esc(d.ticker)} ${esc(d.name || "")}`} <span class="badge">${d.market === "US" ? "미국" : "한국"}</span>${d.high_risk ? " " + qsfRiskTag() : ""}${qsfFilingTags(d.filing_events)}${qsfAuditTag(d.price_audit)} <button type="button" class="ghost qsf-tostock" data-ticker="${esc(d.ticker)}" title="이 종목의 차트·재무·공시 화면을 엽니다">종목 화면</button> <button type="button" class="ghost qsf-close" title="카드를 한 줄로 접습니다. 순위는 그대로입니다.">닫기</button></h2>
    ${d.high_risk ? `<div class="meta">${QSF_RISK_NOTE} 기준일 ${esc(d.high_risk.session)}.</div>` : ""}
    ${d.filing_events ? `<div class="meta">${QSF_FILING_NOTE} 기준일 ${esc(d.filing_events.session)}.</div>` : ""}
    ${(d.deals || []).length ? `<div class="notice">SEC에 인수·합병 절차 공시가 있습니다: ${d.deals.slice(0, 3).map((x) => `${esc(x.label)}(${esc(x.form)}, ${esc(x.date)})`).join(", ")}. 인수 가격이 정해진 종목은 더 오를 여지가 작고 거래가 깨지면 크게 내릴 수 있습니다. 인수하는 쪽이 내는 경우도 있으니 공시 원문을 확인하세요. 점수는 이 공시를 읽지 않습니다.</div>` : ""}
    ${qsfAuditLine(d.price_audit)}
    <div class="qsf-cards">${Object.values(d.cards).map((c) => qsfCard(c)).join("")}</div>
    ${d.committee ? qsfFold("committee", `다섯 투자자와 투자위원회 <span class="meta m0">규칙으로 옮긴 참고 · 점수와 무관</span>`,
      `${icCardHtml(d.committee, d.ticker, d.market)}
    ${d.committee_note ? `<div class="meta"><b>엇갈림</b> ${esc(d.committee_note)}</div>` : ""}`) : ""}
    ${qsfFold("range", `가격 범위 · 예측 층 FC-1 <span class="meta m0">점수에 포함되지 않음</span>`, `<div id="qsffc"><div class="meta">불러오는 중…</div></div>`, false, "qsffcfold")}
    ${qsfFold("tech", `이력과 기술 정보 <span class="meta m0">당일 점검 · 점수 이력 · 위험 등급 · 순위 기준 · P6-11B 참고</span>`, `${qsfRiskGradeLine(d.risk_grade)}
    ${QSF_RANK_NOTE[d.rank_basis] ? `<div class="meta">${QSF_RANK_NOTE[d.rank_basis]}</div>` : ""}
    ${p ? `<div class="meta">P6-11B 참고: ${p.status !== "REAL" ? "기록 없음" : p.in_top5 ? `최근 스캔 상위 5 (${p.rank}위)` : "최근 스캔 상위 5 아님"} · 별도 모델이며 점수에 합치지 않습니다.</div>` : ""}
    <details class="qsf-today-fold" id="qsftodayfold"><summary>당일 점검 (시세·공시·뉴스) <span class="meta m0">점수에 포함되지 않음</span></summary><div id="qsftoday"></div></details>
    <div id="qsfhistory"></div>`, false, "qsftechfold")}</div>`;
  qsfState.cardOpen = true;
  $("#qsfdetail .qsf-close").onclick = () => qsfFoldCard();
  const todayFold = $("#qsftodayfold");          // 펼칠 때 한 번 읽습니다: 공시를 처음 읽는 종목은 오래 걸립니다
  todayFold.addEventListener("toggle", () => { if (todayFold.open && !todayFold.dataset.done) { todayFold.dataset.done = "1"; qsfToday($("#qsftoday"), d.ticker, d.market); } });
  qsfOnOpen($("#qsffcfold"), () => fcStock($("#qsffc"), d.ticker, d.market, d.cards));
  qsfOnOpen($("#qsftechfold"), () => qsfHistory($("#qsfhistory"), d.ticker, d.market));
}

// 기록된 점수 이력: 원장에 남은 값을 그대로 보여 줍니다. 다시 계산하지 않습니다.
async function qsfHistory(box, t, market) {
  const h = await api(`/api/qsf/history?t=${encodeURIComponent(t)}&market=${market}`).catch(() => null);
  if (!box.isConnected || !qsfState.detail || qsfState.detail.ticker !== t) return;
  if (!h || h.status !== "REAL") { box.innerHTML = `<details class="qsf-today-fold"><summary>기록된 점수 이력</summary><div class="empty">${esc((h && h.reason) || "이력을 불러오지 못했습니다.")}</div></details>`; return; }
  const table = (strategy, rows) => {
    const changed = rows.some((r) => r.model_changed);
    const body = rows.slice().reverse().map((r) => `<tr><td class="l">${esc(r.session)}</td><td class="num">${qsfNum(r.score)}</td><td class="l"><span class="qsf-act ${qsfClass(r.action, r.score)}"><i></i>${esc(r.action_label || r.action || "")}</span></td><td class="l">${esc(QSF_CONF[r.confidence] || "")}</td><td class="num">${qsfPrice(r.price, market)}</td><td class="l">${esc(r.model_version || "")}${r.model_changed ? " *" : ""}</td></tr>`).join("");
    return `<h3 class="qc-title">${QSF_STRAT[strategy] || esc(strategy)} <span class="meta m0">${rows.length}개 거래일</span></h3>
      ${changed ? `<div class="meta">* 앞 기록과 모델 버전이 다릅니다. 이 점수 차이에는 수식과 입력 수정이 섞여 있습니다.</div>` : ""}
      <div class="tbl-wrap"><table class="qs-table"><thead><tr><th class="l">거래일</th><th>점수</th><th class="l">판단</th><th class="l">신뢰도</th><th>기록 가격</th><th class="l">모델</th></tr></thead><tbody>${body}</tbody></table></div>`;
  };
  box.innerHTML = `<details class="qsf-today-fold"><summary>기록된 점수 이력</summary><div class="meta">스캔 때 원장에 남긴 값입니다. 최신이 위입니다. 점수가 오르내린 기록이 앞으로의 수익을 말해 주지는 않습니다.</div>
    ${["SWING", "LONG_TERM"].filter((k) => h.strategies[k]).map((k) => table(k, h.strategies[k])).join("")}</details>`;
}

// The holding plan follows the remembered fold like the other sections; the card of a stock the user holds opens it.
// 새로 받지 못해 저장해 둔 자료로 채점한 입력: 무엇을, 며칠 전 자료로, 왜 못 받았는지
function qsfStaleNote(c) {
  const old = (c.provenance && c.provenance.stale) || [];
  if (!old.length) return "";
  const why = { SecPaused: "SEC가 요청을 거절해 10분 동안 묻지 않는 중", EMPTY_RESPONSE: "빈 응답", ConnectionError: "연결 실패", Timeout: "응답 시간 초과", ReadTimeout: "응답 시간 초과" };
  const one = (x) => `${esc(x.what)}${x.age_days === null || x.age_days === undefined ? "" : ` ${x.age_days < 1 ? "하루 안 된" : Math.round(x.age_days) + "일 전"} 자료`}${x.error ? ` (받지 못한 이유: ${esc(why[x.error] || "요청 실패, 오류 종류 " + x.error)})` : ""}`;
  return `<div class="notice"><b>오래된 자료로 채점</b>: 새 자료를 받지 못해 저장해 둔 자료를 썼습니다. ${old.map(one).join(" · ")}. 다시 받아지면 점수가 달라질 수 있습니다.</div>`;
}

// 점수가 읽은 재무의 기준일과, 다른 기간(최근 4분기)의 재무로 계산한 참고 점수 (reports/QSF_FUND_PERIOD_PROTOCOL.md)
function qsfFundPeriodNote(c) {
  const fp = c.fund_period;
  if (!fp || !fp.annual || !fp.trailing) return "";
  const live = fp.live === "TRAILING" ? fp.trailing : fp.annual, other = fp.live === "TRAILING" ? fp.annual : fp.trailing;
  const liveName = fp.live === "TRAILING" ? "최근 4분기" : "연간 보고서", otherName = fp.live === "TRAILING" ? "연간 보고서" : "최근 4분기";
  const age = live.fiscal_end && c.data_date ? Math.round((new Date(c.data_date) - new Date(live.fiscal_end)) / 86400000) : null;
  const head = `재무 기준: ${esc(live.fiscal_end || "확인 불가")}까지 (${liveName}${age === null ? "" : `, ${age}일 지남`})`;
  if (!isNum(other.score)) return `<div class="meta">${head} · ${otherName} 기준 점수는 계산하지 못했습니다.</div>`;
  if (fp.live !== "TRAILING" && !fp.trailing.newer_quarter) return `<div class="meta">${head} · 이보다 새로운 분기 보고서가 없습니다.</div>`;
  const diff = other.score - c.score;
  return `<div class="meta">${head} · <b>${otherName}(${esc(other.fiscal_end || "")}까지) 기준 점수 ${other.score.toFixed(1)}</b> (${diff > 0 ? "+" : ""}${diff.toFixed(1)}) · 참고값입니다. 매일 따로 기록하고 240거래일 뒤 한 번 읽어 정합니다.</div>`;
}

// 근거 균형: 중간(50점)에서 각 요인이 더하거나 뺀 점수. 모든 요인의 값을 더하면 총점 − 50 (terminal/qsf/rank_notes.py).
function qsfBalance(b) {
  if (!b || !isNum(b.points_sum)) return "";
  const li = (x) => `<li><b>${esc(x.label)}</b> <span class="num ${x.points >= 0 ? "up" : "down"}">${x.points >= 0 ? "+" : "−"}${Math.abs(x.points).toFixed(1)}점</span>${x.text ? `<div class="meta m0">${bigInText(esc(x.text))}</div>` : ""}</li>`;
  const side = (title, rows, none) => `<div><h4>${title}</h4>${rows.length ? `<ul>${rows.map(li).join("")}</ul>` : `<div class="meta m0">${none}</div>`}</div>`;
  return `<div class="qsf-balance">${side("점수를 올린 요인", b.plus, "강점으로 칠 요인(0.6 이상)이 없습니다.")}${side("점수를 깎은 요인", b.minus, "약점으로 칠 요인(0.4 이하)이 없습니다.")}
    <div class="meta qb-note">중간(50점)에서 각 요인이 더하거나 뺀 점수입니다. 모든 요인을 더하면 50 ${b.points_sum >= 0 ? "+" : "−"} ${Math.abs(b.points_sum).toFixed(1)} = ${(50 + b.points_sum).toFixed(1)}점.${b.missing.length ? ` 자료가 없어 점수에서 빠진 요인: ${b.missing.map(esc).join(", ")}.` : ""}</div></div>`;
}
function qsfCard(c) {
  const h = c.holding, m = c.market, e = c.entry, names = (c.balance && c.balance.labels) || {};
  // Only the card of a holding's own style carries c.position.
  const factors = c.factors.map((f) => `<tr><td class="l" title="${esc(f.factor)}">${esc(names[f.factor] || f.factor)}</td><td class="num">${f.scored === false ? "참고" : f.weight}</td><td class="num">${f.contribution === null ? "-" : f.contribution.toFixed(1)}</td>
    <td class="l wrap">${bigInText(esc(f.explanation || f.reason || ""))}${f.status === "STALE" ? " (오래된 데이터)" : ""}${f.status === "NOT_APPLICABLE" ? " (해당 없음)" : ""}${f.scored === false ? " (점수 미반영)" : ""}</td></tr>`).join("");
  const horizon = c.strategy === "SWING"
    ? `<dt>예상 보유</dt><dd>약 ${h.expected_sessions}거래일 (범위 ${h.range_sessions[0]}~${h.range_sessions[1]}일)</dd>
       <dt>첫 재평가</dt><dd>${esc(h.first_review)} · 이후 ${h.review_every_sessions}거래일마다</dd>
       <dt>시간 재평가</dt><dd>${esc(h.time_stop_review)} (${esc(h.time_stop_note)})</dd>
       <dt>손절 기준</dt><dd>${qsfPrice(h.stop, m)} · ${esc(h.stop_method || "")}</dd>
       <dt>목표 기준</dt><dd>${qsfPrice(h.target, m)} · ${esc(h.target_method || "")}</dd>
       <dt>비용 반영 손익비</dt><dd>${qsfNum(h.reward_risk, 2)} <span class="meta m0">${esc(h.cost_basis || "")}</span></dd>`
    : `<dt>예상 보유</dt><dd>${h.range_months[0]}~${h.range_months[1]}개월 (강제 종료일 없음)</dd>
       <dt>첫 재평가</dt><dd>${esc(h.first_review)}, 다음 ${esc(h.next_review)} · 분기마다</dd>
       <dt>점검 항목</dt><dd>${h.milestones.map(esc).join(" / ")}</dd>
       <dt>시나리오</dt><dd>${h.scenarios.status === "REAL" ? h.scenarios.cases.map((x) => `${esc(x.case)} ${qsfPrice(x.price, m)} (${esc(x.assumption)})`).join("<br>") : esc(h.scenarios.reason)}</dd>`;
  return `<article class="qsf-card"><header><div><div class="meta m0">${QSF_STRAT[c.strategy]} <span class="tech-id" title="채점 규칙 이름입니다. 기록을 비교할 때 씁니다.">${esc(c.profile)}</span>${c.position ? " · <b>보유 중</b>" : ""}</div>
      <div class="qsf-score num">${c.score === null ? "-" : c.score.toFixed(1)}<small>/100</small></div></div>
      <div>${qsfLabel(c)}<div class="meta mt-1">구간: ${esc(c.band_label)}${c.diagnostic_only ? " · 진단용 점수" : ""}</div></div></header>
    <div class="qsf-meta"><span title="자료가 얼마나 있는지를 말합니다. 맞을 확률이 아닙니다.">신뢰도(자료의 양) <b>${QSF_CONF[c.confidence]}</b></span><span>데이터 반영률 <b>${(c.coverage * 100).toFixed(0)}%</b></span>${isNum(c.input_coverage) && c.input_coverage < c.coverage - 0.005 ? `<span title="요인은 계산됐지만 그 안의 수치 일부가 비어 있습니다. 신뢰도는 이 값도 함께 봅니다.">요인 안 수치 반영률 <b>${(c.input_coverage * 100).toFixed(0)}%</b></span>` : ""}<span title="${esc((c.provenance && c.provenance.price) || "")}">시세 <b>${esc(c.data_date)}</b> ${qsfPrice(c.price, m)}</span><span class="tech-id" title="점수 공식의 버전입니다. 기록을 비교할 때 씁니다.">${esc(c.model_version)}</span></div>
    <div class="qsf-meta qsf-sum"><span>진입 <b>${qsfEntry(e.status, c.strategy)}</b></span>${c.strategy === "SWING" ? `<span>손절 기준 <b class="num">${qsfPrice(h.stop, m)}</b></span><span>목표 기준 <b class="num">${qsfPrice(h.target, m)}</b></span>` : ""}${c.exit ? `<span>보유 종목 <b>${QSF_EXIT[c.exit.action]}</b></span>` : ""}</div>
    ${c.gates.length ? `<div class="notice"><b>위험 게이트 ${c.gates.length}건</b>: ${c.gates.map((g) => esc(g.text)).join(" ")} 점수는 진단용으로 남기지만 실행 대상이 아닙니다.</div>` : ""}
    ${c.earnings_unknown ? `<div class="notice">${esc(c.earnings_unknown)}</div>` : ""}
    ${qsfFold("basis", `근거 <span class="meta m0">점수를 올리고 깎은 요인 · 영역별 점수 · 진입</span>`, `<p>${esc(c.why_summary)}</p>
    ${qsfBalance(c.balance)}
    ${plainBlock(c.plain)}
    ${c.surface_note ? `<div class="meta"><b>엇갈림</b> ${esc(c.surface_note)}</div>` : ""}
    ${qsfStaleNote(c)}${qsfFundPeriodNote(c)}
    <h3>영역별 점수</h3><div class="qsf-domains">${Object.entries(c.domains).filter(([k]) => k !== "REGIME").map(([k, v]) => `<div><span>${esc(v.label)} <small class="meta m0">${v.reference ? "참고 · 점수 미반영" : v.max_points + "점"}${k === "RISK" ? " · 높을수록 좋음" : ""}</small></span>${qsfBar(v.score_100)}</div>`).join("")}</div>
    <h3>진입</h3><p><b>${qsfEntry(e.status, c.strategy)}</b>: ${esc(e.reason)}${e.zone ? ` 기준 구간 ${qsfPrice(e.zone.low, m)}~${qsfPrice(e.zone.high, m)}.` : ""}</p>
    ${c.exit ? `<h3>보유 종목 판단</h3><p><b>${QSF_EXIT[c.exit.action]}</b>: ${esc(c.exit.reason)}</p>` : ""}`, true)}
    ${qsfFold(c.position ? "plan-held" : "plan", "계획 (가설) · 보유 계획과 판단이 바뀌는 조건", `<h3>보유 계획 <span class="meta m0">(가설)</span></h3><dl class="qsf-dl"><dt>진입 예정일</dt><dd>${esc(h.entry_date)}</dd>${horizon}
      <dt>무효화 조건</dt><dd>${h.invalidation.map(esc).join(" / ")}</dd><dt>이 기간의 이유</dt><dd>${h.why.map(esc).join(" / ")}</dd></dl>
    <h3>판단이 바뀌는 조건</h3><ul class="qsf-list">${c.what_would_change.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`, !!c.position)}
    ${c.stability && c.stability.status === "REAL" ? `<div class="meta">직전 기록 ${esc(c.stability.previous_date)} ${c.stability.previous_score.toFixed(1)}점 → 변화 ${c.stability.delta >= 0 ? "+" : ""}${c.stability.delta.toFixed(1)}점${c.stability.large ? " (큰 변화)" : ""}</div>` : ""}
    ${qsfFold("factors", `요인별 계산 (${c.factors.length}개)${c.missing.length ? ` · 빠진 요인 ${c.missing.length}개` : ""} <span class="meta m0">기술 정보</span>`, `<div class="tbl-wrap"><table><thead><tr><th class="l">요인</th><th>배점</th><th>기여</th><th class="l">근거</th></tr></thead><tbody>${factors}</tbody></table></div>`)}
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
    box.innerHTML = `${qsfScanNote(r, c)}${d.price_audit && d.price_audit.level !== "ok" ? qsfAuditLine(d.price_audit) : ""}<div class="qsf-cards">${qsfCard(c)}</div>
      <details class="qsf-today-fold"><summary>당일 점검 (시세·공시·뉴스)</summary><div class="qsf-today-slot"></div></details>`;
    const fold = box.querySelector(".qsf-today-fold");
    fold.addEventListener("toggle", () => { if (fold.open && !fold.dataset.done) { fold.dataset.done = "1"; qsfToday(fold.querySelector(".qsf-today-slot"), r.ticker, market); } });
  } catch (e) { if (box.isConnected) box.innerHTML = `<div class="err">불러오지 못했습니다: ${esc(errKo(e))}</div>`; }
}
// The market's stance (terminal/qsf/stance.py): what the screen calls a candidate and how large the real account's planned
// orders are.  It never changes a score or a record.
const qsfStanceTag = (s, band) => (!s ? "" : s.ok ? ' <span class="badge info" title="지금 고른 성향의 기준을 모두 채운 종목입니다. 점수와 구간은 그대로입니다.">성향 후보</span>'
  : s.why && s.why !== "실행 가능 상태가 아님" && /BUY_CANDIDATE$/.test(band || "") ? ` <span class="badge info" title="매수 후보 구간이지만 지금 고른 성향에서는 후보로 부르지 않습니다: ${esc(s.why)}">성향 밖 · ${esc(s.why)}</span>` : "");
async function qsfStanceDraw() {
  const box = $("#qsfstance"), mk = qsfState.market;
  if (!box) return;
  let d;
  try { d = await api(`/api/qsf/stance?market=${mk}`); } catch (e) { box.innerHTML = ""; return; }
  if (mk !== qsfState.market || !box.isConnected) return;
  const tag = $("#qsfstripstance");
  if (tag) tag.innerHTML = `성향 <b>${esc((d.levels.find((x) => x.level === d.level) || {}).label || d.level)}</b>`;
  const rows = ["후보로 부르는 점수", "자료가 적은 종목", "하루 움직임이 큰 종목", "주문 한 건의 크기", "새 주문 합계", "주문 계획의 후보"].map((h, i) =>
    `<tr><td class="l">${h}</td>${d.levels.map((x) => `<td class="l">${esc(x.what[i].replace(/^[^:]+: /, ""))}</td>`).join("")}</tr>`).join("");
  box.innerHTML = `<div class="qsf-stance"><b>${isKR() ? "한국" : "미국"} 성향</b>
      <span class="seg" role="group" aria-label="성향">${d.levels.map((x) => `<button type="button" data-level="${x.level}" class="${x.level === d.level ? "on" : ""}">${esc(x.label)}</button>`).join("")}</span>
      <span class="meta m0">${d.level === "NORMAL" ? "기본: 아무것도 바꾸지 않은 상태입니다." : `${esc(d.label)}: 후보 표시와 주문 크기가 달라집니다. 점수는 그대로입니다.`}</span>
      <details><summary>단계마다 달라지는 것</summary><div class="tbl-wrap"><table><thead><tr><th class="l"></th>${d.levels.map((x) => `<th class="l">${esc(x.label)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
      <div class="meta">${esc(d.note)} 시장마다 따로 고릅니다. ${esc(d.adverse_note || "")}</div></details>
      ${d.damaged_note ? `<div class="notice">${esc(d.damaged_note)}</div>` : ""}</div>`;
  box.querySelectorAll("button[data-level]").forEach((b) => { b.onclick = async () => {
    if (b.dataset.level === d.level) return;
    try {
      await api("/api/qsf/stance", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ market: mk, level: b.dataset.level }) });
      qsfDropLatest();
      renderQsf(true);
    } catch (e) { notify(errKo(e)); }
  }; });
}
// 순위 표(UI 점검 2026-11-23, 사용자 결정): 50줄 한 표. 줄을 누르면 그 아래에 카드가 펼쳐집니다.
const QSF_RANK_DOMAINS = ["TECHNICAL", "FUNDAMENTAL", "RISK", "EVENTS"];
const QSF_RANK_COLS = 12;
// 순위·스크리너 줄의 표시(2차 묶음 P1-7, 사용자 결정 2026-11-23).  드문 위험 넷(합병 절차, 자금조달 결정, 변동성 상위 20%,
// 시세 이력)은 이름 아래 짧은 문장으로, 흔한 참고(자사주, 자료 양, 빠진 요인, 성향)는 색 없는 작은 칩으로 둡니다.  전체 설명은 title에 있어
// 마우스를 올리거나 폰에서 누르면 보입니다(phone.js taptip).  점수와 순위는 그대로입니다.
function qsfRiskLines(r) {
  const f = r.filing_events || {}, a = r.price_audit, d = r.deal;
  const line = (text, why) => `<div class="qr-risk" title="${why}">${text}</div>`;
  return (d ? line("합병 절차 공시 · 인수 가격에 묶일 수 있음", `${QSF_DEAL_NOTE} ${esc(d.label || "")}(${esc(d.form || "")}, ${esc(d.date || "")})`) : "")
    + (f.financing ? line("자금조달 결정 공시 · 과거 시험에서 평균 수익 낮음", QSF_FILING_NOTE) : "")
    + (r.high_risk ? line("변동성 상위 20% · 크게 흔들릴 수 있음", QSF_RISK_NOTE) : "")
    + (a && a.level !== "ok" ? line("시세 이력 확인 필요 · 계산에 쓴 일봉에 의심 값", esc(a.text || "")) : "");
}
const qsfBuybackChip = (f) => (f && f.buyback ? ` <span class="badge info" title="${QSF_FILING_NOTE}">자사주 취득 · 참고</span>` : "");
function qsfReason(n) {
  if (!n) return DASH;
  const one = (x, up) => (x ? `<div class="${up ? "up" : "down"}">${up ? "▲" : "▼"} ${esc(x.label)} ${up ? "+" : "−"}${Math.abs(x.points).toFixed(1)}</div>` : "");
  return one(n.plus, true) + one(n.minus, false) || '<span class="meta m0">두드러진 요인 없음</span>';
}
function qsfDelta(score, n) {
  if (!n || !isNum(score)) return DASH;
  if (!isNum(n.prev)) return '<span class="meta m0" title="직전 기록 거래일에 이 스타일 점수가 없었습니다">새로</span>';
  const v = score - n.prev;
  return `<span class="num ${v >= 1 ? "up" : v <= -1 ? "down" : "flat"}">${v >= 0.05 ? "+" : v <= -0.05 ? "−" : ""}${Math.abs(v).toFixed(1)}</span>`;
}
function qsfRankRow(r, isTop, n, sector, edges) {
  const out = r.actionability !== "ACTIONABLE", dm = r.domains || {};
  const dom = (k) => `<td class="num w qd qd-col">${isNum(dm[k]) ? `<span class="qd-bar"><i style="width:${Math.max(2, Math.min(100, dm[k]))}%"></i></span>${dm[k].toFixed(0)}` : DASH}</td>`;
  const why = out ? (r.gates.length ? r.gates.map((g) => esc(QSF_GATE[g] || g)).join(", ") : esc(QSF_ACT[r.actionability] || "실행 대상 아님")) : "";
  const entry = `${esc(qsfEntry(r.entry_status, r.strategy || qsfState.strategy) || "")}${why ? `<div class="qr-out">실행 대상 아님 · ${why}</div>` : ""}`;
  return `<tr class="qsf-rrow" data-qsf="${esc(r.ticker)}" tabindex="0" aria-expanded="false">
      <td class="num qr-rank" title="${isNum(r.pct) ? `그날 점수가 나온 종목 가운데 상위 ${r.pct}%` : ""}">${r.rank}${isTop ? '<div><span class="badge ok" title="위험 게이트와 자료 부족을 뺀 점수 상위 3">상위 3</span></div>' : ""}</td>
      <td class="l qr-name">${tickerLabel(r.ticker, r.name)}${r.confidence !== "HIGH" ? ` <span class="badge info" title="자료가 얼마나 있는지를 말합니다. 맞을 확률이 아닙니다.">자료 ${QSF_CONF[r.confidence] || ""}</span>` : ""}${qsfBuybackChip(r.filing_events)}${qsfStanceTag(r.stance, r.band)}${qsfMissTag(r)}${qsfRiskLines(r)}
        <div class="qr-m2">${qsfLabel(r)} ${entry}</div></td>
      <td class="l w">${esc(qsfSector(sector) || "")}</td>
      <td class="num"><b>${qsfInt(r.score)}</b>${qsfNear(r.score, edges)}<div class="qr-md">${qsfDelta(r.score, n)}</div></td><td class="num w qr-dcol">${qsfDelta(r.score, n)}</td>
      ${QSF_RANK_DOMAINS.map(dom).join("")}
      <td class="l w" title="구간: ${esc(r.band_label || "")}">${qsfLabel(r)}</td>
      <td class="l w2">${entry}</td>
      <td class="l qr-why">${qsfReason(n)}</td></tr>
    <tr class="qsf-exp-row" hidden><td colspan="${QSF_RANK_COLS}"><div class="qsf-exp"></div></td></tr>`;
}
async function qsfRank() {
  const box = $("#qsfrank"); if (!box) return;
  const mk = state.market, token = ++qsfState.rankToken;
  let failed = null;
  const [d, nt] = await Promise.all([qsfLatest(mk).catch((e) => { failed = e; return null; }), api(`/api/qsf/rank-notes?market=${mk}`).catch(() => null)]);
  if (token !== qsfState.rankToken || mk !== state.market) return;
  if (failed || !d || d.status !== "REAL") state.loaded.qsf = false;          // 순위를 받지 못했습니다: 다음에 탭을 열 때 다시 그립니다
  if (failed) { box.innerHTML = `<div class="panel"><h2>순위</h2><div class="empty">순위를 불러오지 못했습니다: ${esc(errKo(failed))} 스캔 기록이 없다는 뜻이 아닙니다.</div></div>`; return; }
  if (!d || d.status !== "REAL") { box.innerHTML = `<div class="panel"><h2>순위</h2><div class="empty">아직 스캔 기록이 없습니다. 매일 자동 실행 뒤에 표시됩니다. <button type="button" class="ghost collect-now">지금 수집</button></div></div>`; return; }
  // 카드는 페이지가 열려 있는 동안 기억된다. 스캔이 새로 기록되면 그 시장의 카드를 버려, 새 순위 아래에 이전 스캔의 카드가 나오지 않게 한다.
  const scanMark = `${d.session}|${d.generated_at}`;
  qsfState.scanMark = qsfState.scanMark || {};
  if (qsfState.scanMark[mk] !== scanMark) {
    if (qsfState.scanMark[mk] !== undefined) Object.keys(qsfState.evals).forEach((k) => { if (k.startsWith(`${mk}|`)) delete qsfState.evals[k]; });
    qsfState.scanMark[mk] = scanMark;
  }
  // 상위 n%: 그날 이 시장·스타일로 점수가 나온 종목 가운데 몇 번째인가. 절대 점수와 달리 시장과 공식이 달라도 같은 뜻으로 읽힌다.
  const scoredRows = d.rows.filter((r) => r.strategy === qsfState.strategy), scoredN = scoredRows.filter((r) => isNum(r.score)).length;
  const all = scoredRows.slice(0, 50).map((r, i) => ({ ...r, rank: i + 1, pct: scoredN && isNum(r.score) ? Math.max(1, Math.ceil(((i + 1) / scoredN) * 100)) : null }));
  const top = all.filter((r) => r.actionability === "ACTIONABLE").slice(0, QSF_TOP);
  const notes = nt && nt.status === "REAL" && nt.session === d.session ? nt : null;
  const note = (r) => (notes ? notes.rows[`${r.ticker}|${qsfState.strategy}`] : null);
  const head = `<tr><th class="num">순위</th><th class="l">종목</th><th class="l w">업종</th><th>점수</th><th class="w qr-dcol" title="직전 기록 거래일 점수와의 차이입니다. 1점 미만은 회색입니다. 그 사이 공식이 바뀌었으면 공식 변화도 섞입니다.">점수 변화(전일)</th>
    ${QSF_RANK_DOMAINS.map((k) => `<th class="w qd-col" title="영역 점수(0~100)${k === "RISK" ? ". 높을수록 위험이 낮고 실행하기 쉽습니다(위험이 크다는 뜻이 아님)" : ""}">${QSF_DOMAIN_NAME[k]}</th>`).join("")}<th class="l w">판단</th><th class="l w2">진입</th><th class="l" title="중간(50점)에서 가장 크게 더한 요인과 가장 크게 뺀 요인">가점 / 감점</th></tr>`;
  box.innerHTML = `<div class="panel"><h2>${QSF_STRAT[qsfState.strategy]} 순위 ${all.length}개 <span class="badge">${esc(d.session)}</span></h2>
    <div class="meta">점수순으로 보여 줄 뿐 수익이 더 좋다는 근거는 아닙니다. '상위 3'은 위험 게이트에 걸렸거나 데이터가 부족한 종목을 뺀 위 세 종목입니다.
      줄을 누르면 그 종목 카드가 펼쳐집니다. 순위 숫자에 마우스를 올리면 그날 점수가 나온 ${scoredN}종목 가운데 상위 몇 %인지 보입니다.</div>
    ${d.stance && d.stance.level !== "NORMAL" ? `<div class="meta"><b>성향: ${esc(d.stance.label)}</b> · ${d.stance.line}점 이상인 실행 가능 종목 가운데 이 성향의 조건을 채운 종목에 '성향 후보'를 붙입니다. 점수, 구간, 순위는 그대로입니다.${d.stance.from_record === false ? " 이 스캔은 기록되지 않아 하루 움직임 조건은 보지 못했습니다." : ""}</div>` : ""}
    ${all.some((r) => r.high_risk) ? `<div class="meta">변동성 높음 · 참고: ${QSF_RISK_NOTE}</div>` : ""}
    ${all.some((r) => r.filing_events) ? `<div class="meta">공시 표시 · 참고: ${QSF_FILING_NOTE}</div>` : ""}
    ${all.some((r) => r.deal) ? `<div class="meta">합병 절차 공시 · 참고: ${QSF_DEAL_NOTE}</div>` : ""}
    ${d.live_model_version && d.model_version && d.live_model_version !== d.model_version ? `<div class="notice">이 순위는 ${esc(d.model_version)} 공식으로 기록된 스캔입니다. 종목을 열면 카드는 지금 공식(${esc(d.live_model_version)})으로 다시 계산하므로 점수와 구간 표시가 다를 수 있습니다. 다음 스캔이 기록되면 같아집니다.</div>` : ""}
    ${all.length ? `<div class="tbl-wrap"><table class="qsf-rank-tbl"><thead>${head}</thead><tbody>${all.map((r) => qsfRankRow(r, top.includes(r), note(r), notes && notes.sectors[r.ticker], notes && notes.band_edges)).join("")}</tbody></table></div>` : '<div class="empty">순위에 올릴 종목이 없습니다.</div>'}
    <div class="meta">${notes ? `${esc(notes.note)}${notes.prev_session ? ` 점수 변화는 ${esc(notes.prev_session)} 기록과 비교합니다.` : " 직전 기록 거래일이 없어 점수 변화는 비워 둡니다."}` : "가점·감점, 업종, 점수 변화는 원장에서 읽지 못해 비워 둡니다. 점수와 순위는 그대로입니다."}</div>
    <div class="meta">${d.tickers}종목 평가 · 생성 ${esc((d.generated_at || "").slice(0, 16))} UTC${d.stale_inputs ? ` · <b>${d.stale_inputs.stocks}종목은 새 재무·공시 자료를 받지 못해 저장해 둔 자료로 채점했습니다 (가장 오래된 것 ${Math.round(d.stale_inputs.oldest_days)}일 전)</b>` : ""}</div></div>`;
  const toggle = (tr) => {
    const exp = tr.nextElementSibling, open = tr.getAttribute("aria-expanded") === "true", slot = exp.querySelector(".qsf-exp");
    tr.setAttribute("aria-expanded", open ? "false" : "true");
    exp.hidden = open;
    if (!open && !slot.dataset.done) { slot.dataset.done = "1"; qsfFillRow(slot, all.find((r) => r.ticker === tr.dataset.qsf), mk); }
  };
  box.querySelectorAll(".qsf-rrow").forEach((tr) => {
    tr.onclick = (e) => { if (!e.target.closest("a, button")) toggle(tr); };
    tr.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(tr); } };
  });
}

// ------------------------------------------------------------------ 직전 거래일과 달라진 점
const QSF_DOMAIN_NAME = { TECHNICAL: "기술", FUNDAMENTAL: "재무", RISK: "위험 관리", EVENTS: "이벤트", REGIME: "시장 국면" };
const qsfChangeState = { token: 0 };

function qsfChangeRow(m) {
  const delta = m.delta === null ? "" : `${m.delta > 0 ? "+" : ""}${m.delta.toFixed(1)}`;
  const why = m.reason ? `${esc(QSF_DOMAIN_NAME[m.reason.domain] || m.reason.domain)} ${m.reason.change > 0 ? "+" : ""}${m.reason.change.toFixed(0)}` : "";
  return `<tr><td class="l"><button type="button" class="qs-open" data-t="${esc(m.ticker)}">${tickerLabel(m.ticker, m.name)}</button></td><td class="num">${qsfNum(m.previous_score)}</td><td class="num">${qsfNum(m.score)}</td><td class="num">${delta}</td><td class="l">${why}</td></tr>`;
}
function qsfChangeTable(title, rows, note) {
  if (!rows.length) return `<h3 class="qc-title">${title} <span class="meta m0">없음</span></h3>`;
  return `<h3 class="qc-title">${title} <span class="meta m0">${rows.length}개${note ? " · " + note : ""}</span></h3><div class="tbl-wrap"><table class="qs-table"><thead><tr><th class="l">종목</th><th>이전</th><th>현재</th><th>변화</th><th class="l">가장 크게 움직인 영역</th></tr></thead><tbody>${rows.map(qsfChangeRow).join("")}</tbody></table></div>`;
}
// Korea only: the same scores on the former live universe (the 300 most traded), from the separate daily record.  Never the live ranking.
const QSF_ACT = { ACTIONABLE: "", BLOCKED: "차단", INSUFFICIENT_DATA: "자료 부족" };
function qsfCapHtml(d) {
  const rows = d.rows.map((r) => `<tr><td class="num">${r.rank}</td><td class="l"><a href="#stock/${esc(r.ticker)}">${esc(r.name || r.ticker)}</a> <span class="meta m0">${esc(r.ticker)}</span></td>
    <td class="num">${qsfNum(r.score)}</td><td class="num">${r.traded_rank}</td><td class="l">${r.in_live ? "라이브 대상에도 있음" : "<b>이전 대상에만</b>"}</td><td class="l">${esc(QSF_ACT[r.actionability] ?? r.actionability ?? "")}</td></tr>`).join("");
  return `<div class="panel"><h2>이전 대상(거래대금 상위 ${d.size})으로 본 순위 <small class="meta m0">비교용 · ${QSF_STRAT[d.strategy]} · 기준 ${esc(d.session)} · ${esc(d.model_version || "")}</small></h2>
    <div class="notice">${d.notes.map(esc).join("<br>")}</div>
    <div class="meta">점수가 나온 ${d.scored}종목 중 상위 ${d.rows.length}개 · 두 대상에 모두 있는 종목 ${d.in_both}개 · 이전 대상에만 ${d.former_only}개 · 라이브 대상에만 ${d.live_only}개 · 70점 이상 ${d.buy_band}개 · 쌓인 기록 ${d.records}일</div>
    <div class="tbl-wrap"><table class="qs-table"><thead><tr><th>순위</th><th class="l">종목</th><th>점수</th><th title="20거래일 평균 거래대금 순위">거래대금 순위</th><th class="l">라이브 대상</th><th class="l">상태</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="meta">점수는 그날 기록에 적힌 값입니다(다시 계산하지 않음). 규칙: ${esc(d.protocol)}</div></div>`;
}
async function qsfCap() {
  const box = $("#qsfcap"); if (!box) return;
  if (!isKR()) { box.innerHTML = ""; return; }
  const mk = state.market, st = qsfState.strategy;
  const d = await api(`/api/qsf/former-universe?strategy=${st}`).catch(() => null);
  if (mk !== state.market || st !== qsfState.strategy) return;
  box.innerHTML = d && d.status === "REAL" ? qsfCapHtml(d) : "";
}

async function qsfChanges() {
  const box = $("#qsfchanges"); if (!box) return;
  const mk = state.market, token = ++qsfChangeState.token;
  const d = await api(`/api/qsf/changes?market=${mk}&strategy=${qsfState.strategy}`).catch(() => null);
  if (token !== qsfChangeState.token || mk !== state.market) return;
  if (!d || d.status !== "REAL") { box.innerHTML = d && d.reason ? `<div class="panel"><h2>직전 기록과 달라진 점</h2><div class="empty">${esc(d.reason)}</div></div>` : ""; return; }
  box.innerHTML = `<div class="panel"><h2>직전 기록과 달라진 점 <span class="badge">${esc(d.previous_session)} → ${esc(d.session)}</span> <span class="meta m0">${QSF_STRAT[d.strategy]} ${d.compared}종목 비교</span></h2>
    ${d.model_changed ? `<div class="notice">두 기록의 모델 버전이 다릅니다(${d.previous_model_versions.map(esc).join(", ")} → ${esc(d.model_version)}). 이 차이에는 새 정보뿐 아니라 수식과 입력 수정이 섞여 있습니다.</div>` : ""}
    <div class="meta">기록에 남은 값을 비교할 뿐입니다. 새 매수 후보가 더 좋은 수익을 낸다는 근거는 아닙니다.</div>
    ${qsfChangeTable("새로 매수 후보가 된 종목", d.entered_buy)}${qsfChangeTable("매수 후보에서 빠진 종목", d.left_buy)}
    <details class="qsf-today-fold"><summary>점수가 크게 움직인 종목</summary>${qsfChangeTable("오른 종목", d.up, "상위만")}${qsfChangeTable("내린 종목", d.down, "상위만")}</details>
    ${d.new_in_scan.length || d.gone_from_scan.length ? `<div class="meta">스캔에 새로 들어옴 ${d.new_in_scan.length}개, 빠짐 ${d.gone_from_scan.length}개</div>` : ""}</div>`;
  box.querySelectorAll(".qs-open").forEach((b) => { b.onclick = () => { qsfEvaluate(b.dataset.t, mk); $("#qsfmsg").scrollIntoView({ block: "start" }); }; });
}

// ------------------------------------------------------------------ 스크리너
// 최신 스캔을 거르고 정렬할 뿐입니다. 점수를 다시 계산하지 않고, 서버가 거른 결과만 그립니다.
const QSF_SCREEN_COLS = [["score", "점수"], ["technical", "기술"], ["fundamental", "재무"], ["risk", "위험 관리"], ["events", "이벤트"]];
const QSF_SCREEN_DOMAIN = { technical: "TECHNICAL", fundamental: "FUNDAMENTAL", risk: "RISK", events: "EVENTS" };
const QSF_SCREEN_PAGE = 100;
const qsfSector = sectorKo;
const qsfScreenState = { form: {}, sort: "score", order: "desc", shown: QSF_SCREEN_PAGE, token: 0, timer: null };

function qsfScreenQuery(limit, offset) {
  const f = qsfScreenState.form, p = new URLSearchParams({ market: state.market, strategy: qsfState.strategy, sort: qsfScreenState.sort, order: qsfScreenState.order, limit, offset });
  for (const k of ["q", "sector", "action", "entry", "confidence", "min_score", "min_technical", "min_fundamental", "min_risk"]) if (f[k]) p.set(k, f[k]);
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
  box.innerHTML = `<div class="panel"><h2>스크리너 <span class="meta m0" id="qsfscreencount"></span></h2>
    <div class="meta">최신 스캔의 전 종목을 거르고 정렬합니다. 점수를 바꾸지 않으며, 걸러 낸 목록이 수익이 더 좋다는 근거는 아닙니다. 물어본 값이 없는 종목은 0점으로 치지 않고 빼서 따로 셉니다.</div>
    <form id="qsfscreenform" class="qs-form" autocomplete="off">
      <label class="qs-wide">검색<input type="search" name="q" maxlength="40" placeholder="코드 또는 이름" value="${esc(f.q || "")}"></label>
      <label>업종<select name="sector"><option value="">전체</option>${f.sector ? `<option value="${esc(f.sector)}" selected>${esc(qsfSector(f.sector))}</option>` : ""}</select></label>
      <label>판단<select name="action">${opt("action", "", "전체")}${opt("action", "BUY", "매수 후보")}${opt("action", "WATCH", "관찰")}${opt("action", "AVOID", "회피")}</select></label>
      <label>진입<select name="entry">${opt("entry", "", "전체")}${Object.keys(QSF_ENTRY).map((k) => opt("entry", k, esc(QSF_ENTRY[k]))).join("")}</select></label>
      <label>신뢰도<select name="confidence">${opt("confidence", "", "전체")}${opt("confidence", "MEDIUM", "보통 이상")}${opt("confidence", "HIGH", "높음")}</select></label>
      ${num("min_score", "점수 이상")}${num("min_technical", "기술 이상")}${num("min_fundamental", "재무 이상")}${num("min_risk", "위험 관리 이상")}
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
  catch (e) { if (token === qsfScreenState.token) body.innerHTML = `<div class="empty">조건을 읽지 못했습니다: ${esc(errKo(e))}</div>`; return; }
  if (token !== qsfScreenState.token || mk !== state.market) return;
  if (d.status !== "REAL") { $("#qsfscreencount").textContent = ""; body.innerHTML = `<div class="empty">아직 스캔 기록이 없습니다.</div>`; return; }
  $("#qsfscreencount").textContent = `${QSF_STRAT[d.strategy]} ${d.total}개 중 ${d.matched}개 · 기준 ${d.session}${d.missing_value ? ` · 값이 없어 뺀 종목 ${d.missing_value}개` : ""}${isKR() && d.strategy === "SWING" ? " · 기술 열은 참고(점수 미반영)" : ""}`;
  const pick = $("#qsfscreenform").elements.sector;
  if (pick.options.length <= 2) {      // 처음 받은 응답의 업종으로 선택지를 채웁니다
    const now = pick.value;
    pick.innerHTML = `<option value="">전체</option>` + Object.entries(d.sectors).map(([k, n]) => `<option value="${esc(k)}">${esc(qsfSector(k))} (${n})</option>`).join("");
    pick.value = now;
  }
  if (!d.matched) { body.innerHTML = `<div class="empty">조건에 맞는 종목이 없습니다.</div>`; return; }
  const spread = Object.entries(d.matched_sectors).slice(0, 6).map(([k, n]) => `${esc(qsfSector(k))} ${n}`).join(" · ");
  const head = QSF_SCREEN_COLS.map(([k, label]) => { const on = qsfScreenState.sort === k;
    return `<th aria-sort="${on ? (qsfScreenState.order === "desc" ? "descending" : "ascending") : "none"}"><button type="button" class="qs-sort" data-sort="${k}">${label}${on ? (qsfScreenState.order === "desc" ? " ▼" : " ▲") : ""}</button></th>`; }).join("");
  const rows = d.rows.map((r) => `<tr><td class="l"><button type="button" class="qs-open" data-t="${esc(r.ticker)}">${tickerLabel(r.ticker, r.name)}</button>${qsfBuybackChip(r.filing_events)}${qsfRiskLines(r)}</td>
      <td class="l"${r.industry ? ` title="${esc(r.industry)}"` : ""}>${r.sector ? esc(qsfSector(r.sector)) : DASH}</td><td class="num">${qsfInt(r.score)}</td>${Object.values(QSF_SCREEN_DOMAIN).map((k) => `<td class="num">${qsfNum((r.domains || {})[k], 0)}</td>`).join("")}
      <td class="l">${qsfLabel(r)}</td><td class="l">${esc(QSF_CONF[r.confidence] || "")}</td><td class="l">${esc(qsfEntry(r.entry_status, r.strategy || qsfState.strategy) || "")}${r.gates.length ? `<div class="qr-out">실행 대상 아님 · ${r.gates.map((g) => esc(QSF_GATE[g] || g)).join(", ")}</div>` : ""}</td></tr>`).join("");
  const other = d.live_version && d.model_version && d.live_version !== d.model_version
    ? `<div class="notice">이 목록은 ${esc(d.session)} 기록(공식 ${esc(d.model_version)})입니다. 지금 공식은 ${esc(d.live_version)}이라, 종목을 눌러 새로 계산한 카드와 구간·진입 표시가 다를 수 있습니다. 다음 스캔 뒤에 같아집니다.</div>` : "";
  body.innerHTML = `${other}${spread ? `<div class="meta">결과의 업종 분포: ${spread}</div>` : ""}<div class="tbl-wrap"><table class="qs-table"><thead><tr><th class="l">종목</th><th class="l">업종</th>${head}<th class="l">판단</th><th class="l">신뢰도</th><th class="l">진입과 게이트</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${d.matched > d.rows.length ? `<button type="button" id="qsfscreenmore" class="mt-3">${d.matched - d.rows.length}개 더 보기</button>` : ""}`;
  body.querySelectorAll(".qs-sort").forEach((b) => { b.onclick = () => { const k = b.dataset.sort;
    qsfScreenState.order = qsfScreenState.sort === k && qsfScreenState.order === "desc" ? "asc" : "desc"; qsfScreenState.sort = k; qsfScreenRun(false); }; });
  // The score card is drawn in the rank view; from the screener it was drawn into a hidden panel and nothing appeared.
  body.querySelectorAll(".qs-open").forEach((b) => { b.onclick = () => { qsfSetView("rank"); qsfEvaluate(b.dataset.t, mk); $("#qsfmsg").scrollIntoView({ block: "start" }); }; });
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
  try { d = await api(`/api/qsf/screen?${qsfScreenQuery(2000, 0)}`); } catch (e) { msg.textContent = "저장 실패: " + errKo(e); return; }
  if (d.status !== "REAL") { msg.textContent = "저장할 스캔 기록이 없습니다."; return; }
  const round = (v) => (typeof v === "number" ? Math.round(v * 10) / 10 : v);
  const lines = [["기준일", "전략", "코드", "이름", "업종", "점수", "기술", "재무", "위험", "이벤트", "판단", "신뢰도", "진입", "게이트", "가격", "자금조달 결정", "자사주 취득", "변동성 높음"].join(",")];
  for (const r of d.rows) {
    const dom = r.domains || {}, mark = r.filing_events;
    const marks = d.market === "KR" ? [mark && mark.financing ? "예" : "", mark && mark.buyback ? "예" : "", r.high_risk ? "예" : ""] : ["", "", ""];
    lines.push([d.session, QSF_STRAT[d.strategy], r.ticker, r.name, qsfSector(r.sector), round(r.score), round(dom.TECHNICAL), round(dom.FUNDAMENTAL), round(dom.RISK), round(dom.EVENTS), r.action_label, QSF_CONF[r.confidence], qsfEntry(r.entry_status, r.strategy || qsfState.strategy), r.gates.map((g) => QSF_GATE[g] || g).join(" / "), r.price, ...marks].map(qsfCsvCell).join(","));
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
    el.innerHTML = `<div class="err">${offline ? "터미널 서버가 응답하지 않아 당일 점검을 불러오지 못했습니다. 서버가 켜져 있는지 확인한 뒤 다시 시도하세요." : `당일 점검을 불러오지 못했습니다: ${esc(errKo(e))}`}</div>
      <button type="button" class="qsf-retry mt-2">다시 시도</button>`;
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
  const filings = f.items && f.items.length ? `<ul class="qsf-list">${f.items.map((x) => `<li>${esc(x.filing_date || "")} ${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.form || "공시")}</a>` : esc(x.form || "공시")}${x.description ? ` <span class="meta m0">${esc(x.description)}</span>` : ""}</li>`).join("")}</ul>`
    : `<div class="meta">${f.status === "UNAVAILABLE" ? `공시를 받지 못했습니다${f.reason ? `: ${esc(f.reason)}` : ""}` : "점수 기준일 이후 공시가 없습니다."}</div>`;
  const news = n.status === "UNAVAILABLE" ? `<div class="meta">뉴스를 받지 못했습니다${n.error === "NO_NAME" ? " (종목명을 찾지 못함)" : ""}.</div>`
    : n.items.length ? `${n.status === "STALE" ? '<div class="meta">새 뉴스를 받지 못해 이전에 받은 목록을 보여 줍니다.</div>' : ""}<ul class="qsf-news">${n.items.map((x) => `<li><a href="${esc(x.link)}" target="_blank" rel="noopener noreferrer">${esc(x.title)}</a><span class="meta m0">${esc(x.source || "")} · ${x.published ? when(x.published) : "시각 없음"}</span></li>`).join("")}</ul><div class="meta">출처: ${esc(n.provider || "")} · 받아온 시각 ${when(n.fetched_at)}</div>`
    : '<div class="meta">최근 뉴스가 없습니다.</div>';
  return `<div class="qsf-today"><h3>시세</h3>${quote}<h3>공시 경고</h3>${warn}<h3>최근 공시</h3>${filings}<h3>뉴스 제목</h3>${news}<div class="meta">${esc(d.note)}</div></div>`;
}

const QSF_COHORT = { US_SWING: "미국 스윙", US_LONG_TERM: "미국 장기", KR_SWING: "한국 스윙", KR_LONG_TERM: "한국 장기" };
function qsfVersionNote(cohorts) {
  const seen = {};
  Object.values(cohorts).forEach((c) => Object.entries(c.model_versions || {}).forEach(([v, n]) => { seen[v] = (seen[v] || 0) + n; }));
  const names = Object.keys(seen).sort();
  if (names.length < 2) return "";
  return `<div class="notice">이 집계에는 모델 버전 ${names.length}개의 기록이 섞여 있습니다(${names.map((v) => `${esc(v)} ${seen[v]}건`).join(", ")}). 결과는 한 수식의 성적이 아니라 그동안 쓴 수식들의 성적입니다.</div>`;
}
function qsfMethodHtml(d) {
  const title = `<h2>독자 매매법 KR-M1 <span class="badge">판정 전 참고</span></h2>`;
  const rules = `<div class="meta">회피 표시가 없는 종목 중 스윙 점수 상위 20%가 후보군입니다. 후보군 종목에 차트 신호가 뜨면 다음 거래일 시가에 들어가고, 손절 −2 ATR · 목표 +3 ATR · 10거래일 시간 청산으로 나옵니다. 왕복 비용 0.53%를 뺍니다. 기준선은 신호 없이 10거래일마다 사는 경우입니다.</div>
    <div class="meta"><b>과거 선발 실행(2019~2026)에서는 기준을 통과한 매매법이 없었습니다.</b> 9개 모두 비용을 빼면 거래당 평균 수익이 0 근처이거나 음수였습니다. 그래서 주력이 없고, 앞으로의 기록에서도 판정 없이 수치만 보고합니다. 주문을 실행하지 않고 투자 자문이 아닙니다. 규칙: ${esc(d.protocol)} · 선발 결과: reports/QSF_KR_METHOD_SELECTION_RESULTS.md</div>`;
  if (d.status !== "REAL") return `<div class="panel">${title}<div class="meta">아직 기록이 없습니다. ${esc(d.first)} 거래일부터 매일 기록합니다.</div>${rules}</div>`;
  const pc = (v, n = 2) => (isNum(v) ? qsfPct(v) : DASH);
  const order = ["R1", "R2", "R3", "T1", "T2", "T3", "T4", "B0", "B00"];
  const rows = order.filter((m) => d.methods[m]).map((m) => { const r = d.methods[m], base = m[0] === "B";
    return `<tr><td class="l"><b>${esc(m)}</b> ${esc(d.names[m] || "")}${d.primary.includes(m) ? ' <span class="badge">주력</span>' : ""}${d.family[m] ? `<div class="meta m0">${esc(d.family[m])} 계열</div>` : ""}</td>
      <td class="num">${base ? DASH : (r.today || []).length}</td><td class="num">${base ? DASH : r.signals_recorded}</td><td class="num">${r.trades || 0}</td><td class="num">${r.open_count || 0}</td>
      <td class="num">${r.trades ? pc(r.mean_net) : DASH}</td><td class="num">${r.trades ? (r.win_rate * 100).toFixed(0) + "%" : DASH}</td><td class="num">${isNum(r.payoff) ? r.payoff.toFixed(2) : DASH}</td>
      <td class="num">${isNum(r.mean_net_minus_b0) ? pc(r.mean_net_minus_b0) : DASH}</td></tr>`; }).join("");
  return `<div class="panel">${title}
    <div class="meta">기록 ${d.sessions}거래일(최근 ${esc(d.last)}), 보유가 끝난 신호일 ${d.matured}개. 대상 ${d.universe}종목 중 후보군 ${d.pool}종목. 가격은 ${esc(d.prices_to || "")}까지.</div>
    <div class="tbl-wrap"><table><thead><tr><th class="l">매매법</th><th title="최근 기록일에 후보군에서 신호가 뜬 종목 수">최근 신호</th><th>누적 신호</th><th title="청산까지 끝난 거래">끝난 거래</th><th>열린 거래</th>
      <th title="끝난 거래의 평균, 왕복 비용 0.53% 차감">거래당 순수익</th><th>승률</th><th title="평균 이익 ÷ 평균 손실">손익비</th><th title="같은 기간 기준선 B0의 거래당 평균 순수익과의 차이">기준선 대비</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="meta">${esc(d.note || "")} 거래 수가 적은 동안의 수치는 우연에 크게 흔들립니다.</div>${rules}</div>`;
}
async function qsfMethod() {
  const box = $("#qsfmethod"); if (!box) return;
  if (!isKR()) { box.innerHTML = ""; return; }
  const mk = state.market;
  const d = await api("/api/qsf/kr-method").catch(() => null);
  if (mk !== state.market) return;
  box.innerHTML = d ? qsfMethodHtml(d) : "";
}
// ------------------------------------------------------------------ regime weights (challenger) and the look-ahead audit
const QSF_DOMAIN_KO = { TECHNICAL: "기술", FUNDAMENTAL: "재무", RISK: "위험 관리" };
function qsfRegimeValue(c) {
  const v = c.value || {}, n = (x, d = 4) => (isNum(x) ? (x > 0 ? "+" : "") + x.toFixed(d) : "없음");
  if (c.id === "DIFF_T") return `차이 ${n(v.diff)}, t ${isNum(v.t) ? v.t.toFixed(2) : "없음"}`;
  if (c.id === "BOTH_HALVES") return `전반 ${n(v.early)}, 후반 ${n(v.late)}`;
  if (c.id === "OVER_CONTROL") return `차이 ${n(v.diff)}`;
  return `국면 ${isNum(v.dynamic) ? (v.dynamic * 100).toFixed(2) + "%" : "없음"}, 고정 ${isNum(v.static) ? (v.static * 100).toFixed(2) + "%" : "없음"}`;
}
function qsfRegimeHtml(d, mk) {
  const title = (badge) => `<h2>시장 국면에 따른 영역 가중치 <span class="badge">도전자</span> ${badge || ""}</h2>`;
  if (!d || d.status !== "REAL" || !d.markets[mk]) return `<div class="panel">${title()}<div class="meta">과거 검증 결과가 아직 없습니다. 규칙: reports/QSF_REGIME_WEIGHTS_PROTOCOL.md</div></div>`;
  const m = d.markets[mk], conds = m.conditions || [], passed = conds.filter((c) => c.passed).length;
  const ok = m.verdict === "REGIME_WEIGHTS_SUPPORTED";
  const badge = `<span class="badge ${ok ? "REAL" : "STALE"}">${ok ? "기준 충족" : m.verdict === "NOT_TESTED" ? "시험일 부족" : `기준 미달 (조건 ${passed}/${conds.length} 충족)`}</span>`;
  const f4 = (x) => (isNum(x) ? (x > 0 ? "+" : "") + x.toFixed(4) : "없음");
  const head = m.status === "REAL"
    ? `<div class="meta"><b>과거 걸어가기 검증</b>(시험일 ${m.tested}개, ${esc(m.test_first)} ~ ${esc(m.test_last)}, 스윙 ${d.horizon}거래일): 순위 상관은 고정 가중치 ${f4(m.ic.static)}, 국면 가중치 ${f4(m.ic.dynamic)}, 국면을 나누지 않은 다시 가중 ${f4(m.ic.control)}였습니다.
        국면 − 고정 차이는 ${f4(m.ic_diff)}(t ${isNum(m.ic_diff_t) ? m.ic_diff_t.toFixed(2) : "없음"}, 기준 ${d.settings.min_t} 이상)이고, 국면 쪽이 높았던 시험일은 ${(m.ic_diff_positive_share * 100).toFixed(0)}%입니다.
        ${ok ? "기준을 충족했지만 라이브 점수 반영은 사용자 결정 사항입니다." : "<b>고정 가중치보다 낫다는 근거가 없어 라이브 점수에는 쓰지 않습니다.</b>"}</div>`
    : `<div class="meta">시험일이 ${m.tested || 0}개뿐이라 판정하지 않았습니다.</div>`;
  const crow = conds.map((c) => `<tr><td class="l">${esc(c.label)}</td><td class="l">${esc(c.need)}</td><td class="l">${qsfRegimeValue(c)}</td><td>${c.passed ? '<span class="up">충족</span>' : '<span class="down">미달</span>'}</td></tr>`).join("");
  const w = (x) => (isNum(x) ? (x * 100).toFixed(0) + "%" : DASH);
  const today = (m.record.today || {}).state;
  const trow = [`<tr><td class="l">고정 가중치(라이브 배점)</td>${d.domains.map((k) => `<td class="num">${w(m.static[k])}</td>`).join("")}<td class="num">${DASH}</td></tr>`]
    .concat(Object.entries(m.final_table || {}).map(([s, v]) => `<tr><td class="l">${esc(d.state_labels[s] || s)}${today === s ? ' <span class="badge">최근 기록일의 상태</span>' : ""}${v.how !== "FITTED" ? ' <span class="meta">(과거 날이 적어 고정 가중치)</span>' : ""}</td>${d.domains.map((k) => `<td class="num">${w(v.weights[k])}</td>`).join("")}<td class="num">${v.days}</td></tr>`)).join("");
  const rec = m.record.sessions
    ? `매일 기록 ${m.record.sessions}거래일(${esc(m.record.first)} ~ ${esc(m.record.last)}).`
    : `매일 기록은 ${esc(m.record.start)} 거래일부터 시작합니다.`;
  return `<div class="panel">${title(badge)}${head}
    ${crow ? `<div class="tbl-wrap"><table><thead><tr><th class="l">조건</th><th class="l">기준</th><th class="l">결과</th><th>판정</th></tr></thead><tbody>${crow}</tbody></table></div>` : ""}
    <div class="meta mt-2">상태는 지수만으로 정합니다: 지수가 200거래일 평균 아래면 <b>하락</b>, 위이고 최근 20거래일 변동성이 지난 변동성의 중앙값 이하면 <b>상승·안정</b>, 그보다 크면 <b>상승·불안</b>. 아래 표는 과거 평가일 전체로 정해 고정한 가중치이고, 매일 기록에만 씁니다.</div>
    <div class="tbl-wrap"><table><thead><tr><th class="l">상태</th>${d.domains.map((k) => `<th>${QSF_DOMAIN_KO[k] || k}</th>`).join("")}<th title="그 상태였던 과거 평가일 수">과거 평가일</th></tr></thead><tbody>${trow}</tbody></table></div>
    <div class="meta">${rec} 보유가 끝난 기록일이 ${d.read_at}개가 되면 수치를 한 번 보고합니다. 한 번만 실행했고 설정값이나 조건을 바꿔 다시 시험하지 않습니다.</div>
    <details><summary class="meta">한계 ${d.limits.length}가지</summary>${d.limits.map((x) => `<div class="meta">· ${esc(x)}</div>`).join("")}<div class="meta">규칙: ${esc(d.protocol)} · 결과: reports/QSF_REGIME_WEIGHTS_RESULTS.md</div></details></div>`;
}
async function qsfRegime() {
  const box = $("#qsfregime"); if (!box) return;
  const mk = state.market;
  const d = await api("/api/qsf/regime-weights").catch(() => null);
  if (mk !== state.market) return;
  box.innerHTML = qsfRegimeHtml(d, mk);
}
const QSF_STORE_KO = { krx_forward: "한국 가격 점수", krx_forward_fund: "한국 재무 점수", krx_forward_events: "한국 공시 이벤트", us_challenger: "미국 도전자 점수", kr_swing_challenger: "한국 스윙 도전자", kr_challenger: "한국 묶음 도전자",
  kr_swing_prior: "이전 스윙 공식", kr_cap_universe: "시가총액 대상", kr_traded_universe: "거래대금 대상", kr_method: "독자 매매법", regime_weights_kr: "국면 가중치(한국)", regime_weights_us: "국면 가중치(미국)",
  paper_book_kr: "모의 장부(한국)", paper_book_us: "모의 장부(미국)", forecast_kr: "예측 층(한국)", forecast_us: "예측 층(미국)", score_split_kr: "이전 공식(한국)", score_split_us: "이전 공식(미국)" };
function qsfLookHtml(d) {
  const title = (badge) => `<h2>미래 자료 차단 점검 ${badge || ""}</h2>`;
  const how = `<div class="meta">어떤 날의 값을 계산할 때 그날 이후의 가격을 읽었는지 매일 확인합니다. 같은 함수를 원래 가격과, 그날 뒤의 가격을 모두 지우거나 바꾼 가격에서 한 번씩 더 돌려 결과가 같은지 봅니다. 하나라도 다르면 미래 자료를 읽은 것입니다.</div>`;
  if (!d || d.status === "NO_RECORD") return `<div class="panel">${title()}${how}<div class="meta">아직 점검 기록이 없습니다. 다음 자동 실행에서 처음 점검합니다.</div></div>`;
  const ok = d.status === "OK";
  const badge = `<span class="badge ${ok ? "REAL" : "UNAVAILABLE"}">${ok ? "이상 없음" : d.status === "NO_PRICES" ? "가격 자료 없음" : `문제 ${d.problems.length}건`}</span>`;
  const frow = (d.functions || []).map((f) => `<tr><td class="l">${esc(f.label)}</td><td class="num">${f.days}</td><td class="num">${f.moved}</td><td>${f.ok ? '<span class="up">미래 자료 없음</span>' : f.filled ? '<span class="down">미래 자료를 읽음</span>' : '<span class="down">값이 없어 점검 불가</span>'}</td></tr>`).join("");
  const c = d.control;
  const crow = c ? `<tr><td class="l">${esc(c.label)}</td><td class="num">${c.days}</td><td class="num">${c.moved}</td><td>${c.ok ? '<span class="up">점검이 잡아냄</span>' : '<span class="down">점검이 못 잡음: 점검 자체가 고장</span>'}</td></tr>` : "";
  const rrow = (d.records || []).map((r) => `<tr><td class="l">${esc(QSF_STORE_KO[r.store] || r.store)}</td><td class="num">${r.sessions}</td><td>${r.chain === "OK" ? '<span class="up">정상</span>' : '<span class="down">깨짐</span>'}</td>
    <td class="num">${r.before_next_open} / ${r.sessions}</td><td class="num">${r.late}</td><td class="l">${esc(r.first)} ~ ${esc(r.last)}</td></tr>`).join("");
  const wf = d.walk_forward ? Object.entries(d.walk_forward).map(([m, v]) => `${m === "KR" ? "한국" : "미국"} ${v.folds}회 ${v.leak_free ? "모두 통과" : "위반 있음"}`).join(", ") : null;
  return `<div class="panel">${title(badge)}${how}
    <div class="meta">점검 시각 ${esc((d.checked_at || "").slice(0, 16).replace("T", " "))} UTC · 가격 ${esc(d.prices_to || "")}까지 · 표본 ${d.sampled_days}거래일</div>
    <div class="tbl-wrap"><table><thead><tr><th class="l">계산</th><th>점검한 날</th><th title="그날 뒤의 가격을 바꿨을 때 결과가 달라진 날 수">결과가 달라진 날</th><th>판정</th></tr></thead><tbody>${frow}${crow}</tbody></table></div>
    ${rrow ? `<div class="meta mt-2"><b>기록 저장소</b>: 한 번 적은 기록이 바뀌지 않았는지(해시 연결)와, 다음 장이 열리기 전에 적었는지를 봅니다. 장이 열린 뒤에 적힌 날은 숨기지 않고 셉니다.</div>
    <div class="tbl-wrap"><table><thead><tr><th class="l">기록</th><th>기록일 수</th><th>해시 연결</th><th title="다음 거래일 09:00(한국 시각) 전에 적은 날">다음 장 전 기록</th><th title="제때 못 적고 나중에 채운 날">나중에 채운 날</th><th class="l">기간</th></tr></thead><tbody>${rrow}</tbody></table></div>` : ""}
    ${wf ? `<div class="meta">걸어가기 검증의 순서 점검(가중치를 정할 때 결과가 끝나지 않은 날을 쓰지 않았는지): ${wf}.</div>` : ""}
    <div class="meta">${esc(d.note || "")}</div></div>`;
}
async function qsfLookahead() {
  const box = $("#qsflook"); if (!box) return;
  const d = await api("/api/qsf/lookahead").catch(() => null);
  box.innerHTML = qsfLookHtml(d);
}

// ------------------------------------------------------------------ order plan (real account) and the paper book
function qsfOrderRows(orders, binding) {
  return orders.map((o) => `<tr><td class="l"><b>${esc(o.name || o.ticker)}</b> <span class="meta">${esc(o.ticker)}</span>${qsfDealTag(o.deal)}</td><td>${o.style === "LONG" ? "장기" : "스윙"}</td><td class="num">${o.score.toFixed(1)}${o.band_label ? `<div class="meta m0">${esc(o.band_label)}</div>` : ""}</td>
    <td class="num">${fmt(o.shares, 0)}</td><td class="num">${money(o.ref_close)}</td><td class="num"${isNum(o.limit_order) ? ` title="계산한 상한 ${money(o.limit)}을 호가 단위로 내린 가격입니다. 이 가격 그대로 주문할 수 있습니다."` : ""}>${money(isNum(o.limit_order) ? o.limit_order : o.limit)}</td><td class="num">${money(o.stop)}</td><td class="num">${isNum(o.target) ? money(o.target) : DASH}</td>
    <td class="num">${money(o.notional, 0)} <span class="meta">(${o.weight_pct.toFixed(1)}%)</span></td><td class="num">${o.risk_pct.toFixed(2)}%</td><td class="l">${esc((binding || {})[o.binding] || o.binding_label || o.binding)}</td>
    <td class="num" title="스프레드 가정 ${o.slippage_bps.spread}bp + 주문 크기 충격 ${isNum(o.slippage_bps.impact) ? o.slippage_bps.impact.toFixed(1) : "?"}bp">${o.slippage_bps.total.toFixed(1)}bp</td>
    <td class="num">${money(o.fee_buy)} / ${money(o.fee_sell)}</td><td class="num">${o.est_round_trip_pct.toFixed(2)}%</td></tr>`).join("");
}
const QSF_ORDER_HEAD = `<thead><tr><th class="l">종목</th><th>스타일</th><th>점수</th><th>수량</th><th title="계획을 만든 날의 종가">기준 종가</th><th title="기준 종가 + 0.5 ATR을 호가 단위로 내린 가격(내 계좌 계획). 다음 시가가 이 가격보다 높으면 따라가지 않습니다">지정가 상한</th><th>손절</th><th>목표</th><th>금액 (비중)</th>
  <th title="손절에 닿았을 때 계좌 대비 손실">위험</th><th class="l" title="수량을 정한 한도">묶인 한도</th><th title="편도 슬리피지 추정">슬리피지 추정</th><th title="토스증권 공시 수수료와 매도 세금">수수료 매수 / 매도</th><th title="수수료·세금 + 슬리피지 추정의 왕복 합계">왕복 예상 비용</th></tr></thead>`;
function qsfSkipLine(counts, labels) {
  const parts = Object.entries(counts || {}).map(([k, n]) => `${esc((labels || {})[k] || k)} ${n}종목`);
  return parts.length ? `<div class="meta">계획에서 빠진 후보: ${parts.join(", ")}.</div>` : "";
}
// 이 계획이 읽은 시장 상태 한 줄.  전체 설명은 점수 탭 맨 위 띠를 펼치면 있습니다.
const qsfPlanState = (ms) => (!ms ? "" : `<div class="meta">이 계획이 읽은 ${qsfStateShort({ status: "REAL", ...ms })}${ms.session ? ` · ${esc(ms.session)} 기록` : ""} · 자세한 설명은 맨 위 띠</div>`);
function qsfPlanHtml(d) {
  const title = `<h2>오늘 진입 후보의 주문 계획 <span class="badge">내 계좌 기준</span> <span class="badge risk-note">주문을 보내지 않습니다</span></h2>`;
  const how = `<div class="meta">프로그램이 진입 상태를 '지금 진입 가능'(장기는 '진입을 막는 조건 없음')으로 읽은 종목을 점수 높은 순으로 놓고, 설정해 두신 한도(거래당 위험, 종목 비중, 장기·스윙 비중, 섹터 비중)와 현금 안에서 수량을 정합니다. 이미 보유한 종목과 같은 날 이미 계획된 종목에는 주문을 또 만들지 않습니다.</div>`;
  if (!d) return "";
  if (d.status === "NO_SCAN") return `<div class="panel">${title}${how}<div class="empty">기록된 스캔이 없습니다.</div></div>`;
  if (d.status === "NO_ACCOUNT") return `<div class="panel">${title}${how}${qsfPlanState(d.market_state)}<div class="empty">${esc(d.reason)} 오늘 진입 후보는 ${d.candidates}종목입니다.</div>${d.timing_note ? `<div class="meta">${esc(d.timing_note)}</div>` : ""}</div>`;
  const a = d.assumptions;
  const body = d.orders.length
    ? `<div class="tbl-wrap"><table>${QSF_ORDER_HEAD}<tbody>${qsfOrderRows(d.orders)}</tbody></table></div>`
    : `<div class="empty">한도 안에서 새로 살 수 있는 후보가 없습니다 (후보 ${d.candidates}종목).</div>`;
  return `<div class="panel">${title}${how}
    <div class="meta">기준 거래일 ${esc(d.session)} · 계좌 평가액 ${money(d.equity, 0)} · 현금 ${money(d.cash, 0)} · 진입 후보 ${d.candidates}종목 중 ${d.orders.length}종목 계획 · 계획 후 남는 현금 ${money(d.cash_after, 0)}</div>
    ${qsfPlanState(d.market_state)}${d.size_factor < 1 ? `<div class="notice">시장 상태가 나쁘거나 읽을 수 없는 날이라 새 주문의 거래당 위험 한도와 종목 비중 한도를 ${(d.size_factor * 100).toFixed(0)}%로 계산했습니다.${d.new_exposure_cap ? ` 새 주문의 합계도 계좌의 ${(d.new_exposure_cap * 100).toFixed(0)}%까지만 잡았습니다(이 계획의 합계 ${isNum(d.new_exposure_pct) ? d.new_exposure_pct.toFixed(1) : "?"}%).` : ""}</div>` : ""}
    ${d.stance && d.stance.note ? `<div class="notice">${esc(d.stance.note)}${Object.keys(d.stance.left_out_by || {}).length ? ` 빠진 이유: ${Object.entries(d.stance.left_out_by).map(([k, n]) => `${esc(k)} ${n}건`).join(", ")}.` : ""}</div>` : ""}
    ${body}${d.bands && d.bands.note ? `<div class="notice">${esc(d.bands.note)}</div>` : ""}${qsfSkipLine(d.skipped_counts, Object.fromEntries((d.skipped || []).map((s) => [s.code, s.reason])))}
    <div class="meta">비용: ${esc(a.cost_basis)}. ${esc(a.slippage_note)} 주문은 종목의 20일 평균 거래대금의 ${a.max_participation_pct}%를 넘지 않게 줄이고, 계좌의 ${a.min_weight_pct}% 미만인 주문은 만들지 않습니다. 지정가 상한은 기준 종가 + ${a.limit_atr} ATR을 호가 단위로 내린 가격입니다.</div>
    ${d.timing_note ? `<div class="notice">${esc(d.timing_note)}</div>` : ""}<div class="meta">${esc(d.note)}</div></div>`;
}
async function qsfPlan() {
  const box = $("#qsfplan"); if (!box) return;
  const mk = state.market;
  box.innerHTML = `<div class="panel"><div class="meta">주문 계획을 계산하는 중입니다…</div></div>`;
  let failed = null;
  const d = await api(`/api/qsf/order-plan?market=${mk}`).catch((e) => { failed = e; return null; });
  if (mk !== state.market) return;
  box.innerHTML = failed ? `<div class="panel"><h2>오늘 진입 후보의 주문 계획</h2><div class="empty">불러오지 못했습니다: ${esc(errKo(failed))}</div></div>` : qsfPlanHtml(d);
}
// The turnover rules beside the paper book (TO-1).  Before the reading only counts are shown, never the comparison book's value or return.
// A verdict file that cannot be read, or a switch value that is none of the words: said on the panel, never passed over.
function qsfBookWarn(b, env) {
  return (b.damaged ? `<div class="meta"><span class="badge UNAVAILABLE">결과 파일 손상</span> ${esc(b.damaged)}</div>` : "") +
    (b.switch_unknown ? `<div class="meta"><span class="badge risk-note">.env의 ${env} 값 "${esc(b.switch_unknown)}"을 알아볼 수 없습니다</span> auto(판정을 따름)로 읽었습니다. auto, on, off 가운데 하나로 적으세요.</div>` : "");
}
function qsfTurnoverHtml(tb) {
  if (!tb) return "";
  const r = tb.rules || {}, pbk = tb.paper_book, c = tb.rule_counts || {};
  const pct = (v, n = 2) => (isNum(v) ? v.toFixed(n) + "%" : DASH);
  const own = pbk ? `<div class="meta"><b>기존 장부의 매매량</b>(${pbk.sessions}거래일): 체결 ${pbk.fills}건, 매도 ${pbk.exits}건 · 거래대금 ÷ 평균 평가액 ${pct(pbk.traded_pct, 1)} · 비용(수수료·세금 + 슬리피지 추정) ÷ 평균 평가액 ${pct(pbk.cost_pct)}
    · 손절 뒤 ${r.reentry_wait}거래일 안에 되산 횟수 ${pbk.rebuys_after_stop}건</div>` : "";
  const what = `<div class="meta"><b>두 규칙</b>: 손절로 판 종목은 ${r.reentry_wait}거래일 동안 다시 사지 않습니다. 스윙은 30거래일째부터 점수가 ${r.hold_score}점 이상이고 차단이 없으면 계속 보유합니다(최대 ${r.hold_cap}거래일).
    같은 계좌 상태에서 갈라진 비교 장부가 이 규칙으로 나란히 기록됩니다. 규칙: ${esc(tb.protocol)}</div>`;
  const force = tb.mode !== "auto" ? `<div class="meta"><span class="badge risk-note">.env의 QSF_TURNOVER_RULES=${esc(tb.mode)}</span> 판정과 상관없이 규칙을 ${tb.mode === "on" ? "항상 적용" : "적용하지 않음"}으로 두셨습니다.</div>` : "";
  let body;
  if (tb.status === "DECIDED") {
    const d = tb.decision;
    body = `<div class="meta"><span class="badge ${d.decision === "ADOPT" ? "ok" : ""}">읽은 결과: ${d.decision === "ADOPT" ? "적용 조건 충족 · 자동 적용 안 함" : "기존 규칙 유지"}</span> <span class="badge">${d.evidence === "DISTINCT" ? "수익 차이가 통계로 구분됨" : "수익 차이가 통계로 구분되지 않음"}</span>
      구간 ${esc(d.first)} ~ ${esc(d.last)}</div><ul class="meta">${(d.why || []).map((w) => `<li>${esc(w)}</li>`).join("")}</ul><div class="meta">${esc(d.consequence || "")} ${esc(d.note || "")}</div>`;
  } else if (tb.status === "RECORDING") {
    body = `<div class="meta"><span class="badge">판정 전</span> 비교 기록 ${tb.records} / ${tb.read_at}거래일 (${esc(tb.started)} ~ ${esc(tb.last)}) · 판정까지 ${tb.left}거래일.
      규칙이 한 일: 손절 ${c.STOPS || 0}건, 재진입을 막은 후보 ${c.REENTRY_WAIT || 0}건(종목·날), 보유 연장 ${c.HOLD_EXTENDED || 0}건(종목·날). ${esc(tb.note)}</div>`;
  } else if (tb.status === "DAMAGED") {
    body = "";
  } else {
    body = `<div class="meta"><span class="badge">판정 전</span> 비교 장부의 첫 기록은 ${esc(tb.first)} 거래일입니다. ${esc(tb.note)}</div>`;
  }
  // The button that puts the rules in force (user decision 2026-11-22).  It appears once the reading exists; .env, when set, decides first.
  const sw = tb.status !== "DECIDED" ? `<div class="meta">규칙을 켜는 버튼은 ${tb.read_at}거래일 판정이 나온 뒤 여기에 생깁니다. 그 전에 켜면 비교가 뜻을 잃습니다.</div>`
    : tb.mode !== "auto" ? "" : `<div class="meta"><button type="button" class="qsf-turnover-switch qsf-rule-switch" data-route="/api/qsf/turnover-rules" data-on="${tb.active ? "0" : "1"}">${tb.active ? "이 규칙 쓰지 않기" : "이 규칙 쓰기"}</button>
      <span class="qsf-turnover-said">지금: ${tb.active ? "규칙을 쓰는 중" : "쓰지 않음"}. 누르면 다음 기록부터 모의 장부, 주문 계획, 보유 종목 판단에 반영됩니다.</span></div>`;
  return `<h3>회전율 규칙 비교 <span class="meta">(TO-1${tb.active ? ` · 규칙 적용 중, ${esc(tb.adopted_version)}` : ""})</span></h3>${body}${sw}${qsfBookWarn(tb, "QSF_TURNOVER_RULES")}${force}${own}${what}`;
}
// The rank rules beside the paper book (RK-1): the same reading of progress, counts only before the decision.
function qsfRankBookHtml(rb) {
  if (!rb) return "";
  const r = rb.rules || {}, c = rb.rule_counts || {}, top = (v) => Math.round(v * 100);
  const what = `<div class="meta"><b>두 규칙</b>: 진입 후보는 그날 그 시장·스타일 점수의 상위 ${top(r.entry_top)}% 안일 때만 삽니다. 장기 보유는 순위가 상위 ${top(r.long_exit_top)}% 밖으로 밀리면 팝니다(40점 미만 규칙 대신).
    240거래일 뒤 하루 수익률 차이의 평균이 0보다 크고 t가 기준(표의 2.0을 이 표본 구조에 맞춰 고친 값, 약 2.2) 이상이면 "적용 조건 충족"이라고 알립니다. 스스로 적용하지는 않습니다. 규칙: ${esc(rb.protocol)}</div>`;
  const force = rb.mode !== "auto" ? `<div class="meta"><span class="badge risk-note">.env의 QSF_RANK_RULES=${esc(rb.mode)}</span> 판정과 상관없이 규칙을 ${rb.mode === "on" ? "항상 적용" : "적용하지 않음"}으로 두셨습니다.</div>` : "";
  let body;
  if (rb.status === "DECIDED") {
    const d = rb.decision;
    body = `<div class="meta"><span class="badge ${d.decision === "ADOPT" ? "ok" : ""}">읽은 결과: ${d.decision === "ADOPT" ? "적용 조건 충족 · 자동 적용 안 함" : "기존 규칙 유지"}</span> <span class="badge">${d.evidence === "DISTINCT" ? "수익 차이가 통계로 구분됨" : "수익 차이가 통계로 구분되지 않음"}</span>
      구간 ${esc(d.first)} ~ ${esc(d.last)}</div><ul class="meta">${(d.why || []).map((w) => `<li>${esc(w)}</li>`).join("")}</ul><div class="meta">${esc(d.consequence || "")} ${esc(d.note || "")}</div>`;
  } else if (rb.status === "RECORDING") {
    body = `<div class="meta"><span class="badge">판정 전</span> 비교 기록 ${rb.records} / ${rb.read_at}거래일 (${esc(rb.started)} ~ ${esc(rb.last)}) · 판정까지 ${rb.left}거래일.
      규칙이 한 일: 순위 규칙 때문에 빠진 주문 ${c.RANK_ENTRY || 0}건(종목·날), 순위로 정한 장기 매도 ${c.RANK_EXIT || 0}건. ${esc(rb.note)}</div>`;
  } else if (rb.status === "DAMAGED") {
    body = "";
  } else {
    body = `<div class="meta"><span class="badge">판정 전</span> 비교 장부의 첫 기록은 ${esc(rb.first)} 거래일입니다. ${esc(rb.note)}</div>`;
  }
  const sw = rb.status !== "DECIDED" ? `<div class="meta">규칙을 켜는 버튼은 ${rb.read_at}거래일 판정이 나온 뒤 여기에 생깁니다. 그 전에 켜면 비교가 뜻을 잃습니다.</div>`
    : rb.mode !== "auto" ? "" : `<div class="meta"><button type="button" class="qsf-rule-switch" data-route="/api/qsf/rank-rules" data-on="${rb.active ? "0" : "1"}">${rb.active ? "이 규칙 쓰지 않기" : "이 규칙 쓰기"}</button>
      <span class="qsf-turnover-said">지금: ${rb.active ? "규칙을 쓰는 중" : "쓰지 않음"}. 누르면 다음 기록부터 모의 장부, 주문 계획, 보유 종목 판단에 반영됩니다.</span></div>`;
  return `<h3>순위 규칙 비교 <span class="meta">(RK-1${rb.active ? " · 규칙 적용 중" : ""})</span></h3>${body}${sw}${qsfBookWarn(rb, "QSF_RANK_RULES")}${force}${what}`;
}
function qsfPaperHtml(d, tb, rb) {
  const title = `<h2>모의 체결 장부 <span class="badge">판정 전 참고</span> <span class="badge risk-note">가상의 금액 · 주문을 보내지 않습니다</span></h2>`;
  const rules = `<div class="meta"><b>규칙</b>: 시작 금액 ${money(d.start_cash, 0)}. 매일 위와 같은 방식의 주문 계획을 만들고, 다음 거래일 시가에 체결된 것으로 봅니다(시가가 지정가 상한보다 높거나 손절가 이하면 체결하지 않음).
    미국에서 시장 상태가 나쁜 날(50 미만)의 새 주문은 위험 한도와 비중 한도를 절반으로 계산합니다(2026-11-16부터, PB-2).
    스윙은 종가가 손절·목표에 닿으면 다음 시가에, ${d.swing_time_stop}거래일이 지나면 그날 종가에 팝니다. 장기는 종가가 손절(5 ATR)에 닿거나 장기 점수가 ${d.long_exit_score}점 미만이 되면 다음 시가에 팝니다.
    체결마다 수수료·세금과 슬리피지 추정을 뺍니다. ${esc(d.cost_basis)}. 자세한 규칙: ${esc(d.rules)}</div><div class="meta">${esc(d.note)}</div>`;
  if (d.status !== "REAL") return `<div class="panel">${title}<div class="empty">아직 기록이 없습니다. ${esc(d.first)} 거래일의 점수로 첫 계획을 만들고, 그다음 거래일 시가부터 체결합니다.</div>${qsfTurnoverHtml(tb)}${qsfRankBookHtml(rb)}${rules}</div>`;
  const pc = (v) => (isNum(v) ? `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</span>` : DASH);
  const cell = (k, v, t) => `<div${t ? ` title="${esc(t)}"` : ""}><div class="meta m0">${k}</div><div class="num" style="font-size:16px;font-weight:600">${v}</div></div>`;
  const tiles = `<div class="grid my-2">${cell("평가액", money(d.equity, 0))}${cell("시작 이후 수익률", pc(d.return_pct))}${cell(`${esc(d.benchmark)} 같은 기간`, pc(d.benchmark_return_pct), "첫 기록일 종가부터 최근 기록일 종가까지")}
    ${cell("최대 낙폭", pc(d.max_drawdown_pct))}${cell("현금", money(d.cash, 0))}${cell("끝난 거래 / 이긴 거래", `${d.closed} / ${d.wins}`)}${cell("거래당 평균 순수익", pc(d.mean_net_pct), "끝난 거래의 평균, 비용 차감")}
    ${cell("낸 수수료·세금", money(d.fees, 0))}${cell("슬리피지 추정 합계", money(d.slippage, 0))}</div>`;
  const prow = d.positions.map((p) => `<tr><td class="l"><b>${esc(p.name || p.ticker)}</b> <span class="meta">${esc(p.ticker)}</span>${p.pending_exit ? ` <span class="badge risk-note">다음 시가 매도: ${esc(d.exit_labels[p.pending_exit] || p.pending_exit)}</span>` : ""}</td>
    <td>${p.style === "LONG" ? "장기" : "스윙"}</td><td class="num">${fmt(p.qty, 0)}</td><td class="num">${money(p.entry)}</td><td class="num">${money(p.last_close)}</td><td class="num">${pc(p.unrealized_pct)}</td>
    <td class="num">${isNum(p.weight_pct) ? p.weight_pct.toFixed(1) + "%" : DASH}</td><td class="num">${money(p.stop)}</td><td class="num">${isNum(p.target) ? money(p.target) : DASH}</td><td class="num">${p.sessions}</td><td class="l">${esc(p.entry_session)}</td></tr>`).join("");
  const plan = d.plan || {};
  const planHtml = !plan.scored ? `<div class="meta">최근 기록일(${esc(d.last)})에는 점수 기록이 없어 새 계획이 없습니다.</div>`
    : (plan.orders || []).length ? `<div class="tbl-wrap"><table>${QSF_ORDER_HEAD}<tbody>${qsfOrderRows(plan.orders, d.binding_labels)}</tbody></table></div>` : `<div class="meta">한도 안에서 새로 살 후보가 없습니다 (후보 ${plan.candidates}종목).</div>`;
  const erow = d.recent.exits.map((e) => `<tr><td class="l">${esc(e.session)}</td><td class="l"><b>${esc(e.name || e.ticker)}</b> <span class="meta">${esc(e.ticker)}</span></td><td>${e.style === "LONG" ? "장기" : "스윙"}</td><td class="l">${esc(e.label)}</td>
    <td class="num">${money(e.entry)}</td><td class="num">${money(e.exit)}</td><td class="num">${e.sessions}</td><td class="num">${pc(e.net_pct)}</td><td class="num">${money(e.pnl, 0)}</td></tr>`).join("");
  const frow = d.recent.fills.map((f) => `<tr><td class="l">${esc(f.session)}</td><td class="l"><b>${esc(f.name || f.ticker)}</b> <span class="meta">${esc(f.ticker)}</span></td><td>${f.style === "LONG" ? "장기" : "스윙"}</td><td class="num">${fmt(f.qty, 0)}</td>
    <td class="num">${money(f.open)}</td><td class="num">${money(f.price)}</td><td class="num">${f.slippage_bps.toFixed(1)}bp</td><td class="num">${money(f.fee)}</td></tr>`).join("");
  const un = Object.entries(d.unfilled_counts || {}).map(([k, n]) => `${esc(d.unfilled_labels[k] || k)} ${n}건`).join(", ");
  return `<div class="panel">${title}
    <div class="meta">기록 ${d.sessions}거래일(${esc(d.started)} ~ ${esc(d.last)}) · 기록 연결 ${d.integrity === "OK" ? "정상" : "깨짐"} · 체결 ${d.fills}건${un ? ` · 미체결: ${un}` : ""}</div>${tiles}
    <h3>보유 ${d.positions.length}종목</h3>
    ${prow ? `<div class="tbl-wrap"><table><thead><tr><th class="l">종목</th><th>스타일</th><th>수량</th><th title="슬리피지를 넣은 체결가">매수가</th><th>최근 종가</th><th title="수수료를 넣은 매수 금액 대비">평가 손익</th><th>비중</th><th>손절</th><th>목표</th><th>보유 거래일</th><th class="l">매수일</th></tr></thead><tbody>${prow}</tbody></table></div>` : `<div class="meta">보유 종목이 없습니다.</div>`}
    <h3>다음 거래일 시가의 주문 계획 <span class="meta">(${esc(d.last)} 종가 기준)</span></h3>${qsfPlanState(plan.market_state)}${planHtml}${qsfSkipLine(plan.skipped_counts, d.skip_labels)}
    ${erow ? `<h3>최근 매도</h3><div class="tbl-wrap"><table><thead><tr><th class="l">매도일</th><th class="l">종목</th><th>스타일</th><th class="l">이유</th><th>매수가</th><th>매도가</th><th>보유 거래일</th><th title="수수료·세금·슬리피지 추정 차감">순수익률</th><th>손익</th></tr></thead><tbody>${erow}</tbody></table></div>` : ""}
    ${qsfTurnoverHtml(tb)}${qsfRankBookHtml(rb)}
    ${frow ? `<h3>최근 체결</h3><div class="tbl-wrap"><table><thead><tr><th class="l">체결일</th><th class="l">종목</th><th>스타일</th><th>수량</th><th>시가</th><th title="시가에 슬리피지 추정을 더한 값">체결가</th><th>슬리피지 추정</th><th>수수료</th></tr></thead><tbody>${frow}</tbody></table></div>` : ""}
    ${rules}</div>`;
}
async function qsfPaper() {
  const box = $("#qsfpaper"); if (!box) return;
  const mk = state.market;
  const [d, tb, rb] = await Promise.all([api(`/api/qsf/paper-book?market=${mk}`).catch(() => null), api(`/api/qsf/turnover-book?market=${mk}`).catch(() => null),
    api(`/api/qsf/rank-book?market=${mk}`).catch(() => null)]);
  if (mk !== state.market) return;
  box.innerHTML = d ? qsfPaperHtml(d, tb, rb) : "";
  box.querySelectorAll(".qsf-rule-switch").forEach((b) => { b.onclick = async () => {
    const said = b.parentElement.querySelector(".qsf-turnover-said");
    b.disabled = true;
    try {
      const r = await api(b.dataset.route, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ market: mk, on: b.dataset.on === "1" }) });
      if (r.status !== "OK") { said.textContent = r.reason || "바꾸지 못했습니다."; b.disabled = false; return; }
      if (r.note) notify(r.note, "info");
      qsfPaper();
    } catch (e) { said.textContent = "바꾸지 못했습니다: " + (errKo(e)); b.disabled = false; }
  }; });
}
// Every one-time reading: how far its record is, about when it will be read, and the verdict once the daily job has read it.
async function qsfReadings() {
  const box = $("#qsfreadings"); if (!box) return;
  const d = await api("/api/qsf/readings").catch(() => null);
  if (!d || d.status !== "REAL") { box.innerHTML = ""; return; }
  const state = (r) => (r.state === "READ" ? `<span class="badge ok">읽음</span> <b>${esc(r.verdict)}</b><div class="meta m0">${esc(r.meaning || "")}</div>${(r.reasons || []).map((x) => `<div class="meta m0">${esc(x)}</div>`).join("")}`
    : r.state === "DUE" ? `<span class="badge risk-note">읽을 때가 됨</span>${r.attempts ? ` <span class="meta m0">시도 ${r.attempts}번, 아직 조건 미달</span>` : ""}`
    : `<span class="badge">기다리는 중</span> <span class="meta m0">${isNum(r.left) ? `${r.left}거래일 남음 · ${esc(r.expected)} 무렵` : ""}</span>`);
  const sw = (r) => (!r.switch ? "" : !r.switch.can_switch ? `<div class="meta m0">${r.state === "READ" ? "설정 파일(.env)의 QSF_FUND_PERIOD가 재무 기준을 정하고 있어 버튼을 쓰지 않습니다." : "재무 기준을 바꾸는 버튼은 판정이 나온 뒤 여기에 생깁니다. 판정은 스스로 아무것도 바꾸지 않습니다."}</div>`
    : `<div class="meta m0"><button type="button" class="qsf-fund-switch" data-market="${esc(r.switch.market)}" data-period="${r.switch.live_period === "TRAILING" ? "ANNUAL" : "TRAILING"}">${r.switch.live_period === "TRAILING" ? "연간 보고서 기준으로 되돌리기" : "최근 4분기 기준으로 바꾸기"}</button>
        지금: ${r.switch.live_period === "TRAILING" ? "최근 4분기" : "연간 보고서"} 기준. 누르면 다음 스캔부터 이 시장의 점수가 그 기준을 읽습니다.</div>`);
  const row = (r) => `<tr><td class="l"><b>${esc(r.label)}</b> <span class="badge${r.primary ? " ok" : ""}" title="${r.primary ? "점수가 통하는지에 답하는 네 판정 가운데 하나입니다." : "참고 판정입니다. 판정이 서른 개쯤이라 몇은 우연히 기준을 넘을 수 있어, 점수가 통하는지는 실전 점수 판정 넷으로 답합니다."}">${r.primary ? "주된 판정" : "참고"}</span>${r.applies_itself ? ' <span class="badge">스스로 적용</span>' : ""}</td>
    <td class="num">${isNum(r.records) ? r.records : DASH} / ${r.wanted}</td><td class="l">${state(r)}${sw(r)}</td><td class="l"><span class="meta m0">${esc(r.after)}</span></td>
    <td class="l"><span class="meta m0">${esc(r.state === "READ" ? r.report : r.protocol)}</span></td></tr>`;
  const table = (list) => `<div class="tbl-wrap"><table><thead><tr><th class="l">판정</th><th title="지금까지의 기록 수 / 읽는 데 필요한 기록 수">기록</th><th class="l">상태</th><th class="l">결과가 나오면</th><th class="l">문서</th></tr></thead><tbody>${list.map(row).join("")}</tbody></table></div>`;
  const now = d.readings.filter((r) => r.state !== "WAITING"), due = now.filter((r) => r.state === "DUE").length;
  const next = d.readings.filter((r) => r.state === "WAITING" && isNum(r.left)).sort((a, b) => a.left - b.left)[0];
  const line = `읽은 판정 ${d.read}개, 읽을 때가 된 판정 ${due}개, 기다리는 판정 ${d.total - d.read - due}개.${next ? ` 가장 가까운 판정: ${esc(next.label)}(${next.left}거래일 남음, ${esc(next.expected)} 무렵).` : ""} 판정은 스스로 아무것도 바꾸지 않습니다.`;
  const wasOpen = !!(box.querySelector("details.qsf-readings-all") || {}).open;
  box.innerHTML = `<div class="panel"><h2>판정 일정 <span class="badge">${d.read} / ${d.total} 읽음</span></h2><div class="meta">${line}</div>
    ${now.length ? table(now) : ""}
    <details class="qsf-readings-all"${wasOpen ? " open" : ""}><summary>전체 일정 보기 (${d.total}개)</summary><div class="meta">${esc(d.note)} 안내: ${esc(d.guide)}</div>${table(d.readings)}</details></div>`;
  box.querySelectorAll(".qsf-fund-switch").forEach((b) => { b.onclick = async () => {
    const to = b.dataset.period === "TRAILING" ? "최근 4분기" : "연간 보고서";
    if (!confirm(`${b.dataset.market === "KR" ? "한국" : "미국"} 점수가 읽는 재무 기준을 '${to}'로 바꿉니다. 다음 스캔부터 스윙과 장기 점수 모두에 적용됩니다. 바꿀까요?`)) return;
    try {
      const res = await api("/api/qsf/fund-period", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ market: b.dataset.market, period: b.dataset.period }) });
      notify(res.status === "OK" ? res.note : res.reason || "바꾸지 못했습니다.", res.status === "OK" ? "info" : "err");
      qsfReadings();
    } catch (e) { notify(errKo(e)); }
  }; });
}
async function qsfValidation() {
  const box = $("#qsfvalid"); if (!box) return;
  const d = await api("/api/qsf/validation").catch(() => null);
  if (!d) return;
  const rows = Object.entries(d.cohorts).map(([k, c]) => { const first = Object.values(c.horizons)[0];
    return `<tr><td class="l"><b>${esc(QSF_COHORT[k] || k)}</b></td><td class="num">${c.snapshots}</td><td class="num">${c.sessions}</td><td class="num">${first.independent_samples.toFixed(1)}</td><td class="l">${esc(first.verdict)}</td></tr>`; }).join("");
  box.innerHTML = `<div class="panel"><h2>전향 검증 ${d.integrity.status === "OK" ? badge("REAL") : badge("UNAVAILABLE")}</h2>
    <div class="tbl-wrap"><table><thead><tr><th class="l">코호트</th><th>기록</th><th>거래일</th><th>독립 표본(최단 기간)</th><th class="l">판단</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${qsfVersionNote(d.cohorts)}
    <div class="meta">코호트를 합치지 않습니다. 독립 표본 12개 전에는 점수가 수익을 예측한다고 판단하지 않습니다.</div></div>`;
}

function qsfPct(v) {
  if (v === null || v === undefined) return DASH;
  const x = v * 100;
  return `<span class="${x > 0 ? "up" : x < 0 ? "down" : ""}">${x > 0 ? "+" : ""}${x.toFixed(2)}%</span>`;
}
function qsfTop3Pick(p) {
  const o = p.so_far;
  const now = o ? `${qsfPct(o.net)} <span class="meta m0">(지수 대비 ${qsfPct(o.relative_net)}, ${p.sessions_held}거래일)</span>` : '<span class="meta m0">진입 전</span>';
  return `<tr><td class="num">${p.rank}</td><td class="l">${tickerLabel(p.ticker, p.name)}</td><td class="num">${qsfNum(p.score)}</td><td class="l">${now}</td></tr>`;
}
async function qsfTop3() {
  const box = $("#qsftop3"); if (!box) return;
  const market = qsfState.market, strategy = qsfState.strategy;
  const d = await api(`/api/qsf/top3?market=${market}`).catch(() => null);
  if (!d || market !== qsfState.market || strategy !== qsfState.strategy) return;
  const title = `<h2>점수 상위 3종목 추적 ${d.status === "REAL" ? badge("REAL") : badge("UNAVAILABLE")}</h2>`;
  if (d.status !== "REAL") {
    box.innerHTML = `<div class="panel">${title}<div class="meta">${d.status === "NO_RECORD" ? `아직 고정된 기록이 없습니다. ${esc(d.first)} 거래일부터 스캔 직후 자동으로 고정합니다.` : "기록 검사에 실패해 보여 주지 않습니다."}</div></div>`;
    return;
  }
  const part = d.strategies[strategy];
  const days = part.days.slice(0, 10);
  const h = String(d.verdict_horizon[strategy]);
  const sums = Object.entries(part.summary).map(([v, s]) => { const r = s.horizons[h];
    return `<tr><td class="l">${esc(v)}</td><td class="num">${s.days}</td><td class="num">${r.picks}</td><td class="num">${r.beat_benchmark === null ? DASH : (r.beat_benchmark * 100).toFixed(0) + "%"}</td><td class="num">${qsfPct(r.mean_relative_net)}</td><td class="num">${qsfPct(r.mean_top_minus_universe)}</td><td class="num">${qsfNum(r.mean_rank_corr, 3)}</td><td class="l">${esc(r.verdict || "")}${r.verdict_window ? `<div class="meta m0">${esc(r.verdict_window.note)} (${esc(r.verdict_window.last || "")}까지)</div>` : ""}</td></tr>`; }).join("");
  const blocks = days.map((x) => `<h3>${esc(x.session)} 점수 → ${esc(x.entry_session)} 시가 진입 <span class="meta m0">${esc(x.model_version)}${x.before_open ? "" : " · 개장 뒤 고정이라 집계에서 뺌"}</span></h3>
    <div class="tbl-wrap"><table><thead><tr><th>순위</th><th class="l">종목</th><th>점수</th><th class="l">진입 후 지금까지 (비용 차감)</th></tr></thead><tbody>${x.top.map(qsfTop3Pick).join("")}</tbody></table></div>`).join("");
  box.innerHTML = `<div class="panel">${title}
    <div class="meta">${strategy === "SWING" ? "스윙" : "장기"} 점수 상위 3개를 스캔 직후, 진입일 개장 전에 고정합니다. 진입일 시가에 사서 종가로 평가하고, 왕복 비용 ${d.cost_round_trip_pct.toFixed(2)}%를 뺍니다.</div>
    ${blocks}
    <h3>집계 (${h}거래일 기준)</h3>
    <div class="tbl-wrap"><table><thead><tr><th class="l">모델</th><th>기록일</th><th>끝난 종목</th><th>지수 이긴 비율</th><th>지수 대비 평균</th><th>전체 평균 대비</th><th>순위 상관</th><th class="l">판정</th></tr></thead><tbody>${sums}</tbody></table></div>
    <div class="notice">3종목은 아주 작은 표본이라 몇 주의 성적은 우연과 구분되지 않습니다. 독립 표본 12개 전에는 판정하지 않으며, 이 결과로 점수 수식을 바꾸지 않습니다. 규칙: <code>${esc(d.protocol)}</code></div></div>`;
}

RENDER.qsf = renderQsf;
