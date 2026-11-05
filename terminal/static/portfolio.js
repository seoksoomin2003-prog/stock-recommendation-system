// TERMINAL-2: 포트폴리오 · 매매 보조.  Uses helpers from app.js.  No orders are ever placed.
"use strict";
const KIND_KO = { DEPOSIT: "입금", WITHDRAW: "출금", BUY: "매수", SELL: "매도", DIVIDEND: "배당", FEE: "비용", PLAN: "손절·목표 설정", STYLE: "구분 변경", VOID: "취소" };
const STYLE_KO = { LONG: "장기", SWING: "스윙" };
const KIND_FIELDS = { DEPOSIT: ["amount"], WITHDRAW: ["amount"], FEE: ["amount"], DIVIDEND: ["ticker", "amount"],
  BUY: ["ticker", "style", "qty", "price", "fee", "stop", "target"], SELL: ["ticker", "qty", "price", "fee"], PLAN: ["ticker", "stop", "target"], STYLE: ["ticker", "style"] };
const FIELD_KO = { ticker: "종목 코드", style: "구분", qty: "수량(주)", price: "가격($)", fee: "수수료($)", amount: "금액($)", stop: "손절가($, 선택)", target: "목표가($, 선택)" };
const BIND_KO = { RISK: "1회 거래 위험 한도", WEIGHT: "종목당 최대 비중", CASH: "보유 현금" };
let prefill = null;

