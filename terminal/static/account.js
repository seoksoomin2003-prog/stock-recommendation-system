// 통합 '내 계좌': 미국 주식(달러), 한국 주식(원), 코인(원)을 한 페이지에서 본다 (사용자 요청 2026-11-23).
// 세 계좌는 통화도 현금도 한도도 따로이고, 이 화면은 그날 환율로 바꿔 더해 보여 준다.  시장 스위치와 상관없이 열린다.
"use strict";
const ACCT_KO = { US: "미국 주식", KR: "한국 주식", COIN: "코인" };
const ACCT_CUR = { US: "USD", KR: "KRW", COIN: "KRW" };
const ACCT_HOLD_HINT = "이 프로그램에 적기 전부터 갖고 있던 종목입니다. 산 날짜, 산 가격, 수량을 넣으세요. 입금 기록이 없어도 되고 현금은 바뀌지 않습니다(산 금액만큼 넣은 돈으로 셉니다). 손절가와 목표가는 선택입니다.";
let acctUnit = "KRW";          // 합계를 보여 주는 통화 (원화 / 달러 전환)
try { if (localStorage.getItem("qse-acct-unit") === "USD") acctUnit = "USD"; } catch (e) { /* storage unavailable */ }
let acctForm = { kind: "HOLD", market: "US" };

// 음수는 통화 기호 앞에 빼기표를 둡니다 (−₩1,200)
const acctCur = (v, cur, d) => (!isNum(v) ? DASH : (v < 0 ? "−" : "") + (cur === "KRW" ? `₩${Math.round(Math.abs(v)).toLocaleString("ko-KR")}`
  : `$${Math.abs(v).toLocaleString("ko-KR", { minimumFractionDigits: d ?? 2, maximumFractionDigits: d ?? 2 })}`));
