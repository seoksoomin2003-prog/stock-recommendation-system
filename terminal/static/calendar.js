// 경제 일정: 연준·미국 노동통계국·한국은행이 공식 발표한 일정과 보유·관심 종목의 실적 발표일.  예상치·컨센서스는 없습니다.  읽기 전용.
"use strict";
const CAL_DOW = ["일", "월", "화", "수", "목", "금", "토"];

async function loadCalendar(box) {
  if (!box) return;
  box.innerHTML = ui.head({ title: "다가오는 경제 일정", sub: "60일" }) + loading;
  const mk = state.market;
  let d;
  try { d = await api(mq("/api/calendar?days=60")); } catch (e) { box.innerHTML = ui.head({ title: "다가오는 경제 일정" }) + errBox(e); return; }
  if (!box.isConnected || mk !== state.market) return;
  const rows = [
    ...d.items.map((i) => ({ day: i.date_kst, time: i.time_kst, away: i.days_away, country: i.country,
      what: `<b>${esc(i.name)}</b>${[i.label, !i.time_kst && i.country === "US" ? "미국 현지 날짜" : ""].filter(Boolean).map((x) => ` <span class="meta m0">${esc(x)}</span>`).join("")}`,
      tip: i.time_local ? `현지 ${i.date} ${i.time_local} (${i.time_zone})` : "발표 시각은 기관 일정표에 없습니다" })),
    ...(d.earnings || []).map((e) => ({ day: e.date, time: null, away: null, country: mk, ticker: e.ticker,
      what: `${tickerLabel(e.ticker, e.name, ` data-ticker="${esc(e.ticker)}" class="pointer"`)} 실적 발표 ${e.held ? ui.badge("보유") : ""}${e.watched ? ui.badge("관심") : ""}${e.stale ? ui.badge("오래된 일정", "risk-note") : ""}`,
      tip: "Yahoo 실적 일정 (회사 확정 전에는 추정치)" })),
    ...(d.dividends || []).map((e) => ({ day: e.date, time: null, away: null, country: mk, ticker: e.ticker,
      what: `${tickerLabel(e.ticker, e.name, ` data-ticker="${esc(e.ticker)}" class="pointer"`)} 배당락일 ${e.held ? ui.badge("보유") : ""}${e.watched ? ui.badge("관심") : ""}`,
      tip: "Yahoo 종목 정보의 배당락일 (공식 자료가 아니라 회사 공시와 다를 수 있음)" })),
  ].sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : (a.time || "99") < (b.time || "99") ? -1 : 1));
  const today = d.from;
  const dayLabel = (s) => { const t = new Date(`${s}T00:00:00`); return `${s.slice(5).replace("-", "/")} (${CAL_DOW[t.getDay()]})`; };
  const away = (s) => Math.round((new Date(`${s}T00:00:00`) - new Date(`${today}T00:00:00`)) / 864e5);
  let last = "";
  const line = (r) => { const first = r.day !== last; last = r.day; const n = away(r.day);
    return `<tr${first ? ' class="day-start"' : ""}><td class="l">${first ? `${dayLabel(r.day)} <span class="meta m0">${n === 0 ? "오늘" : n === 1 ? "내일" : n + "일 뒤"}</span>` : ""}</td>
      <td class="l num" title="${esc(r.tip)}">${r.time || DASH}</td><td class="l">${r.country === "KR" ? "한국" : "미국"}</td><td class="l" title="${esc(r.tip)}">${r.what}</td></tr>`; };
  box.innerHTML = `${ui.head({ title: "다가오는 경제 일정", sub: `${d.from} ~ ${d.to} · 한국 시각` })}
    ${ui.table({ cls: "cal", cols: ["날짜", "시각", "나라", "일정"].map((label) => ({ label, cls: "l" })), rows: rows.map(line), empty: "60일 안에 공식 발표된 일정이 없습니다." })}
    ${d.series.filter((s) => s.runs_out || s.stale).map((s) => ui.notice(`${esc(s.name)}: 공식 일정은 ${esc(s.covers_until)}까지만 들어 있습니다${s.stale ? ` (마지막 확인 ${esc(s.checked)}, 갱신 필요)` : ""}. ${esc(s.note || "")}`)).join("")}
    <div class="meta">${esc(d.basis)} 실적 발표일은 ${mk === "KR" ? "한국" : "미국"} 보유·관심 종목 가운데 스캔 때 저장한 날짜만 보입니다${d.earnings_status && d.earnings_status !== "REAL" ? ` (지금은 읽지 못함: ${esc(d.earnings_status)})` : ""}.
      출처: ${d.series.map((s) => `${safeUrl(s.source) ? `<a href="${esc(safeUrl(s.source))}" target="_blank" rel="noopener">${esc(s.name)}</a>` : esc(s.name)} (${esc(s.checked)} 확인)`).join(" · ")}</div>`;
  box.querySelectorAll("[data-ticker]").forEach((b) => (b.onclick = () => openTicker(b.dataset.ticker)));
}
