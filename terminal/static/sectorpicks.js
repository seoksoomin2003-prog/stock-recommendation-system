// 업종 순환 그래프에서 업종을 고르면: 그 업종의 스윙·장기 점수 상위 3종목, 종목을 고르면 매수·매도 시기와 계획상 수익률.
// 점수는 최근 스캔 값 그대로이고, 수익률은 보유 계획의 목표·손절·시나리오 가격에서 계산한 기준선입니다(예측 아님).  읽기 전용.
"use strict";
const SP_BAND = { BUY_CANDIDATE: "g-A", HOLD_WATCH: "g-C", WEAK_REDUCE: "g-D", SELL_AVOID: "g-F" };
const spPct = (to, from) => (isNum(to) && isNum(from) && from > 0 ? (to / from - 1) * 100 : null);
const spPctTxt = (v) => (isNum(v) ? `<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : ""}${v.toFixed(1)}%</span>` : '<span class="missing">없음</span>');

async function loadSectorPicks(f) {
  const box = $("#rrg-picks");
  if (!box || !f) return;
  rrg.sel = f.symbol;
  $("#rrg-table").querySelectorAll("tr[data-fund]").forEach((tr) => tr.classList.toggle("me", tr.dataset.fund === f.symbol));
  box.hidden = false;
  box.innerHTML = `<h2>${esc(f.name)} 업종 점수 상위 종목</h2>${loading}`;
  box.scrollIntoView({ behavior: "smooth", block: "start" });
  const mk = state.market;
  let d;
  try { d = await api(mq(`/api/qsf/sector-picks?fund=${encodeURIComponent(f.symbol)}`)); } catch (e) { box.innerHTML = `<h2>${esc(f.name)} 업종 점수 상위 종목</h2>${errBox(e)}`; return; }
  if (rrg.sel !== f.symbol || mk !== state.market) return;
  if (d.status !== "REAL") { box.innerHTML = `<h2>${esc(f.name)} 업종 점수 상위 종목</h2><div class="empty">${badge("UNAVAILABLE")} ${esc(d.reason || "스캔 결과가 없습니다.")}</div>`; return; }
  const col = (k) => {
    const s = d.strategies[k];
    const list = s.top.length ? s.top.map((p) => `<button type="button" class="sp-pick" data-t="${esc(p.ticker)}">
        <span class="sp-rank">${p.rank}</span><span class="sp-name"><b>${esc(p.name || p.ticker)}</b> <span class="meta" style="margin:0">${esc(p.ticker)}${isKR() ? ` · ${esc(p.industry || "")}` : ""}</span></span>
        <span class="sp-score num">${fmt(p.score, 1)}</span><span class="grade ${SP_BAND[p.band] || ""}" style="width:auto;padding:0 6px">${esc(p.band_label || "")}</span>
        ${p.gates && p.gates.length ? `<span class="badge risk-note">${p.gates.map((g) => esc(QSF_GATE[g] || g)).join(", ")}</span>` : ""}${p.high_risk ? '<span class="badge risk-note">고위험 표시</span>' : ""}</button>`).join("")
      : '<div class="empty">점수가 있는 종목이 없습니다.</div>';
    return `<div><h3>${QSF_STRAT[k]} 점수 상위 3 <span class="meta" style="margin:0">${d.basis_kind === "HOLDINGS" ? `ETF 보유 ${d.fund_holdings}종목 중 스캔 대상 ${s.ranked}개` : `업종 ${s.ranked}개 중`} · 매수 후보 ${s.buy_candidates}개</span></h3>${list}</div>`;
  };
  box.innerHTML = `<h2>${esc(f.name)} 업종 점수 상위 종목 <span class="meta" style="margin:0">스캔 거래일 ${esc(d.session)} · ${esc(d.model_version || "")}</span></h2>
    <div class="sp-cols">${col("SWING")}${col("LONG_TERM")}</div>
    <div class="meta">포함 기준: ${esc(d.rule)} ${esc(d.basis)} '매수 후보'가 아닌 종목은 업종 안에서 점수가 높을 뿐 매수 구간이 아닙니다.</div>
    <div id="sp-plan"></div>`;
  box.querySelectorAll(".sp-pick").forEach((b) => (b.onclick = () => {
    box.querySelectorAll(".sp-pick").forEach((x) => x.classList.toggle("on", x.dataset.t === b.dataset.t));
    loadPickPlan(b.dataset.t);
  }));
}

