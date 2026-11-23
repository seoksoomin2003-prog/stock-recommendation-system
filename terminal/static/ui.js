// Shared screen parts (UI batch 3 P2-4, 2026-11-23).  Loaded before app.js; no build step, no library.
// Every builder returns an HTML string.  Arguments named text, title, sub and label are plain text and are escaped here;
// arguments named body, rows, html and actions are HTML the caller already built (and escaped).
// For new templates, html`...` escapes every value unless it is wrapped in raw(...).
"use strict";
const ui = (() => {
  const escape = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  class Raw { constructor(s) { this.s = String(s); } toString() { return this.s; } }
  const raw = (s) => (s instanceof Raw ? s : new Raw(s ?? ""));
  const value = (v) => (v instanceof Raw ? v.s : Array.isArray(v) ? v.map(value).join("") : v === null || v === undefined || v === false ? "" : escape(v));
  const html = (strings, ...values) => raw(strings.reduce((out, s, i) => out + s + (i < values.length ? value(values[i]) : ""), ""));
  const cls = (...names) => names.filter(Boolean).join(" ");

  // <h2>title <span class="meta m0">sub</span> <span class="ph-actions">actions</span></h2>: the actions sit at the header's right end
  const head = ({ title, sub, actions } = {}) => `<h2>${escape(title)}${sub ? ` <span class="meta m0">${escape(sub)}</span>` : ""}${actions ? ` <span class="ph-actions">${actions}</span>` : ""}</h2>`;
  const panel = ({ title, sub, actions, body = "", id, cls: extra } = {}) =>
    `<div class="${cls("panel", extra)}"${id ? ` id="${escape(id)}"` : ""}>${title ? head({ title, sub, actions }) : ""}${body}</div>`;
  // cols: [{ label, cls, title }]; rows: HTML of the <tr> rows; empty: text when there are no rows
  const table = ({ cols, rows, cls: extra, id, empty } = {}) => {
    const body = Array.isArray(rows) ? rows.join("") : rows || "";
    if (!body && empty) return ui.empty(empty);
    const th = (c) => `<th${c.cls ? ` class="${escape(c.cls)}"` : ""}${c.title ? ` title="${escape(c.title)}"` : ""}>${escape(c.label ?? "")}</th>`;
    return `<div class="tbl-wrap"><table${extra ? ` class="${escape(extra)}"` : ""}${id ? ` id="${escape(id)}"` : ""}>${cols ? `<thead><tr>${cols.map(th).join("")}</tr></thead>` : ""}<tbody>${body}</tbody></table></div>`;
  };
  const notice = (body, tone) => `<div class="${cls("notice", tone)}">${body}</div>`;
  const empty = (text) => `<div class="empty">${escape(text)}</div>`;
  const badge = (text, tone, title) => `<span class="${cls("badge", tone)}"${title ? ` title="${escape(title)}"` : ""}>${escape(text)}</span>`;
  const meta = (body) => `<div class="meta">${body}</div>`;
  const kv = (pairs) => `<div class="kv">${pairs.map(([label, body]) => `<div><span>${escape(label)}</span><b>${body}</b></div>`).join("")}</div>`;
  const fold = ({ title, body = "", open = false, hint = "자세히", cls: extra } = {}) =>
    `<details class="${cls(extra)}"${open ? " open" : ""}><summary>${title}${hint ? ` <span class="fold-hint">${escape(hint)}</span>` : ""}</summary>${body}</details>`;
  // items: [[value, label]]; the selected one is marked on and aria-pressed
  const seg = ({ items, value: on, label, id } = {}) => `<span class="seg"${id ? ` id="${escape(id)}"` : ""} role="group"${label ? ` aria-label="${escape(label)}"` : ""}>${items
    .map(([v, l]) => `<button type="button" data-v="${escape(v)}" class="${v === on ? "on" : ""}" aria-pressed="${v === on}">${escape(l)}</button>`).join("")}</span>`;
  // The workspace grid of style.css (workstation stage 2).  ctx, main, right and lower are HTML; a part left out is not written.
  // name -> data-ws, view -> data-view, single -> one column at every width, narrow -> the 1280 px cap, label -> the right column's name.
  const ws = ({ name, view, single, narrow, ctx, main = "", right, lower, label = "분석" } = {}) =>
    `<div class="${cls("ws", single && "ws--single", narrow && "ws--narrow")}"${name ? ` data-ws="${escape(name)}"` : ""}${view ? ` data-view="${escape(view)}"` : ""}>`
    + (ctx ? `<div class="ws-ctx">${ctx}</div>` : "")
    + `<div class="ws-body"><div class="ws-main">${main}</div>${right ? `<div class="ws-right" role="complementary" aria-label="${escape(label)}">${right}</div>` : ""}</div>`
    + (lower ? `<div class="ws-lower">${lower}</div>` : "") + "</div>";
  // One right-column panel.  With no body it shows the empty sentence (what to pick to fill it), never a blank box.
  // first -> in one column it comes before the main column (.ws-first).
  const rightPanel = ({ title, sub, actions, body, empty = "왼쪽 표에서 줄을 고르면 여기에 자세히 보입니다.", id, first, cls: extra } = {}) =>
    panel({ title, sub, actions, id, cls: cls(first && "ws-first", extra), body: body || `<div class="ws-empty">${escape(empty)}</div>` });
  return { escape, raw, html, head, panel, table, notice, empty, badge, meta, kv, fold, seg, ws, rightPanel };
})();
const { html, raw } = ui;

