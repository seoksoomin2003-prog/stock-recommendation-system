// 코인: 사용자의 다른 프로젝트(horizon_bot_beta) 예측기가 계산한 점수를 읽어 보여 줍니다.  터미널은 코인 점수를 만들지 않고, 코인 자료를 받지 않으며, 주문 기능이 없습니다.
"use strict";
const coinPct = (v, d = 2) => (isNum(v) ? `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${(v * 100 > 0 ? "+" : "") + (v * 100).toFixed(d)}%</span>` : DASH);
const coinPrice = (v) => (isNum(v) ? (v >= 1 ? v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : v.toFixed(6)) : DASH);
const coinWhen = (ms) => new Date(ms).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });

async function renderCoin() {
  const el = $("#tab-coin");
  state.loaded.coin = true;
  el.innerHTML = loading;
  let d;
  try { d = await api("/api/coin/latest"); } catch (e) { el.innerHTML = errBox(e); return; }
  if (state.tab !== "coin") return;
  const caveats = (d.caveats || []).map((x) => `<li>${esc(x)}</li>`).join("");
  const head = `<details class="notice qsf-caveat"><summary><b>대상 코인끼리의 순위입니다. 오를지 내릴지를 말하지 않습니다.</b> <span class="fold-hint">자세히</span></summary><ul class="qsf-list">${caveats}</ul></details>`;
  if (d.status === "UNAVAILABLE") {
    el.innerHTML = `<div class="panel"><h2>코인 상대 순위 ${badge("UNAVAILABLE")}</h2>${head}<div class="empty">${esc(d.reason || "자료를 읽지 못했습니다.")}</div><div class="meta">출처: ${esc(d.source || "")}</div></div>`;
    return;
  }
  const stale = d.status === "STALE" ? `<div class="msg err">점수가 ${Math.round(d.age_hours)}시간 전 마감 기준입니다. 4시간마다 새로 나와야 하는 값이라 오래된 것입니다. 예측기가 멈췄거나 맥이 잠들어 있었습니다.</div>` : "";
  const place = (p, n) => (isNum(p) ? `<div class="meta" style="margin:0">낮은 순 ${p}/${n}</div>` : "");
  const rows = d.rows.map((r) => `<tr class="click coin-row" data-coin="${esc(r.name || r.coin)}">
    <td>${r.rank}</td><td class="l"><b>${esc(r.coin)}</b> <span class="meta" style="margin:0">${esc(r.name || "")}${r.per_thousand ? " · 1,000개 단위" : ""}</span></td>
    <td class="num">${coinPct(r.alpha)}${r.beats_cost ? ' <span class="badge">비용 넘음</span>' : ""}</td>
    <td class="num">${coinPrice(r.price)}</td><td class="num">${coinPct(r.change_1d, 1)}</td><td class="num">${coinPct(r.change_7d, 1)}</td><td class="num">${coinPct(r.change_30d, 1)}</td>
    <td class="num">${isNum(r.funding) ? (r.funding * 100).toFixed(4) + "%" : DASH}${place(r.funding_place, r.of)}</td>
    <td class="num">${isNum(r.sigma_day) ? (r.sigma_day * 100).toFixed(1) + "%" : DASH}${place(r.sigma_place, r.of)}</td>
    <td class="num">${isNum(r.beta) ? r.beta.toFixed(2) : DASH}${place(r.beta_place, r.of)}</td></tr>`).join("");
  const m = d.market || {};
  const fact = (label, value) => `<div><span>${label}</span><b>${value}</b></div>`;
  el.innerHTML = `<div class="panel"><h2>코인 상대 순위 ${badge(d.status)} <span class="badge">${coinWhen(d.close_ms)} 마감 · 4시간봉</span></h2>${head}${stale}
      <div class="meta" style="margin-top:6px">기대 상대 폭은 앞으로 7일 동안 대상의 중간 코인보다 더 움직일 것으로 본 값입니다. 왕복 비용 ${(d.cost_round_trip * 100).toFixed(2)}%를 넘으면 표시가 붙습니다. 행을 누르면 비서가 그 코인을 설명합니다.</div>
      <div class="tbl-wrap"><table><thead><tr><th>순위</th><th class="l">코인</th><th title="7일 동안 대상의 중간 코인 대비">기대 상대 폭</th><th>가격(USDT)</th><th>1일</th><th>7일</th><th>30일</th>
        <th title="8시간마다 롱이 숏에게 내는 비율. 낮을수록 점수에 유리">자금조달비</th><th title="하루 변동성. 낮을수록 점수에 유리">변동성</th><th title="대상 평균 대비 민감도. 낮을수록 점수에 유리">베타</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="meta">출처: ${esc(d.source)} · 점수 v${esc(d.version)} · 신호 셋의 수치는 터미널이 예측기의 봉 자료에서 같은 정의로 다시 계산한 참고값입니다.</div></div>
    <div class="panel"><h2>코인 시장 <span class="badge">참고</span></h2>
      <div class="kv">${fact("비트코인", coinPrice(m.btc_price) + " USDT")}${fact("7일", coinPct(m.btc_change_7d, 1))}${fact("30일", coinPct(m.btc_change_30d, 1))}${fact("200일 평균 대비", coinPct(m.btc_vs_200d, 1))}
        ${fact("1년 고점 대비", coinPct(m.btc_from_high_1y, 1))}${fact("7일 동안 내린 코인", `${m.falling_7d} / ${m.coins}`)}${fact("200일 평균 위", `${m.above_200d} / ${m.above_200d_of}`)}
        ${fact("평균 자금조달비(8시간)", isNum(m.funding_mean) ? (m.funding_mean * 100).toFixed(4) + "%" : DASH)}</div>
      <div class="meta">${esc(m.note || "")}</div></div>`;
  el.onclick = (e) => { const row = e.target.closest(".coin-row"); if (row) askAssistant(`${row.dataset.coin} 분석해 줘`); };
}
RENDER.coin = renderCoin;
ALWAYS_FRESH.add("coin");
