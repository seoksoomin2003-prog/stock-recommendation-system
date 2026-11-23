# 디자인 시스템 평가 (2026-11-23)

작성: 총괄 디자인 평가자. 주 근거는 Agent 4(F1~F22)의 직접 집계, Agent 1(UI-05, UI-06), Agent 5(대비 계산), 조정자 측정과 재집계, 총괄 평가자의 style.css 재확인과 대비 재계산입니다. 대상: `~/Developer/quant-stock-engine/terminal/static/`.

## 요약

- **색만 시스템이고 나머지는 숫자입니다.** `:root`에 색 token 30개(의미 12, 계열 8, 이동평균 10)와 3단 테마 전환이 있습니다. 글자 크기·간격·모서리·그림자·z-index·내용 폭·breakpoint에는 token이 없습니다.
- **부품 층이 없습니다.** 표 77, 패널 116, 안내 상자 39, 빈 상태 62, 세그먼트 13이 21개 JS 파일의 템플릿 문자열로 매번 새로 쓰였습니다(F1).
- **인라인 style**: JS 소스에 `style="…"` 261개, 그중 `class="meta" style="margin:0"` 한 패턴이 **151개**(조정자 재집계, 약 58 %). 렌더된 점수 상세에는 style 속성을 가진 요소가 731개입니다(측정표). 두 숫자는 서로 다른 것을 센 값입니다.
- **결론**: 프레임워크 없이 token + 작은 `ui.js` 부품 + CSS 재배치로 충분히 시스템을 세울 수 있습니다. 가장 큰 비용은 정적 파일 문자열을 고정한 테스트 약 24개 파일입니다(F20).
- 점수: 일관성·프론트엔드 **4.5 / 10**(Agent 4 제안에 동의).

## 1. Token 현황

| 종류 | 현재 | 근거 | 판단 |
|---|---|---|---|
| 의미 색 | `--bg --panel --ink --muted --line --up --down --accent --warn --bad --chip --grid` | style.css:2-4 | 양호 |
| 계열·이동평균 색 | `--s1..--s8`, `--ma5..--ma200`, `--sma20/50/200` | style.css:4-5 | 양호. 캔버스가 `cssVar()`로 읽고 테마 변경 시 다시 그림(app.js:130, 342-352) |
| 테마 밖 고정 색 | `#fff` 4곳(style.css:42,102,135,250), 판단 알약 `--act` 고정 hex 4색(style.css:150), map.js:38·94 hex | F 표 | 누수. `#fff` on accent가 어두운 테마 대비 2.70의 원인 |
| 정의 안 된 token | `var(--hover, …)` 2곳(style.css:235, 346), `.muted` 클래스 사용 3곳에 규칙 없음 | F4, 조정자 확인 | 늘 대체값·기본 글자색으로 그려짐 |
| 어두운 팔레트 | 같은 값이 두 벌(시스템 설정용 style.css:9-18, 버튼용 19-26) | F5 | test_chart_analysis.py:180이 `--maN:` 3회 등장을 강제 |
| 글자 크기 | 없음. CSS 선언 13 px×30, 12×24, 14×8, 15×7, 11×6, 16×4, 26×2, 12.5×2, 34·28·24·18 각 1. 화면에서 본 값 10.8~34 px | EVIDENCE, F3 | token 필요 |
| 글자 굵기 | 400×2, 500×4, 600×19, 650×2, 700×9 | F 표 | 3단계면 충분 |
| 간격 | padding 39종, margin 46종, gap 18종 | F 표 | token 필요 |
| 모서리 | 6 px×11, 8×8, 4×8, 10×4, 3, 2×2, 14, 12 (8종) | EVIDENCE | 3단계 + pill |
| 그림자 | 4종(style.css:122, 231, 342, 382) | F 표 | 2종 |
| z-index | 5, 20, 30, 50, 50(`#cmd`와 `#taptip` 같음) | F 표 | 작은 척도 |
| 내용 폭 | `max-width: 1280px` 2곳(style.css:68, 120) | D5 | 1920에서 약 640 px 미사용의 원인 |
| breakpoint | CSS 560, 600(2곳), 700, 720(2곳), 760 + JS `innerWidth < 600` 7곳 | F7, 조정자 확인 | 768 태블릿이 데스크톱 배치를 받는 원인 |

