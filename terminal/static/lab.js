// TERMINAL-3: 도전자 모델 전향적 비교(모델 탭) + 연구실 탭.  Uses helpers from app.js.
"use strict";
// Model colours are categorical series slots (visualization spec 2.5): not the status green, not a moving-average colour.  SPY is the benchmark.
const LAB_COLORS = { MOM_12_1: "--s1", LOWVOL_252: "--s2", TREND_SWING: "--s3", BASE_EW: "--s4", SPY: "--bench" };
const pctR = (v, d = 2) => (isNum(v) ? pct(v * 100, d) : DASH);

// ------------------------------------------------------------------ 모델 탭: 전향적 비교
const _renderModelBase = RENDER.model;
RENDER.model = async function () {
  await _renderModelBase();
  if (isKR()) return;                  // challengers and the research lab are US only so far
  const host = $("#tab-model");
  const panel = document.createElement("div");
  panel.className = "panel"; panel.id = "cmp"; panel.innerHTML = loading;
  // replace the stage-1 placeholder panel ("도전자 모델") with the comparison
  const old = [...host.querySelectorAll(".panel")].find((p) => p.querySelector("h2") && p.querySelector("h2").textContent.trim() === "도전자 모델");
  if (old) old.replaceWith(panel); else host.appendChild(panel);
  renderComparison();
};
async function renderComparison() {
  const el = $("#cmp"); if (!el) return;
  let d;
  try { d = await api("/api/lab/compare"); } catch (e) { el.innerHTML = `<h2>도전자 모델 비교</h2><div class="msg err">${esc(errKo(e))}</div>`; return; }
  const H = d.horizons;
  const cell = (a) => {
    if (!a || !a.matured) return `<td class="num"><span class="missing">${a && a.pending ? "대기 " + a.pending : "—"}</span></td>`;
    return `<td class="num" title="만기 ${a.matured}개 · 독립 표본 약 ${a.independent.toFixed(1)}개 · SPY 이긴 비율 ${(a.hit_rate * 100).toFixed(0)}%">${pctR(a.mean_excess)}<br><span class="meta m0">${a.matured}개 · ${esc(a.verdict)}</span></td>`;
  };
  const latest = (m) => {
    const l = d.latest[m]; if (!l) return '<span class="missing">기록 없음</span>';
    const ts = l.picks.slice(0, 10).map((x) => `<b data-ticker="${esc(x.ticker)}" class="pointer">${esc(x.ticker)}</b>`).join(" ");
    return `${ts}${l.n_picks > 10 ? ` 외 ${l.n_picks - 10}` : ""} <span class="meta m0">· 진입 ${esc(l.entry_session)}</span>`;
  };
  el.innerHTML = `<h2>도전자 모델 비교 (전향적) ${d.integrity.status !== "OK" ? badge("UNAVAILABLE") : ""}</h2>
    <div class="notice">앞으로 생기는 실제 가격으로만 비교합니다. 기록이 쌓이기 전에는 모두 '대기' 또는 '판단 보류'입니다.
      독립 표본이 ${d.min_independent}개 이상 쌓이기 전에는 어느 모델이 낫다고 판단하지 마세요.</div>
    <div class="tbl-wrap"><table><thead><tr><th>모델</th><th class="l">성격</th><th>코호트</th>${H.map((h) => `<th>${h}일 평균 초과수익<br><span class="meta m0">vs SPY</span></th>`).join("")}<th class="l">최근 선정 종목</th></tr></thead>
    <tbody>${d.order.map((m) => { const r = d.results[m] || { cohorts: 0, horizons: {} }; const meta = d.models[m] || {};
      return `<tr><td title="${esc(meta.rule || "")}"><b>${esc(meta.name || m)}</b>${m === "P6-11B" ? " " + badge("FROZEN") : ""}</td><td class="l">${esc(meta.style || "")}</td>
        <td class="num">${r.cohorts}</td>${H.map((h) => cell(r.horizons[String(h)])).join("")}<td class="l" style="white-space:normal;min-width:220px">${latest(m)}</td></tr>`; }).join("")}</tbody></table></div>
    <div class="meta">${esc(d.method)} 가격 데이터 마지막 날 ${esc(d.panel_last || "없음")} · 다음 신호일 ${esc(d.signal_session)}.</div>
    <div class="mt-3"><button id="labrun" class="btn-primary">데이터 갱신 + 오늘 신호 기록</button>
      <span class="meta" id="labmsg">미국 장 마감(동부 17:00, 한국 오전 7시경) 이후에 실행하면 그날 종가로 기록됩니다. 같은 날 여러 번 눌러도 한 번만 기록됩니다.</span></div>
    <div class="meta" id="autoline"></div>`;
  $("#labrun").onclick = startLabRun;
  automationLine().then((t) => { const n = $("#autoline"); if (n) n.textContent = t; });
  if (d.job && d.job.state === "RUNNING") pollLab();
}
async function automationLine() {
  const a = await api("/api/automation/status").catch(() => null);
  if (!a) return "";
  const tg = { CONFIGURED: "텔레그램 연결됨", NOT_CONFIGURED: "텔레그램 미설정", INVALID: "텔레그램 설정 오류" }[a.telegram];
  const run = a.installed ? `자동 실행 켜짐 (한국 시간 ${a.schedule_kst[0]})` : "자동 실행 꺼짐";
  const last = a.last_run ? `마지막 실행 ${a.last_run.at.slice(0, 16).replace("T", " ")} UTC, 기준 거래일 ${a.last_run.session}` : "실행 기록 없음";
  const gaps = a.last_run && a.last_run.missing_sessions.length ? `, 빠진 거래일 ${a.last_run.missing_sessions.length}일` : "";
  const sa = a.server_agent;
  const srv = sa ? (sa.installed ? `서버 자동 재시작 켜짐${sa.runs > 1 ? ` (재시작 ${sa.runs - 1}회)` : ""}` : "서버 자동 재시작 꺼짐") : "";
  return `${run} · ${srv ? srv + " · " : ""}${tg} · ${last}${gaps}`;
}
async function startLabRun() {
  try { await post("/api/lab/run", {}); pollLab(); } catch (e) { $("#labmsg").textContent = errKo(e); }
}
async function pollLab() {
  const msg = $("#labmsg"), btn = $("#labrun");
  if (btn) btn.disabled = true;
  const s = await api("/api/lab/status").catch(() => null);
  const j = s && s.job;
  if (!j) { if (btn) btn.disabled = false; return; }
  if (j.state === "RUNNING") {
    if (msg) msg.textContent = `가격 받는 중… ${j.total ? `${j.done}/${j.total}` : ""} (처음에는 몇 분 걸립니다)`;
    setTimeout(pollLab, 3000); return;
  }
  if (btn) btn.disabled = false;
  if (j.state === "FAILED" && msg) { msg.className = "msg err"; msg.textContent = "실패: " + errKo({ message: j.error || "" }); return; }
  if (j.state === "DONE") {
    const r = j.result.record;
    if (msg) { msg.className = "msg ok"; msg.textContent = r.recorded.length ? `${r.signal_session} 신호 ${r.recorded.length}개 모델 기록 완료 (진입 ${r.entry_session}).` : `${r.signal_session} 신호는 이미 기록되어 있습니다.`; }
    setTimeout(renderComparison, 800);
  }
}

