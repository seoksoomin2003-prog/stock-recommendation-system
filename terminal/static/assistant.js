// 오늘(비서): 프로그램이 이미 계산한 것을 정해진 규칙으로 정리해 보여 줍니다.  외부 AI를 쓰지 않고, 주문을 실행하지 않으며, 매수·매도를 권하지 않습니다.
"use strict";
const ASST_LEVELS = ["ACT", "DUE", "INFO"];
const ASST_TAB_KO = { portfolio: "포트폴리오", qsf: "점수", assist: "매매 보조", lab: "연구실", stock: "종목", today: "오늘", coin: "코인", overview: "시장 개요", macro: "거시" };
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
  } catch (e) { out.innerHTML = `<div class="msg err">${esc(ERR_KO[e.message] || e.message)}</div>`; }
}
// 명령창이나 다른 탭에서: 오늘 탭으로 옮긴 뒤 묻습니다.
function askAssistant(q) {
  asstPending = q;
  if (state.tab === "today" && $("#asst-q")) { asstPending = null; asstAsk(q); window.scrollTo(0, 0); return; }
  show("today"); window.scrollTo(0, 0);
}

async function renderToday() {
  const box = $("#tab-today");
  state.loaded.today = true;
  const mk = isCoin() ? "코인" : isKR() ? "한국" : "미국";
  box.innerHTML = `<div class="panel"><h2>오늘 <span class="badge">${mk}</span></h2>
      <form id="asst-form" class="asst-ask" autocomplete="off"><input id="asst-q" maxlength="200" placeholder="${isCoin() ? "물어보기 (예: 코인 상위는? · 비트코인 분석해 줘 · help)" : "물어보기 (예: 삼성전자 점수 왜 낮아? · 오늘 뭐 해야 해? · help)"}" aria-label="비서에게 묻기">
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
    const groups = ASST_LEVELS.map((lv) => {
      const rows = d.items.filter((i) => i.level === lv);
      return rows.length ? `<h3 class="asst-h ${lv}">${esc(d.levels[lv])} <span class="badge">${rows.length}</span></h3><ul class="asst-list">${rows.map(asstItem).join("")}</ul>` : "";
    }).join("");
    const unread = (d.unread_parts || []).length ? `<div class="msg err">읽지 못한 부분: ${d.unread_parts.map((p) => esc(p.label)).join(", ")}. 이 부분의 항목은 위 목록에 빠져 있습니다.</div>` : "";
    brief.innerHTML = `<h2>${esc(d.headline)}</h2><div class="meta" style="margin-top:0">${mk} 시장 · 기준 거래일 ${esc(d.session || "기록 없음")} · ${when(d.generated_at)} 기준</div>
      ${unread}${groups || '<div class="meta">보여 줄 항목이 없습니다.</div>'}<div class="meta">${esc(d.note)}</div>`;
  } catch (e) { brief.innerHTML = `<div class="msg err">오늘 목록을 만들지 못했습니다: ${esc(ERR_KO[e.message] || e.message)}</div>`; }
}
RENDER.today = renderToday;
ALWAYS_FRESH.add("today");
