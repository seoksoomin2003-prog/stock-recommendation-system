// 종목 화면의 동종업계 비교: 같은 업종 스캔 종목과 점수·재무 비율을 나란히 보고, 점수 영역별 업종 내 위치를 A~F로 본다.  읽기 전용.
"use strict";
const PEER_PARTS = [["SCORE", "총점"], ["TECHNICAL", "기술"], ["FUNDAMENTAL", "재무"], ["RISK", "위험"], ["EVENTS", "이벤트"]];
const PEER_COLS = [
  ["market_cap", "시가총액", (r) => big(r.market_cap, isKR() ? "KRW" : "USD")],
  ["change_1m", "1개월", (r) => pct(isNum(r.change_1m) ? r.change_1m * 100 : null, 1)],
  ["swing", "스윙", (r) => fmt(r.swing, 1)], ["long", "장기", (r) => fmt(r.long, 1)],
  ["pe", "PER", (r) => fmt(r.ratios && r.ratios.pe, 1)], ["pb", "PBR", (r) => fmt(r.ratios && r.ratios.pb, 2)],
  ["fcf_yield", "FCF 수익률", (r) => pctOf(r.ratios && r.ratios.fcf_yield)], ["op_margin", "영업이익률", (r) => pctOf(r.ratios && r.ratios.op_margin)],
  ["roe", "ROE", (r) => pctOf(r.ratios && r.ratios.roe)], ["rev_cagr3", "3년 매출성장", (r) => pctOf(r.ratios && r.ratios.rev_cagr3)],
  ["debt_equity", "부채/자본", (r) => fmt(r.ratios && r.ratios.debt_equity, 2)],
];
const pctOf = (v) => (isNum(v) ? `${(v * 100).toFixed(1)}%` : DASH);
const peerVal = (r, k) => (k in r ? r[k] : r.ratios ? r.ratios[k] : null);
const peerState = { sort: "market_cap", desc: true, data: null, all: false };

async function loadPeers(t) {
  const box = $("#s-peers");
  if (!box) return;
  box.innerHTML = `<h2>동종업계 비교</h2>${loading}`;
  try {
    const d = await api(mq(`/api/qsf/peers?t=${encodeURIComponent(t)}`));
    if (state.ticker !== t) return;
    peerState.data = d; peerState.all = false; paintPeers();
  } catch (e) { if (state.ticker === t) box.innerHTML = `<h2>동종업계 비교</h2>${errBox(e)}`; }
}
function paintPeers() {
  const box = $("#s-peers"), d = peerState.data;
  if (!box || !d) return;
  if (d.status !== "REAL") { box.innerHTML = '<h2>동종업계 비교</h2><div class="empty">이 종목은 QSF 스캔 대상이 아니라 업종 비교가 없습니다.</div>'; return; }
  const gradeRow = (st, name) => `<tr><td class="l">${name}</td>${PEER_PARTS.map(([k]) => {
    const g = (d.grades[st] || {})[k] || {};
    return `<td>${g.grade ? `<span class="grade g-${g.grade}" title="업종 ${g.n}개 중 상위 ${Math.round((1 - g.percentile) * 100)}% · 값 ${fmt(g.value, 1)}">${g.grade}</span>` : `<span class="missing" title="${g.n < 6 ? "비교할 종목이 6개 미만" : "값 없음"}">—</span>`}</td>`;
  }).join("")}</tr>`;
  const rows = [...d.peers].sort((a, b) => {
    const x = peerVal(a, peerState.sort), y = peerVal(b, peerState.sort);
    if (!isNum(x) && !isNum(y)) return 0; if (!isNum(x)) return 1; if (!isNum(y)) return -1;      // missing values go last, never treated as 0
    return peerState.desc ? y - x : x - y;
  });
  const shown = peerState.all ? rows : rows.filter((r, i) => i < 12 || r.ticker === d.ticker);
  box.innerHTML = `<h2>동종업계 비교 <span class="meta" style="margin:0">${esc(sectorKo(d.group))} · ${esc(d.basis)} ${d.peers.length}개 종목</span></h2>
    <div class="tbl-wrap"><table class="grades"><thead><tr><th class="l">업종 내 위치</th>${PEER_PARTS.map(([, n]) => `<th>${n}</th>`).join("")}</tr></thead>
      <tbody>${gradeRow("SWING", "스윙 점수")}${gradeRow("LONG_TERM", "장기 점수")}</tbody></table></div>
    <div class="meta">${esc(d.basis_note)} 글자에 마우스를 올리면 순위와 값이 보입니다.</div>
    <div class="tbl-wrap"><table id="peer-tbl"><thead><tr><th class="l">종목</th>${PEER_COLS.map(([k, n]) => `<th class="sort${peerState.sort === k ? " on" : ""}" data-k="${k}">${n}${peerState.sort === k ? (peerState.desc ? " ▼" : " ▲") : ""}</th>`).join("")}</tr></thead>
      <tbody>${shown.map((r) => `<tr class="click${r.ticker === d.ticker ? " me" : ""}" data-ticker="${esc(r.ticker)}"><td class="l"><b>${esc(r.name || r.ticker)}</b> <span class="meta" style="margin:0">${esc(r.ticker)}</span></td>${PEER_COLS.map(([, , f]) => `<td class="num">${f(r)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    ${rows.length > shown.length ? `<button class="ghost" id="peer-all" type="button">${rows.length}개 모두 보기</button>` : ""}
    <div class="meta">점수: 스캔 거래일 ${esc(d.session)} · ${esc(d.model_version || "")}. 재무 비율: ${d.ratio_session ? `${esc(d.ratio_version)} 원장 기록 ${esc(d.ratio_session)} (점수가 실제로 읽은 값)` : `${esc(d.ratio_version)} 원장 기록이 아직 없어 비어 있습니다. 첫 기록은 다음 자동 실행 뒤에 생깁니다.`} 머리글을 누르면 정렬합니다.</div>`;
  box.querySelectorAll("th.sort").forEach((th) => (th.onclick = (e) => {
    e.stopPropagation(); const k = th.dataset.k;
    peerState.desc = peerState.sort === k ? !peerState.desc : true; peerState.sort = k; paintPeers();
  }));
  const all = $("#peer-all"); if (all) all.onclick = () => { peerState.all = true; paintPeers(); };
}
