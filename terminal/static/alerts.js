// 알림 센터: 가격·하루 등락·QSF 점수 구간·실적 일정에 조건을 걸어 두면, 매일 자동 실행이 일봉 종가로 확인해 텔레그램·맥 알림으로 보냅니다.
// 실시간 알림이 아니며 주문은 실행하지 않습니다.
"use strict";
const AL_VALUE = { PRICE_ABOVE: ["가격", "decimal"], PRICE_BELOW: ["가격", "decimal"], MOVE: ["등락폭(%)", "decimal"], EARNINGS_SOON: ["며칠 전", "numeric"] };
const AL_ERR = { BAD_TYPE: "조건을 고르세요.", TICKER_REQUIRED: "가격 조건은 종목 코드가 필요합니다.", BAD_VALUE: "값이 올바르지 않습니다. (등락폭 0~50%, 실적 1~30일)",
  BAD_STRATEGY: "구분이 올바르지 않습니다.", TOO_MANY_RULES: "알림 조건은 최대 200개입니다.", INVALID_TICKER: "종목 코드 형식이 올바르지 않습니다." };
const AL_NOTE = { NO_PRICE: "최근 확정 종가 없음", NO_PREVIOUS_CLOSE: "전일 종가 없음", NO_EARNINGS_DATE: "실적 일정 모름", NOT_SCANNED: "QSF 스캔 대상 아님" };
const alTime = (iso) => stamp(iso) || esc(iso);
const alPost = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

