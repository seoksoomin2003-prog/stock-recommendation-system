"""Workstation redesign stage 7 (2026-11-24): the account form's double-submit guard and '방금 기록 취소' (owner decision U-7 / O-9),
committee and 매매 보조 deep links (O-7), holdings picked into the right panel (U-5), neutral |r| shading in the holdings correlation
table, and the computer-only buttons shown greyed with their reason on a paired phone.  Display and wiring only: no score changes."""
import json
import urllib.request
from pathlib import Path

from terminal import server
from terminal.services import Terminal
from tests.test_terminal_1 import AFTER, fake_src
from tests.test_terminal_1 import _loopback_only  # noqa: F401  (autouse: these tests may reach 127.0.0.1 only)
from tests.test_ui_batch_1 import body, node

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "terminal" / "static"
JS = {p.name: p.read_text(encoding="utf-8") for p in STATIC.glob("*.js")}
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
ACCT, PF, APP, CO, QSF = JS["account.js"], JS["portfolio.js"], JS["app.js"], JS["committee.js"], JS["qsf.js"]

# The account form's script run in node with a stand-in page: the form, its submit button and the message line.
HARNESS = r"""
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNum = (v) => typeof v === "number" && isFinite(v);
const DASH = "—", loading = "…", RENDER = {}, state = { loaded: {}, tab: "account" };
const localStorage = { getItem: () => null, setItem() {} };
const marketOf = (t) => (/^[0-9][0-9A-Z]{5}$/.test(String(t).toUpperCase()) ? "KR" : "US");
const qtyFmt = (v) => String(v);
const KIND_KO = { DEPOSIT: "입금", BUY: "매수", VOID: "취소" }, STYLE_KO = { LONG: "장기", SWING: "스윙" };
const KIND_FIELDS = { DEPOSIT: ["amount"], BUY: ["ticker", "style", "qty", "price", "fee", "stop", "target"] };
const els = {};
const box = (id) => els[id] || (els[id] = { id, textContent: "", innerHTML: "", className: "", hidden: false, onclick: null,
  focus() {}, scrollIntoView() {}, querySelector: () => null, querySelectorAll: () => [], setAttribute() {}, removeAttribute() {} });
const btn = { disabled: false };
const field = (v) => ({ value: v, focus() {} });
const form = { kind: field("DEPOSIT"), market: field("US"), date: field("2026-11-20"), note: field(""), amount: field("100"), ticker: field(""), style: field(""),
  qty: field(""), price: field(""), fee: field(""), stop: field(""), target: field(""), busy: null,
  querySelectorAll: () => [], querySelector: (s) => (s.includes("submit") ? btn : null),
  setAttribute(k, v) { if (k === "aria-busy") this.busy = v; }, removeAttribute(k) { if (k === "aria-busy") this.busy = null; } };
const $ = (s) => (s === "#acctform" ? form : box(s));
const sent = [], answer = [];
const post = (path, b) => { sent.push([path, b]); return new Promise((ok, no) => answer.push({ ok, no })); };
const api = () => new Promise(() => {});                 // the redraw after a record never comes back here
const notify = () => {}, errKo = (e) => String(e.message || e), show = () => {}, setMarket = () => {};
let confirmed = [];
const uiConfirm = (text) => { confirmed.push(text); return Promise.resolve(true); };
""" + JS["account.js"]


def run(script):
    return node(HARNESS + script)


def test_a_second_click_while_the_record_is_on_its_way_is_refused():
    got = run(r"""
(async () => {
  acctBind({ holdings: [], coins: [] });
  form.onsubmit({ preventDefault() {} }); form.onsubmit({ preventDefault() {} });      // a double click
  const during = [sent.length, btn.disabled, form.busy];
  answer[0].ok({ entry: { id: "abc123def456", kind: "DEPOSIT" } }); await new Promise((r) => setTimeout(r, 0));
  const after = [sent.length, btn.disabled, acctLast && acctLast.id, acctLast && acctLast.text, box("#acctmsg").textContent];
  form.onsubmit({ preventDefault() {} });                // the old form stays shut until the redraw replaces it
  console.log(JSON.stringify({ during, after, again: sent.length }));
})();""")
    assert got["during"] == [1, True, "true"]
    assert got["after"][:3] == [1, True, "abc123def456"] and got["after"][3] == "기록했습니다: 입금 $100.00 · 미국 주식."
    assert got["after"][4].startswith("기록했습니다: 입금") and got["after"][4].endswith("다시 불러오는 중…")
    assert got["again"] == 2 and "acctBusy = true; btn.disabled = true;" in ACCT          # a later, separate submit is a new request


def test_a_refused_record_opens_the_button_again():
    got = run(r"""
(async () => {
  acctBind({ holdings: [], coins: [] });
  form.onsubmit({ preventDefault() {} });
  answer[0].no(new Error("현금이 부족합니다")); await new Promise((r) => setTimeout(r, 0));
  console.log(JSON.stringify([btn.disabled, form.busy, box("#acctmsg").textContent, acctLast]));
})();""")
    assert got == [False, None, "현금이 부족합니다", None]


