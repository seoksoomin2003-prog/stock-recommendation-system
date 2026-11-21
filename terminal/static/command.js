// 명령창과 단축키: '/' 또는 Ctrl/⌘+K로 열고, 종목 코드·회사명·탭 이름·명령을 쳐서 바로 이동한다.  읽기 전용 이동만 한다.
"use strict";
const CMD_ALIASES = {
  today: ["오늘", "비서", "할일", "today", "brief"], coin: ["코인 순위", "coin rank"],
  overview: ["개요", "시장", "overview", "ov"], stock: ["종목", "stock", "des"], qsf: ["점수", "score", "qsf", "순위", "rank"],
  map: ["지도", "히트맵", "heatmap", "map", "imap", "rrg", "순환"], compare: ["비교", "compare", "comp"],
  macro: ["거시", "macro", "eco", "일정", "캘린더", "calendar"], watch: ["관심", "관심종목", "watch", "watchlist"],
  portfolio: ["포트폴리오", "포트", "portfolio", "port", "위험", "risk"], assist: ["보조", "매매", "assist", "알림", "alert", "alrt"],
  model: ["모델", "model"], lab: ["연구", "연구실", "lab", "기록"],
};
const CMD_MARKETS = { US: ["미국", "us", "usa"], KR: ["한국", "kr", "korea"], COIN: ["코인", "coin", "crypto", "가상자산"] };

function cmdTabs() {
  return [...document.querySelectorAll(".tabs button")].map((b) => ({ tab: b.dataset.tab, label: b.textContent.trim(), key: "" }));
}
// What a typed line means, best first.  Each item: {label, hint, run}.
function cmdParse(raw) {
  const q = raw.trim(), low = q.toLowerCase(), out = [];
  if (!q) {
    cmdTabs().forEach((t) => out.push({ label: t.label, hint: t.key ? `탭 · ${t.key}` : "탭", run: () => show(t.tab) }));
    recentTickers().slice(0, 6).forEach((t) => out.push({ label: t, hint: "최근 본 종목", run: () => openTicker(t) }));
    return out;
  }
  const words = q.split(/\s+/), first = words[0], rest = words.slice(1).join(" ").toLowerCase();
  for (const [m, names] of Object.entries(CMD_MARKETS)) if (names.includes(low)) out.push({ label: `${names[0]} 시장으로 전환`, hint: "시장", run: () => setMarket(m) });
  const tabs = cmdTabs();
  for (const t of tabs) {
    const names = [t.label, ...(CMD_ALIASES[t.tab] || [])].map((s) => s.toLowerCase());
    if (names.some((n) => n.startsWith(low) || low.startsWith(n) && low.length <= n.length + 1)) out.push({ label: t.label, hint: "탭", run: () => show(t.tab) });
  }
  const code = first.toUpperCase();
  if (/^[0-9][0-9A-Z]{5}$/.test(code) || /^\^?[A-Z][A-Z0-9.\-]{0,9}$/.test(code)) {
    const target = tabs.find((t) => rest && [t.label, ...(CMD_ALIASES[t.tab] || [])].some((n) => n.toLowerCase() === rest));
    const item = target && target.tab === "compare" && typeof compareWith === "function"
      ? { label: `${code} 비교 차트`, hint: "비교", run: () => compareWith([code]) }
      : { label: `${code} 종목 화면`, hint: "종목", run: () => openTicker(code) };
    // a word that is exactly a tab or market name (port, kr, map) goes there first; the ticker of the same letters comes second
    const exact = words.length === 1 && (Object.values(CMD_MARKETS).flat().includes(low) || tabs.some((t) => [t.label, ...(CMD_ALIASES[t.tab] || [])].some((n) => n.toLowerCase() === low)));
    exact ? out.push(item) : out.unshift(item);
  }
  if (/[가-힣]/.test(q) && !out.length) out.push({ label: `'${q}' 한국 종목 검색`, hint: "검색", run: () => searchKr(q) });
  if (typeof askAssistant === "function" && ["help", "h", "?", "？", "도움", "도움말", "질문", "질문 목록", "비서"].includes(low))
    out.unshift({ label: "비서에게 물어볼 수 있는 질문 목록 보기", hint: "도움말", run: () => askAssistant("help") });
  // 문장으로 적은 것은 비서에게 묻습니다.  물음표로 끝나거나 묻는 말이 들어 있으면 맨 위에 둡니다.
  if (q.length >= 2 && typeof askAssistant === "function" && (/\s/.test(q) || /[?？]$/.test(q))) {
    const ask = { label: `'${q}' 비서에게 묻기`, hint: "질문", run: () => askAssistant(q) };
    /[?？]$|왜|어때|뭐|뭘|언제|어디|얼마|돼|될까|할까|알려|괜찮/.test(q) ? out.unshift(ask) : out.push(ask);
  }
  return out;
}