const acctPrice = (v, cur) => (!isNum(v) ? DASH : cur === "KRW" ? `₩${v.toLocaleString("ko-KR", { maximumFractionDigits: v < 100 ? 2 : 0 })}` : `$${v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
// 합계 통화로: 원화 금액을 받아 원화 그대로 또는 그날 환율로 달러로
const acctTotal = (krw, rate) => (!isNum(krw) ? DASH : acctUnit === "KRW" ? acctCur(krw, "KRW") : isNum(rate) && rate > 0 ? acctCur(krw / rate, "USD") : DASH);
const acctPnl = (krw, rate) => (!isNum(krw) ? DASH : `<span class="${krw > 0 ? "up" : krw < 0 ? "down" : "flat"} num">${krw > 0 ? "+" : ""}${acctTotal(krw, rate)}</span>`);
const acctToday = (mk) => new Intl.DateTimeFormat("en-CA", { timeZone: mk === "US" ? "America/New_York" : "Asia/Seoul" }).format(new Date());

function acctHoldingsHtml(d) {
  if (!d.holdings.length) return '<div class="empty">보유 종목이 없습니다. 아래 "거래 기록 추가"에서 "이미 가지고 있는 종목 추가"를 고르면 지금 갖고 있는 종목을 바로 넣을 수 있습니다.</div>';
  const rate = d.total.usdkrw;
  const rows = d.holdings.map((h) => `<tr><td class="l">${ACCT_KO[h.market]}</td>
    <td class="l"><b>${esc(h.ticker)}</b> <span class="meta m0">${esc(h.name || "")}</span>${h.status !== "REAL" ? " " + badge(h.status) : ""}</td>
    <td class="l">${esc(STYLE_KO[h.style] || "미지정")}</td><td class="num">${qtyFmt(h.qty)}</td><td class="num">${acctPrice(h.avg_cost, h.currency)}</td><td class="num">${acctPrice(h.close, h.currency)}</td>
    <td class="num">${acctCur(h.value, h.currency)}</td><td class="num">${acctTotal(h.value_krw, rate)}</td><td class="num">${isNum(h.weight_total_pct) ? h.weight_total_pct.toFixed(1) + "%" : DASH}</td>
    <td class="num">${pct(h.unrealized_pct)}</td><td class="num">${h.stop ? acctPrice(h.stop, h.currency) : DASH}</td><td class="num">${h.target ? acctPrice(h.target, h.currency) : DASH}</td></tr>`).join("");
  return `<div class="tbl-wrap"><table><thead><tr><th class="l">계좌</th><th class="l">종목</th><th class="l">구분</th><th>수량</th><th>평균 단가</th><th>지금 가격</th><th>평가액</th>
    <th>${acctUnit === "KRW" ? "원화로" : "달러로"}</th><th title="세 계좌를 합친 금액 가운데 이 종목의 몫">전체 비중</th><th>손익</th><th>손절가</th><th>목표가</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function acctFormHtml(d) {
  const f = acctForm, cur = ACCT_CUR[f.market] === "KRW" ? "₩" : "$";
  const kinds = ["HOLD", "BUY", "SELL", "DEPOSIT", "WITHDRAW", "DIVIDEND", "FEE", "PLAN", "STYLE"];
  const label = { ticker: f.market === "COIN" ? "코인 이름 (예: BTC)" : "종목 코드", style: "구분", qty: f.market === "COIN" ? "수량(개)" : "수량(주)", price: f.kind === "HOLD" ? `산 가격(${cur})` : `가격(${cur})`,
    fee: `수수료(${cur})`, amount: `금액(${cur})`, stop: `손절가(${cur}, 선택)`, target: `목표가(${cur}, 선택)` };
  const styleSelect = `<select name="style"><option value="">선택</option>${Object.entries(STYLE_KO).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>`;
  const coins = (d.coins || []).map((c) => `<option value="${esc(c.coin)}">${esc(c.name || "")}</option>`).join("");
  return `<form class="form" id="acctform" autocomplete="off">
    <label>종류<select name="kind">${kinds.map((k) => `<option value="${k}" ${k === f.kind ? "selected" : ""}>${KIND_KO[k]}</option>`).join("")}</select></label>
    <label>계좌<select name="market">${Object.keys(ACCT_KO).map((m) => `<option value="${m}" ${m === f.market ? "selected" : ""}>${ACCT_KO[m]} (${ACCT_CUR[m] === "KRW" ? "원" : "달러"})</option>`).join("")}</select></label>
    <label>${f.kind === "HOLD" ? "산 날짜" : "날짜"}<input name="date" type="date" value="${esc(f.date || acctToday(f.market))}" max="${acctToday(f.market)}"></label>
    ${Object.keys(label).map((k) => k === "style" ? `<label data-f="style">${label[k]}${styleSelect}</label>`
      : `<label data-f="${k}">${label[k]}<input name="${k}" ${k === "ticker" ? `maxlength="15" style="text-transform:uppercase" ${f.market === "COIN" ? 'list="acctcoins"' : ""}` : 'inputmode="decimal"'}></label>`).join("")}
    <datalist id="acctcoins">${coins}</datalist>
    <label class="wide">메모 (선택)<input name="note" maxlength="500"></label>
    <div class="wide"><button class="btn-primary" type="submit">기록 추가</button> <span class="meta" id="accthint"></span><div class="msg" id="acctmsg"></div></div>
  </form>`;
}

function acctBind(d) {
  const f = $("#acctform"); if (!f) return;
  const held = new Set(d.holdings.map((h) => `${h.market}:${h.ticker}`));
  const hint = () => {
    const k = f.kind.value, m = f.market.value;
    $("#accthint").textContent = k === "HOLD" ? ACCT_HOLD_HINT + (m === "COIN" ? " 코인의 지금 가격은 바이낸스 달러 가격에 환율을 곱한 값이라 국내 거래소 가격과 다를 수 있습니다." : "")
      : m === "COIN" ? "코인은 원화로 적습니다. 지금 가격은 바이낸스 달러 가격에 환율을 곱한 값이라 국내 거래소 가격과 다를 수 있습니다."
      : "실제로 체결된 내용만 적으세요. 이 화면은 주문을 내지 않습니다.";
  };
  const sync = () => { const need = KIND_FIELDS[f.kind.value]; f.querySelectorAll("[data-f]").forEach((l) => (l.hidden = !need.includes(l.dataset.f))); hint(); };
  // 종류나 계좌를 바꾸면 통화 표시와 칸 이름이 달라지므로 양식을 다시 그립니다 (이미 넣은 날짜는 남깁니다)
  const redraw = () => { acctForm = { kind: f.kind.value, market: f.market.value, date: f.date.value }; $("#acctform-panel").querySelector("form").outerHTML = acctFormHtml(d); acctBind(d); };
  f.kind.onchange = redraw; f.market.onchange = redraw; sync();
  f.ticker.onblur = () => {            // 주식 코드는 모양으로 시장이 정해집니다: 계좌 칸을 맞춰 줍니다
    const t = f.ticker.value.trim().toUpperCase();
    if (t && f.market.value !== "COIN" && marketOf(t) !== f.market.value) { f.market.value = marketOf(t); const keep = t; redraw(); $("#acctform").ticker.value = keep; }
    // What the form cannot refuse but the user should know before saving (assessment 2026-11-23)
    const m = $("#acctform").market.value, covered = new Set((d.coins || []).map((c) => c.coin)), msg = $("#acctmsg");
    const warn = !t ? "" : /[가-힣]/.test(t) ? "종목 이름이 아니라 코드로 적어야 합니다(예: 삼성전자는 005930, 애플은 AAPL)."
      : m === "COIN" && /^\d{6}$/.test(t) ? "6자리 숫자는 한국 주식 코드로 보입니다. 주식이라면 계좌를 '한국 주식'으로 바꾸세요. 그대로 두면 코인으로 기록됩니다."
      : m === "COIN" && covered.size && !covered.has(t) ? `'${t}'은(는) 가격을 받는 코인 ${covered.size}종에 없습니다. 기록은 되지만 지금 가격과 평가액이 '없음'으로 나오고 합계도 비게 됩니다.`
      : m !== "COIN" && covered.has(t) ? `'${t}'은(는) 코인 이름이기도 합니다. 코인이라면 계좌를 '코인'으로 바꾸세요. 그대로 두면 주식 코드로 기록됩니다.` : "";
    msg.className = "msg"; msg.textContent = warn;
  };
  f.onsubmit = async (e) => {
    e.preventDefault();
    const msg = $("#acctmsg"), body = { kind: f.kind.value, date: f.date.value, note: f.note.value, market: f.market.value };
    KIND_FIELDS[body.kind].forEach((k) => { const v = f[k].value.trim().replace(/,/g, ""); if (v) body[k] = k === "ticker" ? v.toUpperCase() : v; });
    if (body.ticker && body.market !== "COIN") body.market = marketOf(body.ticker);
    if (((body.kind === "BUY" || body.kind === "HOLD") && !held.has(`${body.market}:${body.ticker}`) && !body.style) || (body.kind === "STYLE" && !body.style)) {
      msg.className = "msg err"; msg.textContent = "구분(장기 또는 스윙)을 선택하세요."; f.style.focus(); return;
    }
    try { await post("/api/journal/add", body); acctForm = { kind: body.kind, market: body.market }; msg.className = "msg ok"; msg.textContent = "기록했습니다. 다시 불러오는 중…"; renderAccount(); }
    catch (err) { msg.className = "msg err"; msg.textContent = errKo(err); }
  };
}

function acctJournalRow(r) {
  const cur = ACCT_CUR[r.market] || "USD";
  const amt = isNum(r.amount) ? acctCur(r.amount, cur) : isNum(r.qty) && isNum(r.price) ? acctCur(r.qty * r.price, cur) : DASH;
  const style = r.style ? `${STYLE_KO[r.style]} ` : "";
  const extra = r.kind === "STYLE" ? `${style}으로 변경` : r.kind === "PLAN" || ((r.kind === "BUY" || r.kind === "HOLD") && (r.stop || r.target)) ? ` 손절 ${r.stop ? acctPrice(r.stop, cur) : "—"} · 목표 ${r.target ? acctPrice(r.target, cur) : "—"}` : "";
  return `<tr class="${r.voided ? "voided" : ""}"><td>${esc(r.date || r.recorded_at.slice(0, 10))}</td><td class="l">${ACCT_KO[r.market] || esc(r.market)}</td>
    <td class="l">${esc(KIND_KO[r.kind] || r.kind)}${r.voided ? " · 취소됨" : ""}</td><td class="l">${esc(r.ticker || "")}</td><td class="num">${isNum(r.qty) ? qtyFmt(r.qty) : ""}</td>
    <td class="num">${isNum(r.price) ? acctPrice(r.price, cur) : ""}</td><td class="num">${amt}</td>
    <td class="l meta" style="margin:0;white-space:normal;min-width:120px">${esc((r.note || "") + (r.kind === "BUY" || r.kind === "HOLD" ? ` ${style}` : "") + extra + (r.kind === "VOID" ? ` (기록 ${r.ref} 취소)` : ""))}</td>
    <td>${r.kind !== "VOID" && !r.voided ? `<button class="x" data-void="${esc(r.id)}" title="이 기록 취소">취소</button>` : ""}</td></tr>`;
}

async function renderAccount() {
  const el = $("#tab-account");
  if (!el.innerHTML) el.innerHTML = loading;
  let d;
  try { d = await api("/api/account"); } catch (e) { el.innerHTML = errBox(e); return; }
  state.loaded.account = true;
  const t = d.total, rate = t.usdkrw;
  const parts = d.accounts.map((a) => `<tr><td class="l"><b>${a.label}</b> <span class="meta m0">${a.currency === "KRW" ? "원" : "달러"}${a.records ? "" : " · 기록 없음"}</span></td>
    <td class="num">${acctCur(a.equity, a.currency)}${a.complete ? "" : " " + badge("STALE")}</td><td class="num">${acctTotal(a.equity_krw, rate)}</td>
    <td class="num">${isNum(a.equity_krw) && t.krw ? ((a.equity_krw / t.krw) * 100).toFixed(1) + "%" : DASH}</td><td class="num">${acctCur(a.cash, a.currency)}</td>
    <td class="num">${acctCur(a.market_value, a.currency)}</td><td class="num">${acctPnl(a.total_pnl_krw, rate)}</td>
    <td>${a.market === "COIN" ? "" : `<button type="button" class="ghost acct-detail" data-m="${a.market}">자세히</button>`}</td></tr>`).join("");
  el.innerHTML = `
    ${d.integrity.status !== "OK" ? `<div class="notice">거래 기록 무결성 오류: ${esc(d.integrity.reason || "")}. 새 기록 추가가 중단됩니다.</div>` : ""}
    <div class="panel"><h2>내 계좌 <span class="meta m0">미국 주식 · 한국 주식 · 코인</span>
        <span class="seg" id="acctunit" role="group" aria-label="합계 통화"><button type="button" data-u="KRW" class="${acctUnit === "KRW" ? "on" : ""}">원화</button><button type="button" data-u="USD" class="${acctUnit === "USD" ? "on" : ""}">달러</button></span></h2>
      ${t.missing.length ? `<div class="notice">가격을 받지 못한 종목이 있어 합계를 확정할 수 없습니다: ${esc(t.missing.join(" / "))}</div>` : ""}
      ${!isNum(rate) ? '<div class="notice">환율을 받지 못해 달러 계좌를 원화로 바꾸지 못했습니다. 합계가 비어 있을 수 있습니다.</div>' : ""}
      <div class="head"><span class="big num">${acctTotal(t.krw, rate)}</span> <span class="meta m0">${acctUnit === "KRW" ? (isNum(t.usd) ? `≈ ${acctCur(t.usd, "USD")}` : "") : (isNum(t.krw) ? `≈ ${acctCur(t.krw, "KRW")}` : "")}</span></div>
      <div class="kv">
        <div><span>총 손익 (평가액 − 넣은 돈)</span><b>${acctPnl(t.total_pnl_krw, rate)}</b></div>
        <div><span>오늘 손익</span><b>${acctPnl(t.day_pnl_krw, rate)}</b></div>
        <div><span>현금</span><b class="num">${acctTotal(t.cash_krw, rate)}</b></div>
        <div><span>주식·코인 평가액</span><b class="num">${acctTotal(t.market_value_krw, rate)}</b></div>
        <div><span>넣은 돈 (입금 − 출금)</span><b class="num">${acctTotal(t.net_deposits_krw, rate)}</b></div>
        <div><span>환율</span><b class="num">${isNum(rate) ? `1달러 = ${fmt(rate)}원` : DASH}</b> <span class="meta m0">${esc(t.fx_date || "")}</span></div>
      </div>
      <div class="tbl-wrap"><table><thead><tr><th class="l">계좌</th><th>평가액</th><th>${acctUnit === "KRW" ? "원화로" : "달러로"}</th><th>비중</th><th>현금</th><th>주식·코인</th><th>총 손익</th><th></th></tr></thead><tbody>${parts}</tbody></table></div>
      <div class="meta">'자세히'는 그 시장의 위험 분석, 수익률 곡선, 보유 점검, 한도 설정으로 갑니다.</div></div>
    <div class="panel"><h2>보유 종목 <span class="meta m0">${d.holdings.length}개 · 세 계좌 합쳐 금액순</span></h2>${acctHoldingsHtml(d)}</div>
    <div class="panel" id="acctform-panel"><h2>거래 기록 추가</h2>${acctFormHtml(d)}</div>
    <div class="panel"><h2>거래 기록 <span class="meta m0">${d.journal_count}건${d.journal_count > d.journal.length ? ` 중 최근 ${d.journal.length}건` : ""} · 추가만 가능, 취소는 별도 기록으로 남습니다</span></h2>
      ${d.journal.length ? `<div class="tbl-wrap"><table><thead><tr><th>날짜</th><th class="l">계좌</th><th class="l">종류</th><th class="l">종목</th><th>수량</th><th>가격</th><th>금액</th><th class="l">메모</th><th></th></tr></thead>
        <tbody>${d.journal.map(acctJournalRow).join("")}</tbody></table></div>` : '<div class="empty">기록이 없습니다.</div>'}</div>
    <div class="panel">${d.notes.map((x) => `<div class="meta">${esc(x)}</div>`).join("")}${d.coin_error ? `<div class="meta">코인 가격을 새로 받지 못했습니다(${esc(d.coin_error)}). 저장해 둔 가격이 있으면 그것으로 보여 줍니다.</div>` : ""}</div>`;
  $("#acctunit").querySelectorAll("button").forEach((b) => { b.onclick = () => { acctUnit = b.dataset.u; try { localStorage.setItem("qse-acct-unit", acctUnit); } catch (e) { /* not remembered */ } renderAccount(); }; });
  el.querySelectorAll(".acct-detail").forEach((b) => { b.onclick = () => { setMarket(b.dataset.m, false); show("portfolio"); }; });
  el.querySelectorAll("[data-void]").forEach((b) => { b.onclick = async () => {
    if (!confirm("이 기록을 취소합니다. 지우지 않고 '취소' 기록을 덧붙입니다.")) return;
    try { await post("/api/journal/void", { ref: b.dataset.void }); renderAccount(); } catch (err) { alert(errKo(err)); }
  }; });
  acctBind(d);
}
RENDER.account = renderAccount;
$("#acctbtn").onclick = () => show("account");
