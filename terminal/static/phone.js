// '폰 연결': 같은 와이파이의 휴대폰에서 이 화면을 여는 문을 켜고 끈다 (terminal/phone_view.py).  켜고 끄기는 이 컴퓨터에서만 된다.
"use strict";
const phonePost = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const phoneWhen = (iso) => stamp(iso);
let phoneTimer = null;

function phoneHtml(d) {
  const close = '<button type="button" class="ghost" id="phoneclose" aria-label="닫기">✕</button>';
  if (!d.on) return `<div class="phone-body"><div class="phone-head"><b>휴대폰 연결: 꺼짐</b> <button type="button" id="phoneon">켜기</button> ${close}</div>
    <div class="meta">켜면 같은 와이파이에 있는 휴대폰의 브라우저로 이 화면을 열 수 있습니다. 처음 한 번, 여기 뜨는 여섯 자리 코드를 휴대폰에 넣어야 합니다. ${esc(d.note || "")}</div></div>`;
  const left = d.code_until ? Math.max(0, Math.round((new Date(d.code_until) - Date.now()) / 60000)) : 0;
  const addr = (d.addresses || []).length ? d.addresses.map((a) => `<code class="phone-addr">${esc(a)}</code>`).join(" 또는 ")
    : "이 컴퓨터의 와이파이 주소를 찾지 못했습니다. 와이파이에 연결돼 있는지 확인하세요.";
  const code = d.code ? `<span class="phone-code">${esc(d.code)}</span> <span class="meta m0">약 ${left}분 남음 · 틀릴 수 있는 횟수 ${d.tries_left}번 · 한 번 쓰면 사라집니다</span>`
    : `<span class="meta m0">${d.code_state === "LOCKED" ? "틀린 횟수가 많아 코드를 닫았습니다." : d.code_state === "EXPIRED" ? "코드의 시간이 지났습니다." : "지금 살아 있는 코드가 없습니다."} 기기를 더 연결하려면 새 코드를 만드세요.</span>`;
  const dev = (d.devices || []).length ? `<ul class="phone-devs">${d.devices.map((x) => `<li>${esc(x.name || "기기")} · 연결 ${esc(phoneWhen(x.paired_at))} · 마지막 접속 ${esc(phoneWhen(x.last_seen))}
      <button type="button" class="ghost phone-unpair" data-id="${esc(x.id)}">끊기</button></li>`).join("")}</ul>` : '<div class="meta">아직 연결된 기기가 없습니다.</div>';
  const bad = d.listen_error ? `<div class="err">휴대폰 쪽 문을 열지 못했습니다(${esc(d.listen_error)}). 포트 ${d.port}을 다른 프로그램이 쓰고 있는지 확인한 뒤 껐다 켜세요.</div>` : "";
  return `<div class="phone-body"><div class="phone-head"><b>휴대폰 연결: 켜짐</b> <button type="button" id="phoneoff">끄기</button> ${close}</div>${bad}
    <div><b>1.</b> 휴대폰을 같은 와이파이에 연결하고 브라우저 주소창에 넣으세요: ${addr}</div>
    <div><b>2.</b> 연결 코드: ${code} <button type="button" class="ghost" id="phonecode">새 코드</button></div>
    <div><b>연결된 기기</b> (최대 ${d.max_devices}대, ${d.device_days}일 뒤 다시 연결)</div>${dev}
    <div class="meta">휴대폰에서는 모든 화면을 보고 거래 기록·모의 매매·관심종목·알림을 넣을 수 있습니다. 규칙 버튼, 수집 시작, 설정, 이 연결을 켜고 끄는 일은 이 컴퓨터에서만 됩니다.
      휴대폰에서 열리지 않으면 이 컴퓨터가 '들어오는 연결 허용'을 물었을 때 허용했는지, 두 기기가 같은 와이파이인지 확인하세요. ${esc(d.note || "")}</div></div>`;
}

async function phonePaint(d) {
  const bar = $("#phonebar");
  try { d = d || await api("/api/phone/status"); } catch (e) { bar.innerHTML = `<div class="phone-body"><span class="err">${esc(errKo(e))}</span></div>`; return; }
  bar.innerHTML = phoneHtml(d);
  $("#phonebtn").textContent = d.on ? "폰 연결 · 켜짐" : "폰 연결";
  const act = (sel, fn) => bar.querySelectorAll(sel).forEach((b) => { b.onclick = async () => {
    b.disabled = true;
    try { phonePaint(await fn(b)); } catch (e) { b.disabled = false; notify(errKo(e)); }
  }; });
  act("#phoneon", () => phonePost("/api/phone/switch", { on: true }));
  act("#phoneoff", () => (confirm("휴대폰 연결을 끕니다. 연결된 기기도 모두 끊깁니다.") ? phonePost("/api/phone/switch", { on: false }) : api("/api/phone/status")));
  act("#phonecode", () => phonePost("/api/phone/code"));
  act(".phone-unpair", (b) => phonePost("/api/phone/unpair", { id: b.dataset.id }));
  const x = $("#phoneclose");
  if (x) x.onclick = phoneClose;
}
function phoneClose() { $("#phonebar").hidden = true; clearInterval(phoneTimer); phoneTimer = null; }

// The button exists on the computer only.  A paired phone is told it is a phone, and the controls that work only on the
// computer are hidden there.
api("/api/phone/status").then((d) => {
  if (d.phone) document.documentElement.classList.add("on-phone");
  if (d.available === false) return;
  const btn = $("#phonebtn");
  btn.hidden = false;
  btn.textContent = d.on ? "폰 연결 · 켜짐" : "폰 연결";
  btn.onclick = () => {
    const bar = $("#phonebar");
    if (!bar.hidden) return phoneClose();
    bar.hidden = false;
    phonePaint();
    phoneTimer = setInterval(() => { if (!document.hidden) phonePaint(); }, 15000);        // a device that pairs shows up without a reload
  };
}).catch(() => {});

// Touch screens have no hover: a tap on a marked word shows its explanation (the title text) in a bar at the bottom.
if (window.matchMedia && window.matchMedia("(pointer: coarse)").matches) {
  const tip = document.createElement("div");
  tip.id = "taptip"; tip.hidden = true; tip.setAttribute("role", "status");
  document.body.appendChild(tip);
  document.addEventListener("click", (e) => {
    const el = e.target.closest ? e.target.closest("[title]") : null;
    const ctl = e.target.closest && e.target.closest("button, a, input, select, textarea, summary, label");
    // A marked word inside a button (a badge on a rank row) is read too; the button still does what it does.  A control's own
    // title is not shown: the tap is for the control.
    const busy = ctl && (!el || el === ctl || !ctl.contains(el));
    if (!el || busy || !el.getAttribute("title") || el === tip) { tip.hidden = true; return; }
    tip.textContent = el.getAttribute("title");
    tip.hidden = false;
  }, true);
}