def test_cancel_just_recorded_voids_exactly_that_record_through_the_journal_void():
    got = run(r"""
(async () => {
  acctLast = { id: "abc123def456", text: "기록했습니다: 입금 $100.00 · 미국 주식." };
  acctDone();
  const line = box("#acctmsg").innerHTML;
  const going = acctVoid("abc123def456", "방금 기록을 취소했습니다.");
  await new Promise((r) => setTimeout(r, 0));
  answer[0].ok({ entry: { id: "fff000fff000", kind: "VOID", ref: "abc123def456" } });
  const ok = await going;
  console.log(JSON.stringify({ line, ok, sent, confirmed, last: acctLast }));
})();""")
    assert 'data-undo="abc123def456"' in got["line"] and "방금 기록 취소</button>" in got["line"]
    assert got["ok"] is True and got["sent"] == [["/api/journal/void", {"ref": "abc123def456"}]]
    assert got["confirmed"] == ["이 기록을 취소합니다. 지우지 않고 '취소' 기록을 덧붙입니다."]                      # the journal's own confirm text
    assert got["last"] == {"voided": True, "text": "방금 기록을 취소했습니다."}


def test_no_id_in_the_answer_means_no_cancel_button():
    got = run(r"""acctLast = { id: null, text: "기록했습니다: 입금 $100.00 · 미국 주식." }; acctDone(); console.log(JSON.stringify(box("#acctmsg").innerHTML));""")
    assert "data-undo" not in got and got.startswith("기록했습니다")


def test_one_confirm_and_one_void_route_serve_the_table_and_the_undo():
    assert ACCT.count("await uiConfirm(") == 1 and ACCT.count('post("/api/journal/void"') == 1
    assert 'el.querySelectorAll("[data-void]").forEach((b) => { b.onclick = () => acctVoid(b.dataset.void); });' in ACCT
    assert 'acctVoid(b.dataset.undo, "방금 기록을 취소했습니다.' in ACCT and "r.entry.id" in ACCT
    assert 'id="acctmsg" role="status" aria-live="polite"' in ACCT
    # the paper form and the alert form are guarded the same way (UX spec 11.1)
    assert "if (ptBusy) return;" in JS["paper.js"] and "ptBusy = true; btn.disabled = true;" in JS["paper.js"]
    assert "if (btn.disabled) return;" in JS["alerts.js"] and "finally { btn.disabled = false;" in JS["alerts.js"]


def test_record_then_void_through_the_server_appends_and_never_deletes(tmp_path):
    t = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)
    httpd = server.serve(port=0, terminal=t, background=True)
    base = f"http://127.0.0.1:{httpd.server_port}"

    def post(path, b):
        req = urllib.request.Request(base + path, data=json.dumps(b).encode(), method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    try:
        made = post("/api/journal/add", {"kind": "DEPOSIT", "date": "2026-11-02", "amount": "1000", "market": "US"})
        rid = made["entry"]["id"]
        assert isinstance(rid, str) and len(rid) == 12                      # the id the '방금 기록 취소' button sends back
        void = post("/api/journal/void", {"ref": rid})
        assert void["entry"]["kind"] == "VOID" and void["entry"]["ref"] == rid
        recs, integ = t.journal.read()
        assert integ["status"] == "OK" and [r["kind"] for r in recs] == ["DEPOSIT", "VOID"] and recs[0]["id"] == rid
        lines = (tmp_path / "data" / "terminal" / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_committee_views_and_assist_sections_have_addresses():
    assert 'return `committee:${icState.view}`;' in APP and 'icSetView(b.dataset.v, true)' in CO
    assert 'if (push && state.tab === "committee" && location.hash !== "#" + tabHash("committee")) history.pushState(' in CO
    route = body(APP, "function fromHash(")
    assert 'if (tab === "committee" && typeof icState !== "undefined")' in route and 'ASSIST_SECTIONS[view]' in route
    assert 'const ASSIST_SECTIONS = { size: ["as-size"' in PF and 'location.hash = h;' in body(PF, "function assistGo(")
    assert '$("#pf-alert").onclick = () => assistGo("alerts", t);' in PF and 'history.replaceState(null, "", "#assist:" + b.dataset.sec);' in PF


def test_holdings_fill_the_right_panel_only_in_two_columns():
    assert 'if (!wsCanSplit() || e.target.closest("button, a, [data-ticker]")) return;' in ACCT
    assert 'if (!wsCanSplit() || e.target.closest("button, a")) return;' in PF and "e.stopPropagation();\n    pfState.sel = tr.dataset.ticker; pfSide(); wsRightTop(\"#pf-pick\");" in PF
    assert "qsfScanSummary($(\"#acct-pick-score\"), h.ticker, h.market, { compact: true" in ACCT and 'qsfScanSummary($("#pf-pick-score"), t, state.market, { compact: true' in PF
    assert "@container content (max-width: 1119px) { #acct-pick, #pf-pick { display: none; } }" in CSS
    assert "wsSideMarks();" in APP


def test_holdings_correlation_uses_the_neutral_shading_of_compare():
    risk = body(PF, "async function loadRisk(")
    assert "cmpCorrCell(v, i === j)" in risk and "fmt(v, 2)" not in risk


def test_computer_only_buttons_are_greyed_with_the_reason_on_a_phone():
    assert '<span class="meta m0 phone-why" id="qsfstancewhy">성향은 컴퓨터에서 바꿉니다</span>' in QSF and "재무 기준은 컴퓨터에서 바꿉니다." in QSF
    assert "if (b.dataset.level === d.level || qsfOnPhone()) return;" in QSF and "if (qsfOnPhone()) return;" in QSF
    assert ".on-phone .phone-why { display: inline; }" in CSS and ".on-phone #qsfstanceseg button, .on-phone .qsf-fund-switch { opacity: 0.55;" in CSS
