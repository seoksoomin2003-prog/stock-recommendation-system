// 모의 매매: 직접 고른 종목을 직접 정한 가격에 사고판 것으로 적어 두는 가상의 계좌.
// 주문을 보내지 않고, 실제 포트폴리오 기록과 다른 파일에 저장합니다. 수수료·세금은 토스증권 공시값으로 자동 계산합니다.
const PT_KIND_KO = { BUY: "매수", SELL: "매도", DEPOSIT: "모의 자금 넣기", WITHDRAW: "모의 자금 빼기", VOID: "취소" };
const PT_FIELDS = { BUY: ["ticker", "qty", "price", "fee"], SELL: ["ticker", "qty", "price", "fee"], DEPOSIT: ["amount"], WITHDRAW: ["amount"] };
let ptPrefill = null;

function ptPct(v) { return isNum(v) ? `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${v.toFixed(2)}%</span>` : DASH; }
function ptSigned(v, d) { return isNum(v) ? `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${money(v, d).replace(/^-/, "−")}</span>` : DASH; }
function ptFeeText(parts) {
  if (!parts) return "";
  const bits = [`수수료 ${money(parts.commission)}`];
  if (parts.tax) bits.push(`거래세 ${money(parts.tax)}`);
  if (parts.exchange_fee) bits.push(`SEC 수수료 ${money(parts.exchange_fee)}`);
  return bits.join(" + ");
}

function ptFormHtml(d) {
  const first = !d.records, p = ptPrefill || (first ? { kind: "DEPOSIT", amount: d.start_hint } : { kind: "BUY" });
  const v = (k) => (p[k] === undefined || p[k] === null ? "" : esc(p[k]));
  return `<form class="form" id="ptform" autocomplete="off">
    <label>종류<select name="kind">${["BUY", "SELL", "DEPOSIT", "WITHDRAW"].map((k) => `<option value="${k}"${p.kind === k ? " selected" : ""}>${PT_KIND_KO[k]}</option>`).join("")}</select></label>
    <label data-f="ticker">종목 코드<input name="ticker" value="${v("ticker")}" placeholder="${isKR() ? "예: 005930" : "예: AAPL"}"></label>
    <label data-f="qty">수량(주)<input name="qty" inputmode="decimal" value="${v("qty")}"></label>
    <label data-f="price">가격(${curSym()})<input name="price" inputmode="decimal" value="${v("price")}"></label>
    <label data-f="amount">금액(${curSym()})<input name="amount" inputmode="decimal" value="${v("amount")}"></label>
    <label data-f="fee" title="비워 두면 토스증권 수수료와 매도 세금을 자동으로 계산합니다">수수료·세금(${curSym()}, 비우면 자동)<input name="fee" inputmode="decimal" placeholder="자동 계산"></label>
    <label>날짜<input name="date" type="date" value="${esc(p.date || d.today || "")}" max="${esc(d.today || "")}"></label>
    <label>메모(선택)<input name="note" maxlength="200" value="${v("note")}"></label>
    <button class="btn-primary">기록</button>
    <div class="wide meta" id="ptpreview" style="margin:0"></div><div class="wide meta" id="ptmsg" style="margin:0"></div></form>`;
}