async function loadPickPlan(t) {
  const box = $("#sp-plan"), mk = state.market;
  if (!box) return;
  box.innerHTML = '<div class="meta">점수와 보유 계획을 계산하는 중… (처음 보는 종목은 몇 초 걸립니다)</div>';
  let d;
  try { d = await qsfEval(t, mk); } catch (e) { box.innerHTML = errBox(e); return; }
  if (!box.isConnected || mk !== state.market) return;
  if (d.status && d.status !== "REAL" && !d.cards) { box.innerHTML = `<div class="empty">${esc(d.reason || d.error || "평가할 수 없습니다.")}</div>`; return; }
  const card = (c) => {
    const h = c.holding || {}, e = c.entry || {}, px = c.price;
    const buy = `<b>${esc(QSF_ENTRY[e.status] || e.status || "")}</b> · ${esc(e.reason || "")}
      <br>진입 예정일 ${esc(h.entry_date || "-")}${e.zone ? ` · 기준 구간 ${qsfPrice(e.zone.low, mk)}~${qsfPrice(e.zone.high, mk)}` : ""}`;
    let sell, ret;
    if (c.strategy === "SWING") {
      sell = `목표 ${qsfPrice(h.target, mk)} 도달 또는 손절 ${qsfPrice(h.stop, mk)} 이탈 시(종가 기준)
        <br>예상 보유 약 ${h.expected_sessions}거래일(${(h.range_sessions || []).join("~")}일) · 예상 청산일 ${esc(h.expected_exit || "-")} · 시간 재평가 ${esc(h.time_stop_review || "-")}`;
      ret = `<table class="sp-ret"><tr><td class="l">목표가까지</td><td class="num">${spPctTxt(spPct(h.target, px))}</td><td class="l meta" style="margin:0">${esc(h.target_method || "")}</td></tr>
        <tr><td class="l">손절가까지</td><td class="num">${spPctTxt(spPct(h.stop, px))}</td><td class="l meta" style="margin:0">${esc(h.stop_method || "")}</td></tr>
        <tr><td class="l">손익비</td><td class="num">${qsfNum(h.reward_risk, 2)}</td><td class="l meta" style="margin:0">${esc(h.cost_basis || "")}</td></tr></table>`;
    } else {
      sell = `예상 보유 ${(h.range_months || []).join("~")}개월(강제 종료일 없음) · 재평가 ${esc(h.first_review || "-")}, ${esc(h.next_review || "-")}
        <br>무효화되면 매도 검토: ${(h.invalidation || []).slice(0, 3).map(esc).join(" / ")}`;
      const sc = h.scenarios || {};
      ret = sc.status === "REAL"
        ? `<table class="sp-ret">${sc.cases.map((x) => `<tr><td class="l">${esc(x.case)} (1년 뒤)</td><td class="num">${spPctTxt(spPct(x.price, px))}</td><td class="l meta" style="margin:0">${qsfPrice(x.price, mk)} · ${esc(x.assumption)}</td></tr>`).join("")}</table>`
        : `<div class="meta">시나리오를 계산하지 못했습니다: ${esc(sc.reason || "")}</div>`;
    }
    return `<article class="qsf-card"><header><div><div class="meta" style="margin:0">${QSF_STRAT[c.strategy]}</div>
        <div class="qsf-score num">${c.score === null ? "-" : c.score.toFixed(1)}<small>/100</small></div></div>
        <div>${qsfLabel(c)}<div class="meta" style="margin:4px 0 0">구간 ${esc(c.band_label)} · 신뢰도 ${QSF_CONF[c.confidence] || ""} · 시세 ${esc(c.data_date)} ${qsfPrice(px, mk)}</div></div></header>
      ${c.gates && c.gates.length ? `<div class="notice">위험 게이트: ${c.gates.map((g) => esc(g.text)).join(" ")}</div>` : ""}
      <h3>매수 시기</h3><p>${buy}</p><h3>매도 시기</h3><p>${sell}</p>
      <h3>계획상 수익률 <span class="meta" style="margin:0">현재가 대비, 예측 아님</span></h3>${ret}</article>`;
  };
  box.innerHTML = `<h3>${esc(d.name || t)} <span class="meta" style="margin:0">${esc(t)}</span> <button class="ghost" type="button" id="sp-open">종목 화면에서 자세히</button></h3>
    <div class="qsf-cards">${["SWING", "LONG_TERM"].filter((k) => d.cards[k]).map((k) => card(d.cards[k])).join("")}</div>
    <div class="meta">점수는 지금 다시 계산한 값이라 순위표의 스캔 점수와 조금 다를 수 있습니다. 수익률은 보유 계획의 목표·손절·시나리오 가격을 현재가와 비교한 것으로,
      과거 검증에서 점수가 미래 수익을 설명한다는 근거는 아직 찾지 못했습니다. 매수 판단의 근거로 쓰지 말고, 주문은 직접 판단해 내세요.</div>`;
  $("#sp-open").onclick = () => openTicker(t);
}