### 대비 (총괄 평가자 재계산, WCAG 상대휘도)

| 조합 | 값 | 판정 |
|---|---|---|
| 어두운: 흰 글자 on `--accent` #6d9bff (`.search button`, `.seg button.on`, `.btn-primary`) | 2.70 | 실패 (사용자가 쓰는 테마) |
| 밝은: 흰 글자 on `--accent` #2457d6 | 6.16 | 통과 |
| 어두운: 글자 token on `--panel` (ink 14.21, muted 5.70, up 7.31, down 5.96, warn 8.35) | — | 모두 통과 |
| 밝은: `--up` #0a8f5a on 흰 패널 / chip | 4.13 / 3.64 | 실패 |
| 밝은: `--warn` #b26b00 on 흰 패널 / chip | 4.20 / 3.71 | 실패 |
| 입력 테두리 `--line` vs `--panel` | 1.27(밝은) / 1.24(어두운) | 3:1 미달 (A8) |

## 2. 부품 목록 (현재)

| 부품 | 재사용 함수 | 손으로 쓴 횟수·문제 | 근거 |
|---|---|---|---|
| 표 | 없음 | `<table` 77. 정렬 머리글 두 구현(peers.js:45-49 키보드 불가 / qsf.js:616-624 `button` + `aria-sort`) | F1 |
| 패널 + h2 | 없음 | `.panel` 116, h2 108. h2 15 px vs 본문 14 px | F1, UI-06 |
| 안내 상자 `.notice` | 없음 | 39. 위험 게이트·오래된 자료·합병·실적일 미상이 모두 같은 노란 상자 | F1, W 오류 문구 |
| 빈 상태 `.empty` | 없음 | 62 | F1 |
| 오류 상자 | `errBox()` | 25회 사용, 별도 `.err` 직접 작성도 있음 | F 표 |
| 출처 줄 | `meta()` | 16회 — 좋은 예 | F 표 |
| 보조 글 `.meta` | 없음 | 459회, 151회가 `style="margin:0"` | F2 + 재집계 |
| 배지 | `badge()`, `liveBadge()` | 함수 34회 vs 직접 82회 | F 표 |
| 판단 알약 | `qsfLabel()` | 직접 4회, 색 경계 70/55/40이 화면 코드에(qsf.js:37) | F19 |
| 시세 카드 | `card()` | 시장 개요와 오늘 탭 공유 — 좋은 예 | F 강점 |
| 시장 상태 블록 | `qsfMarketState()` | 함수는 하나, 전체 블록이 3곳 | D8 |
| 세그먼트 `.seg` | 없음 | 13 | F 표 |
| 접기 | 두 방식 | `.fold`(h2 클릭) 12 + `<details>` 23 | F10 |
| 키-값 격자 `.kv` | 없음 | 19 | F 표 |
| 버튼 | CSS만 | `<button` 87개 중 `type=` 없는 것 16 | F 표 |
| 입력 | 없음 | `#qsfticker`, `#cha-q`에 배경·테두리·글자색 규칙 없음 → 브라우저 기본 회색(17, 10, 39) | UI-05 |
| 툴팁 위치 계산 | 없음 | 같은 한 줄이 6곳 | F 표 |
| 숫자 서식 | `fmt/pct/big` | 파일별 서식 함수 14개 이상, qsf.js:848 지역 `pct`가 전역을 가림 | F9 |
| 빈 값 | `DASH` | `DASH` 114회 + `"—"` 17 + `없음` 7 + `-` + `–` 등 최소 5가지 | F8 |
| 차트 준비 | `spark/setupCanvas/line` | 공유 — 좋은 예 | F 강점 |

## 3. CSS 구성

- 447줄 한 파일, 기능이 생길 때마다 구역을 뒤에 덧붙인 구조(구역 주석 18개, style.css:129-408).
- 중복 선택자 `.legend`(103, 246), `.search`(36, 340), `.cha-line b`(405, 406). 순위가 표로 바뀐 뒤 남은 것으로 보이는 선택자 약 9개(F6, 동적 클래스명 가능성 때문에 확신도 보통).
- `body { overflow-x: hidden }`(style.css:30)이 넘침을 숨겨 측정에 안 잡힐 수 있음(R7).

