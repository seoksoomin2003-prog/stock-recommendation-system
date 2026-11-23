// 명령창과 단축키: '/' 또는 Ctrl/⌘+K로 열고, 종목 코드·회사명·탭 이름·명령을 쳐서 바로 이동한다.  읽기 전용 이동만 한다.
"use strict";
const CMD_ALIASES = {
  today: ["오늘", "비서", "할일", "today", "brief"], coin: ["코인 순위", "coin rank"],
  overview: ["개요", "시장", "overview", "ov"], stock: ["종목", "stock", "des"], qsf: ["점수", "score", "qsf", "순위", "rank"],
  map: ["지도", "히트맵", "heatmap", "map", "imap", "rrg", "순환"], compare: ["비교", "compare", "comp"],
  chart: ["차트", "차트분석", "chart", "rsi", "macd", "볼린저", "bollinger", "이평", "이동평균"],
  macro: ["거시", "macro", "eco", "일정", "캘린더", "calendar"], watch: ["관심", "관심종목", "watch", "watchlist"],
  portfolio: ["포트폴리오", "포트", "portfolio", "port", "위험", "risk"], assist: ["보조", "매매", "assist", "알림", "alert", "alrt"],
  model: ["모델", "model"], lab: ["연구", "연구실", "lab", "기록"],
};
const CMD_MARKETS = { US: ["미국", "us", "usa"], KR: ["한국", "kr", "korea"], COIN: ["코인", "coin", "crypto", "가상자산"] };

const CMD_HELP = ["help", "h", "?", "？", "도움", "도움말", "질문", "질문 목록", "비서"];

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
      : target && target.tab === "chart" && typeof chartWith === "function" ? { label: `${code} 차트분석`, hint: "차트", run: () => chartWith(code) }
      : { label: `${code} 종목 화면`, hint: "종목", ticker: code, run: () => findSymbol(code) };      // 스캔한 종목의 코드가 아니면 가까운 종목을 먼저 묻습니다
    // 'X 점수': 그 종목의 점수 카드 (6차 묶음 P2-15).  코드는 종목 화면, 점수는 카드라는 규칙을 명령창에서도 지킵니다.
    const scoreItem = typeof qsfOpenCard === "function" && !isCoin() ? { label: `${code} 점수 카드`, hint: "점수", run: () => qsfOpenCard(code) } : null;
    // a word that is exactly a tab or market name (port, kr, map) goes there first; the ticker of the same letters comes second
    const exact = words.length === 1 && (Object.values(CMD_MARKETS).flat().includes(low) || tabs.some((t) => [t.label, ...(CMD_ALIASES[t.tab] || [])].some((n) => n.toLowerCase() === low)));
    exact ? out.push(item) : out.unshift(item);
    if (scoreItem && target && target.tab === "qsf") out.unshift(scoreItem);          // 'X 점수': 카드가 먼저
    else if (scoreItem && !target) out.splice(out.indexOf(item) + 1, 0, scoreItem);   // 코드만: 종목 화면 바로 다음
  }
  if (/[가-힣]/.test(q) && !out.length) out.push({ label: `'${q}' 한국 종목 검색`, hint: "검색", run: () => findSymbol(q) });
  if (typeof askAssistant === "function" && CMD_HELP.includes(low))
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
cmdEl.innerHTML = `<div class="cmd-box" role="dialog" aria-modal="true" aria-label="명령창"><input id="cmd-q" role="combobox" aria-expanded="true" aria-controls="cmd-list" aria-autocomplete="list" aria-label="명령창 입력" autocomplete="off" spellcheck="false" placeholder="종목 코드, 회사명, 탭 이름, 질문, help (예: AAPL, 삼성전자, 점수, 지도, 한국)">
  <ul id="cmd-list" role="listbox" aria-label="이동할 곳"></ul>
  <div class="cmd-help" id="cmd-help"></div><div class="cmd-keys"><button type="button" class="ghost" id="cmd-keys"></button></div></div>`;
