// '지금 수집': 매일 자동 실행과 같은 작업을 지금 시작한다.  이미 끝난 단계는 건너뛰고, 준비되지 않은 날은 기록하지 않는다.
"use strict";
const COLLECT_START_WAIT_MS = 60000;      // 시작한 프로세스가 상태를 남길 때까지 기다리는 한도
let collectClicked = null;                // 버튼을 누른 시각(서버 시각 ISO)과 브라우저 시각
let collectSawRun = false;                // 이 화면에서 실행 중인 것을 본 적이 있는지

// 수집이 끝났거나 '화면 새로 고침'을 눌렀습니다: 기억해 둔 순위 응답과 종목 찾기 결과를 버리고, 순위·카드 탭은 다음에 열 때 다시 그립니다.
function collectStale() {
  if (typeof qsfDropLatest === "function") qsfDropLatest();
  if (typeof symbolCache !== "undefined") symbolCache.clear();
  state.loaded.qsf = false;
  if (typeof topChips === "function") topChips();          // 머리줄의 시장 상태·자료 시각 칩도 다시 읽습니다
}

function collectPaint(html, closable) {
  const bar = $("#collectbar");
  bar.hidden = false;
  bar.innerHTML = `<span class="collect-text">${html}</span>${closable ? '<button type="button" class="ghost" id="collectclose" aria-label="닫기">✕</button>' : ""}`;
  const x = $("#collectclose");
  if (x) x.onclick = () => { bar.hidden = true; };
  const r = $("#collectrefresh");
  if (r) r.onclick = () => { bar.hidden = true; collectStale(); state.loaded = {}; show(state.tab, false); };
}

function collectResult(a) {
  const la = a.last_attempt || {};
  if (la.status === "UP_TO_DATE") return `이미 최신입니다 · 기준 거래일 ${esc(la.session || "")}. 새 자료는 미국 장 마감(한국 시간 오전 6~7시) 뒤, 한국은 다음 날 아침에 나옵니다.`;
  if (la.status === "ERROR") return `<span class="err">수집 중 오류가 났습니다${la.type ? ` (오류 종류 ${esc(la.type)})` : ""}.</span> 기록 파일: data/automation/manual_run.log`;
  const steps = Object.entries(a.steps || {});
  const named = (st) => steps.filter(([, v]) => v && v.status === st).map(([k, v]) => `${esc(a.step_names[k] || k)}${v.detail ? ` (${esc(v.detail)})` : ""}`);
  const failed = named("FAILED"), waiting = named("WAITING");
  return `수집을 마쳤습니다 · 기준 거래일 ${esc(la.session || "")}`
    + (failed.length ? ` · <span class="err">실패: ${failed.join(", ")}</span>` : "")
    + (waiting.length ? ` · 아직 공개 전: ${waiting.join(", ")}` : "")
    + (failed.length ? " · 다시 누르면 실패한 단계만 다시 시도합니다." : "")
    + ' <button type="button" class="ghost" id="collectrefresh">화면 새로 고침</button>';
}

async function collectPoll() {
  const btn = $("#collect");
  const a = await api("/api/automation/status").catch(() => null);
  if (!a) {
    btn.disabled = false;
    if (collectClicked || collectSawRun) collectPaint('<span class="err">수집 상태를 읽지 못했습니다.</span>', true);
    return;
  }
  if (a.running) {
    collectSawRun = true;
    btn.disabled = true;
    const r = a.running, name = r.step ? (a.step_names[r.step] || r.step) : "준비";
    collectPaint(`자료 수집 중 · ${esc(name)}${r.total ? ` · ${r.done}/${r.total} 단계 완료` : ""} · 시작 ${when(r.started_at)} · 남은 단계가 많으면 15~25분 걸립니다. 맥을 깨워 두세요.`, false);
    setTimeout(collectPoll, 3000);
    return;
  }
  const la = a.last_attempt;
  if (collectClicked && !(la && Date.parse(la.at) >= Date.parse(collectClicked.at))) {      // 누른 뒤 아직 결과가 없다
    if (Date.now() - collectClicked.ms < COLLECT_START_WAIT_MS) {
      btn.disabled = true;
      collectPaint("수집을 시작하는 중…", false);
      setTimeout(collectPoll, 2000);
      return;
    }
    btn.disabled = false; collectClicked = null;
    collectPaint('<span class="err">수집이 시작되지 않았습니다.</span> 기록 파일: data/automation/manual_run.log', true);
    return;
  }
  btn.disabled = false;
  if (!collectClicked && !collectSawRun) return;          // 화면을 열었을 때 실행 중이 아니면 아무것도 띄우지 않는다
  collectClicked = null; collectSawRun = false;
  collectStale();
  collectPaint(collectResult(a), true);
}

async function collectStart() {
  const btn = $("#collect");
  btn.disabled = true;
  try {
    const res = await post("/api/automation/run", {});
    collectClicked = res.status === "STARTED" ? { at: res.at, ms: Date.now() } : null;
    if (res.status !== "STARTED") collectSawRun = true;   // 이미 실행 중: 그 실행을 따라간다
    collectPaint("수집을 시작하는 중…", false);
    collectPoll();
  } catch (e) {
    btn.disabled = false;
    collectPaint(`<span class="err">수집을 시작하지 못했습니다: ${esc(errKo(e))}</span>`, true);
  }
}

$("#collect").onclick = collectStart;
collectPoll();          // 자동 실행이 돌고 있으면 화면을 열자마자 보여 준다