function money(v, d = 2) {
  if (!isNum(v)) return DASH;
  const n = isKR() ? 0 : d;
  return `${v < 0 ? "-" : ""}${isKR() ? "₩" : "$"}${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: n, maximumFractionDigits: n })}`;
}
const curSym = () => (isKR() ? "₩" : "$");
const wrongMarket = (t) => `${t}은(는) ${marketOf(t) === "KR" ? "한국" : "미국"} 종목입니다. 위의 시장 스위치를 ${marketOf(t) === "KR" ? "한국" : "미국"}으로 바꾼 뒤 입력하세요.`;
const KR_SELL_HINT = "한국 주식 매도 시 수수료 칸에는 증권사 수수료와 증권거래세(2026년 코스피·코스닥 모두 0.20%)를 합쳐 넣으세요. 세율은 바뀔 수 있으니 체결 내역의 금액을 기준으로 하세요.";
function pnl(v) { return isNum(v) ? `<span class="${v > 0 ? "up" : v < 0 ? "down" : "flat"} num">${v > 0 ? "+" : ""}${money(v)}</span>` : DASH; }
const qtyFmt = (v) => (isNum(v) ? v.toLocaleString("ko-KR", { maximumFractionDigits: 4 }) : DASH);
function todayET() { return new Intl.DateTimeFormat("en-CA", { timeZone: isKR() ? "Asia/Seoul" : "America/New_York" }).format(new Date()); }
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// ------------------------------------------------------------------ 포트폴리오
async function renderPortfolio() {
  const el = $("#tab-portfolio"), mk = state.market;
  if (!el.innerHTML) el.innerHTML = loading;
  let d;
  try { d = await api(mq("/api/portfolio")); } catch (e) { if (mk === state.market) el.innerHTML = errBox(e); return; }
  if (mk !== state.market) return;
  state.loaded.portfolio = true;
  const s = d.summary, fx = d.fx, empty = !d.journal.length;
  const krw = (v) => (mk === "US" && isNum(v) && isNum(fx.usdkrw) ? `<span class="meta" style="margin:0">≈ ₩${Math.round(v * fx.usdkrw).toLocaleString("ko-KR")}</span>` : "");
  el.innerHTML = `
    ${d.integrity.status !== "OK" ? `<div class="notice">거래 기록 무결성 오류: ${esc(d.integrity.reason || "")}${d.integrity.line ? ` (${d.integrity.line}번째 줄)` : ""}. 새 기록 추가가 중단됩니다. data/terminal/journal.jsonl 을 확인하세요.</div>` : ""}
    ${empty ? `<div class="panel"><h2>시작하기</h2><div class="meta" style="font-size:13px">1) 아래 '거래 기록'에서 <b>입금</b>을 먼저 기록하고 2) 실제로 체결된 <b>매수·매도</b>를 기록하세요.
      보유 종목·평균단가·손익은 기록으로부터 자동 계산됩니다. 기록은 이 Mac에만 저장되며, 잘못 입력한 기록은 삭제 대신 '취소'로 무효화합니다.</div></div>` : ""}
    ${totalHtml(d.total)}
    <div class="panel"><h2>${mk === "KR" ? "한국(원화)" : "미국(달러)"} 계좌 요약 ${s.complete ? "" : badge("STALE")}</h2>
      ${s.complete ? "" : `<div class="notice">시세가 없는 종목(${esc(s.missing_prices.join(", "))})이 있어 총액을 확정할 수 없습니다.</div>`}
      <div class="head"><span class="big num">${money(s.equity)}</span> ${krw(s.equity)}</div>
      <div class="kv">
        <div><span>총 손익 (평가액 − 순입금)</span><b>${pnl(s.total_pnl)}</b></div>
        <div><span>오늘 손익</span><b>${pnl(s.day_pnl)}</b></div>
        <div><span>미실현 손익</span><b>${pnl(s.unrealized)}</b></div>
        <div><span>실현 손익</span><b>${pnl(s.realized)}</b></div>
        <div><span>현금</span><b class="num">${money(s.cash)}</b> <span class="meta" style="margin:0">${isNum(s.cash_pct) ? s.cash_pct.toFixed(1) + "%" : ""}</span></div>
        <div><span>주식 평가액</span><b class="num">${money(s.market_value)}</b></div>
        <div><span>순입금</span><b class="num">${money(s.net_deposits)}</b></div>
        <div><span>배당 / 비용</span><b class="num">${money(s.dividends)} / ${money(s.fees)}</b></div>
        <div><span>손절 시 손실 합계</span><b class="num">${money(s.risk_to_stops)}</b> <span class="meta" style="margin:0">${isNum(s.risk_to_stops_pct) ? "계좌의 " + s.risk_to_stops_pct.toFixed(2) + "%" : ""}</span></div>
      </div>
      ${s.unprotected.length ? `<div class="meta">손절가 미설정 종목은 손실 합계에 포함되지 않습니다: ${esc(s.unprotected.join(", "))}</div>` : ""}
      ${meta(d.source, d.cache && d.cache.fetched_at, isNum(fx.usdkrw) ? `원/달러 ${fmt(fx.usdkrw)} (${esc(fx.date || "")})` : "")}</div>
    ${d.alerts.length ? `<div class="panel"><h2>경고 <span class="meta" style="margin:0">${d.alerts.length}건 · 화면 표시만 하며 주문하지 않습니다</span></h2>
      <ul class="alerts">${d.alerts.map((a) => `<li class="${esc(a.level)}">${esc(a.text)}</li>`).join("")}</ul></div>` : ""}
    ${holdingsHtml(d)}
    ${Object.keys(d.sectors).length ? `<div class="panel"><h2>섹터 비중 <span class="meta" style="margin:0">한도 ${d.settings.max_sector_pct}%</span></h2><table><tbody>
      ${Object.entries(d.sectors).map(([k, v]) => `<tr><td>${esc(k)}</td><td style="width:60%"><div class="bar ${v > d.settings.max_sector_pct ? "over" : ""}"><i style="width:${Math.min(100, v).toFixed(1)}%"></i></div></td><td class="num">${v.toFixed(1)}%</td></tr>`).join("")}
      </tbody></table></div>` : ""}
    <div class="panel"><h2>계좌 수익률 vs ${esc(d.benchmark)}</h2><div id="eq-sum" class="meta">불러오는 중…</div><div class="chart"><canvas id="eqc"></canvas></div><div id="eq-meta"></div></div>
    <div class="panel"><h2>매매 성과 (매도 건 기준)</h2>${statsHtml(d.stats)}
      ${d.stats.count ? styleStatsHtml(d.stats_by_style) : ""}
      ${d.closed.length ? `<div class="tbl-wrap"><table><thead><tr><th>매도일</th><th class="l">종목</th><th class="l">구분</th><th>수량</th><th>평균단가</th><th>매도가</th><th>실현 손익</th><th>수익률</th><th>보유 일수</th></tr></thead>
      <tbody>${d.closed.slice(0, 50).map((c) => `<tr><td>${esc(c.date)}</td><td class="l"><b>${esc(c.ticker)}</b></td><td class="l">${esc(STYLE_KO[c.style] || "미지정")}</td><td class="num">${qtyFmt(c.qty)}</td><td class="num">${money(c.avg_cost)}</td><td class="num">${money(c.price)}</td><td>${pnl(c.pnl)}</td><td>${pct(c.return_pct, 1)}</td><td class="num">${c.hold_days}일</td></tr>`).join("")}</tbody></table></div>` : ""}</div>
    <div class="panel" id="jform-panel"><h2>거래 기록 추가</h2>${formHtml(d)}</div>
    <div class="panel"><h2>거래 기록 <span class="meta" style="margin:0">${d.journal.length}건 · 추가만 가능, 취소는 별도 기록으로 남습니다</span></h2>
      ${d.journal.length ? `<div class="tbl-wrap"><table><thead><tr><th>날짜</th><th class="l">종류</th><th class="l">종목</th><th>수량</th><th>가격</th><th>금액</th><th class="l">메모</th><th></th></tr></thead>
      <tbody>${d.journal.map(journalRow).join("")}</tbody></table></div>` : '<div class="empty">기록이 없습니다.</div>'}</div>
    <div class="panel meta">${esc(d.note)}</div>`;
  bindForm(d);
  loadSignals();
  el.querySelectorAll("[data-void]").forEach((b) => (b.onclick = async (e) => {
    e.stopPropagation();
    if (!confirm("이 기록을 취소할까요? 원래 기록은 남고, 취소 기록이 추가됩니다.")) return;
    try { await post("/api/journal/void", { ref: b.dataset.void }); renderPortfolio(); } catch (err) { alert(err.message); }
  }));
  loadEquity();
}
function totalHtml(t) {
  if (!t) return "";
  const won = (v) => (isNum(v) ? `₩${Math.round(v).toLocaleString("ko-KR")}` : DASH);
  return `<div class="panel"><h2>전체 자산 <span class="meta" style="margin:0">원화 환산</span></h2>
    <div class="head"><span class="big num">${won(t.krw)}</span></div>
    ${isNum(t.krw) ? "" : '<div class="notice">시세나 환율이 없는 항목이 있어 합계를 확정할 수 없습니다.</div>'}
    <div class="kv"><div><span>한국 계좌</span><b class="num">${won(t.kr_equity)}</b></div>
      <div><span>미국 계좌</span><b class="num">${won(t.us_krw)}</b> <span class="meta" style="margin:0">${isNum(t.us_equity) ? "$" + t.us_equity.toLocaleString("en-US", { maximumFractionDigits: 2 }) : ""}</span></div>
      <div><span>원/달러</span><b class="num">${isNum(t.usdkrw) ? fmt(t.usdkrw) : DASH}</b> <span class="meta" style="margin:0">${esc(t.fx_date || "")}</span></div></div></div>`;
}
function holdingRow(h) {
  const stop = h.stop ? `${money(h.stop)} <span class="meta" style="margin:0">(${pct(h.stop_distance_pct, 1, false)})</span>` : '<span class="missing">미설정</span>';
  const swing = h.style === "SWING";
  return `<tr class="click" data-ticker="${esc(h.ticker)}"><td><b>${esc(h.ticker)}</b>${h.name ? ` <span class="meta" style="margin:0">${esc(h.name)}</span>` : ""} ${liveBadge(h.intraday)}${h.status !== "REAL" ? " " + badge(h.status) : ""}</td>
    <td class="num">${isNum(h.weight_pct) ? h.weight_pct.toFixed(1) + "%" : DASH}</td><td class="num" data-sig="score" data-t="${esc(h.ticker)}">${DASH}</td><td class="l" data-sig="action" data-t="${esc(h.ticker)}">${DASH}</td><td class="num">${stop}</td>
    ${swing ? `<td class="num">${h.target ? money(h.target) : DASH}</td><td class="l" data-sig="left" data-t="${esc(h.ticker)}">${DASH}</td>` : `<td class="l" data-sig="review" data-t="${esc(h.ticker)}">${DASH}</td>`}
    <td>${pnl(h.unrealized)} ${pct(h.unrealized_pct, 1)}</td><td>${pct(h.change_pct)}</td><td class="num">${qtyFmt(h.qty)}</td><td class="num">${money(h.avg_cost)}</td><td class="num">${money(h.close)}</td><td class="num">${money(h.value)}</td>
    <td class="l">${esc(h.sector || "미분류")}</td></tr>`;
}
function holdingTable(title, rows, style, sum, target) {
  if (!rows.length) return "";
  const swing = style === "SWING";
  const head = sum ? `<span class="meta" style="margin:0">${rows.length}개 · 평가액 ${money(sum.value)}${isNum(sum.share_pct) ? ` · 주식 중 ${sum.share_pct.toFixed(0)}%` : ""}${isNum(target) ? ` (목표 ${target.toFixed(0)}%)` : ""}${isNum(sum.unrealized_pct) ? ` · 미실현 ${sum.unrealized_pct > 0 ? "+" : ""}${sum.unrealized_pct.toFixed(1)}%` : ""}</span>` : `<span class="meta" style="margin:0">${rows.length}개 · 구분을 정하면 보유 판정이 계산됩니다</span>`;
  return `<div class="panel"><h2>${title} ${head}</h2><div class="tbl-wrap"><table><thead><tr><th>종목</th><th>비중</th><th>점수</th><th class="l">판정</th><th>손절가(거리)</th>
    ${swing ? '<th>목표가</th><th class="l">남은 기간</th>' : '<th class="l">다음 점검</th>'}<th>미실현 손익</th><th>오늘</th><th>수량</th><th>평균단가</th><th>현재가</th><th>평가액</th><th class="l">섹터</th></tr></thead><tbody>${rows.map(holdingRow).join("")}</tbody></table></div></div>`;
}
function holdingsHtml(d) {
  if (!d.holdings.length) return '<div class="panel"><h2>보유 종목</h2><div class="empty">보유 종목이 없습니다.</div></div>';
  const st = d.summary.styles, by = (s) => d.holdings.filter((h) => (h.style || null) === s);
  return holdingTable("장기", by("LONG"), "LONG", st.LONG, st.target_long_pct) + holdingTable("스윙", by("SWING"), "SWING", st.SWING, st.target_swing_pct)
    + holdingTable("구분 없음", by(null), null, null, null)
    + '<div class="panel" id="sigpanel"><h2>보유 판정</h2><div id="sigout" class="meta" style="margin:0">계산 중… (처음에는 공시를 읽느라 시간이 걸릴 수 있습니다)</div></div>';
}
async function loadSignals() {
  const out = $("#sigout"), mk = state.market; if (!out) return;
  const cell = (k, t) => document.querySelector(`[data-sig="${k}"][data-t="${CSS.escape(t)}"]`);
  try {
    const d = await api(mq("/api/portfolio/signals"));
    if (mk !== state.market) return;
    const notes = [];
    d.items.forEach((s) => {
      const t = s.ticker;
      if (s.status !== "REAL") { const c = cell("action", t); if (c) c.innerHTML = `<span class="missing">${s.status === "NO_STYLE" ? "구분 필요" : "계산 불가"}</span>`; return; }
      const a = s.exit.action, tone = { EXIT: "act-sell", THESIS_INVALIDATED: "act-sell", REDUCE: "act-reduce", PARTIAL_TAKE_PROFIT: "act-reduce", TIME_STOP_REVIEW: "act-reduce" }[a] || "act-hold";
      cell("score", t).textContent = s.score === null ? "-" : s.score.toFixed(0);
      cell("action", t).innerHTML = `<span class="qsf-act ${tone}"><i></i>${esc(QSF_EXIT[a] || a)}</span>`;
      const left = cell("left", t); if (left) left.textContent = `${s.sessions_left}거래일 (${s.time_limit})`;
      const rev = cell("review", t); if (rev) rev.textContent = s.earnings_date ? `실적 ${s.earnings_date}` : "분기 실적 공시 후";
      if (a !== "HOLD") notes.push(`<li class="${tone === "act-sell" ? "bad" : "warn"}"><b>${esc(t)} ${esc(QSF_EXIT[a] || a)}</b>: ${esc(s.exit.reason)}</li>`);
    });
    out.innerHTML = `${notes.length ? `<ul class="alerts">${notes.join("")}</ul>` : "조치가 필요한 종목이 없습니다."}<div class="meta">${esc(d.note)}</div>`;
  } catch (e) { out.innerHTML = `<span class="err">판정을 계산하지 못했습니다: ${esc(e.message)}</span>`; }
}
function styleStatsHtml(by) {
  const row = (s) => { const x = by[s]; return `<tr><td class="l">${STYLE_KO[s]}</td><td class="num">${x.count}</td><td class="num">${x.count ? fmt(x.win_rate_pct, 1) + "%" : DASH}</td><td class="num">${x.count ? fmt(x.payoff, 2) : DASH}</td><td>${x.count ? pnl(x.total) : DASH}</td></tr>`; };
  return `<div class="tbl-wrap"><table><thead><tr><th class="l">구분</th><th>매도 건수</th><th>승률</th><th>손익비</th><th>실현 손익</th></tr></thead><tbody>${row("LONG")}${row("SWING")}</tbody></table></div>`;
}
function statsHtml(st) {
  if (!st.count) return '<div class="empty">아직 매도 기록이 없습니다.</div>';
  return `<div class="kv"><div><span>매도 건수</span><b>${st.count}</b></div><div><span>승률</span><b>${fmt(st.win_rate_pct, 1)}%</b></div>
    <div><span>평균 이익</span><b>${pnl(st.avg_win)}</b></div><div><span>평균 손실</span><b>${pnl(st.avg_loss)}</b></div>
    <div><span>손익비</span><b>${fmt(st.payoff, 2)}</b></div><div><span>실현 손익 합계</span><b>${pnl(st.total)}</b></div></div>
    ${st.small_sample ? '<div class="meta">표본이 20건 미만이라 승률·손익비로 실력을 판단하기 어렵습니다.</div>' : ""}`;
}
function journalRow(r) {
  const amt = isNum(r.amount) ? money(r.amount) : isNum(r.qty) && isNum(r.price) ? money(r.qty * r.price) : DASH;
  const styleText = r.style ? `${STYLE_KO[r.style]} ` : "";
  const extra = r.kind === "STYLE" ? `${styleText}으로 변경` : r.kind === "PLAN" || (r.kind === "BUY" && (r.stop || r.target)) ? ` 손절 ${r.stop ? money(r.stop) : "—"} · 목표 ${r.target ? money(r.target) : "—"}` : "";
  const ref = r.kind === "VOID" ? ` (기록 ${esc(r.ref)} 취소)` : "";
  return `<tr class="${r.voided ? "voided" : ""}"><td>${esc(r.date || r.recorded_at.slice(0, 10))}</td><td class="l">${esc(KIND_KO[r.kind] || r.kind)}${r.voided ? " · 취소됨" : ""}</td>
    <td class="l">${esc(r.ticker || "")}</td><td class="num">${isNum(r.qty) ? qtyFmt(r.qty) : ""}</td><td class="num">${isNum(r.price) ? money(r.price) : ""}</td><td class="num">${amt}</td>
    <td class="l meta" style="margin:0;white-space:normal;min-width:120px">${esc((r.note || "") + (r.kind === "BUY" ? ` ${styleText}` : "") + extra + ref)}</td>
    <td>${r.kind !== "VOID" && !r.voided ? `<button class="x" data-void="${esc(r.id)}" title="이 기록 취소">취소</button>` : ""}</td></tr>`;
}
function formHtml() {
  const p = prefill || {};
  const styleSelect = `<select name="style"><option value="">선택</option>${Object.entries(STYLE_KO).map(([k, v]) => `<option value="${k}" ${p.style === k ? "selected" : ""}>${v}</option>`).join("")}</select>`;
  const kind = p.kind || "BUY";
  return `<form class="form" id="jform" autocomplete="off">
    <label>종류<select name="kind">${Object.keys(KIND_FIELDS).map((k) => `<option value="${k}" ${k === kind ? "selected" : ""}>${KIND_KO[k]}</option>`).join("")}</select></label>
    <label>날짜(${isKR() ? "한국" : "미국"} 기준)<input name="date" type="date" value="${esc(p.date || todayET())}" max="${todayET()}"></label>
    ${Object.keys(FIELD_KO).map((f) => f === "style" ? `<label data-f="style">${FIELD_KO[f]}${styleSelect}</label>` : `<label data-f="${f}">${FIELD_KO[f].replace("$", curSym())}<input name="${f}" ${f === "ticker" ? 'maxlength="15" style="text-transform:uppercase"' : 'inputmode="decimal"'} value="${esc(p[f] ?? "")}"></label>`).join("")}
    <label class="wide">메모 (매매 이유 등, 선택)<input name="note" maxlength="500" value="${esc(p.note || "")}"></label>
    <div class="wide"><button class="btn-primary" type="submit">기록 추가</button> <span class="meta">실제로 체결된 내용만 기록하세요. 이 화면은 주문을 내지 않습니다.</span>${isKR() ? `<div class="meta">${KR_SELL_HINT}</div>` : ""}<div class="msg" id="jmsg"></div></div>
  </form>`;
}
function bindForm(d) {
  const f = $("#jform"); if (!f) return;
  const held = new Set((d ? d.holdings : []).map((h) => h.ticker));
  const sync = () => { const need = KIND_FIELDS[f.kind.value]; f.querySelectorAll("[data-f]").forEach((l) => (l.hidden = !need.includes(l.dataset.f))); };
  f.kind.onchange = sync; sync();
  f.onsubmit = async (e) => {
    e.preventDefault();
    const body = { kind: f.kind.value, date: f.date.value, note: f.note.value, market: state.market };
    KIND_FIELDS[body.kind].forEach((k) => { const v = f[k].value.trim().replace(/,/g, ""); if (v) body[k] = k === "ticker" ? v.toUpperCase() : v; });
    if (body.ticker && marketOf(body.ticker) !== state.market) { $("#jmsg").className = "msg err"; $("#jmsg").textContent = wrongMarket(body.ticker); f.ticker.focus(); return; }
    if ((body.kind === "BUY" && !held.has(body.ticker) && !body.style) || (body.kind === "STYLE" && !body.style)) {
      $("#jmsg").className = "msg err"; $("#jmsg").textContent = "장기 또는 스윙을 선택하세요."; f.style.focus(); return;
    }
    try { await post("/api/journal/add", body); prefill = null; $("#jmsg").className = "msg ok"; $("#jmsg").textContent = "기록했습니다. 시세를 다시 불러오는 중…"; renderPortfolio(); }
    catch (err) { $("#jmsg").className = "msg err"; $("#jmsg").textContent = ERR_KO[err.message] || err.message; }
  };
  if (prefill) { $("#jform-panel").scrollIntoView({ behavior: "smooth" }); }
}
let eqData = null;
async function loadEquity() {
  try {
    const mk = state.market, d = await api(mq("/api/portfolio/equity"));
    if (mk !== state.market) return;
    eqData = d;
    if (!d.points.length) { $("#eq-sum").innerHTML = "거래 기록이 생기면 계좌 가치 곡선을 그립니다."; return; }
    $("#eq-sum").innerHTML = `시작 ${esc(d.start)} 이후 · 내 계좌(TWR) ${pct(d.twr_pct)} · ${esc(d.benchmark)} ${pct(d.bench_pct)}`;
    $("#eq-meta").innerHTML = meta(d.source, d.fetched_at, esc(d.method));
    drawEquity(); redrawers.add(drawEquity);
  } catch (e) { $("#eq-sum").innerHTML = `<span class="err">${esc(e.message)}</span>`; }
}
function drawEquity() {
  const cv = $("#eqc"), d = eqData;
  if (!cv || !cv.isConnected || !d || d.points.length < 2) return;
  const { ctx, w, h } = setupCanvas(cv, 220);
  const pts = d.points, vals = pts.flatMap((p) => [p.twr_pct, p.bench_pct]).filter(isNum);
  if (!vals.length) return;
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals); const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
  const padR = 48, x = (i) => (i / (pts.length - 1)) * (w - padR), y = (v) => 6 + (1 - (v - lo) / (hi - lo)) * (h - 26);
  ctx.font = "11px -apple-system, sans-serif"; ctx.fillStyle = cssVar("--muted"); ctx.textBaseline = "middle";
  for (let k = 0; k <= 4; k++) { const v = lo + ((hi - lo) * k) / 4; ctx.strokeStyle = cssVar("--grid"); ctx.beginPath(); ctx.moveTo(0, y(v)); ctx.lineTo(w - padR, y(v)); ctx.stroke(); ctx.fillText(v.toFixed(1) + "%", w - padR + 6, y(v)); }
  ctx.strokeStyle = cssVar("--line"); ctx.beginPath(); ctx.moveTo(0, y(0)); ctx.lineTo(w - padR, y(0)); ctx.stroke();
  ctx.textBaseline = "bottom"; ctx.fillText(pts[0].date, 0, h); ctx.textAlign = "right"; ctx.fillText(pts[pts.length - 1].date, w - padR, h); ctx.textAlign = "left";
  line(ctx, pts.map((p) => p.bench_pct), x, y, cssVar("--muted"), 1.3);
  line(ctx, pts.map((p) => p.twr_pct), x, y, cssVar("--accent"), 2);
  ctx.fillStyle = cssVar("--accent"); ctx.fillText("● 내 계좌", 4, 18); ctx.fillStyle = cssVar("--muted"); ctx.fillText("● " + d.benchmark, 80, 18);
}