## 4. 테마

- 자동/밝게/어둡게 3단, `data-theme` 속성, 캔버스 다시 그리기 — 제품 수준.
- 사용자는 어두운 테마를 명시적으로 씀(EVIDENCE). 그 테마의 accent 배경 위 흰 글자가 유일한 AA 실패 조합.
- 판단 알약 색이 "테마 무관 고정"(style.css:149 주석)이라 밝은 테마 대비를 따로 관리하지 않음. 알약 테두리 #16A34A on 흰 = 3.30, on 어두운 panel = 5.25(비텍스트 3:1 통과).
- 색 관례: 한 쌍의 전역 token(`--up` 초록, `--down` 빨강)을 미국·한국 두 시장이 함께 씀(style.css:3, 12, 21). 국내 증권사(사용자의 토스증권 포함)는 빨강이 상승입니다. 이것은 결함이 아니라 **사용자가 정할 일**입니다(DESIGN_DIRECTION_PROPOSAL.md 2절).

## 5. 제안 token 세트

값은 현재 값에서 가장 가까운 단계로 모읍니다(12.5 → 12 또는 13). 대비 값은 총괄 평가자가 계산했습니다.

```css
:root {
  /* 글자 */
  --fs-xs: 11px;   /* 배지, 축 눈금 */
  --fs-sm: 12px;   /* meta, 표 보조 */
  --fs-md: 13px;   /* 표 본문 */
  --fs-base: 14px; /* 본문 */
  --fs-lg: 16px;   /* 패널 제목 h2 (현재 15) */
  --fs-xl: 20px;   /* 화면 제목 h1 (현재 없음) */
  --fs-display: 28px; /* 카드 점수 (현재 34) */
  --fw-normal: 400; --fw-strong: 600; --fw-heavy: 700;
  /* 간격 (4 px 격자) */
  --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px; --sp-5: 24px; --sp-6: 32px;
  /* 모서리 */
  --r-sm: 4px; --r-md: 6px; --r-lg: 8px; --r-pill: 999px;
  /* 그림자 */
  --shadow-1: 0 1px 2px rgba(0,0,0,.18);
  --shadow-2: 0 6px 24px rgba(0,0,0,.35);
  /* 층 */
  --z-header: 10; --z-popover: 20; --z-dialog: 40; --z-toast: 50;
  /* 폭 */
  --content-max: 1280px;       /* 글 위주 화면 */
  --content-max-wide: 1680px;  /* 순위·스크리너·시장 개요·차트분석 */
  /* 새 색 token (밝은 테마) */
  --on-accent: #ffffff;        /* on #2457d6 = 6.16 */
  --line-strong: #7b8594;      /* 입력 테두리, on 흰 = 3.73 */
  --hover: #eef1f5;
  --up: #067a4b;               /* 흰 5.39, chip 4.76 (현재 #0a8f5a 4.13) */
  --warn: #8f5600;             /* 흰 6.00, chip 5.30 (현재 #b26b00 4.20) */
}
:root[data-theme="dark"] {
  --on-accent: #0e1116;        /* on #6d9bff = 7.01 (현재 흰 글자 2.70) */
  --line-strong: #6b7686;      /* --bg 위 4.11, --panel 위 3.76 */
  --hover: #1f2630;
}
```

- breakpoint(사용자 정의 속성은 미디어 쿼리 안에서 못 쓰므로 주석 상수 + JS 상수 한 곳): **폰 ≤ 640 px, 태블릿 641–1023 px, 데스크톱 1024–1599 px, 넓은 화면 ≥ 1600 px.** JS의 `innerWidth < 600` 7곳은 `matchMedia("(max-width: 640px)")` 한 함수로.
- 의미가 다른 색을 분리하는 token(값은 방향 제안서 2절): `--price-up/--price-down`(가격 등락, 시장별 전환 가능), `--judge-candidate/--judge-hold/--judge-avoid`(앱의 판단), `--status-ok/--status-pending`(점검·검증 상태). 지금은 `--up` 초록 하나가 다섯 가지 뜻을 가집니다(레드팀).

