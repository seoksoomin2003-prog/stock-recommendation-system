// 경제 일정: 연준·미국 노동통계국·한국은행이 공식 발표한 일정과 보유·관심 종목의 실적 발표일.  예상치·컨센서스는 없습니다.  읽기 전용.
"use strict";
const CAL_DOW = ["일", "월", "화", "수", "목", "금", "토"];

async function loadCalendar(box) {
  if (!box) return;
  box.innerHTML = `<h2>다가오는 경제 일정 <span class="meta" style="margin:0">60일</span></h2>${loading}`;
  const mk = state.market;
  let d;
  try { d = await api(mq("/api/calendar?days=60")); } catch (e) { box.innerHTML = `<h2>다가오는 경제 일정</h2>${errBox(e)}`; return; }
  if (!box.isConnected || mk !== state.market) return;
  const rows = [
    ...d.items.map((i) => ({ day: i.date_kst, time: i.time_kst, away: i.days_away, country: i.country,
      what: `<b>${esc(i.name)}</b>${[i.label, !i.time_kst && i.country === "US" ? "미국 현지 날짜" : ""].filter(Boolean).map((x) => ` <span class="meta" style="margin:0">${esc(x)}</span>`).join("")}`,
      tip: i.time_local ? `현지 ${i.date} ${i.time_local} (${i.time_zone})` : "발표 시각은 기관 일정표에 없습니다" })),
    ...(d.earnings || []).map((e) => ({ day: e.date, time: null, away: null, country: mk, ticker: e.ticker,
      what: `<b data-ticker="${esc(e.ticker)}" style="cursor:pointer">${esc(e.ticker)}</b> ${esc(e.name || "")} 실적 발표 ${e.held ? '<span class="badge">보유</span>' : ""}${e.watched ? '<span class="badge">관심</span>' : ""}${e.stale ? '<span class="badge risk-note">오래된 일정</span>' : ""}`,
      tip: "Yahoo 실적 일정 (회사 확정 전에는 추정치)" })),
  ].sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : (a.time || "99") < (b.time || "99") ? -1 : 1));
  const today = d.from;
  const dayLabel = (s) => { const t = new Date(`${s}T00:00:00`); return `${s.slice(5).replace("-", "/")} (${CAL_DOW[t.getDay()]})`; };
  const away = (s) => Math.round((new Date(`${s}T00:00:00`) - new Date(`${today}T00:00:00`)) / 864e5);
  let last = "";
  box.innerHTML = `<h2>다가오는 경제 일정 <span class="meta" style="margin:0">${esc(d.from)} ~ ${esc(d.to)} · 한국 시각</span></h2>
    ${rows.length ? `<div class="tbl-wrap"><table class="cal"><thead><tr><th class="l">날짜</th><th class="l">시각</th><th class="l">나라</th><th class="l">일정</th></tr></thead><tbody>
      ${rows.map((r) => { const first = r.day !== last; last = r.day; const n = away(r.day);
        return `<tr${first ? ' class="day-start"' : ""}><td class="l">${first ? `${dayLabel(r.day)} <span class="meta" style="margin:0">${n === 0 ? "오늘" : n === 1 ? "내일" : n + "일 뒤"}</span>` : ""}</td>
          <td class="l num" title="${esc(r.tip)}">${r.time || DASH}</td><td class="l">${r.country === "KR" ? "한국" : "미국"}</td><td class="l" title="${esc(r.tip)}">${r.what}</td></tr>`; }).join("")}
      </tbody></table></div>` : '<div class="empty">60일 안에 공식 발표된 일정이 없습니다.</div>'}
    ${d.series.filter((s) => s.runs_out || s.stale).map((s) => `<div class="notice">${esc(s.name)}: 공식 일정은 ${esc(s.covers_until)}까지만 들어 있습니다${s.stale ? ` (마지막 확인 ${esc(s.checked)}, 갱신 필요)` : ""}. ${esc(s.note || "")}</div>`).join("")}
    <div class="meta">${esc(d.basis)} 실적 발표일은 ${mk === "KR" ? "한국" : "미국"} 보유·관심 종목 가운데 스캔 때 저장한 날짜만 보입니다${d.earnings_status && d.earnings_status !== "REAL" ? ` (지금은 읽지 못함: ${esc(d.earnings_status)})` : ""}.
      출처: ${d.series.map((s) => `<a href="${esc(s.source)}" target="_blank" rel="noopener">${esc(s.name)}</a> (${esc(s.checked)} 확인)`).join(" · ")}</div>`;
  box.querySelectorAll("[data-ticker]").forEach((b) => (b.onclick = () => openTicker(b.dataset.ticker)));
}