// In-page confirm (workstation stage 2, owner decision U-6): replaces the browser's own confirm window, which looked like an error and
// could not be styled.  Resolves true on the OK button, false on 취소, Esc or a click outside.  Keyboard focus stays inside while it
// is open (Tab cycles the two buttons) and goes back to where it was.  With danger the OK button is red-edged and focus starts on 취소.
// Only one is open at a time: opening a second answers the first with false.  Rendered at body level (position: fixed).
let uiConfirmOpen = null;
function uiConfirm(message, { okLabel = "확인", cancelLabel = "취소", danger = false } = {}) {
  if (uiConfirmOpen) uiConfirmOpen(false);
  return new Promise((resolve) => {
    const back = document.activeElement, id = `ui-dlg-${Date.now()}`;
    const wrap = document.createElement("div");
    wrap.className = "ui-dialog-wrap";
    wrap.innerHTML = `<div class="ui-dialog" role="alertdialog" aria-modal="true" aria-describedby="${id}"><p id="${id}">${ui.escape(message)}</p>
      <div class="ui-dialog-acts"><button type="button" data-ok="0">${ui.escape(cancelLabel)}</button><button type="button" data-ok="1" class="${danger ? "ui-danger" : "btn-primary"}">${ui.escape(okLabel)}</button></div></div>`;
    const [no, yes] = wrap.querySelectorAll("button");
    const done = (v) => {
      if (!wrap.isConnected) return;
      wrap.remove(); document.removeEventListener("keydown", key, true); uiConfirmOpen = null;
      if (back && back.isConnected && typeof back.focus === "function") back.focus();
      resolve(v);
    };
    const key = (e) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done(false); return; }
      if (e.key === "Tab") { e.preventDefault(); (document.activeElement === yes ? no : yes).focus(); return; }
      e.stopPropagation();          // the page's shortcuts (number keys, /, Esc for menus) wait; Enter and Space still press the button
    };
    no.onclick = () => done(false); yes.onclick = () => done(true);
    wrap.addEventListener("click", (e) => { if (e.target === wrap) done(false); });
    document.addEventListener("keydown", key, true);
    uiConfirmOpen = done;
    document.body.appendChild(wrap);
    (danger ? no : yes).focus();
  });
}