// ------------------------------------------------------------------ 연구실
let labData = null, labCost = "0";
async function renderLab() {
  const el = $("#labbody"); if (!el) return;
  if (isKR()) { el.innerHTML = '<div class="panel empty">연구실은 아직 미국 전용입니다. 위에서 미국을 선택하면 볼 수 있습니다.</div>'; return; }
  el.innerHTML = '<div class="panel empty">과거 시뮬레이션 계산 중… (처음에는 수십 초 걸릴 수 있습니다)</div>';
  let d;
  try { d = await api("/api/lab/research"); } catch (e) { el.innerHTML = errBox(e); return; }
  state.loaded.lab = true;
  if (d.status !== "REAL") { el.innerHTML = `<div class="panel"><h2>연구실</h2><div class="empty">${esc(d.reason || "")}</div><div class="meta">모델 탭의 '데이터 갱신' 버튼으로 가격 데이터를 먼저 받으세요.</div></div>`; return; }
  labData = d;
  const codes = Object.keys(d.models);
  const yrs = Object.keys(d.benchmark.by_year || {});
  const row = (name, m, color) => `<tr><td><span style="color:var(${color})">●</span> <b>${esc(name)}</b></td><td>${pctR(m.total_return, 1)}</td><td>${pctR(m.cagr, 1)}</td><td class="num">${isNum(m.vol) ? (m.vol * 100).toFixed(1) + "%" : DASH}</td><td class="num">${fmt(m.sharpe, 2)}</td><td>${pctR(m.max_drawdown, 1)}</td><td class="num">${isNum(m.avg_turnover) ? (m.avg_turnover * 100).toFixed(0) + "%" : DASH}</td></tr>`;
  el.innerHTML = `
    <div class="panel"><h2>연구실 — 과거 시뮬레이션 <span class="badge STALE">참고용</span></h2>
      <div class="notice"><b>참고용입니다.</b><ul style="margin:6px 0 0 18px;padding:0">${d.limitations.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
      <div class="head my-2"><span class="meta m0">거래 비용(편도)</span>
        <span class="seg" id="costseg">${d.costs_bps.map((c) => `<button data-c="${c}" class="${String(c) === labCost ? "on" : ""}">${c} bps</button>`).join("")}</span></div>
      <div class="chart"><canvas id="labc"></canvas></div>
      <div class="legend mt-2">${codes.map((c) => `<span><i style="background:var(${LAB_COLORS[c]})"></i>${esc(d.models_meta[c].name)}</span>`).join("")}<span><i style="background:var(--bench)"></i>SPY</span></div>
      <div class="meta">${esc(d.method)} · 유니버스 ${d.universe_size}종목 · 데이터 마지막 날 ${esc(d.panel_last)}
        · 지수 편입일 적용 ${d.membership && d.membership.pit ? `예 (${esc(d.membership.source || "")}, ${when(d.membership.retrieved_at)})` : '<b class="err">아니오</b>'}</div></div>
    <div class="panel"><h2>성과 지표 <span class="meta m0" id="costlbl">비용 ${labCost} bps</span></h2><div class="tbl-wrap"><table id="labtbl"></table></div>
      <div class="meta">샤프 비율은 무위험수익률 0을 가정했습니다. 회전율은 월 교체 시 평균 교체 비중입니다.</div></div>
    <div class="panel"><h2>연도별 SPY 대비 초과수익</h2><div class="tbl-wrap"><table id="labyr"></table></div>
      <div class="meta">첫 해와 마지막 해는 1년이 채 되지 않는 기간입니다.</div></div>
    <div class="panel"><h2>규칙 (미리 고정, 튜닝하지 않음)</h2><table><tbody>${codes.map((c) => `<tr><td><b>${esc(d.models_meta[c].name)}</b></td><td class="l wrap">${esc(d.models_meta[c].rule)}</td></tr>`).join("")}</tbody></table></div>`;
  const fill = () => {
    $("#costlbl").textContent = `비용 ${labCost} bps`;
    $("#labtbl").innerHTML = `<thead><tr><th>모델</th><th>누적</th><th>연환산</th><th>변동성</th><th>샤프</th><th>최대 낙폭</th><th>회전율</th></tr></thead><tbody>
      ${codes.map((c) => row(d.models_meta[c].name, d.models[c][labCost], LAB_COLORS[c])).join("")}${row("SPY (매수 후 보유)", d.benchmark, "--bench")}</tbody>`;
    $("#labyr").innerHTML = `<thead><tr><th>모델</th>${yrs.map((y) => `<th>${y}</th>`).join("")}</tr></thead><tbody>
      ${codes.map((c) => `<tr><td>${esc(d.models_meta[c].name)}</td>${yrs.map((y) => `<td>${pctR((d.models[c][labCost].excess_by_year || {})[y], 1)}</td>`).join("")}</tr>`).join("")}
      <tr><td class="meta">SPY 수익률</td>${yrs.map((y) => `<td>${pctR(d.benchmark.by_year[y], 1)}</td>`).join("")}</tr></tbody>`;
    drawLab();
  };
  $("#costseg").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; labCost = b.dataset.c; $("#costseg").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); fill(); };
  fill(); redrawOn("lab", "main", drawLab);
}
function drawLab() {
  const cv = $("#labc"), d = labData;
  if (!cv || !cv.isConnected || !d) return;
  const { ctx, w, h } = setupCanvas(cv, isPhone() ? 240 : 320);
  const series = Object.keys(d.models).map((c) => ({ c, s: d.models[c][labCost] })).filter((x) => x.s && x.s.nav);
  series.push({ c: "SPY", s: d.benchmark });
  const all = series.flatMap((x) => x.s.nav).filter(isNum).map((v) => Math.log(v));
  let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * 0.05 || 0.1; lo -= pad; hi += pad;
  const padR = 52, n = d.benchmark.nav.length;
  const y = (v) => 6 + (1 - (Math.log(v) - lo) / (hi - lo)) * (h - 26);
  const T = vizTokens();
  ctx.font = vizFont(11); ctx.fillStyle = T.tick; ctx.textBaseline = "middle";
  for (let k = 0; k <= 4; k++) { const lv = lo + ((hi - lo) * k) / 4, v = Math.exp(lv), yy = y(v); ctx.strokeStyle = T.grid; ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(w - padR, yy); ctx.stroke(); ctx.fillText(((v - 1) * 100).toFixed(0) + "%", w - padR + 6, yy); }
  ctx.textBaseline = "bottom"; ctx.fillText(d.benchmark.dates[0], 0, h); ctx.textAlign = "right"; ctx.fillText(d.benchmark.dates[n - 1], w - padR, h); ctx.textAlign = "left";
  series.forEach(({ c, s }) => { const m = s.nav.length; line(ctx, s.nav, (i) => (i / (m - 1)) * (w - padR), y, cssVar(LAB_COLORS[c]), c === "SPY" ? 1.3 : 1.8); });
}