async function renderAlerts(box) {
  if (!box) return;
  box.innerHTML = `${ui.head({ title: "알림 센터", actions: '<button class="ghost" id="al-check" type="button" style="float:right">지금 확인</button>' })}
    <form class="form" id="al-form" autocomplete="off">
      <label>조건<select name="type">${[["PRICE_ABOVE", "종가가 이 가격 이상"], ["PRICE_BELOW", "종가가 이 가격 이하"], ["MOVE", "하루 등락폭이 이 % 이상"], ["BAND_CHANGE", "QSF 점수 구간이 바뀜"], ["EARNINGS_SOON", "실적 발표가 다가옴"]]
        .map(([k, n]) => `<option value="${k}">${n}</option>`).join("")}</select></label>
      <label>종목 코드<input name="ticker" maxlength="15" class="upper" placeholder="비우면 ${isKR() ? "한국" : "미국"} 보유·관심 종목 전체"></label>
      <label id="al-vlabel"><span>가격</span><input name="value" inputmode="decimal"></label>
      <label id="al-slabel" hidden>구분<select name="strategy"><option value="SWING">스윙 점수</option><option value="LONG_TERM">장기 점수</option></select></label>
      <div><button class="btn-primary" type="submit">조건 추가</button></div>
    </form><div class="msg" id="al-msg"></div>
    <div id="al-rules">${loading}</div><div id="al-now"></div><div id="al-log"></div>`;
  const f = $("#al-form");
  prefillTicker(f.ticker);          // 열어 둔 종목을 미리 적어 둡니다.  전체 종목에 걸려면 칸을 비우면 됩니다.
  const sync = () => {
    const t = f.type.value, v = AL_VALUE[t];
    $("#al-vlabel").hidden = !v; $("#al-slabel").hidden = t !== "BAND_CHANGE";
    if (v) { $("#al-vlabel span").textContent = t.startsWith("PRICE") ? `가격(${isKR() ? "원" : "$"})` : v[0]; f.value.inputMode = v[1]; }
  };
  f.type.onchange = sync; sync();
  f.onsubmit = async (e) => {
    e.preventDefault();
    const t = f.type.value, body = { type: t, ticker: f.ticker.value.trim(), market: state.market };
    if (AL_VALUE[t]) { const n = Number(f.value.value.replace(/,/g, "")); body.value = t === "EARNINGS_SOON" ? Math.round(n) : n; }
    if (t === "BAND_CHANGE") body.strategy = f.strategy.value;
    try { await alPost("/api/alerts/add", body); $("#al-msg").className = "msg ok"; $("#al-msg").textContent = "추가했습니다."; f.value.value = ""; loadAlerts(); }
    catch (err) { $("#al-msg").className = "msg err"; $("#al-msg").textContent = AL_ERR[err.message] || errKo(err); }
  };
  $("#al-check").onclick = checkAlerts;
  loadAlerts();
}
async function loadAlerts() {
  const box = $("#al-rules");
  if (!box) return;
  let d;
  try { d = await api("/api/alerts"); } catch (e) { box.innerHTML = errBox(e); return; }
  if (!box.isConnected) return;
  box.innerHTML = ui.table({ cols: [{ label: "조건", cls: "l" }, { label: "상태", cls: "l" }, { label: "" }], empty: "걸어 둔 조건이 없습니다.", rows: d.rules.map((r) => `<tr>
        <td class="l">${esc(r.name)}</td>
        <td class="l">${r.status === "ACTIVE" ? ui.badge("대기") : ui.badge(`발동 ${r.triggered_at || ""}`, "risk-note")}</td>
        <td class="num">${r.status === "TRIGGERED" ? `<button class="ghost" data-rearm="${esc(r.id)}" type="button">다시 켜기</button> ` : ""}<button class="ghost" data-del="${esc(r.id)}" type="button">삭제</button></td></tr>`) });
  box.insertAdjacentHTML("beforeend", `<div class="meta">${esc(d.basis)} 가격 조건은 한 번 발동하면 멈추고, 구간·등락·실적 조건은 바뀔 때마다 알립니다. 점수 구간 변화는 검증된 매매 신호가 아닙니다.</div>`);
  box.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => { await alPost("/api/alerts/remove", { id: b.dataset.del }).catch(() => null); loadAlerts(); }));
  box.querySelectorAll("[data-rearm]").forEach((b) => (b.onclick = async () => { await alPost("/api/alerts/rearm", { id: b.dataset.rearm }).catch(() => null); loadAlerts(); }));
  $("#al-log").innerHTML = d.log.length
    ? `<h3>최근 보낸 알림</h3>${ui.table({ rows: d.log.slice(0, 20).map((a) => `<tr><td class="l">${alTime(a.at)}</td><td class="l">${a.market === "KR" ? "[한국] " : ""}${esc(a.text)}</td></tr>`) })}`
    : "";
}
async function checkAlerts() {
  const box = $("#al-now");
  if (!box) return;
  box.innerHTML = '<div class="meta">확인하는 중…</div>';
  let d;
  try { d = await api("/api/alerts/check"); } catch (e) { box.innerHTML = errBox(e); return; }
  if (!box.isConnected) return;
  const missed = {};
  d.notes.forEach((n) => (missed[n.reason] = (missed[n.reason] || new Set()).add(n.ticker)));
  box.innerHTML = `<h3>지금 확인한 결과 <span class="meta m0">${alTime(d.checked_at)} · 조건 ${d.rules}개</span></h3>
    ${d.alerts.length ? `<ul class="alerts">${d.alerts.map((a) => `<li class="${esc(a.level)}">${a.market === "KR" ? "[한국] " : ""}${esc(a.text)}</li>`).join("")}</ul>` : ui.empty("지금 발동할 조건이 없습니다.")}
    ${Object.keys(missed).length ? `<div class="meta">확인하지 못한 종목: ${Object.entries(missed).map(([k, s]) => `${AL_NOTE[k] || k} ${[...s].slice(0, 8).map(esc).join(", ")}${s.size > 8 ? ` 외 ${s.size - 8}개` : ""}`).join(" · ")}</div>` : ""}
    <div class="meta">미리보기일 뿐 보내지 않고 기록하지도 않습니다. 실제 알림은 다음 자동 실행 때 나갑니다.</div>`;
}