document.body.appendChild(cmdEl);
let cmdItems = [], cmdSel = 0, cmdMoved = false, cmdSymTimer = null, cmdSymToken = 0, cmdBack = null;
// 한 글자 단축키(/ ? 1~9 M) 켜고 끄기 (5차 묶음 P3-4, 사용자 결정 2026-11-23): 기본은 켜짐.  ⌘K(Ctrl+K)는 늘 됩니다.
let keysOn = true;
try { keysOn = localStorage.getItem("qse-keys") !== "off"; } catch (e) { /* storage unavailable: on */ }
function keysPaint() {
  const label = keysOn ? "한 글자 단축키 끄기" : "한 글자 단축키 켜기";
  $("#keysbtn").textContent = label; $("#cmd-keys").textContent = label;
  $("#cmd-help").innerHTML = "↑↓ 선택 · Enter 이동 · Esc 닫기 · " + (keysOn
    ? "어디서나 <kbd>/</kbd> 또는 <kbd>⌘K</kbd> · 묶음 바로가기 <kbd>1</kbd>~<kbd>9</kbd>(메뉴 순서) · 시장 전환 <kbd>M</kbd> · 도움말 <kbd>?</kbd>"
    : "한 글자 단축키 꺼짐 · 명령창은 <kbd>⌘K</kbd>(Ctrl+K)로 엽니다");
}
function keysToggle() {
  keysOn = !keysOn;
  try { localStorage.setItem("qse-keys", keysOn ? "on" : "off"); } catch (e) { /* not remembered */ }
  keysPaint();
  if (typeof notify === "function") notify(keysOn ? "한 글자 단축키를 켰습니다." : "한 글자 단축키를 껐습니다. 명령창은 ⌘K(Ctrl+K)로 엽니다.", "info");
}
// 시장·탭 이름이나 도움말처럼 그 자체가 명령인 말
function cmdIsCommand(low) {
  return CMD_HELP.includes(low) || Object.values(CMD_MARKETS).flat().includes(low) || cmdTabs().some((t) => [t.label, ...(CMD_ALIASES[t.tab] || [])].some((n) => n.toLowerCase() === low));
}
// 명령이 아닌 말은 스캔한 종목에서도 찾아(/api/symbols) 결과에 더합니다.  이미 있던 이동 결과의 순서는 바꾸지 않고, 검색·질문 줄 앞에 넣습니다.
function cmdSymbols(raw) {
  clearTimeout(cmdSymTimer);
  const token = ++cmdSymToken, q = raw.trim();
  if (!q || q.length > 30 || /[?？]$/.test(q) || cmdIsCommand(q.toLowerCase())) return;
  cmdSymTimer = setTimeout(async () => {
    let d;
    try { d = await symbolSuggest(q); } catch (e) { return; }
    if (token !== cmdSymToken || cmdEl.hidden || $("#cmd-q").value.trim() !== q) return;
    const have = new Set(cmdItems.map((it) => it.ticker).filter(Boolean));
    const found = (d.items || []).filter((i) => !have.has(i.ticker))
      .map((i) => ({ label: `${i.ticker} ${i.name}`, hint: `종목 · ${MARKET_KO[i.market] || i.market}`, ticker: i.ticker, run: () => openTicker(i.ticker) }));
    if (!found.length) return;
    const cur = cmdItems[cmdSel];
    let at = cmdItems.length;
    while (at > 0 && ["검색", "질문"].includes(cmdItems[at - 1].hint)) at--;
    cmdItems.splice(at, 0, ...found);
    cmdSel = cmdMoved ? Math.max(0, cmdItems.indexOf(cur)) : 0;          // 화살표로 고른 줄은 그 줄에 그대로 둡니다
    cmdPaint();
  }, 150);
}
function cmdPaint() {
  $("#cmd-list").innerHTML = cmdItems.map((it, i) => `<li role="option" id="cmd-opt-${i}" aria-selected="${i === cmdSel}" class="${i === cmdSel ? "on" : ""}" data-i="${i}"><span>${esc(it.label)}</span><small>${esc(it.hint)}</small></li>`).join("")
    || '<li class="none">해당하는 이동이 없습니다.</li>';
  const on = $("#cmd-opt-" + cmdSel);
  on ? $("#cmd-q").setAttribute("aria-activedescendant", on.id) : $("#cmd-q").removeAttribute("aria-activedescendant");
  if (on) on.scrollIntoView({ block: "nearest" });
}
// 열 때 초점이 있던 곳을 기억해 닫을 때 되돌립니다 (5차 묶음 P2-13).  고른 곳으로 이동할 때는 되돌리지 않습니다.
function cmdOpen() {
  cmdBack = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
  cmdEl.hidden = false; $("#cmd-q").value = ""; cmdItems = cmdParse(""); cmdSel = 0; cmdMoved = false; cmdSymbols(""); cmdPaint(); $("#cmd-q").focus();
}
function cmdClose(back = true) {
  if (cmdEl.hidden) return;
  cmdEl.hidden = true;
  if (back && cmdBack && cmdBack.isConnected) cmdBack.focus();
  cmdBack = null;
}
function cmdRun(i) { const it = cmdItems[i]; if (!it) return; cmdClose(false); it.run(); window.scrollTo(0, 0); }
$("#cmd-q").addEventListener("input", (e) => { cmdItems = cmdParse(e.target.value); cmdSel = 0; cmdMoved = false; cmdPaint(); cmdSymbols(e.target.value); });
$("#cmd-q").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { cmdSel = Math.min(cmdSel + 1, cmdItems.length - 1); cmdMoved = true; cmdPaint(); e.preventDefault(); }
  else if (e.key === "ArrowUp") { cmdSel = Math.max(cmdSel - 1, 0); cmdMoved = true; cmdPaint(); e.preventDefault(); }
  else if (e.key === "Enter" && !e.isComposing) { cmdRun(cmdSel); e.preventDefault(); }
  else if (e.key === "Escape") cmdClose();
});
// 창이 열린 동안 Tab은 입력칸과 단축키 단추 사이에서만 돕니다.
cmdEl.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && e.target.id !== "cmd-q") return cmdClose();
  if (e.key !== "Tab") return;
  e.preventDefault();
  (document.activeElement === $("#cmd-q") ? $("#cmd-keys") : $("#cmd-q")).focus();
});
$("#cmd-keys").onclick = keysToggle;
$("#keysbtn").onclick = keysToggle;
keysPaint();
$("#cmd-list").addEventListener("click", (e) => { const li = e.target.closest("li[data-i]"); if (li) cmdRun(+li.dataset.i); });
cmdEl.addEventListener("click", (e) => { if (e.target === cmdEl) cmdClose(); });

function typing(e) { const t = e.target; return t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)); }
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); cmdEl.hidden ? cmdOpen() : cmdClose(); return; }
  if (!keysOn || !cmdEl.hidden || typing(e) || e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
  if (e.key === "/") { e.preventDefault(); cmdOpen(); return; }
  if (e.key === "?") { e.preventDefault(); cmdOpen(); return; }
  // 숫자 키는 왼쪽 메뉴에 보이는 묶음의 순서를 따릅니다 (작업 화면 개편 2026-11-24): 코인 시장에서는 1 오늘, 2 내 계좌, 3 코인.
  if (/^[1-9]$/.test(e.key)) { const g = navGroups()[+e.key - 1]; if (g) { showGroup(g); window.scrollTo(0, 0); } return; }
  if (e.key === "m" || e.key === "M") setMarket({ US: "KR", KR: "COIN", COIN: "US" }[state.market] || "US");
});
$("#cmdbtn").onclick = cmdOpen;
