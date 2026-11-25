// 오늘(비서): 프로그램이 이미 계산한 것을 정해진 규칙으로 정리해 보여 줍니다.  외부 AI를 쓰지 않고, 주문을 실행하지 않으며, 매수·매도를 권하지 않습니다.
"use strict";
const ASST_LEVELS = ["ACT", "DUE", "INFO"];
const ASST_TAB_KO = { account: "통합 계좌", portfolio: "시장별 자세히", committee: "투자위원회", qsf: "순위·카드", assist: "매매 보조", lab: "연구실", stock: "종목 정보", today: "오늘", coin: "코인", overview: "시장 개요", macro: "거시" };
let asstPending = null;       // 명령창에서 넘어온 질문

// '… 탭에서 보기'는 탭만이 아니라 그 항목을 보여 주는 보기까지 엽니다 (6차 묶음 P2-18).  항목 종류로 정하고, 종목이 있으면 그 카드나 화면입니다.
const ASST_VIEW = { PLAN_UNAVAILABLE: "exec", ORDERS_MORE: "exec", NO_ORDERS: "exec", NEW_VERDICT: "track", VERDICT_STUCK: "track",
  IC_INTERRUPT: "ports", IC_OVERWEIGHT: "ports", IC_EXCLUDED: "ports" };