## 6. 제안 부품 목록 (`ui.js`, 빌드 없음, app.js 앞에 로드)

| 부품 | 역할 | 대체하는 것 |
|---|---|---|
| `html\`…\`` + `raw()` | 자동 이스케이프 태그 템플릿 | 관례 의존 이스케이프(F17) |
| `ui.panel({title, sub, actions, body})` | 패널 + h2 | `.panel` 116 |
| `ui.table({cols, rows, empty, sort})` | 표, 정렬 머리글은 `button` + `aria-sort`, 열 전체가 비면 접고 한 줄 안내 | `<table` 77, peers 정렬, D3 |
| `ui.notice({tone: "gate" | "info" | "stale"})` | 실행을 막는 것과 참고를 모양으로 구분 | `.notice` 39 |
| `ui.empty({text, action})` | 빈 상태 + 이동 버튼 | `.empty` 62, 터미널 명령 안내(W11) |
| `ui.seg({items, value, label})` | 세그먼트, `aria-pressed`, `word-break: keep-all` | `.seg` 13, R6 |
| `ui.fold({title, open, key})` | `<details>` 기반, 열림 저장 | `.fold` 12 |
| `ui.kv(pairs)` | 키-값 격자 | `.kv` 19 |
| `ui.badge(text, tone)` | 배지 | 직접 작성 82 |
| `ui.statusStrip({market, validation, stance})` | 점수 탭·상세 상단 한 줄 상태 띠 | 머리 블록 270 px, 시장 상태 블록 3곳 |
| `ui.scoreChip({score, band, conf, nearEdge})` | 표용 정수 점수 + 판단 + 자료 충족 | 소수점 점수, 70점 색 절벽 |
| `ui.tip.place(e)` | 툴팁 위치 | 같은 한 줄 6곳 |
| `fmt.num/pct/signedPct/money(market)/qty/score/big(market)` | 숫자 서식 한 곳, 빈 값은 `DASH` 하나 | 서식 함수 14+, 빈 값 5가지 |
| `chart.axisTicks(lo, hi, n, market)` | 1·2·2.5·5×10ⁿ 반올림 눈금, 천 단위 구분 | app.js:497-499 vs chart.js:129 |
| `chart.guardBar(bar)` | 시가 0·범위 밖 시가 표시 | D1 |

## 7. 이행 순서 (Agent 4의 7절을 따르되 순서 조정)

0. 준비: 정적 파일 문자열을 고정한 테스트 목록 정리(F20; 예: test_ui_audit_2026_11_23.py:191, test_chart_analysis.py:180). 기준 스크린샷 40장 보관(저장소 밖).
1. token: 위 세트 추가, `#fff` → `--on-accent`, `--hover` 정의, `.muted` 처리. 글자 크기 12종 → 7종.
2. 인라인 style: `.meta-i`(줄 안 보조 글) 한 클래스로 151개 제거, 나머지 약 110개는 유틸리티 6~8개로. 동적 폭(`width:${…}%`)은 남김.
3. `ui.js` 부품: 작은 파일(calendar, peers, alerts, coin, sectorpicks)부터, qsf.js는 마지막.
4. CSS 재배치: token → 기본 → 레이아웃 → 부품 → 화면별 → 반응형. 죽은 규칙·중복 선택자 삭제, 어두운 팔레트 한 벌(첫 페인트 전 `data-theme` 설정 스크립트), breakpoint 4단계.
5. ES 모듈은 나중(소스 고정 테스트가 줄어든 뒤). 전역 이름 459개는 지금 충돌 0건(F13).

예상 규모(Agent 4, 확신도 낮음): 1~4단계 6~9 작업일, 그중 약 3분의 1이 테스트 수정.

## 8. 하지 말 것

- React/Vue 등 프레임워크 이전, CDN 의존, 빌드 단계 추가: 폰에서 같은 파일을 여는 구조와 맞지 않음.
- 점수 구간 색 경계 값(70/55/40) 자체를 바꾸는 일: 화면이 서버의 구간 이름을 읽게만 함(F19).

## 확인하지 못한 것

- 죽은 선택자 목록의 정확성(동적 클래스명), 실제 렌더 성능, 테스트 단언 가운데 정적 파일 대상만의 정확한 수.
