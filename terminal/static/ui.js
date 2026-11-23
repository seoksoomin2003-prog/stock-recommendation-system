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

  // <h2>title <span class="meta m0">sub</span> actions</h2>
  const head = ({ title, sub, actions } = {}) => `<h2>${escape(title)}${sub ? ` <span class="meta m0">${escape(sub)}</span>` : ""}${actions ? ` ${actions}` : ""}</h2>`;
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
  return { escape, raw, html, head, panel, table, notice, empty, badge, meta, kv, fold, seg };
})();
const { html, raw } = ui;