function asstGo(tab, ticker, view) {
  if (ticker && tab === "stock") return openTicker(ticker);
  if (tab === "qsf" && ticker && typeof qsfOpenCard === "function") return qsfOpenCard(ticker);
  if (tab === "qsf" && view) { qsfState.view = view; show("qsf"); qsfSetView(view, true); }
  else if (tab === "committee" && view && typeof icState !== "undefined") { icState.view = view; show("committee"); if ($("#icview")) icSetView(view); }
  else show(tab);
  window.scrollTo(0, 0);
}
// 할 일 한 줄 (6차 묶음 P2-20): 첫 문장을 제목으로, 나머지는 접어 둡니다.  수준은 왼쪽 띠의 색과 굵기로 봅니다.
// 문장 끝은 한글이나 닫는 괄호 뒤의 마침표만 봅니다: 'Inc. ', 'Corp. ' 같은 영문 약어에서 끊지 않습니다.
function asstFirst(text) { const m = String(text || "").match(/^.+?[가-힣)][.!?](?=\s|$)/); return m ? m[0] : String(text || ""); }
// '사도 돼?'의 결론 (사용자 결정 2026-11-24): 사도 됨 · 기다림 · 사지 않음을 맨 위에 크게, 바로 아래 이유와 바뀌는 조건, 다른 전략 한 줄.
// 판단 색(6차 묶음 P2-8): 사도 됨 보라, 기다림 회색, 사지 않음 주황.  가격 색은 쓰지 않습니다.
const ASST_VERDICT_CLASS = { OK: "v-ok", WAIT: "v-wait", NO: "v-no" };
function asstVerdict(v) {
  return `<div class="asst-verdict ${ASST_VERDICT_CLASS[v.key] || "v-wait"}"><div class="asst-v-head"><b>${esc(v.label)}</b><span class="meta m0">${esc(v.strategy)} · 프로그램 규칙 기준</span></div>
    <p class="asst-sum">${esc(v.why)}</p>${v.change ? `<div class="asst-v-change">바뀌는 조건: ${esc(v.change)}</div>` : ""}${(v.cautions || []).map((c) => `<div class="asst-v-change">같이 볼 것: ${esc(c)}</div>`).join("")}${v.other ? `<div class="meta">${esc(v.other)}</div>` : ""}${v.caveat ? `<div class="meta">${esc(v.caveat)}</div>` : ""}</div>`;
}
function asstItem(i) {
  const view = ASST_VIEW[i.kind] || "", where = i.tab && i.tab !== "today" ? `<button type="button" class="ghost asst-go" data-tab="${esc(i.tab)}" data-view="${esc(view)}">${esc(ASST_TAB_KO[i.tab] || i.tab)} 탭에서 보기</button>` : "";
  const stock = i.ticker ? `<button type="button" class="chip" data-ticker="${esc(i.ticker)}">${esc(i.ticker)}</button>` : "";
  const first = asstFirst(i.text), rest = String(i.text || "").slice(first.length).trim();
  const body = rest ? `<details class="asst-more"><summary>${esc(first)}</summary><div>${esc(rest)}</div></details>` : `<div class="asst-one">${esc(first)}</div>`;
  return `<li class="asst-item ${esc(i.level)}">${body}<div class="asst-act">${stock}${where}</div></li>`;
}
// 답: 결론 한 줄을 먼저, 그 아래 제목이 붙은 묶음들, 끝에 자료 기준과 이어서 물어볼 것.
function asstAnswer(a) {
  const list = (rows) => `<ul>${rows.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  // 결론 상자에 이미 보인 '바뀌는 조건'과 '다른 전략'은 아래 목록에서 한 번 더 쓰지 않습니다 (글로만 받는 곳에는 둘 다 남아 있습니다)
  const shown = (s) => (a.verdict ? { ...s, lines: s.title === "다른 전략" ? [] : s.lines.filter((x) => !String(x).startsWith("바뀌는 조건: ")) } : s);
  const body = (a.sections || []).length ? a.sections.map(shown).filter((s) => s.lines.length).map((s) => `<h4>${esc(s.title)}</h4>${list(s.lines)}`).join("") : a.summary ? "" : list(a.lines || []);
  const chips = (rows, cls) => `<div class="chips">${rows.map((x) => `<button type="button" class="chip ${cls}">${esc(x)}</button>`).join("")}</div>`;
  const follow = (a.follow || []).length ? `<h4>이어서 물어보기</h4>${chips(a.follow, "asst-ex")}` : "";
  const more = (a.examples || []).length ? `<h4>눌러서 물어보기</h4>${chips(a.examples, "asst-ex")}` : "";
  const go = a.tab && a.tab !== "today" ? `<button type="button" class="ghost asst-go" data-tab="${esc(a.tab)}" data-ticker="${esc(a.ticker || "")}">${esc(ASST_TAB_KO[a.tab] || a.tab)} 탭에서 보기</button>` : "";
  return `<div class="asst-answer ${a.status === "REAL" ? "" : "unknown"}"><div class="asst-q">${esc(a.question || "")}</div><h3>${esc(a.title || "")}</h3>
    ${a.verdict ? asstVerdict(a.verdict) : a.summary ? `<p class="asst-sum">${esc(a.summary)}</p>` : ""}${body}${a.basis ? `<div class="meta">${esc(a.basis)}</div>` : ""}${follow}${more}
    <div class="asst-act">${go}</div><div class="meta">${esc(a.note || "")}</div></div>`;
}
async function asstAsk(q) {
  const out = $("#asst-out"); if (!out) return;
  q = (q || "").trim(); if (!q) return;
  $("#asst-q").value = q;
  out.innerHTML = loading;
  try {
    const a = await api("/api/assistant/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q, market: state.market }) });
    out.innerHTML = asstAnswer(a);
  } catch (e) { out.innerHTML = `<div class="msg err">${esc(errKo(e))}</div>`; }
}
// 명령창이나 다른 탭에서: 오늘 탭으로 옮긴 뒤 묻습니다.
function askAssistant(q) {
  asstPending = q;
  if (state.tab === "today" && $("#asst-q")) { asstPending = null; asstAsk(q); window.scrollTo(0, 0); return; }
  show("today"); window.scrollTo(0, 0);
}

// 첫 줄: 시장 탭과 같은 숫자 타일과 시장 상태(점수 미반영).  서버가 주지 않은 숫자는 만들지 않습니다.
function asstTiles(t) {
  if (!t || !(t.items || []).length) return "";
  const ms = t.market_state, bad = ms && ms.state !== "FAVOURABLE";
  const st = ms && isNum(ms.score_100) ? `<div class="card asst-state" title="어떤 종목 점수에도 들어가지 않는 값입니다"><div class="nm">시장 상태 <span class="muted">점수 미반영</span></div>
      <div class="px num">${ms.score_100.toFixed(0)}<small class="muted">/100</small></div>
      <div><span class="badge${bad ? " risk-note" : ""}">${esc(ms.label || "")}</span>${bad && isNum(ms.size_factor) && ms.size_factor < 1 ? ` <span class="meta m0">새 주문 크기 ${(ms.size_factor * 100).toFixed(0)}%</span>` : ""}</div>
      <div class="meta mt-1">${esc(ms.session || "")} 기록</div></div>` : "";
  return `<div class="grid asst-tiles">${t.items.map(card).join("")}${st}</div>${meta(t.source || "", t.fetched_at)}`;
}
// 오늘의 후보(사용자 결정 2026-11-23): 스타일마다 '지금 진입 가능'(장기는 '진입을 막는 조건 없음')인 종목을 점수순으로 다섯까지.
// 점수는 정수, 구간 경계 1점 안이면 '경계 근처'. 한계 문장은 후보 제목 바로 아래(UI 1차 묶음, 사용자 결정 2026-11-23).
const ASST_STYLE = { SWING: "스윙", LONG_TERM: "장기" };
function asstCands(c, note) {
  if (!c || !c.styles) return "";
  // points and score changes are not price moves (stage 2, visualization spec section 8 item 2): ink with ▲▼ and a sign, grey under one point
  const why = (r) => (r.plus ? `<div class="pts">▲ ${esc(r.plus.label)} +${r.plus.points.toFixed(1)}</div>` : "") + (r.minus ? `<div class="pts">▼ ${esc(r.minus.label)} −${Math.abs(r.minus.points).toFixed(1)}</div>` : "") || DASH;
  const moved = (r) => (isNum(r.prev) ? ` <small class="${Math.abs(r.score - r.prev) >= 1 ? "pts" : "flat"}" title="직전 기록 거래일과의 차이(1점 미만은 회색)">${r.score - r.prev >= 0 ? "+" : "−"}${Math.abs(r.score - r.prev).toFixed(1)}</small>` : "");
  const one = (k) => {
    const s = c.styles[k];
    if (!s) return "";
    const rows = s.rows.map((r) => `<tr><td class="l an"><button type="button" class="chip" data-ticker="${esc(r.ticker)}" title="${esc(tickerText(r.ticker, r.name || ""))}">${esc(nameFirst(r.ticker, r.name) ? r.name : r.ticker)}</button> <span class="meta m0 an-sub">${esc(nameFirst(r.ticker, r.name) ? r.ticker : r.name || "")}</span><div class="qr-m2">${esc(r.band_label || "")}</div></td>
      <td class="num"><b>${qsfInt(r.score)}</b>${moved(r)}${qsfNear(r.score, c.band_edges)}${r.confidence === "LOW" ? ' <span class="badge STALE" title="계산에 쓸 자료가 일부 없거나 오래됐습니다. 이 점수를 믿는 정도가 낮습니다.">신뢰도 낮음</span>' : ""}</td><td class="l w">${esc(r.band_label || "")}</td><td class="l w">${esc(sectorKo(r.sector))}</td><td class="l aw">${why(r)}</td></tr>`).join("");
    const ready = k === "LONG_TERM" ? "진입을 막는 조건 없음" : "지금 진입 가능";
    return `<div class="asst-cand"><h4>${ASST_STYLE[k]} <span class="meta m0">${ready} ${s.total}종목 · 그중 매수 후보 구간(70점 이상) ${s.buy_band}</span></h4>
      ${rows ? `<div class="tbl-wrap"><table><thead><tr><th class="l">종목</th><th>점수</th><th class="l w">구간</th><th class="l w">업종</th><th class="l">가점 / 감점</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<div class="meta">${ready}인 종목이 없습니다.</div>`}</div>`;
  };
  return `<h2>오늘의 후보 ${c.session ? `<span class="badge">${esc(c.session)}</span>` : ""}</h2>${note ? `<div class="notice">${esc(note)}</div>` : ""}<div class="asst-cands">${one("SWING")}${one("LONG_TERM")}</div><div class="meta">${esc(c.note || "")}</div>`;
}
// 작업 화면 (작업 화면 개편 3단계, 배치 명세 3.1 · 결정 D5): 맨 위 줄에 제목·요약 문장·시장 숫자 타일, 가운데에 묻는 칸과 답·할 일,
// 오른쪽에 오늘의 후보, 아래에 작업 상태.  뼈대는 한 번만 만들고 목록(asstBrief)은 data-brief가 붙은 네 칸만 채우므로, 목록을 새로
// 받아도 묻고 답한 칸은 지워지지 않습니다.  좁은 화면(내용 폭 1120px 미만)은 한 줄로: 맨 위 줄 → 묻기·답 → 할 일 → 후보 → 작업 상태.
const asstTitle = (mk) => `<h2>오늘 <span class="badge">${mk}</span></h2>`;
async function renderToday() {
  const box = $("#tab-today");
  state.loaded.today = true;
  const mk = isCoin() ? "코인" : isKR() ? "한국" : "미국";
  box.innerHTML = `<div class="ws" data-ws="today" id="asst-brief">
    <div class="ws-ctx" id="asst-ctx" data-brief>${asstTitle(mk)}<div class="meta">불러오는 중…</div></div>
    <div class="ws-body"><div class="ws-main">
      <div class="panel" id="asst-askp"><form id="asst-form" class="asst-ask" autocomplete="off"><input id="asst-q" maxlength="200" placeholder="${isCoin() ? "물어보기 (예: 코인 상위는? · 비트코인 분석해 줘 · help)" : `물어보기 (예: ${isKR() ? "삼성전자" : "AAPL"} 점수 왜 낮아? · 오늘 뭐 해야 해? · help)`}" aria-label="비서에게 묻기">
        <button class="btn-primary" type="submit">묻기</button><button class="ghost" type="button" id="asst-help">물어볼 수 있는 것</button></form>
      <div id="asst-out"></div></div>
      <div id="asst-items" data-brief></div></div>
      <div class="ws-right" role="complementary" aria-label="오늘의 후보" id="asst-cands" data-brief></div></div>
    <div class="ws-lower" id="asst-ops" data-brief></div></div>`;
  $("#asst-form").onsubmit = (e) => { e.preventDefault(); asstAsk($("#asst-q").value); };
  $("#asst-help").onclick = () => asstAsk("help");
  box.onclick = (e) => {
    const go = e.target.closest(".asst-go"), ex = e.target.closest(".asst-ex"), tk = e.target.closest("[data-ticker]");
    if (ex) return asstAsk(ex.textContent);
    if (go) return asstGo(go.dataset.tab, go.dataset.ticker, go.dataset.view);
    if (tk && tk.dataset.ticker) return openTicker(tk.dataset.ticker);
  };
  if (asstPending) { const q = asstPending; asstPending = null; asstAsk(q); }
  await asstBrief(false);
}
// 오늘 탭에 돌아왔을 때 (5차 묶음 P2-22, 사용자 결정 2026-11-23): 앞서 그린 화면을 그대로 두고 흐리게 한 뒤 '갱신 중'을 띄우고,
// 새 목록이 오면 바꿉니다.  받지 못하면 앞 화면이 언제 것인지 적어 둡니다.  묻고 답한 칸은 그대로입니다.
function asstReturn(scrollY) {
  window.scrollTo(0, scrollY);
  if (asstPending) { const q = asstPending; asstPending = null; asstAsk(q); window.scrollTo(0, 0); }
  asstBrief(true);
}
let asstBriefToken = 0;
async function asstBrief(again) {
  const brief = $("#asst-brief"), mk = isCoin() ? "코인" : isKR() ? "한국" : "미국", market = state.market, token = ++asstBriefToken;
  if (!brief) return;
  const ctx = $("#asst-ctx"), had = again && brief.dataset.at ? brief.dataset.at : "";
  if (had) {
    brief.querySelectorAll(".asst-refresh").forEach((x) => x.remove());
    brief.classList.add("refreshing");
    ctx.insertAdjacentHTML("afterbegin", `<div class="asst-refresh" role="status">갱신 중… 아래는 ${esc(stamp(had) || had)}에 만든 목록입니다.</div>`);
  }
  try {
    const d = await api(`/api/assistant/today?market=${market}`);
    if (token !== asstBriefToken || market !== state.market || !brief.isConnected) return;
    // 자동 실행·기록 상태는 아래 '작업 상태'로 따로 모읍니다(시장에 대해 할 일과 섞지 않습니다). 할 일 수준이 있으면 펼쳐 둡니다.
    const main = d.items.filter((i) => !i.ops), ops = d.items.filter((i) => i.ops);
    const groups = ASST_LEVELS.map((lv) => {
      const rows = main.filter((i) => i.level === lv);
      return rows.length ? `<h3 class="asst-h ${lv}">${esc(d.levels[lv])} <span class="badge">${rows.length}</span></h3><ul class="asst-list">${rows.map(asstItem).join("")}</ul>` : "";
    }).join("");
    const opsBox = ops.length ? `<details class="asst-ops"${ops.some((i) => i.level === "ACT") ? " open" : ""}><summary>작업 상태 (자동 실행·기록) <span class="badge">${ops.length}</span></summary><ul class="asst-list">${ops.map(asstItem).join("")}</ul></details>` : "";
    const unread = (d.unread_parts || []).length ? `<div class="msg err">읽지 못한 부분: ${d.unread_parts.map((p) => esc(p.label)).join(", ")}. 이 부분의 항목은 이 화면에 빠져 있습니다.</div>` : "";
    const cands = asstCands(d.candidates, d.note), note = d.candidates && d.candidates.styles ? "" : `<div class="meta">${esc(d.note)}</div>`;
    brief.classList.remove("refreshing");
    brief.dataset.at = d.generated_at || "";
    ctx.innerHTML = `${asstTitle(mk)}<div class="asst-headline">${esc(d.headline_main || d.headline)}</div><div class="meta">${mk} 시장 · 기준 거래일 ${esc(d.session || "기록 없음")} · ${when(d.generated_at)} 기준</div>
      ${unread}${asstTiles(d.tiles)}`;
    $("#asst-items").innerHTML = `<div class="panel">${groups ? `<h2>할 일과 알림</h2>${groups}` : '<div class="meta mt-0">보여 줄 항목이 없습니다.</div>'}</div>`;
    $("#asst-cands").innerHTML = cands ? `<div class="panel asst-candp">${cands}</div>` : "";            // 후보가 없으면(코인 시장 등) 오른쪽 칸 없이 한 줄
    $("#asst-ops").innerHTML = opsBox || note ? `<div class="panel span-all asst-lowp">${opsBox}${note}</div>` : "";
    const sparks = () => brief.querySelectorAll("canvas[data-spark]").forEach((cv) => spark(cv, JSON.parse(cv.dataset.spark)));
    redrawOn("today", "sparks", sparks);
    if (state.tab === "today") sparks(); else redrawLater.add("today:sparks");      // 숨은 탭의 캔버스는 폭이 0입니다
  } catch (e) {
    if (token !== asstBriefToken || !brief.isConnected) return;
    if (had) {
      brief.classList.remove("refreshing");
      brief.querySelectorAll(".asst-refresh").forEach((x) => x.remove());
      ctx.insertAdjacentHTML("afterbegin", `<div class="msg err">새 목록을 받지 못했습니다: ${esc(errKo(e))}. 아래는 ${esc(stamp(had) || had)}에 만든 목록입니다.</div>`);
    } else {
      ctx.innerHTML = asstTitle(mk);
      $("#asst-items").innerHTML = `<div class="panel"><div class="msg err mt-0">오늘 목록을 만들지 못했습니다: ${esc(errKo(e))}</div></div>`;
    }
  }
}
RENDER.today = renderToday;
RETURN.today = asstReturn;