function ptWireForm(d, mk) {
  const form = $("#ptform"); if (!form) return;
  const get = (n) => form.elements[n].value.trim(), preview = $("#ptpreview"), msg = $("#ptmsg");
  let token = 0, timer = null;
  const fields = () => {
    const kind = get("kind"), want = PT_FIELDS[kind];
    form.querySelectorAll("[data-f]").forEach((l) => { l.hidden = !want.includes(l.dataset.f); });
  };
  const num = (n) => { const t = get(n).replace(/[,_\s]/g, ""); return t ? Number(t) : NaN; };
  const show = async () => {
    const kind = get("kind"), mine = ++token;
    if (kind !== "BUY" && kind !== "SELL") { preview.innerHTML = kind === "DEPOSIT" ? "가상의 돈입니다. 이 금액 안에서 모의 매수를 기록할 수 있습니다." : ""; return; }
    const qty = num("qty"), price = num("price");
    if (!(qty > 0 && price > 0)) { preview.innerHTML = "수량과 가격을 넣으면 수수료와 실제로 오가는 금액을 보여 줍니다."; return; }
    const typed = get("fee") ? num("fee") : null;
    let parts = null, fee = typed;
    if (typed === null) {
      const tm = marketOf(get("ticker").toUpperCase() || (mk === "KR" ? "005930" : "AAPL"));
      try { parts = await api(`/api/paper-trade/fee?market=${tm}&side=${kind}&qty=${qty}&price=${price}`); } catch (e) { parts = null; }
      if (mine !== token) return;
      fee = parts ? parts.total : null;
    }
    const value = qty * price;
    const total = isNum(fee) ? (kind === "BUY" ? value + fee : value - fee) : null;
    preview.innerHTML = `거래 금액 ${money(value)} · ${typed === null ? (parts ? `${ptFeeText(parts)} (자동)` : "수수료를 계산하지 못했습니다") : `수수료·세금 ${money(typed)} (직접 입력)`}` +
      (isNum(total) ? ` · <b>${kind === "BUY" ? "나가는 돈" : "들어오는 돈"} ${money(total)}</b>` : "");
  };
  const later = () => { clearTimeout(timer); timer = setTimeout(show, 250); };
  form.elements.kind.onchange = () => { fields(); show(); };
  ["ticker", "qty", "price", "fee"].forEach((n) => (form.elements[n].oninput = later));
  form.onsubmit = async (e) => {
    e.preventDefault();
    const kind = get("kind"), body = { kind, date: get("date"), note: get("note"), market: mk };
    PT_FIELDS[kind].forEach((n) => { body[n] = n === "ticker" ? get(n).toUpperCase() : get(n).replace(/[,_\s]/g, ""); });
    try {
      await api("/api/paper-trade/add", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      ptPrefill = null;
      if (body.ticker) setMarket(marketOf(body.ticker), false);
      renderPaper();
    } catch (err) { msg.innerHTML = `<span class="down">${esc(errKo(err))}</span>`; }
  };
  fields(); show();
}

async function ptVoid(id) {
  if (!confirm("이 기록을 취소할까요? 기록은 지워지지 않고 '취소됨'으로 남습니다.")) return;
  try { await api("/api/paper-trade/void", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ref: id }) }); renderPaper(); }
  catch (e) { alert(errKo(e)); }
}