// ------------------------------------------------------------------ 매매 보조
async function renderAssist() {
  const el = $("#tab-assist");
  if (!el.innerHTML) el.innerHTML = loading;
  let st;
  try { st = await api("/api/settings"); } catch (e) { el.innerHTML = errBox(e); return; }
  state.loaded.assist = true;
  el.innerHTML = `
    <div class="panel"><h2>포지션 크기 계산기</h2>
      <form class="form" id="szform" autocomplete="off">
        <label>종목 코드<input name="t" maxlength="15" style="text-transform:uppercase" placeholder="${isKR() ? "예: 005930" : "예: AAPL"}"></label>
        <label>구분<select name="style"><option value="">보유 구분 또는 공통</option><option value="LONG">장기</option><option value="SWING">스윙</option></select></label>
        <label>진입가(${curSym()})<input name="entry" inputmode="decimal" placeholder="비우면 최근 종가"></label>
        <label>손절가(${curSym()})<input name="stop" inputmode="decimal" placeholder="비우면 구분별 ATR 제안"></label>
        <label>계좌 금액(${curSym()}, 선택)<input name="equity" inputmode="decimal" placeholder="비우면 거래 기록 기준"></label>
        <div><button class="btn-primary" type="submit">계산</button></div>
      </form><div id="szout"></div></div>
    <div class="panel"><h2>위험 관리 설정</h2>
      <form class="form" id="stform">
        <label>장기 1회 위험(%)<input name="risk_long_pct" inputmode="decimal" value="${st.risk_long_pct}"></label>
        <label>장기 종목당 최대 비중(%)<input name="max_position_long_pct" inputmode="decimal" value="${st.max_position_long_pct}"></label>
        <label>장기 손절 제안(ATR 배수)<input name="stop_atr_long" inputmode="decimal" value="${st.stop_atr_long}"></label>
        <label>스윙 1회 위험(%)<input name="risk_swing_pct" inputmode="decimal" value="${st.risk_swing_pct}"></label>
        <label>스윙 종목당 최대 비중(%)<input name="max_position_swing_pct" inputmode="decimal" value="${st.max_position_swing_pct}"></label>
        <label>스윙 손절 제안(ATR 배수)<input name="stop_atr_swing" inputmode="decimal" value="${st.stop_atr_swing}"></label>
        <label>장기 목표 비중(%)<input name="target_long_pct" inputmode="decimal" value="${st.target_long_pct}"></label>
        <label>목표 이탈 경고(%p)<input name="style_drift_pct" inputmode="decimal" value="${st.style_drift_pct}"></label>
        <label>한국 장기 1회 위험(%)<input name="risk_long_kr_pct" inputmode="decimal" value="${st.risk_long_kr_pct}"></label>
        <label>한국 장기 최대 비중(%)<input name="max_position_long_kr_pct" inputmode="decimal" value="${st.max_position_long_kr_pct}"></label>
        <label>한국 스윙 1회 위험(%)<input name="risk_swing_kr_pct" inputmode="decimal" value="${st.risk_swing_kr_pct}"></label>
        <label>한국 스윙 최대 비중(%)<input name="max_position_swing_kr_pct" inputmode="decimal" value="${st.max_position_swing_kr_pct}"></label>
        <label>한국 장기 목표 비중(%)<input name="target_long_kr_pct" inputmode="decimal" value="${st.target_long_kr_pct}"></label>
        <label>구분 없는 종목 위험(%)<input name="risk_per_trade_pct" inputmode="decimal" value="${st.risk_per_trade_pct}"></label>
        <label>구분 없는 종목 최대 비중(%)<input name="max_position_pct" inputmode="decimal" value="${st.max_position_pct}"></label>
        <label>섹터당 최대 비중(%)<input name="max_sector_pct" inputmode="decimal" value="${st.max_sector_pct}"></label>
        <label>손절 근접 경고(%)<input name="near_stop_pct" inputmode="decimal" value="${st.near_stop_pct}"></label>
        <div><button type="submit">저장</button></div></form>
      <div class="meta">1회 거래 위험: 손절가에 도달했을 때 잃는 금액을 계좌의 몇 %로 제한할지 정합니다. 이 값들은 계산기와 경고에 쓰입니다.</div><div class="msg" id="stmsg"></div></div>
    <div class="panel" id="plan">${loading}</div>`;
  $("#szform").onsubmit = (e) => { e.preventDefault(); runSizing(); };
  $("#stform").onsubmit = async (e) => {
    e.preventDefault(); const f = e.target, body = {};
    ["risk_long_pct", "max_position_long_pct", "stop_atr_long", "risk_swing_pct", "max_position_swing_pct", "stop_atr_swing", "target_long_pct", "risk_long_kr_pct", "max_position_long_kr_pct", "risk_swing_kr_pct", "max_position_swing_kr_pct", "target_long_kr_pct", "style_drift_pct", "risk_per_trade_pct", "max_position_pct", "max_sector_pct", "near_stop_pct"].forEach((k) => (body[k] = f[k].value));
    try { await post("/api/settings", body); $("#stmsg").className = "msg ok"; $("#stmsg").textContent = "저장했습니다."; }
    catch (err) { $("#stmsg").className = "msg err"; $("#stmsg").textContent = err.message; }
  };
  loadPlan();
}
let lastSizing = null;
async function runSizing() {
  const f = $("#szform"), out = $("#szout"), qs = new URLSearchParams();
  ["t", "style", "entry", "stop", "equity"].forEach((k) => { const v = f[k].value.trim().replace(/,/g, ""); if (v) qs.set(k, k === "t" ? v.toUpperCase() : v); });
  qs.set("market", state.market);
  if (qs.get("t") && marketOf(qs.get("t")) !== state.market) { out.innerHTML = `<div class="msg err">${esc(wrongMarket(qs.get("t")))}</div>`; return; }
  out.innerHTML = '<div class="meta">계산 중…</div>';
  try {
    const d = await api("/api/sizing?" + qs); lastSizing = d;
    const r = d.result;
    const ctx = d.ticker ? `<div class="meta">${esc(d.ticker)} 최근 종가 ${money(d.last_close)} (${esc(d.last_date || "")}) · ATR(14) ${money(d.atr14)} · ${d.stop_atr} ATR 손절 제안 ${money(d.suggested_stop)}${isNum(d.held_qty) ? ` · 현재 보유 ${qtyFmt(d.held_qty)}주` : ""}</div>` : "";
    if (!r) { out.innerHTML = ctx + `<div class="meta">${esc(d.reason)}</div>`; return; }
    out.innerHTML = `${ctx}<div class="result" style="margin-top:10px"><span class="big num">${r.shares.toLocaleString("ko-KR")}주</span>
        <span class="meta">${d.style ? STYLE_KO[d.style] + " · " : ""}${money(r.entry)} 진입 · 손절 ${money(r.stop)} (${d.stop_source}, −${r.stop_distance_pct.toFixed(1)}%)</span></div>
      <div class="kv"><div><span>매수 금액</span><b class="num">${money(r.notional)}</b></div><div><span>계좌 대비 비중</span><b>${r.weight_pct.toFixed(1)}%</b></div>
        <div><span>손절 시 손실</span><b class="num">${money(r.risk_amount)}</b> <span class="meta" style="margin:0">${r.risk_pct.toFixed(2)}%</span></div>
        <div><span>수량을 정한 한도</span><b>${esc(BIND_KO[r.binding])}</b></div></div>
      <div class="meta">한도별 최대 수량: 위험 ${r.limits.RISK}주 · 비중 ${r.limits.WEIGHT}주 · 현금 ${r.limits.CASH}주 (계좌 ${money(d.equity)}${d.equity_source === "입력값" ? " 입력값, 전액 현금으로 가정" : ""}, 현금 ${money(d.cash)}, 위험 예산 ${money(r.risk_budget)})</div>
      ${r.shares > 0 && d.ticker ? '<button id="tojournal" style="margin-top:8px">이 수량으로 매수 기록 작성</button> <span class="meta">체결된 뒤에 기록하세요.</span>' : ""}`;
    const b = $("#tojournal");
    if (b) b.onclick = () => { prefill = { kind: "BUY", ticker: d.ticker, style: d.style || "", qty: r.shares, price: r.entry.toFixed(isKR() ? 0 : 2), stop: r.stop.toFixed(isKR() ? 0 : 2) }; show("portfolio"); };
  } catch (e) { out.innerHTML = `<div class="msg err">${esc(ERR_KO[e.message] || e.message)}</div>`; }
}
async function loadPlan() {
  const el = $("#plan");
  if (isKR()) { el.remove(); return; }      // P6-11B is a US model
  try {
    const d = await api("/api/model/plan");
    if (d.status === "UNAVAILABLE") { el.innerHTML = `<h2>P6-11B 계획 대조</h2><div class="empty">${esc(d.reason)}</div>`; return; }
    el.innerHTML = `<h2>P6-11B 계획 대조 ${badge("FROZEN")} ${d.status === "STALE" ? badge("STALE") : ""}</h2>
      <div class="meta" style="margin-top:0">최근 전체 스캔 ${when(d.executed_at)}${isNum(d.age_days) ? ` (${d.age_days}일 전)` : ""} · 내 계좌 ${money(d.equity)} 기준으로 환산</div>
      <div class="tbl-wrap"><table><thead><tr><th>순위</th><th class="l">종목</th><th>기준가</th><th>목표 비중</th><th>목표 수량</th><th>1차 진입 수량</th><th>모델 손절가</th><th>보유</th><th>기간</th><th></th></tr></thead>
      <tbody>${d.items.map((r, i) => `<tr><td>${esc(r.rank)}</td><td class="l"><b data-ticker="${esc(r.ticker)}" title="${esc(r.name || "")} · 눌러서 종목 화면" style="cursor:pointer">${esc(r.ticker)}</b></td>
        <td class="num">${money(r.close)} <span class="meta" style="margin:0">${esc(r.last_bar || "")}</span></td><td class="num">${isNum(r.target_weight) ? (r.target_weight * 100).toFixed(0) + "%" : DASH}</td>
        <td class="num">${isNum(r.target_shares) ? r.target_shares + "주" : DASH}</td><td class="num">${isNum(r.entry1_shares) ? r.entry1_shares + "주" : DASH}</td>
        <td class="num">${money(r.hard_stop)}</td><td>${isNum(r.held_qty) ? qtyFmt(r.held_qty) + "주" : '<span class="missing">미보유</span>'}</td>
        <td>${isNum(r.horizon_days) ? r.horizon_days + "일" : DASH}</td><td><button class="x" data-calc="${i}">계산기</button></td></tr>`).join("")}</tbody></table></div>
      <div class="meta">${esc(d.disclaimer)} 1차 진입 후 2차 진입 조건은 '종가 > 20일 지수이동평균'입니다 (모델 설명 기준).</div>`;
    el.querySelectorAll("[data-calc]").forEach((b) => (b.onclick = () => {
      const r = d.items[+b.dataset.calc], f = $("#szform");
      f.t.value = r.ticker; f.entry.value = isNum(r.close) ? r.close.toFixed(2) : ""; f.stop.value = isNum(r.hard_stop) ? r.hard_stop.toFixed(2) : "";
      el.querySelector(".tbl-wrap").scrollLeft = 0;
      runSizing(); f.scrollIntoView({ behavior: "smooth" });
    }));
  } catch (e) { el.innerHTML = `<h2>P6-11B 계획 대조</h2><div class="msg err">${esc(e.message)}</div>`; }
}

RENDER.portfolio = renderPortfolio;
RENDER.assist = renderAssist;