// ------------------------------------------------------------------ 전향 기록 현황판
const SPAN = (y) => (y <= 0 ? "지금 충족" : y < 1 ? `약 ${Math.max(1, Math.round(y * 12))}개월` : `약 ${y < 10 ? y.toFixed(1) : Math.round(y)}년`);
function recordProgress(q) {
  return (q.progress || []).reduce((a, p) => { a[`${p.strategy}|${p.horizon}`] = p; return a; }, {});
}
// 시세 이력 점검: 점수를 계산한 일봉 자체가 맞는지. 읽기 전용, 점수를 고치지 않습니다.
function recAudit(pa) {
  if (!pa) return "";
  const one = (name, x) => {
    if (!x || x.status !== "REAL") return `<div class="meta">${name}: 점검 결과 없음</div>`;
    const kinds = Object.entries(x.by_kind || {}).map(([k, n]) => `${esc(x.kind_text[k])} ${n}건`).join(", ");
    const days = (x.common_dates || []).map((c) => `${esc(c.date)}(${c.stocks}종목)`).join(", ");
    return `<div class="kv"><div><span>${name} 점검 종목</span><b class="num">${x.checked}</b></div><div><span>문제 있는 종목</span><b class="num">${x.flagged}${x.bad ? ` <span class="meta m0">(심각 ${x.bad})</span>` : ""}</b></div><div><span>기준 스캔</span><b>${esc(x.session)}</b></div>${x.market === "US" ? `<div><span>확정 전 마지막 일봉</span><b class="num">${x.provisional_last_bars}</b></div>` : ""}</div>
      <div class="meta">${esc(x.source)}. ${kinds ? `${kinds}.` : "문제를 찾지 못했습니다."}${days ? ` 여러 종목이 함께 틀린 날: ${days}.` : ""}</div>`;
  };
  return `<h3>시세 이력 점검 <span class="meta m0">점수 입력 확인 · 점수에 반영 안 함</span></h3>${one("미국", pa.US)}${one("한국", pa.KR)}
    <div class="meta">최근 1년(${(pa.KR && pa.KR.window_sessions) || (pa.US && pa.US.window_sessions) || 253}거래일)만 봅니다. 한국은 KRX 공식 일별 시세와, 미국은 두 번째 무료 출처가 없어 NYSE 거래일 달력과 일봉 자체의 앞뒤만 맞춰 봅니다.</div>`;
}
async function renderRecord() {
  const el = $("#recpanel"); if (!el) return;
  el.innerHTML = `<div class="panel">${loading}</div>`;
  let d;
  try { d = await api("/api/record"); } catch (e) { el.innerHTML = errBox(e); return; }
  const us = d.qsf.US, kr = d.qsf.KR, b = d.baseline, a = d.automation;
  const pu = recordProgress(us), pk = recordProgress(kr);
  const rows = (us.progress || []).map((p) => {
    const k = pk[`${p.strategy}|${p.horizon}`] || {};
    const cell = (x) => `${isNum(x.independent) ? x.independent.toFixed(1) : DASH} / ${x.target} <span class="meta m0">(만기 ${x.matured_sessions})</span>`;
    return `<tr${p.primary ? ' class="rec-primary"' : ""}><td class="l">${p.strategy === "SWING" ? "스윙" : "장기"} ${p.horizon}거래일${p.primary ? " (주 지평)" : ""}</td><td class="num">${p.needed_sessions.toLocaleString("ko-KR")}</td><td class="num">${cell(p)}</td><td class="num">${cell(k)}</td><td class="num">${SPAN(p.remaining_years)}</td></tr>`;
  }).join("");
  const mk = (name, q) => `<div><span>${name} 기록 거래일</span><b class="num">${q.sessions}</b></div><div><span>${name} 현재 버전</span><b class="num">${q.current_version_sessions}</b></div><div><span>${name} 마지막 기록</span><b>${esc(q.last || "—")}</b></div>`;
  const stat = { OK: "완료", FAILED: "실패", SKIPPED: "건너뜀", WAITING: "자료 대기" };
  const f = d.kr_forward;
  const u = d.us_challenger;
  el.innerHTML = `<div class="panel"><h2>전향 기록 현황 <span class="tech-id">${esc(d.model_version)}</span></h2>
    ${d.alerts.length ? `<ul class="rec-alerts">${d.alerts.map((x) => `<li class="${x.level}">${esc(x.text)}</li>`).join("")}</ul>` : '<div class="meta">문제없이 기록이 쌓이고 있습니다.</div>'}
    <h3>QSF 점수 기록</h3><div class="kv">${mk("미국", us)}${mk("한국", kr)}</div>
    <h3>판단까지 남은 기간</h3><div class="tbl-wrap"><table><thead><tr><th class="l">지평</th><th>필요 거래일</th><th>미국 독립 표본</th><th>한국 독립 표본</th><th>남은 기간 (미국)</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="meta">현재 버전 기록만 셉니다. 독립 표본은 만기 거래일 수를 지평으로 나눈 값이고, ${d.minimum_independent}개가 기준입니다. 남은 기간은 매 거래일 빠짐없이 기록한다고 가정한 값입니다.</div>
    <h3>기준 모델 기록</h3>${b.status === "REAL" ? `<div class="kv"><div><span>자본금</span><b>${b.capital_configured ? "입력됨" : '<span class="missing">미입력</span>'}</b></div><div><span>결과 확정 / 기준</span><b class="num">${b.completed} / ${b.target}</b></div><div><span>결과 대기</span><b class="num">${b.pending}</b></div><div><span>유효 스캔 날짜</span><b class="num">${b.scan_dates}</b></div><div><span>마지막 유효 스캔</span><b>${esc(b.last_scan_date || "—")}</b></div></div>` : `<div class="empty">추적 기록을 읽지 못했습니다 (${esc(b.error || "")}).</div>`}
    <h3>한국 결합 점수 기록 <span class="meta m0">라이브와 분리</span></h3><div class="kv"><div><span>기록 거래일</span><b class="num">${f.sessions}</b></div><div><span>마지막 기록</span><b>${esc(f.last || "—")}</b></div><div><span>늦은 기록</span><b class="num">${f.late}</b></div><div><span>독립 표본 (20거래일)</span><b class="num">${f.independent.toFixed(1)} / ${f.target}</b></div><div><span>남은 기간</span><b>${SPAN(f.remaining_sessions / 252)}</b></div><div><span>시세 대조 (KRX)</span><b>${f.price_check ? `${esc(f.price_check.session)}: ${f.price_check.checked}종목 중 ${f.price_check.gaps}개 차이` : DASH}</b></div></div>
    <div class="meta">재무 점수 기록: ${f.fund.sessions}거래일 · 마지막 ${esc(f.fund.last || "—")} · 독립 표본 ${f.fund.independent.toFixed(1)} / ${f.fund.target}</div>
    ${f.events ? `<div class="meta">공시 사건 기록: ${f.events.sessions}거래일 · 마지막 ${esc(f.events.last || "—")} · 독립 표본 ${f.events.independent.toFixed(1)} / ${f.events.target}</div>` : ""}
    <h3>미국 도전자 점수 기록 <span class="meta m0">라이브와 분리</span></h3><div class="kv"><div><span>기록 거래일</span><b class="num">${u.sessions}</b></div><div><span>마지막 기록</span><b>${esc(u.last || "—")}</b></div><div><span>늦은 기록</span><b class="num">${u.late}</b></div><div><span>스윙 독립 표본 (20거래일)</span><b class="num">${u.independent.toFixed(1)} / ${u.target}</b></div><div><span>장기 독립 표본 (63거래일)</span><b class="num">${u.long_independent.toFixed(1)} / ${u.target}</b></div></div>
    <div class="meta">점수와 날짜만 쌓습니다. 수익률은 표본이 찬 뒤 한 번만 평가합니다. 이 점수는 추천과 라이브 점수에 쓰이지 않습니다.${u.sessions ? "" : ` 첫 기록 대상은 ${esc(u.first_due)}입니다.`}</div>
    ${recAudit(d.price_audit)}
    <h3>자동 실행</h3><div class="kv">${d.disk ? `<div><span>디스크 여유</span><b class="num">${d.disk.free_gb}GB</b></div>` : ""}${d.backup ? `<div><span>마지막 백업</span><b>${esc(d.backup.latest || "—")}</b></div>` : ""}<div><span>설치</span><b>${a.installed ? "설치됨" : '<span class="missing">미설치</span>'}</b></div><div><span>실행 시각</span><b>${esc(a.schedule_text || (a.schedule_kst || []).join(", "))}</b></div><div><span>마지막 실행</span><b>${a.last_run_at ? when(a.last_run_at) : DASH}</b></div><div><span>기준 거래일</span><b>${esc(a.latest_session || "—")}</b></div></div>
    <div class="meta">${a.steps.map((s) => `${esc(s.name)}: ${esc(stat[s.status] || "기록 없음")}`).join(" · ")}</div>
    <div class="meta">${esc(d.note)}</div></div>`;
}
RENDER.lab = async function () {
  $("#tab-lab").innerHTML = '<div id="recpanel"></div><div id="labbody"></div>';
  renderRecord();
  await renderLab();
};