const cmdEl = document.createElement("div");
cmdEl.id = "cmd";
cmdEl.hidden = true;
cmdEl.innerHTML = `<div class="cmd-box" role="dialog" aria-label="명령창"><input id="cmd-q" autocomplete="off" spellcheck="false" placeholder="종목 코드, 회사명, 탭 이름, 질문, help (예: AAPL, 삼성전자, 점수, 지도, 한국)">
  <ul id="cmd-list" role="listbox"></ul>
  <div class="cmd-help">↑↓ 선택 · Enter 이동 · Esc 닫기 · 어디서나 <kbd>/</kbd> 또는 <kbd>⌘K</kbd> · 묶음 바로가기 <kbd>1</kbd>~<kbd>6</kbd> · 시장 전환 <kbd>M</kbd> · 도움말 <kbd>?</kbd></div></div>`;
document.body.appendChild(cmdEl);
let cmdItems = [], cmdSel = 0;
function cmdPaint() {
  $("#cmd-list").innerHTML = cmdItems.map((it, i) => `<li role="option" class="${i === cmdSel ? "on" : ""}" data-i="${i}"><span>${esc(it.label)}</span><small>${esc(it.hint)}</small></li>`).join("")
    || '<li class="none">해당하는 이동이 없습니다.</li>';
}
function cmdOpen() {
  cmdEl.hidden = false; $("#cmd-q").value = ""; cmdItems = cmdParse(""); cmdSel = 0; cmdPaint(); $("#cmd-q").focus();
}
function cmdClose() { cmdEl.hidden = true; }
function cmdRun(i) { const it = cmdItems[i]; if (!it) return; cmdClose(); it.run(); window.scrollTo(0, 0); }
$("#cmd-q").addEventListener("input", (e) => { cmdItems = cmdParse(e.target.value); cmdSel = 0; cmdPaint(); });
$("#cmd-q").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { cmdSel = Math.min(cmdSel + 1, cmdItems.length - 1); cmdPaint(); e.preventDefault(); }
  else if (e.key === "ArrowUp") { cmdSel = Math.max(cmdSel - 1, 0); cmdPaint(); e.preventDefault(); }
  else if (e.key === "Enter" && !e.isComposing) { cmdRun(cmdSel); e.preventDefault(); }
  else if (e.key === "Escape") cmdClose();
});
$("#cmd-list").addEventListener("click", (e) => { const li = e.target.closest("li[data-i]"); if (li) cmdRun(+li.dataset.i); });
cmdEl.addEventListener("click", (e) => { if (e.target === cmdEl) cmdClose(); });

function typing(e) { const t = e.target; return t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)); }
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); cmdEl.hidden ? cmdOpen() : cmdClose(); return; }
  if (!cmdEl.hidden || typing(e) || e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
  if (e.key === "/") { e.preventDefault(); cmdOpen(); return; }
  if (e.key === "?") { e.preventDefault(); cmdOpen(); return; }
  if (/^[1-9]$/.test(e.key)) { const g = document.querySelectorAll(".groups button")[+e.key - 1]; if (g) { showGroup(g.dataset.group); window.scrollTo(0, 0); } return; }
  if (e.key === "m" || e.key === "M") setMarket({ US: "KR", KR: "COIN", COIN: "US" }[state.market] || "US");
});
$("#cmdbtn").onclick = cmdOpen;
