// 오늘(비서): 프로그램이 이미 계산한 것을 정해진 규칙으로 정리해 보여 줍니다.  외부 AI를 쓰지 않고, 주문을 실행하지 않으며, 매수·매도를 권하지 않습니다.
"use strict";
const ASST_LEVELS = ["ACT", "DUE", "INFO"];
const ASST_TAB_KO = { account: "내 계좌", portfolio: "시장별 자세히", committee: "투자위원회", qsf: "점수", assist: "매매 보조", lab: "연구실", stock: "종목", today: "오늘", coin: "코인", overview: "시장 개요", macro: "거시" };
let asstPending = null;       // 명령창에서 넘어온 질문

function asstGo(tab, ticker) {
  if (ticker && tab === "stock") return openTicker(ticker);
  show(tab); window.scrollTo(0, 0);
}
function asstItem(i) {
  const where = i.tab && i.tab !== "today" ? `<button type="button" class="ghost asst-go" data-tab="${esc(i.tab)}">${esc(ASST_TAB_KO[i.tab] || i.tab)} 탭에서 보기</button>` : "";
  const stock = i.ticker ? `<button type="button" class="chip" data-ticker="${esc(i.ticker)}">${esc(i.ticker)}</button>` : "";
  return `<li class="asst-item ${esc(i.level)}"><div>${esc(i.text)}</div><div class="asst-act">${stock}${where}</div></li>`;
}
// 답: 결론 한 줄을 먼저, 그 아래 제목이 붙은 묶음들, 끝에 자료 기준과 이어서 물어볼 것.
function asstAnswer(a) {
  const list = (rows) => `<ul>${rows.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  const body = (a.sections || []).length ? a.sections.map((s) => `<h4>${esc(s.title)}</h4>${list(s.lines)}`).join("") : a.summary ? "" : list(a.lines || []);
  const chips = (rows, cls) => `<div class="chips">${rows.map((x) => `<button type="button" class="chip ${cls}">${esc(x)}</button>`).join("")}</div>`;
  const follow = (a.follow || []).length ? `<h4>이어서 물어보기</h4>${chips(a.follow, "asst-ex")}` : "";
  const more = (a.examples || []).length ? `<h4>눌러서 물어보기</h4>${chips(a.examples, "asst-ex")}` : "";
  const go = a.tab && a.tab !== "today" ? `<button type="button" class="ghost asst-go" data-tab="${esc(a.tab)}" data-ticker="${esc(a.ticker || "")}">${esc(ASST_TAB_KO[a.tab] || a.tab)} 탭에서 보기</button>` : "";
  return `<div class="asst-answer ${a.status === "REAL" ? "" : "unknown"}"><div class="asst-q">${esc(a.question || "")}</div><h3>${esc(a.title || "")}</h3>
    ${a.summary ? `<p class="asst-sum">${esc(a.summary)}</p>` : ""}${body}${a.basis ? `<div class="meta">${esc(a.basis)}</div>` : ""}${follow}${more}
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
      <div><span class="badge${bad ? " risk-note" : ""}">${esc(ms.label || "")}</span>${bad && isNum(ms.size_factor) && ms.size_factor < 1 ? ` <span class="meta" style="margin:0">새 주문 크기 ${(ms.size_factor * 100).toFixed(0)}%</span>` : ""}</div>
      <div class="meta" style="margin-top:4px">${esc(ms.session || "")} 기록</div></div>` : "";
  return `<div class="grid asst-tiles">${t.items.map(card).join("")}${st}</div>${meta(t.source || "", t.fetched_at)}`;
}
// 오늘의 후보(사용자 결정 2026-11-23): 스타일마다 '지금 진입 가능'(장기는 '진입을 막는 조건 없음')인 종목을 점수순으로 다섯까지.
// 점수는 정수, 구간 경계 1점 안이면 '경계 근처'. 한계 문장은 후보 제목 바로 아래(UI 1차 묶음, 사용자 결정 2026-11-23).
const ASST_STYLE = { SWING: "스윙", LONG_TERM: "장기" };
function asstCands(c, note) {
  if (!c || !c.styles) return "";
  const why = (r) => (r.plus ? `<div class="up">▲ ${esc(r.plus.label)} +${r.plus.points.toFixed(1)}</div>` : "") + (r.minus ? `<div class="down">▼ ${esc(r.minus.label)} −${Math.abs(r.minus.points).toFixed(1)}</div>` : "") || DASH;
  const moved = (r) => (isNum(r.prev) ? ` <small class="${r.score - r.prev >= 1 ? "up" : r.score - r.prev <= -1 ? "down" : "flat"}" title="직전 기록 거래일과의 차이(1점 미만은 회색)">${r.score - r.prev >= 0 ? "+" : "−"}${Math.abs(r.score - r.prev).toFixed(1)}</small>` : "");
  const one = (k) => {
    const s = c.styles[k];
    if (!s) return "";
    const rows = s.rows.map((r) => `<tr><td class="l an"><button type="button" class="chip" data-ticker="${esc(r.ticker)}">${esc(r.ticker)}</button> <span class="meta" style="margin:0">${esc(r.name || "")}</span></td>
      <td class="num"><b>${qsfInt(r.score)}</b>${moved(r)}${qsfNear(r.score, c.band_edges)}</td><td class="l w">${esc(r.band_label || "")}</td><td class="l w">${esc(sectorKo(r.sector))}</td><td class="l aw">${why(r)}</td></tr>`).join("");
    const ready = k === "LONG_TERM" ? "진입을 막는 조건 없음" : "지금 진입 가능";
    return `<div class="asst-cand"><h4>${ASST_STYLE[k]} <span class="meta" style="margin:0">${ready} ${s.total}종목 · 그중 매수 후보 구간(70점 이상) ${s.buy_band}</span></h4>
      ${rows ? `<div class="tbl-wrap"><table><thead><tr><th class="l">종목</th><th>점수</th><th class="l w">구간</th><th class="l w">업종</th><th class="l">가점 / 감점</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<div class="meta">${ready}인 종목이 없습니다.</div>`}</div>`;
  };
  return `<h3>오늘의 후보 ${c.session ? `<span class="badge">${esc(c.session)}</span>` : ""}</h3>${note ? `<div class="notice">${esc(note)}</div>` : ""}<div class="asst-cands">${one("SWING")}${one("LONG_TERM")}</div><div class="meta">${esc(c.note || "")}</div>`;
}
let asstSparks = null;
async function renderToday() {
  const box = $("#tab-today");
  state.loaded.today = true;
  const mk = isCoin() ? "코인" : isKR() ? "한국" : "미국";
  box.innerHTML = `<div class="panel"><h2>오늘 <span class="badge">${mk}</span></h2>
      <form id="asst-form" class="asst-ask" autocomplete="off"><input id="asst-q" maxlength="200" placeholder="${isCoin() ? "물어보기 (예: 코인 상위는? · 비트코인 분석해 줘 · help)" : `물어보기 (예: ${isKR() ? "삼성전자" : "AAPL"} 점수 왜 낮아? · 오늘 뭐 해야 해? · help)`}" aria-label="비서에게 묻기">
        <button class="btn-primary" type="submit">묻기</button><button class="ghost" type="button" id="asst-help">물어볼 수 있는 것</button></form>
      <div id="asst-out"></div></div>
    <div class="panel" id="asst-brief">${loading}</div>`;
  $("#asst-form").onsubmit = (e) => { e.preventDefault(); asstAsk($("#asst-q").value); };
  $("#asst-help").onclick = () => asstAsk("help");
  box.onclick = (e) => {
    const go = e.target.closest(".asst-go"), ex = e.target.closest(".asst-ex"), tk = e.target.closest("[data-ticker]");
    if (ex) return asstAsk(ex.textContent);
    if (go) return asstGo(go.dataset.tab, go.dataset.ticker);
    if (tk && tk.dataset.ticker) return openTicker(tk.dataset.ticker);
  };
  if (asstPending) { const q = asstPending; asstPending = null; asstAsk(q); }
  const brief = $("#asst-brief");
  try {
    const d = await api(`/api/assistant/today?market=${state.market}`);
    if (state.tab !== "today" || !$("#asst-brief")) return;
    // 자동 실행·기록 상태는 아래 '작업 상태'로 따로 모읍니다(시장에 대해 할 일과 섞지 않습니다). 할 일 수준이 있으면 펼쳐 둡니다.
    const main = d.items.filter((i) => !i.ops), ops = d.items.filter((i) => i.ops);
    const groups = ASST_LEVELS.map((lv) => {
      const rows = main.filter((i) => i.level === lv);
      return rows.length ? `<h3 class="asst-h ${lv}">${esc(d.levels[lv])} <span class="badge">${rows.length}</span></h3><ul class="asst-list">${rows.map(asstItem).join("")}</ul>` : "";
    }).join("");
    const opsBox = ops.length ? `<details class="asst-ops"${ops.some((i) => i.level === "ACT") ? " open" : ""}><summary>작업 상태 (자동 실행·기록) <span class="badge">${ops.length}</span></summary><ul class="asst-list">${ops.map(asstItem).join("")}</ul></details>` : "";
    const unread = (d.unread_parts || []).length ? `<div class="msg err">읽지 못한 부분: ${d.unread_parts.map((p) => esc(p.label)).join(", ")}. 이 부분의 항목은 이 화면에 빠져 있습니다.</div>` : "";
    brief.innerHTML = `<h2>${esc(d.headline_main || d.headline)}</h2><div class="meta" style="margin-top:0">${mk} 시장 · 기준 거래일 ${esc(d.session || "기록 없음")} · ${when(d.generated_at)} 기준</div>
      ${unread}${asstTiles(d.tiles)}${asstCands(d.candidates, d.note)}${groups ? `<h3>할 일과 알림</h3>${groups}` : '<div class="meta">보여 줄 항목이 없습니다.</div>'}${opsBox}${d.candidates && d.candidates.styles ? "" : `<div class="meta">${esc(d.note)}</div>`}`;
    if (asstSparks) redrawers.delete(asstSparks);
    asstSparks = () => brief.querySelectorAll("canvas[data-spark]").forEach((cv) => spark(cv, JSON.parse(cv.dataset.spark)));
    asstSparks(); redrawers.add(asstSparks);
  } catch (e) { brief.innerHTML = `<div class="msg err">오늘 목록을 만들지 못했습니다: ${esc(errKo(e))}</div>`; }
}
RENDER.today = renderToday;
ALWAYS_FRESH.add("today");