async function renderPaper() {
  const el = $("#tab-paper"), mk = state.market;
  if (!el.innerHTML) el.innerHTML = loading;
  let d;
  try { d = await api(mq("/api/paper-trade")); } catch (e) { if (mk === state.market) el.innerHTML = errBox(e); return; }
  if (mk !== state.market) return;
  state.loaded.paper = true;
  const title = `<h2>모의 매매 기록 <span class="badge">가상의 계좌</span> <span class="badge risk-note">주문을 보내지 않습니다</span></h2>`;
  const about = `<div class="meta">직접 고른 종목을 직접 정한 가격에 사고판 것으로 적어 두면, 수수료와 세금을 빼고 얼마가 남았는지 계산해 둡니다. ${esc(d.note)}</div>
    <div class="meta">수수료 기준: ${esc(d.fee_basis)}. 프로그램이 자동으로 사고파는 기록은 점수 탭의 '주문 계획·모의 장부'에 따로 있습니다.</div>`;
  if (d.status !== "REAL") {
    el.innerHTML = `<div class="panel">${title}<div class="notice">모의 매매 기록 파일에 문제가 있어 새 기록을 받을 수 없습니다: ${esc((d.integrity || {}).reason || "")}. data/terminal/paper_journal.jsonl 을 확인하세요.</div>${about}</div>`;
    return;
  }
  const s = d.stats, dec = mk === "KR" ? 0 : 2;
  const kv = (k, v, t) => `<div${t ? ` title="${esc(t)}"` : ""}><span>${k}</span><b class="num">${v}</b></div>`;
  const tiles = `<div class="kv">${kv("평가액", isNum(d.equity) ? money(d.equity, dec) : '<span class="missing">시세 없음</span>', "현금 + 보유 종목의 최근 종가 평가")}${kv("현금", money(d.cash, dec))}
    ${kv("넣은 모의 자금", money(d.net_deposits, dec), "넣은 금액 − 뺀 금액")}${kv("총 손익", `${ptSigned(d.total_pnl, dec)} ${isNum(d.return_pct) ? `<span class="meta m0">(${ptPct(d.return_pct)})</span>` : ""}`, "평가액 − 넣은 모의 자금. 보유 종목은 아직 팔지 않은 평가 손익입니다")}
    ${kv("끝난 거래 순손익", ptSigned(s.net, dec), "매도까지 끝난 거래의 손익에서 수수료·세금을 뺀 합계")}${kv("낸 수수료·세금", money(d.fees, dec), "매수·매도 기록에 적힌 수수료와 세금의 합")}
    ${kv("끝난 거래 / 이익 거래", `${s.count} / ${s.wins}`)}${kv("거래당 평균 순수익률", ptPct(s.mean_net_pct))}</div>`;
  const prow = d.positions.map((p) => `<tr><td class="l"><b>${esc(p.name || p.ticker)}</b> <span class="meta m0">${esc(p.ticker)}</span></td><td class="num">${fmt(p.qty, Number.isInteger(p.qty) ? 0 : 4)}</td>
    <td class="num" title="매수 수수료를 넣은 평균">${money(p.avg)}</td><td class="num">${isNum(p.close) ? money(p.close) : '<span class="missing">시세 없음</span>'}${p.date ? ` <span class="meta m0">${esc(p.date.slice(5))}</span>` : ""}</td>
    <td class="num">${isNum(p.value) ? money(p.value, dec) : DASH}</td><td class="num">${ptSigned(p.unrealized, dec)} <span class="meta m0">${ptPct(p.unrealized_pct)}</span></td>
    <td class="num" title="최근 종가에 모두 팔 때의 수수료·세금">${isNum(p.exit_fee) ? money(p.exit_fee) : DASH}</td><td class="l">${esc(p.opened)}</td>
    <td><button type="button" data-sell="${esc(p.ticker)}" data-qty="${p.qty}" data-px="${isNum(p.close) ? p.close : ""}">매도 기록</button></td></tr>`).join("");
  const crow = d.closed.map((c) => `<tr><td class="l">${esc(c.date)}</td><td class="l"><b>${esc(c.name || c.ticker)}</b> <span class="meta m0">${esc(c.ticker)}</span></td><td class="num">${fmt(c.qty, Number.isInteger(c.qty) ? 0 : 4)}</td>
    <td class="num">${money(c.buy_price)}</td><td class="num">${money(c.price)}</td><td class="num">${money(c.paid, dec)}</td><td class="num">${money(c.proceeds, dec)}</td>
    <td class="num" title="매수 때 ${money(c.fee_buy)} + 매도 때 ${money(c.fee_sell)}">${money(c.fees)}</td><td class="num">${ptSigned(c.net, dec)}</td><td class="num">${ptPct(c.net_pct)}</td><td class="num">${c.hold_days}일</td></tr>`).join("");
  const jrow = d.journal.map((r) => `<tr${r.voided ? ' style="opacity:.5"' : ""}><td class="l">${esc(r.date || "")}</td><td class="l">${esc(PT_KIND_KO[r.kind] || r.kind)}${r.voided ? ' <span class="badge">취소됨</span>' : ""}</td>
    <td class="l">${r.ticker ? `${esc(r.name || r.ticker)} <span class="meta m0">${esc(r.ticker)}</span>` : ""}</td><td class="num">${isNum(r.qty) ? fmt(r.qty, Number.isInteger(r.qty) ? 0 : 4) : ""}</td>
    <td class="num">${isNum(r.price) ? money(r.price) : isNum(r.amount) ? money(r.amount, dec) : ""}</td>
    <td class="num"${r.fee_parts ? ` title="${esc(ptFeeText(r.fee_parts).replace(/<[^>]+>/g, ""))}"` : ""}>${isNum(r.fee) ? `${money(r.fee)} <span class="meta m0">${r.fee_auto ? "자동" : "직접"}</span>` : ""}</td>
    <td class="l">${esc(r.note || "")}</td><td>${r.kind !== "VOID" && !r.voided ? `<button type="button" data-void="${esc(r.id)}">취소</button>` : ""}</td></tr>`).join("");
  el.innerHTML = `<div class="panel">${title}${about}${d.records ? tiles : ""}</div>
    <div class="panel"><h2>${d.records ? "기록 추가" : "시작하기: 모의 자금을 먼저 넣으세요"}</h2>${ptFormHtml(d)}</div>
    <div class="panel"><h2>보유 중 ${d.positions.length}종목</h2>${prow ? `<div class="tbl-wrap"><table><thead><tr><th class="l">종목</th><th>수량</th><th>평균 매수가</th><th>최근 종가</th><th>평가액</th><th>평가 손익</th><th>팔 때 수수료·세금</th><th class="l">첫 매수일</th><th></th></tr></thead><tbody>${prow}</tbody></table></div>
      <div class="meta">최근 종가는 지연 시세입니다. 평가 손익은 매수 수수료까지 넣은 금액 대비이고, 팔 때의 수수료·세금은 아직 빼지 않았습니다.</div>` : `<div class="empty">보유 중인 모의 종목이 없습니다.</div>`}</div>
    <div class="panel"><h2>끝난 거래 ${s.count}건</h2>${crow ? `<div class="tbl-wrap"><table><thead><tr><th class="l">매도일</th><th class="l">종목</th><th>수량</th><th title="매수 평균가(수수료 제외)">매수가</th><th>매도가</th><th>산 금액</th><th>판 금액</th><th title="매수 때와 매도 때의 수수료·세금 합">수수료·세금</th><th title="판 금액 − 산 금액 − 수수료·세금">순손익</th><th title="순손익 ÷ (산 금액 + 매수 수수료)">순수익률</th><th>보유</th></tr></thead><tbody>${crow}</tbody></table></div>
      <div class="meta">합계: 수수료 전 손익 ${ptSigned(s.gross, dec)}, 수수료·세금 ${money(s.fees, dec)}, 순손익 ${ptSigned(s.net, dec)}${isNum(s.win_rate_pct) ? `, 이익 거래 비율 ${s.win_rate_pct.toFixed(0)}%` : ""}. ${s.count < 20 ? "거래 수가 적어 이 수치로 실력이나 방법을 판단하기는 이릅니다." : ""}</div>` : `<div class="empty">아직 매도까지 끝난 거래가 없습니다.</div>`}</div>
    <div class="panel"><h2>기록 ${d.records}건</h2>${jrow ? `<div class="tbl-wrap"><table><thead><tr><th class="l">날짜</th><th class="l">종류</th><th class="l">종목</th><th>수량</th><th>가격 / 금액</th><th>수수료·세금</th><th class="l">메모</th><th></th></tr></thead><tbody>${jrow}</tbody></table></div>
      <div class="meta">잘못 적은 기록은 지우지 않고 '취소'로 무효화합니다. 기록은 이 Mac의 data/terminal/paper_journal.jsonl 에만 저장됩니다.</div>` : `<div class="empty">기록이 없습니다.</div>`}</div>`;
  ptWireForm(d, mk);
  el.querySelectorAll("[data-void]").forEach((b) => (b.onclick = () => ptVoid(b.dataset.void)));
  el.querySelectorAll("[data-sell]").forEach((b) => (b.onclick = () => {
    ptPrefill = { kind: "SELL", ticker: b.dataset.sell, qty: b.dataset.qty, price: b.dataset.px };
    renderPaper().then(() => { const f = $("#ptform"); if (f) f.scrollIntoView({ block: "center" }); });
  }));
}
RENDER.paper = renderPaper;
