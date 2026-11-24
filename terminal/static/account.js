// 통합 '내 계좌': 미국 주식(달러), 한국 주식(원), 코인(원)을 한 페이지에서 본다 (사용자 요청 2026-11-23).
// 세 계좌는 통화도 현금도 한도도 따로이고, 이 화면은 그날 환율로 바꿔 더해 보여 준다.  시장 스위치와 상관없이 열린다.
"use strict";
const ACCT_KO = { US: "미국 주식", KR: "한국 주식", COIN: "코인" };
const ACCT_CUR = { US: "USD", KR: "KRW", COIN: "KRW" };
const ACCT_HOLD_HINT = "이 프로그램에 적기 전부터 갖고 있던 종목입니다. 산 날짜, 산 가격, 수량을 넣으세요. 입금 기록이 없어도 되고 현금은 바뀌지 않습니다(산 금액만큼 넣은 돈으로 셉니다). 손절가와 목표가는 선택입니다.";
let acctUnit = "KRW";          // 합계를 보여 주는 통화 (원화 / 달러 전환)
try { if (localStorage.getItem("qse-acct-unit") === "USD") acctUnit = "USD"; } catch (e) { /* storage unavailable */ }
let acctForm = { kind: "HOLD", market: "US" };
// 작업 화면 개편 7단계 (사용자 결정 U-7, O-9): 보낸 기록의 응답이 올 때까지 '기록 추가'를 다시 받지 않습니다(두 번 눌러 두 줄이 붙던 문제).
// 양식이 다시 그려져도(종류·계좌를 바꾸면 새 양식) 막히도록 양식 밖에 둡니다.  acctLast: 방금 붙인 기록(응답의 id)과 그 한 줄 설명.
// 다음 그리기에서 한 번만 보여 줍니다.  acctPick: 두 칸 화면에서 고른 보유 종목 (계좌:종목).
let acctBusy = false, acctLast = null, acctPick = null;

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
  const rows = d.holdings.map((h) => `<tr data-hold="${esc(acctKey(h))}"><td class="l">${ACCT_KO[h.market]}</td>
    <td class="l">${tickerLabel(h.ticker, h.name)}${h.status !== "REAL" ? " " + badge(h.status) : ""}</td>
    <td class="l">${esc(STYLE_KO[h.style] || "미지정")}</td><td class="num">${qtyFmt(h.qty)}</td><td class="num">${acctPrice(h.avg_cost, h.currency)}</td><td class="num">${acctPrice(h.close, h.currency)}</td>
    <td class="num">${acctCur(h.value, h.currency)}</td><td class="num">${acctTotal(h.value_krw, rate)}</td><td class="num">${isNum(h.weight_total_pct) ? h.weight_total_pct.toFixed(1) + "%" : DASH}</td>
    <td class="num">${pct(h.unrealized_pct)}</td><td class="num">${h.stop ? acctPrice(h.stop, h.currency) : DASH}</td><td class="num">${h.target ? acctPrice(h.target, h.currency) : DASH}</td></tr>`).join("");
  return `<div class="tbl-wrap"><table id="acctholds"><thead><tr><th class="l">계좌</th><th class="l">종목</th><th class="l">구분</th><th>수량</th><th>평균 단가</th><th>지금 가격</th><th>평가액</th>
    <th>${acctUnit === "KRW" ? "원화로" : "달러로"}</th><th title="세 계좌를 합친 금액 가운데 이 종목의 몫">전체 비중</th><th>손익</th><th>손절가</th><th>목표가</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

// 거래 기록 양식은 이 화면 하나입니다 (6차 묶음 P2-16).  시장별 화면과 크기 계산기는 시장과 값을 채워 이리로 보냅니다.
function acctRecord(market, fill) {
  acctForm = { kind: (fill && fill.kind) || "BUY", market: ACCT_KO[market] ? market : "US", fill: fill || null, scroll: true };
  show("account");
}
function acctFormHtml(d) {
  const f = acctForm, cur = ACCT_CUR[f.market] === "KRW" ? "₩" : "$", fill = f.fill || {};
  const kinds = ["HOLD", "BUY", "SELL", "DEPOSIT", "WITHDRAW", "DIVIDEND", "FEE", "PLAN", "STYLE"];
  const label = { ticker: f.market === "COIN" ? "코인 이름 (예: BTC)" : "종목 코드", style: "구분", qty: f.market === "COIN" ? "수량(개)" : "수량(주)", price: f.kind === "HOLD" ? `산 가격(${f.market === "COIN" ? "1개당" : "1주당"}, ${cur})` : `가격(${f.market === "COIN" ? "1개당" : "1주당"}, ${cur})`,
    fee: `수수료(${cur})`, amount: `금액(${cur})`, stop: `손절가(${cur}, 선택)`, target: `목표가(${cur}, 선택)` };
  const styleSelect = `<select name="style"><option value="">선택</option>${Object.entries(STYLE_KO).map(([k, v]) => `<option value="${k}"${fill.style === k ? " selected" : ""}>${v}</option>`).join("")}</select>`;
  const coins = (d.coins || []).map((c) => `<option value="${esc(c.coin)}">${esc(c.name || "")}</option>`).join("");
  return `<form class="form" id="acctform" autocomplete="off">
    <label>종류<select name="kind">${kinds.map((k) => `<option value="${k}" ${k === f.kind ? "selected" : ""}>${KIND_KO[k]}</option>`).join("")}</select></label>
    <label>계좌<select name="market">${Object.keys(ACCT_KO).map((m) => `<option value="${m}" ${m === f.market ? "selected" : ""}>${ACCT_KO[m]} (${ACCT_CUR[m] === "KRW" ? "원" : "달러"})</option>`).join("")}</select></label>
    <label>${f.kind === "HOLD" ? "산 날짜" : "날짜"}${f.market === "US" ? "(미국 기준)" : ""}<input name="date" type="date" value="${esc(f.date || acctToday(f.market))}" max="${acctToday(f.market)}"></label>
    ${Object.keys(label).map((k) => k === "style" ? `<label data-f="style">${label[k]}${styleSelect}</label>`
      : `<label data-f="${k}">${label[k]}<input name="${k}"${fill[k] !== undefined && fill[k] !== null ? ` value="${esc(fill[k])}"` : ""} ${k === "ticker" ? `maxlength="15" style="text-transform:uppercase" ${f.market === "COIN" ? 'list="acctcoins"' : ""}` : 'inputmode="decimal"'}></label>`).join("")}
    <datalist id="acctcoins">${coins}</datalist>
    <label class="wide">메모 (선택)<input name="note" maxlength="500"></label>
    <div class="wide meta m0" id="acctpricenote" aria-live="polite"></div>
    <div class="wide m0" id="accttotal" aria-live="polite"></div>
    <div class="wide"><button class="btn-primary" type="submit">기록 추가</button> <span class="meta" id="accthint"></span><div class="msg" id="acctmsg" role="status" aria-live="polite"></div></div>
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
  if (acctForm.scroll) { acctForm.scroll = false; $("#acctform-panel").scrollIntoView({ block: "start" }); (f.ticker.value ? f.qty : f.ticker).focus({ preventScroll: true }); }
  f.kind.onchange = redraw; f.market.onchange = redraw; sync();
  // 수량 × 1주당 가격 = 거래 금액 (사용자 요청 2026-11-24).  가격 칸은 1주당 가격 그대로 기록하고, 합계는 보여 주기만 합니다.
  const total = () => {
    const box = $("#accttotal"), k = f.kind.value; if (!box) return;
    const num = (n) => { const t = (f[n] ? f[n].value : "").replace(/[,_\s]/g, ""); return t ? Number(t) : NaN; };
    const q = num("qty"), p = num("price"), fee = num("fee"), cur = ACCT_CUR[f.market.value], unit = f.market.value === "COIN" ? "개" : "주";
    if (!["BUY", "SELL", "HOLD"].includes(k) || !(q > 0 && p > 0)) { box.textContent = ""; return; }
    const value = q * p, withFee = isNum(fee) && fee > 0 ? (k === "SELL" ? value - fee : value + fee) : null;
    box.innerHTML = `${k === "HOLD" ? "산 금액" : "거래 금액"} <b>${acctCur(value, cur)}</b> <span class="meta">= ${qtyFmt(q)}${unit} × ${acctPrice(p, cur)}</span>`
      + (withFee !== null ? ` · 수수료 넣으면 <b>${acctCur(withFee, cur)}</b> <span class="meta">(${k === "SELL" ? "들어오는 돈" : "나가는 돈"})</span>` : "");
  };
  ["qty", "price", "fee"].forEach((n) => { if (f[n] && f[n].addEventListener) f[n].addEventListener("input", total); });
  const auto = priceAuto(f, { kinds: ["BUY", "SELL", "HOLD"], market: () => f.market.value, note: $("#acctpricenote"), changed: total });
  f._priceAuto = auto;
  f.ticker.onblur = () => {            // 주식 코드는 모양으로 시장이 정해집니다: 계좌 칸을 맞춰 줍니다
    const t = f.ticker.value.trim().toUpperCase();
    if (t && f.market.value !== "COIN" && marketOf(t) !== f.market.value) { f.market.value = marketOf(t); const keep = t; redraw(); $("#acctform").ticker.value = keep; $("#acctform")._priceAuto.run(); }
    // What the form cannot refuse but the user should know before saving (assessment 2026-11-23)
    const m = $("#acctform").market.value, covered = new Set((d.coins || []).map((c) => c.coin)), msg = $("#acctmsg");
    const warn = !t ? "" : /[가-힣]/.test(t) ? "종목 이름이 아니라 코드로 적어야 합니다(예: 삼성전자는 005930, 애플은 AAPL)."
      : m === "COIN" && /^\d{6}$/.test(t) ? "6자리 숫자는 한국 주식 코드로 보입니다. 주식이라면 계좌를 '한국 주식'으로 바꾸세요. 그대로 두면 코인으로 기록됩니다."
      : m === "COIN" && covered.size && !covered.has(t) ? `'${t}'은(는) 가격을 받는 코인 ${covered.size}종에 없습니다. 기록은 되지만 지금 가격과 평가액이 '없음'으로 나오고 합계도 비게 됩니다.`
      : m !== "COIN" && covered.has(t) ? `'${t}'은(는) 코인 이름이기도 합니다. 코인이라면 계좌를 '코인'으로 바꾸세요. 그대로 두면 주식 코드로 기록됩니다.` : "";
    if (warn || !msg.querySelector(".acct-undo")) { msg.className = "msg"; msg.textContent = warn; }      // 방금 기록 취소 줄은 경고가 있을 때만 덮습니다
  };
  f.onsubmit = async (e) => {
    e.preventDefault();
    if (acctBusy) return;                     // 앞의 기록을 보내는 중: 두 번째 누름은 받지 않습니다
    const msg = $("#acctmsg"), body = { kind: f.kind.value, date: f.date.value, note: f.note.value, market: f.market.value };
    KIND_FIELDS[body.kind].forEach((k) => { const v = f[k].value.trim().replace(/,/g, ""); if (v) body[k] = k === "ticker" ? v.toUpperCase() : v; });
    if (body.ticker && body.market !== "COIN") body.market = marketOf(body.ticker);
    if (((body.kind === "BUY" || body.kind === "HOLD") && !held.has(`${body.market}:${body.ticker}`) && !body.style) || (body.kind === "STYLE" && !body.style)) {
      msg.className = "msg err"; msg.textContent = "구분(장기 또는 스윙)을 선택하세요."; f.style.focus(); return;
    }
    const btn = f.querySelector('button[type="submit"]');
    acctBusy = true; btn.disabled = true; f.setAttribute("aria-busy", "true");
    try {
      const r = await post("/api/journal/add", body);
      acctForm = { kind: body.kind, market: body.market };
      // 보낸 칸으로 만든 한 줄 (자료 파일을 다시 읽지 않음).  취소 단추는 응답이 돌려준 그 기록의 id만 씁니다.
      acctLast = { id: r && r.entry && r.entry.id ? String(r.entry.id) : null, text: acctDoneText(body) };
      msg.className = "msg ok"; msg.textContent = `${acctLast.text} 다시 불러오는 중…`;
      renderAccount();                        // 새 양식이 이 양식을 바꿉니다.  그때까지 단추는 눌리지 않은 채로 둡니다
    } catch (err) { msg.className = "msg err"; msg.textContent = errKo(err); btn.disabled = false; f.removeAttribute("aria-busy"); }
    finally { acctBusy = false; }
  };
  auto.run(); total();
  acctDone();
}
// '기록했습니다: 매수 AAPL 10주 · 미국 주식.'  보낸 칸에서만 만듭니다.
function acctDoneText(b) {
  const what = [KIND_KO[b.kind] || b.kind, b.ticker || "", isNum(Number(b.qty)) && b.qty ? `${qtyFmt(Number(b.qty))}${b.market === "COIN" ? "개" : "주"}` : "",
    !b.ticker && b.amount ? acctCur(Number(b.amount), ACCT_CUR[b.market]) : ""].filter(Boolean).join(" ");
  return `기록했습니다: ${what} · ${ACCT_KO[b.market] || b.market}.`;
}
// 방금 붙인 기록의 한 줄과 '방금 기록 취소' (사용자 결정 U-7): 거래 기록 표의 '취소'와 같은 확인과 같은 취소 요청(acctVoid)으로 그 한 기록에
// '취소' 기록을 덧붙입니다.  지우지 않습니다.  응답에 id가 없으면 단추를 만들지 않습니다.
function acctDone() {
  const msg = $("#acctmsg"), last = acctLast;
  if (!msg || !last) return;
  acctLast = null;                            // 한 번만: 다른 화면에 다녀오면 '방금'이 아닙니다
  msg.className = "msg ok";
  msg.innerHTML = last.voided ? esc(last.text) : `${esc(last.text)}${last.id ? ` <button type="button" class="ghost acct-undo" data-undo="${esc(last.id)}">방금 기록 취소</button>` : ""}`;
  const b = msg.querySelector(".acct-undo");
  if (b) b.onclick = async () => { b.disabled = true; if (!(await acctVoid(b.dataset.undo, "방금 기록을 취소했습니다. 원래 기록은 남고 '취소' 기록이 덧붙었습니다."))) b.disabled = false; };
}
// 기록 하나를 취소합니다: 확인 뒤 '취소'(VOID) 기록을 덧붙이고 다시 그립니다.  표의 '취소'와 '방금 기록 취소'가 함께 씁니다.
async function acctVoid(ref, done) {
  if (!(await uiConfirm("이 기록을 취소합니다. 지우지 않고 '취소' 기록을 덧붙입니다.", { okLabel: "기록 취소", danger: true }))) return false;
  try { await post("/api/journal/void", { ref }); if (done) acctLast = { voided: true, text: done }; renderAccount(); return true; }
  catch (err) { notify(errKo(err)); return false; }
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

// 작업 화면 개편 7단계 (배치 명세 3.9, 사용자 결정 U-5): 맨 위 줄에 제목, 원화/달러 전환, 무결성·가격·환율 알림.  가운데 칸에 계좌별 표와
// 보유 종목 표, 오른쪽 칸에 합계(한 칸에서는 맨 앞, .ws-first)와 거래 기록 양식, 아래 줄에 거래 기록과 각주.  두 칸일 때 보유 종목 줄을
// 누르면(또는 Enter) 오른쪽 칸 맨 위(#acct-pick)에 그 종목의 표 값과 기록된 스캔의 점수 요약이 나옵니다.  한 칸에서는 전처럼 아무 일도 없습니다.
async function renderAccount() {
  const el = $("#tab-account");
  if (!el.innerHTML) el.innerHTML = loading;
  let d;
  try { d = await api("/api/account"); } catch (e) { el.innerHTML = errBox(e); return; }
  state.loaded.account = true;
  const t = d.total, rate = t.usdkrw;
  acctState.d = d;
  if (acctPick && !d.holdings.some((h) => acctKey(h) === acctPick)) acctPick = null;
  const parts = d.accounts.map((a) => `<tr><td class="l"><b>${esc(a.label)}</b> <span class="meta m0">${a.currency === "KRW" ? "원" : "달러"}${a.records ? "" : " · 기록 없음"}</span></td>
    <td class="num">${acctCur(a.equity, a.currency)}${a.complete ? "" : " " + badge("STALE")}</td><td class="num">${acctTotal(a.equity_krw, rate)}</td>
    <td class="num">${isNum(a.equity_krw) && t.krw ? ((a.equity_krw / t.krw) * 100).toFixed(1) + "%" : DASH}</td><td class="num">${acctCur(a.cash, a.currency)}</td>
    <td class="num">${acctCur(a.market_value, a.currency)}</td><td class="num">${acctPnl(a.total_pnl_krw, rate)}</td>
    <td>${a.market === "COIN" ? "" : `<button type="button" class="ghost acct-detail" data-m="${esc(a.market)}">자세히</button>`}</td></tr>`).join("");
  el.innerHTML = ui.ws({ name: "account", label: "계좌 합계와 거래 기록 양식",
    ctx: `<h2>통합 계좌 <span class="meta m0">미국 주식 · 한국 주식 · 코인</span></h2>
      <span class="ws-tools"><span class="seg" id="acctunit" role="group" aria-label="합계 통화"><button type="button" data-u="KRW" class="${acctUnit === "KRW" ? "on" : ""}">원화</button><button type="button" data-u="USD" class="${acctUnit === "USD" ? "on" : ""}">달러</button></span></span>
      ${d.integrity.status !== "OK" ? `<div class="notice">거래 기록 무결성 오류: ${esc(d.integrity.reason || "")}. 새 기록 추가가 중단됩니다.</div>` : ""}
      ${t.missing.length ? `<div class="notice">가격을 받지 못한 종목이 있어 합계를 확정할 수 없습니다: ${esc(t.missing.join(" / "))}</div>` : ""}
      ${!isNum(rate) ? '<div class="notice">환율을 받지 못해 달러 계좌를 원화로 바꾸지 못했습니다. 합계가 비어 있을 수 있습니다.</div>' : ""}`,
    main: `<div class="panel"><h2>계좌별 <span class="meta m0">세 계좌 · ${acctUnit === "KRW" ? "원화" : "달러"} 환산</span></h2>
      <div class="tbl-wrap"><table><thead><tr><th class="l">계좌</th><th>평가액</th><th>${acctUnit === "KRW" ? "원화로" : "달러로"}</th><th>비중</th><th>현금</th><th>주식·코인</th><th>총 손익</th><th></th></tr></thead><tbody>${parts}</tbody></table></div>
      <div class="meta">'자세히'는 그 시장의 위험 분석, 수익률 곡선, 보유 점검, 한도 설정으로 갑니다.</div></div>
    <div class="panel"><h2>보유 종목 <span class="meta m0">${d.holdings.length}개 · 세 계좌 합쳐 금액순</span></h2>${acctHoldingsHtml(d)}</div>`,
    right: `<div class="panel" id="acct-pick" hidden></div>
    <div class="panel ws-first acct-total"><h2>합계 <span class="meta m0">${acctUnit === "KRW" ? "원화" : "달러"}</span></h2>
      <div class="head"><span class="big num">${acctTotal(t.krw, rate)}</span> <span class="meta m0">${acctUnit === "KRW" ? (isNum(t.usd) ? `≈ ${acctCur(t.usd, "USD")}` : "") : (isNum(t.krw) ? `≈ ${acctCur(t.krw, "KRW")}` : "")}</span></div>
      <div class="kv">
        <div><span>총 손익 (평가액 − 넣은 돈)</span><b>${acctPnl(t.total_pnl_krw, rate)}</b></div>
        <div><span>오늘 손익</span><b>${acctPnl(t.day_pnl_krw, rate)}</b></div>
        <div><span>현금</span><b class="num">${acctTotal(t.cash_krw, rate)}</b></div>
        <div><span>주식·코인 평가액</span><b class="num">${acctTotal(t.market_value_krw, rate)}</b></div>
        <div><span>넣은 돈 (입금 − 출금)</span><b class="num">${acctTotal(t.net_deposits_krw, rate)}</b></div>
        <div><span>환율</span><b class="num">${isNum(rate) ? `1달러 = ${fmt(rate)}원` : DASH}</b> <span class="meta m0">${esc(t.fx_date || "")}</span></div>
      </div></div>
    <div class="panel" id="acctform-panel"><h2>거래 기록 추가</h2>${acctFormHtml(d)}</div>`,
    lower: `<div class="panel span-all"><h2>거래 기록 <span class="meta m0">${d.journal_count}건${d.journal_count > d.journal.length ? ` 중 최근 ${d.journal.length}건` : ""} · 추가만 가능, 취소는 별도 기록으로 남습니다</span></h2>
      ${d.journal.length ? `<div class="tbl-wrap"><table><thead><tr><th>날짜</th><th class="l">계좌</th><th class="l">종류</th><th class="l">종목</th><th>수량</th><th>가격</th><th>금액</th><th class="l">메모</th><th></th></tr></thead>
        <tbody>${d.journal.map(acctJournalRow).join("")}</tbody></table></div>` : '<div class="empty">기록이 없습니다.</div>'}</div>
    <div class="panel span-all">${d.notes.map((x) => `<div class="meta">${esc(x)}</div>`).join("")}${d.coin_error ? `<div class="meta">코인 가격을 새로 받지 못했습니다(${esc(d.coin_error)}). 저장해 둔 가격이 있으면 그것으로 보여 줍니다.</div>` : ""}</div>` });
  $("#acctunit").querySelectorAll("button").forEach((b) => { b.onclick = () => { acctUnit = b.dataset.u; try { localStorage.setItem("qse-acct-unit", acctUnit); } catch (e) { /* not remembered */ } renderAccount(); }; });
  el.querySelectorAll(".acct-detail").forEach((b) => { b.onclick = () => { setMarket(b.dataset.m, false); show("portfolio"); }; });
  el.querySelectorAll("[data-void]").forEach((b) => { b.onclick = () => acctVoid(b.dataset.void); });
  const tb = el.querySelector("#acctholds tbody");
  if (tb) {
    tb.addEventListener("click", (e) => {
      if (!wsCanSplit() || e.target.closest("button, a, [data-ticker]")) return;        // 한 칸: 전처럼 아무 일도 없음
      const tr = e.target.closest("tr[data-hold]");
      if (tr) { acctPick = tr.dataset.hold; acctSide(); wsRightTop("#acct-pick"); }
    });
    tb.addEventListener("keydown", (e) => {
      const tr = e.target.closest && e.target.closest("tr[data-hold]");
      if (!tr || e.target !== tr || (e.key !== "Enter" && e.key !== " ") || !wsCanSplit()) return;
      e.preventDefault(); acctPick = tr.dataset.hold; acctSide(); wsRightTop("#acct-pick");
    });
  }
  acctSide();
  acctBind(d);
}
const acctState = { d: null };
const acctKey = (h) => `${h.market}:${h.ticker}`;
// 고른 줄 표시: 두 칸일 때만 aria-selected와 Tab 순서(한 칸에서는 줄이 아무 일도 하지 않으므로 초점도 받지 않음).  내용 폭이 바뀔 때도 부릅니다.
function acctMark() {
  const split = wsCanSplit();
  document.querySelectorAll("#acctholds tbody tr[data-hold]").forEach((tr) => {
    if (split) tr.tabIndex = 0; else tr.removeAttribute("tabindex");
    tr.classList.toggle("acct-pickable", split);
    if (split && tr.dataset.hold === acctPick) tr.setAttribute("aria-selected", "true"); else tr.removeAttribute("aria-selected");
  });
  const box = $("#acct-pick");
  if (box) box.hidden = !(split && acctPick);
}
// 오른쪽 칸 맨 위: 표의 값(새로 계산한 것 없음)과, 주식이면 순위가 쓰는 기록된 스캔의 점수 요약(qsfScanSummary)과 이동 단추.  코인은 표의 값만.
function acctSide() {
  acctMark();
  const box = $("#acct-pick"), d = acctState.d, h = d && acctPick && d.holdings.find((x) => acctKey(x) === acctPick);
  if (!box || !h || box.hidden) return;
  const rate = d.total.usdkrw, stock = h.market !== "COIN";
  box.innerHTML = `<h2>${tickerLabel(h.ticker, h.name)} <span class="meta m0">${ACCT_KO[h.market]}</span>
      <span class="ph-actions"><button type="button" class="ghost" id="acct-pick-x" title="고른 줄을 풉니다">닫기</button></span></h2>
    <div class="w-facts">
      <div><span class="lbl">구분</span><b>${esc(STYLE_KO[h.style] || "미지정")}</b></div><div><span class="lbl">수량</span><b class="num">${qtyFmt(h.qty)}</b></div>
      <div><span class="lbl">평균 단가</span><b class="num">${acctPrice(h.avg_cost, h.currency)}</b></div><div><span class="lbl">지금 가격</span><b class="num">${acctPrice(h.close, h.currency)}</b>${h.status !== "REAL" ? " " + badge(h.status) : ""}</div>
      <div><span class="lbl">평가액</span><b class="num">${acctCur(h.value, h.currency)}</b></div><div><span class="lbl">${acctUnit === "KRW" ? "원화로" : "달러로"}</span><b class="num">${acctTotal(h.value_krw, rate)}</b></div>
      <div><span class="lbl">전체 비중</span><b class="num">${isNum(h.weight_total_pct) ? h.weight_total_pct.toFixed(1) + "%" : DASH}</b></div><div><span class="lbl">손익</span><b>${pct(h.unrealized_pct)}</b></div>
      <div><span class="lbl">손절가</span><b class="num">${h.stop ? acctPrice(h.stop, h.currency) : DASH}</b></div><div><span class="lbl">목표가</span><b class="num">${h.target ? acctPrice(h.target, h.currency) : DASH}</b></div>
    </div>
    ${stock ? `<div id="acct-pick-score" class="mt-2"></div>
    <div class="qsf-sum-acts"><button type="button" class="btn-primary" data-ticker="${esc(h.ticker)}" title="차트·재무·공시를 봅니다">종목 화면</button>
      <button type="button" class="ghost acct-detail" data-m="${esc(h.market)}" title="그 시장의 보유 판정, 위험 분석, 수익률 곡선">시장별 자세히</button></div>`
      : '<div class="meta">코인은 점수 기록이 없습니다. 지금 가격은 바이낸스 달러 가격에 환율을 곱한 값입니다.</div>'}`;
  $("#acct-pick-x").onclick = () => {
    const was = acctPick; acctPick = null; acctMark();
    const tr = document.querySelector(`#acctholds tr[data-hold="${CSS.escape(was)}"]`); if (tr) tr.focus();
  };
  box.querySelectorAll(".acct-detail").forEach((b) => { b.onclick = () => { setMarket(b.dataset.m, false); show("portfolio"); }; });
  const key = acctPick;
  if (stock && typeof qsfScanSummary === "function") qsfScanSummary($("#acct-pick-score"), h.ticker, h.market, { compact: true, still: () => acctPick === key && state.tab === "account" });
}
RENDER.account = renderAccount;
$("#acctbtn").onclick = () => show("account");
