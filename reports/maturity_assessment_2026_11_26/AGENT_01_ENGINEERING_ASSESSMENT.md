# AGENT 01 — 소프트웨어 구조와 백엔드 엔지니어링 (2026-11-26, 커밋 `de1a250`)

잣대는 "전문가급 투자 리서치 제품"(바이사이드 리서치 데스크나 상용 리서치 터미널이 받아들일 수준)이다. 한 사람이 쓰는 도구로서의 점수는 6절에 한 줄로 따로 적었다.

## 1. 무엇을 어떻게 봤나

- 저장소 `~/Developer/quant-stock-engine`, 읽기만 했다. 저장소 안에 쓴 것은 없다. 스크립트와 출력은 `evidence/agent_01/`에 있다.
- 측정 스크립트(인상이 아니라 숫자): `metrics.py`(함수 길이, 넓은 예외, 모듈 크기 — AST), `spread.txt`(요인·시장·공급처·설정값이 흩어진 정도 — grep), `tests_kind.py`(소스 글자를 읽는 테스트의 비율 — AST), `shard_cost.py`(원장 조각 하나를 읽는 비용), `pick.py` + `parity.py`(오늘 서버의 한 종목 평가와 아침 스캔 기록의 비교).
- 끝까지 읽은 코드: `terminal/qsf/service.py`의 `context`/`card`/`evaluate`/`scan`/`_kr_scan_input`/`_session_bars`, `terminal/qsf/engine.py`의 `score`·구간 함수, `terminal/qsf/ledger.py`의 `Ledger`, `terminal/cache.py` 전체, `terminal/server.py`의 `make_handler`/`serve`, `terminal/automation.py`의 `_run`/`_step`/`_readings`, `terminal/qsf/config.py`의 프로필 표.
- 실행: `app.py automation status`(capital 줄 제외), `GET /api/health` 1회, `GET /api/qsf/evaluate` 3회(MSFT, JPM, 005930), 테스트 파일 1개(`tests/test_qsf_stored_rank.py`, 24 passed, 23초).
- 수익률·IC·성과는 계산하지 않았다. 원장에서는 점수와 요인 정규값만 읽었다.

## 2. 필수 질문의 답

### Q1. 구조가 정말 운영 가능한 수준인가, 그냥 돌아가는 수준인가

**답: 한 대의 맥 위에서는 "조심스럽게 만든, 돌아가는 시스템"이다. 전문가급 의미의 production-ready는 아니다. 분류: VERIFIED(아래 근거).**

돌아간다는 근거:
- 오늘 아침 기록: 미국 504종목 1,008장 684초 오류 0, 한국 300종목 600장 1,587초 오류 0, 모델 `QSF-1.6.0`(`data/qsf/latest_*.json`). VERIFIED.
- 원장 연결 검증 `OK`, 조각 36개(무효 3개)(`shard_cost.txt`). 원장은 해시 사슬, 조각을 디스크에 내린 뒤 색인 줄을 쓰고 fsync, 파일 잠금, 무효 표시(`terminal/qsf/ledger.py:264-293`, `:102-130`). VERIFIED.
- 서버 건강 응답 `server_errors.count = 0`. 서버는 127.0.0.1만 듣고, Host 검사, 교차 사이트 차단, POST는 잠금 하나로 직렬화, 내부 오류는 종류만 밖으로 낸다(`terminal/server.py:351-408`). VERIFIED(코드).
- 파일 캐시는 실패 시 옛 값을 STALE로 돌려주고 빈 응답을 저장하지 않으며, 같은 키의 동시 요청을 하나로 줄인다(`terminal/cache.py:60-97`). VERIFIED(코드).
- 스캔(쓰기)은 별도 프로세스(`app.py:938`)에서만 돈다. 서버 스레드는 읽기와 한 종목 평가만 한다. 그래서 `QSF` 객체에 얹힌 스캔용 상태(`_download_failures`, `_kr_target`, `_regime_hold` 등 31곳)가 서버 요청과 섞이지 않는다. VERIFIED(grep: `.scan(` 호출은 `app.py`와 기록 전용 모듈 두 곳뿐).

전문가급이 아니라는 근거:
- 실행 기반이 노트북 한 대의 launchd다. 알림(텔레그램, macOS)도 같은 맥에서 나간다. 맥이 꺼지거나 잠들면 실행도 알림도 함께 멈춘다. 16세션의 단계 기록에서 `NEWS_KR` 실패 8/14, `QSF_KR` 실패 1, `LAB` 실패 1(`data/automation/state.json`, 마지막 상태 기준). VERIFIED.
- 지속 통합이 없다. `.github` 없음, git 훅 없음, 린터·타입 검사 설정 없음(`pyproject.toml`·`setup.cfg` 없음), 개발 의존성은 pytest 두 개뿐(`requirements-dev.txt`). VERIFIED.
- 변경 속도: 23일에 375커밋, 11-24 이후 파이썬·JS 삽입 12,581줄(테스트와 보고서 증거 스크립트 포함). 검토자는 작성자 자신뿐이다. VERIFIED(`git log`).
- 저장소가 전부 JSON 파일이다. 스키마 정의, 이행(migration) 도구, 질의 계층이 없다. 실전 코드에 데이터베이스는 없다(sqlite는 옛 `alpha_engine`과 테스트에만). VERIFIED.
- 미국 가격의 공급처는 비공식 라이브러리 하나(yfinance 1.8.0)이고 대체 경로가 없다. 한국은 KRX 자료로 봉을 다시 만든다(이쪽이 더 튼튼하다). VERIFIED(`terminal/sources.py:109-138`, `requirements.txt`).
- 관측성: `logging`을 쓰는 모듈은 4개, `app.py`에는 `print`가 129개다. 지표 수집, 추세 대시보드, 맥 밖에서 보는 감시가 없다. VERIFIED.

### Q2. 요인·모델·공급처·분석 모듈을 큰 구조 변경 없이 더할 수 있나

**답: 요인과 "점수 옆의 읽기 전용 모듈"은 된다. 공급처는 중간이다. 세 번째 시장은 안 된다. 분류: PARTIALLY VERIFIED(코드 추적, 실제로 더해 보지는 않았다).**

- **요인 하나**: 함수 하나를 `terminal/qsf/factors.py`에 쓰고 `CALC`(`:489-495`)에 넣고, `terminal/qsf/config.py:99-118`의 가중치 표에 한 줄. 엔진(`engine.py:203-229`)은 표를 돌 뿐이라 손대지 않는다. 여기까지는 깔끔하다. 그러나 요인 이름이 손으로 적힌 곳이 7~9개 파일이다: `terminal/assistant.py`, `terminal/plain.py`, `terminal/committee/figures.py`, `terminal/qsf/inventory.py`, `terminal/qsf/us_challenger.py`, `terminal/qsf/kr_challenger.py`, `terminal/qsf/views.py`, `terminal/analyst_extra.py`(`spread.txt`). 새 입력이 필요하면 `service.py`의 `_us_fund`/`_kr_fund_events`와 `fundamentals.metrics`(195줄 함수, `fundamentals.py:276`)도 건드린다. 그리고 공식이 2027-12까지 동결이라 실전 점수에는 넣을 수 없고, 비교 기록(도전자)으로만 넣을 수 있다. 구조상 "작은 변경", 절차상 "새 버전".
- **공급처 하나**: `QSF(src=...)`와 `Terminal(src=...)`로 공급처 모듈을 주입한다(`service.py:111`, `services.py:118`). 테스트가 이 문으로 가짜를 넣는다. 좋은 설계다. 하지만 공급처 "인터페이스"는 없다. 호출부가 `src.yahoo_history(`를 이름으로 18곳에서 부르고, 한국 공급처는 다른 계층(`markets/kr/market_data.py`의 `YahooKRProvider`, `markets/kr/dart.py`)에 있으며, `requests`/`yfinance`를 직접 들여오는 파일이 32개다(그중 `terminal/qsf/research_*`·`validate*` 16개). 야후를 다른 가격원으로 바꾸려면 함수 이름·반환 모양에 맞춘 대역을 만들어 끼우는 식이 되고, 연구 모듈은 따로 고쳐야 한다.
- **시장 하나**: `== "US"` / `== "KR"` 분기가 파이썬 36개 파일에 154곳, 화면 JS 10개 파일에 약 50곳이다. 많은 곳이 `if market == "US": ... else:`(= 한국)인 이분법이다(`service.py:774-782`, `:1027-1031`, `server.py`의 `_two`). 세 번째 시장은 큰 구조 변경이다. 코인은 점수 밖의 별도 길로 붙였다(`coin_bridge.py`), 즉 이미 이 한계를 돌아간 흔적이다.
- **분석 모듈 하나(점수 밖)**: 가장 쉬운 축이다. 비교 기록과 읽기 전용 화면이 20개 넘게 같은 틀(원장 한 세션 읽기 → 자기 폴더에 기록 → `readings.REGISTRY`)로 붙어 있다. 대가는 중복이다(4절 W4).

### Q3. 구조적 약점 — 4절 표에 file:line과 함께 적었다.

### Q4. 스캔과 한 종목 평가는 정말 한 길을 지나나

**답: 점수 계산은 한 길이다. 입력을 얻는 길은 둘이다. 분류: VERIFIED(코드 + 실행).**

- 코드: `scan`은 종목마다 `self.context(t, market, pre.get(t))` → `self.card(ctx, s, …)`(`service.py:1046-1053`), `evaluate`는 `self.context(ticker, market)` → `self.card(ctx, s, …)`(`:899-906`). 둘 다 `engine.score` 하나로 간다. 보유 종목을 자기 전략 프로필로만 넘기는 규칙도 같다(`:905`, `:1053`).
- 갈리는 곳은 `context` 안 세 군데다(`service.py:785-801`): (1) 가격 봉 — 스캔은 `_session_bars`(100종목 묶음, 세션 완결 검사 후 캐시), 한 종목은 `_history`(30분 캐시의 종목+지수 요청); (2) 상대강도 순위 — 스캔은 자기 유니버스 순위, 한 종목은 `ranks_<시장>.json`에 스캔이 남긴 수익률(`_stored_rank`, `:1001-1010`); (3) 한국 봉 — 한 종목 쪽은 한 종목짜리 `_krx_bars` 재구성.
- 실행(`parity.txt`): 오늘 서버의 한 종목 평가와 아침 스캔의 원장 기록(세션 2026-11-25) 비교.
  - MSFT: 스윙 57.6865 = 57.6865, 장기 74.3930 = 74.3930. 요인 20개 중 1개가 소수 8번째 자리에서 다름.
  - JPM: 스윙 46.9640 = 46.9640, 장기 64.3364 = 64.3364.
  - 005930: 스윙 57.6505 대 57.6520(차이 0.0015점: `momentum`, `breakout_volume`, `risk_reward`가 4~5번째 자리에서 다름 — 봉을 얻는 길이 달라서다). 장기 64.3474 = 64.3474. `usdkrw_regime`은 0.962 → 0.927로 달랐다(기록 뒤 환율 값이 갱신됨; 참고 도메인이라 점수에 들지 않는다).
  - 구간은 여섯 장 모두 같았다. 순위 근거는 셋 다 `UNIVERSE`(스캔의 숫자를 읽음).
- 테스트 근거: `tests/test_qsf_stored_rank.py`가 스캔 전후·다른 세션·깨진 파일·유니버스 밖 종목의 경우를 본다(오늘 24 passed).
- 남는 한계: 한국에서 같은 세션의 같은 종목이 0.001점대로 다를 수 있고, 시장 상태 참고값은 하루 안에서 움직인다. 구간 경계(70, 67)에 걸친 종목에서는 화면과 기록이 다른 말을 할 여지가 이론상 있다. 표본 3종목으로는 빈도를 말할 수 없다.

### Q5. 테스트는 증거로서 얼마나 좋은가. 일일 실행의 조용한 실패는 어떻게 드러나나

**테스트. 분류: PARTIALLY VERIFIED(정적 집계 + 파일 1개 실행; 전체 실행은 총괄의 2,364 passed를 따름).**
- 테스트 파일 179개, 테스트 함수 2,148개(매개변수 전개 전), 31,383줄. 실전 코드 약 53,000줄과 비슷한 부피다.
- 소스 글자를 읽는 테스트 함수(`.py/.js/.html`을 `read_text`·`getsource`·`ast`로 읽음)는 187개, 8.7%다. 68개 파일에 걸쳐 있고, 절반 이상이 그런 파일은 15개인데 대부분 화면 묶음이다(`test_ui_batch_1~5.py`가 59/61). 즉 **화면(JS 6,204줄)은 실행 테스트가 사실상 없다.** 글자가 있다는 것만 본다. 브라우저에서 깨져도 통과한다.
- 나머지 약 91%는 가짜 공급처를 주입해 실제 함수를 돌리는 동작 테스트다. 네트워크는 소켓 단계에서 막고(`tests/conftest.py:289-295`), 사용자 자격 증명을 지우고, 보호 파일이 바뀌면 실패시키는 감시가 있다(`conftest.py:237-262`). HTTP 서버를 실제로 띄우는 파일은 9개다.
- 증거로서의 한계: (1) 작성자와 테스트 작성자가 같고, 테스트 이름 다수가 "그날 고친 것"의 회귀 고정이다(`test_audit_fixes_2026_11_22.py` 등). 넓이는 사건 목록을 따라간다. (2) 실제 공급처 응답 모양이 바뀌는 경우를 잡는 계약 테스트가 없다. 가짜는 작성자가 생각한 모양이다. (3) 커버리지 측정이 없다(도구 미설치). 줄 커버리지 숫자는 UNVERIFIED. (4) 통과 = 코드가 의도대로 돈다. 투자 타당성의 증거는 아니다.

**조용한 실패. 분류: PARTIALLY VERIFIED(코드, 상태 파일).**
드러나는 길:
- 종목 단위 오류는 스캔을 멈추지 않고 `errors`(종류)와 `data/qsf/logs/scan_errors.log`(파일:줄)에 남는다(`service.py:1061-1063`, `:1310-1326`).
- 부분 자료의 날은 기록하지 않는다: 세션 도달 비율, 내려받기 실패, 지수, 한국 유니버스 크기, 재무 비율 80%(`service.py:1032-1042`, `:1068-1072`). 종료 코드 3/4/5/7이 단계 상태로 번역된다(`automation.py:297-304`).
- 단계 상태는 `state.json`에 남고 하루 요약이 텔레그램과 macOS 알림으로 나간다. 실패가 있으면 요약에 적힌다(`automation.py:905-925`). `LAB`은 종료 코드 0이어도 그날 기록이 실제로 있는지 다시 본다(`:286-288`).
- 옆 기록이 멈춘 것은 `terminal/store_watch.py`가 원인이 아니라 결과(다른 기록보다 3세션 뒤처짐)로 잡는다. 작성자가 이 문제를 알고 만든 장치다(`store_watch.py:1-9`).
구멍:
- **맥 밖의 감시가 없다.** 맥이 꺼져 있거나 launchd 등록이 풀리면 실패 알림 자체가 오지 않는다. "알림이 안 온 것"을 사용자가 알아차려야 한다. 전문가급에서는 결격이다.
- 옆 기록은 단계 실패로 올라오지 않도록 감싸 놓았다. 멈춤은 3세션 뒤에야 보인다(`store_watch.py:19`).
- 넓은 예외 250개 중 54개가 아무 흔적 없이 넘긴다(`metrics.txt`). 예: `service.py:913-927`(`_rank_in_scan`의 `except Exception: pass` — 표시용), `service.py:813-819`(거래 고정: 실패 시 "확인 못 함" 표시로 바뀜, 이건 흔적이 있다).
- `missing_sessions`는 도전자(Lab) 원장만 본다(`automation.py:654-660`). QSF 원장의 빠진 세션은 화면의 `record_status`(2세션 뒤처지면 경고, `record_status.py:16`)에 맡겨져 있다.

## 3. 확인된 강점

1. **점수 계산의 길이 하나다.** 실행으로 확인했다(Q4). VERIFIED.
2. **원장이 직업적으로 만들어졌다.** 추가만 가능, 해시 사슬, fsync 순서, 잠금, 무효 표시, 같은 세션 재기록 방지(`ledger.py:264-293`). 조각 파싱 0.06~0.10초, 검증 0.03초. VERIFIED.
3. **모르는 것을 지어내지 않는 규칙이 코드 전반에 일관된다.** 캐시 STALE, 빈 응답 미저장, NaN → null(`server.py:420-428`), 부분 자료의 날 미기록. VERIFIED.
4. **공급처 주입과 시계 주입**(`src=`, `now=`)으로 테스트가 실제 함수를 네트워크 없이 돌린다. VERIFIED.
5. **쓰기와 읽기의 프로세스 분리.** 스캔은 CLI 프로세스, 서버는 읽기. 프로세스 사이는 파일 잠금 10여 곳과 원자적 교체로 맞춘다. VERIFIED(grep).
6. **로컬 서버의 보안 위생**이 개인 도구치고 높다(Host·Origin·Sec-Fetch-Site 검사, 본문 크기 제한, 로그 비밀값 가림 `server.py:44-53`). VERIFIED(코드; 침투 시험은 안 함).
7. **의존성이 적고 고정돼 있다**(실전 길은 numpy, pandas, yfinance, requests, bs4, psutil; 버전 고정). VERIFIED.

## 4. 약점과 빠진 것

| # | 약점 | 근거(file:line) | 심각도 | 투자 출력 영향 |
|---|---|---|---|---|
| W1 | 실행·알림·백업·감시가 모두 잠드는 노트북 한 대에 있다. 외부 감시 없음 | `terminal/automation.py:27-30`(launchd), `state.json` 16세션 중 `NEWS_KR` 실패 8 | 높음 | 있음(기록이 늦거나 빠지면 전향 표본이 준다) |
| W2 | CI·린터·타입 검사·코드 검토가 없다. 23일 375커밋 | 저장소 루트, `requirements-dev.txt` | 높음(전문가급 기준) | 간접 |
| W3 | 미국 가격이 비공식 공급처 하나, 대체 없음. 공급처 인터페이스 없음(이름으로 18곳 호출, 직접 import 32개 파일) | `terminal/sources.py:109-138`, `spread.txt` | 높음 | 있음(공급처가 막히면 그날 기록 없음; 조용히 틀리지는 않도록 막아 둠) |
| W4 | 원장의 비공개 함수(`_live_rows`, `_load`, `_rows`)를 원장 밖 24개 파일이 직접 부른다(grep). "한 세션 읽기" 함수가 12벌 복사돼 있다. `Ledger(` 생성 23개 모듈 | `terminal/qsf/order_plan.py:115`, `forecast.py:341`, `fund_period.py:136`, `paper_book.py:237`, `rank_notes.py:64`, `score_split.py:62`, `regime_weights.py:309`, `kr_challenger.py:75`, `us_challenger.py:85`, `kr_swing_prior.py:59`, `kr_swing_challenger.py:57`, `assistant.py:746` | 중간 | 간접(조각 형식을 바꾸면 12곳이 따로 깨진다) |
| W5 | 시장 이분법: `"US"/"KR"` 분기 154곳·36파일(+JS 약 50곳). 세 번째 시장은 재구조화 | `terminal/qsf/service.py`(26), `terminal/services.py`(20), `terminal/qsf/views.py`(19), `terminal/assistant.py`(15) | 중간 | 없음(지금 범위에서는) |
| W6 | 설정이 흩어져 있다. `terminal/` 안 `config.py` 밖 모듈 수준 대문자 상수 1,021개·134파일, `os.getenv` 62곳·12파일 이상, TTL 표 4곳 이상. 구간 문턱 55/40/70이 `config.BANDS`와 따로 코드에 박혀 있다 | `terminal/qsf/engine.py:46-47`, `terminal/qsf/ledger.py:457`, `terminal/qsf/kr_cap_view.py:37`, `terminal/services.py:17`, `terminal/qsf/service.py:35-43`, `terminal/analyst_extra.py:22` | 중간 | 간접(문턱을 한 곳만 바꾸면 말이 갈린다; 지금은 동결) |
| W7 | 거대 모듈·함수. `assistant.py` 2,094줄(`stock_answer` 206줄, `briefing` 179, `analyst_note` 179, `plain_answer` 162), `fundamentals.metrics` 195줄, `server.make_handler` 157줄, `paper_book.step` 139줄. 60줄 넘는 함수 67개, 120자 넘는 줄 5,237개 | `terminal/assistant.py:1496`, `:445`, `:1122`, `:1704`; `terminal/qsf/fundamentals.py:276`; `terminal/server.py:252`; `terminal/qsf/paper_book.py:95` | 중간 | 간접(`metrics`는 재무 입력의 한가운데다) |
| W8 | API 96개(GET 74, POST 22)가 람다 사전 하나에 있다. 응답 스키마·버전·문서가 없다. 화면과 서버의 계약은 암묵적이고, 화면은 실행 테스트가 없다 | `terminal/server.py:145-250`; `tests/test_ui_batch_*.py` | 중간 | 간접(필드 이름이 바뀌면 화면이 조용히 빈칸이 된다) |
| W9 | 넓은 예외 250개(실전 `terminal/` 약 150개), 그중 54개가 흔적 없이 넘김 | `terminal/assistant.py`(26/9), `terminal/qsf/service.py`(23/9), `terminal/qsf/views.py`(8/5), `terminal/today.py`(5/3) | 낮음~중간 | 간접(표시 누락이 "없음"으로 읽힐 수 있다) |
| W10 | 옛 모델(P6-11B)이 매일 같이 돈다: `core/` 4,302줄, `pipeline/` 2,776줄, `main.py`(`run_live_cycle` 484줄), `data/loader.py` 893줄. `data/`가 파이썬 패키지이면서 자료 폴더다 | `main.py:95`, `terminal/automation.py:289-296`, `data/__init__.py` | 낮음~중간 | 없음(점수에 안 섞임, `service.py:950-957`) |
| W11 | 규모의 천장. 캐시 폴더 하나에 파일 15,112개·643MB, 미국 세션 조각 하나가 JSON 10MB. 원장 전체를 도는 읽기(`stability.py:25-29`, `views.py:498`, `price_archive.py:65`)는 세션 수에 비례한다(1년 뒤 시장당 약 25초). 일일 실행은 순차 단일 프로세스(한국 스캔 26분) | `shard_cost.txt`, `terminal/qsf/stability.py:20-31` | 낮음(지금), 중간(1~2년 뒤) | 없음 |
| W12 | 작은 것: 위원회 `_MEMO`가 잠금 없는 전역 사전이고 8개를 넘으면 통째로 비운다 | `terminal/committee/service.py:16`, `:121-132` | 낮음 | 없음 |

불필요한 복잡성으로 보는 것: 비교 기록·도전자·읽기 모듈이 20개가 넘고 각자 자기 기록 폴더·잠금·세션 읽기 함수를 갖는다. 하나하나는 작지만 합치면 `terminal/qsf/`가 22,656줄(88개 파일)이고 그중 실전 점수 길은 7개 모듈(config, engine, factors, fundamentals, technicals, service, holding) 3,491줄이다. 점수 길 대 주변의 비가 약 1:5.5다.

## 5. 이전 평가(2026-11-25, 63~65%, 개인 도구 잣대)의 항목과 그 뒤

| 이전 항목 | 오늘 | 근거 |
|---|---|---|
| 같은 버전 번호 안에서 구간 규칙이 바뀜 | FIXED(동작). 규칙 버전이 따로 생겼고 기록 줄에 `rules_version` 칸이 들어간다 | `terminal/qsf/config.py:22`, `engine.py:284`; 11-25 조각의 키 목록(`pick.py` 출력) |
| 버전이 자주 바뀜(14세션 8개) | CHANGED. 동결을 선언했고 1.6.0으로 한 세션 기록됨. 동결이 지켜지는지는 시간이 보여 준다. 코드 변경 속도는 그대로다(11-25 하루 17커밋) | `config.py:25`, `git log` |
| 거래 고정의 조용한 꺼짐(D1/D2) | FIXED(동작): SEC 목록이 없으면 `deal_unchecked`를 세운다. 화면 문구까지는 보지 않았다 | `terminal/qsf/service.py:813-819` |
| DART 목록, 같은 날 저녁에는 캐시가 안 됨 | STILL OPEN. 논리 그대로 | `service.py:696-700` |
| 원장 읽기·구간 문턱·설정값 중복 | STILL OPEN. 오늘 숫자로 셌다(12벌, 3곳, 1,021개) | W4, W6 |
| 린터 없음, 소스 글자 테스트 | STILL OPEN. 내 집계는 테스트 함수 187개(8.7%); 이전 "309곳"은 세는 단위가 달랐을 것이다 | `tests_kind.txt` |
| 넓은 예외 184개 | STILL OPEN. 내 집계 250개는 `core/`·`pipeline/`을 포함한 범위다 | `metrics.txt` |
| 위원회 `_MEMO` 잠금 없음 | STILL OPEN | `committee/service.py:16` |
| `log_message`의 `self.path` | STILL OPEN(줄이 그대로다; 오류 재현은 하지 않았다) | `server.py:263-264` |
| A5 한국 카드가 세션 하루 늦을 수 있음 | 다시 보지 않았다 | — |
| 공시 목록의 세 경로 | 다시 보지 않았다 | — |

새로 본 것(이전 문서에 없던 관점): 시장 이분법의 크기(W5), 공급처 인터페이스 부재의 크기(W3), 화면 실행 테스트 부재(W8), 점수 길 대 주변 코드의 비 약 1:5.5, 한국 한 종목 평가와 스캔 기록의 0.0015점 차이를 오늘 세션에서 다시 확인.

이전 문서와 다른 점: 이전 평가는 "65%, 성숙 구간 아래쪽"이었다. 그 숫자는 개인 도구 잣대에서는 지금도 맞다고 본다. 전문가급 잣대에서는 맞지 않는다(6절).

## 6. 제안 점수

**소프트웨어 구조와 백엔드 엔지니어링: 46% (기능 구간, 41~60%의 아래쪽). 근거 신뢰도: MEDIUM.**

- 전문가급 제품이 요구하는 것 가운데 갖춘 것: 한 길의 점수 계산, 변조를 알아차리는 기록, 정직한 실패 처리, 넓은 동작 테스트. 이것들은 실제로 돌고 오늘 확인했다.
- 갖추지 못한 것: 독립 실행 환경과 이중화, 호스트 밖 감시, CI와 정적 검사, 두 번째 사람의 검토, 공급처 추상화와 대체 경로, 저장 스키마와 이행, API 계약, 화면 실행 테스트, 운영 지표. 이것들은 "있으면 좋은 것"이 아니라 전문가급의 기본이다. 절반 이상이 비어 있으므로 61%를 넘길 수 없다.
- 40% 아래로 내리지 않은 이유: 비어 있는 것 대부분이 "혼자, 무료, 맥 한 대"라는 조건의 결과이지 솜씨의 결함이 아니고, 조건 안에서 할 수 있는 것(원자적 쓰기, 미기록 관문, 테스트 격리)은 평균적인 전문 팀보다 꼼꼼한 곳도 있다.
- 신뢰도 MEDIUM: 점수 길·원장·캐시·서버·일일 실행은 끝까지 읽고 일부를 실행했다. 화면 JS, `assistant.py` 본문, 위원회 엔진, 연구 모듈, 옛 모델은 크기와 구조만 쟀다.

**한 사람의 도구 잣대라면: 64%**(이전 63~65%와 같은 자리. 규칙 버전 분리와 거래 고정 표시는 나아졌고, 중복·부피·속도는 그대로다).

## 7. 확인하지 못한 것

- 전체 테스트 실행 결과(총괄의 2,364 passed를 따름). 줄 커버리지(도구 없음) — UNVERIFIED.
- 화면 JS의 실제 동작(브라우저를 쓰지 않았다), 폰 문, 1분봉 차트.
- 공급처가 실제로 막혔을 때의 동작(가짜로만 시험돼 있다).
- 서버의 동시 요청 부하에서의 경쟁 조건(코드로만 봤다. 부하를 걸지 않았다).
- 백업의 복원(복원 연습을 하지 않았다. 백업이 같은 디스크인지도 다시 보지 않았다).
- 한국 0.0015점 차이가 구간 경계에서 실제로 말을 바꾼 사례가 있는지(표본 3종목).
- A5, 공시 세 경로, `log_message` 오류의 재현.
- `core/`·`pipeline/`의 품질(범위 밖, 크기만 쟀다).

## 8. 전문가급까지의 거리

**소유자의 조건 안에서 닿을 수 있는 것**(무료 자료, 맥 한 대, 주문 없음):
- 커밋 전 자동 검사: 린터(정의 안 된 이름·안 쓰는 이름) + 빠른 테스트 묶음을 git 훅으로. 비용 0.
- 원장 읽기를 `Ledger`의 공개 함수 하나로 모으기(12벌 → 1). 동작 불변, AST로 확인 가능.
- 공급처 얇은 인터페이스: `prices.history(symbols, period)` 한 겹을 두고 야후 구현을 그 뒤로. 대체원을 실제로 붙이지 않더라도 끼울 자리가 생긴다.
- API 응답의 모양 고정: 핵심 10개 응답(카드, 스캔 요약, 건강, 기록 상태)에 대해 키 목록을 테스트로 고정하고, 화면 JS가 읽는 키와 대조하는 테스트.
- 화면 실행 테스트 소량: 가짜 응답을 넣고 헤드리스로 핵심 화면 3~4개가 예외 없이 그려지는지.
- 호스트 밖 감시의 무료 대용: 하루 요약이 정해진 시각까지 오지 않으면 알리는 장치는 맥 밖에 있어야 한다. 무료 외부 일정 서비스는 "서버 없음" 조건과 부딪히므로 소유자 결정 사항이다. 조건 안의 차선은 폰 쪽 고정 알람("08:30까지 요약이 안 왔으면 맥을 연다")이다.
- 설정 한 곳: TTL과 구간 문턱만이라도 `config`에서 읽게.
- 큰 함수 넷(`stock_answer`, `metrics`, `briefing`, `analyst_note`)의 분해. 테스트가 소스 글자를 고정하고 있어 그대로 옮기는 방식이어야 한다.

**소유자가 배제한 것이 있어야 닿는 것**(유료 자료, 서버, 사람):
- 잠들지 않는 실행 환경과 이중화, 호스트 밖 모니터링·호출 체계.
- 계약과 SLA가 있는 가격·재무 공급처, 그리고 두 번째 공급처와의 교차 검증.
- 두 번째 사람의 코드 검토, 변경 승인 절차, 릴리스 단계(스테이징 → 실전).
- 관계형 저장소와 스키마 이행, 다중 사용자·권한·감사 로그.
- 화면의 구성요소화와 빌드·테스트 사슬.
이 묶음이 46%와 전문가급(80% 이상) 사이 거리의 대부분이다. 작은 걸음이 아니다.

## 9. 개선 우선순위

**P0** (기록의 연속성을 지킨다 — 이 제품의 유일한 증거가 전향 기록이므로)
- 맥이 꺼졌을 때 "알림이 안 옴"을 알아차릴 방법을 하나 정한다(위의 차선 포함). 결정은 소유자 몫.
- 백업 복원을 한 번 실제로 해 본다(다른 폴더에 풀고 `qsf verify`).

**P1**
- git 훅: 린터 + 10분 안쪽의 핵심 테스트 묶음. 동결 기간의 하루 15커밋을 받치는 최소 장치다.
- `Ledger` 공개 읽기 함수(`session(market, session)`, `sessions(market)`)를 만들고 12벌을 그것으로 바꾼다.
- 핵심 API 응답의 키 고정 테스트 + 화면이 읽는 키와의 대조.

**P2**
- 가격 공급처 한 겹(인터페이스) 도입. 연구 모듈의 직접 `requests`/`yfinance` import를 그 뒤로.
- 구간 문턱과 TTL을 `config` 한 곳에서 읽게(`engine.py:46-47`, `ledger.py:457`, `kr_cap_view.py:37`).
- 흔적 없는 넓은 예외 54곳 중 `terminal/qsf/service.py`·`views.py`의 14곳에 종류 한 줄 기록.
- 한국 한 종목 평가가 같은 세션의 스캔 봉을 읽게 해 0.001점대 차이를 없앤다(순위는 이미 그렇게 한다).

**P3**
- 큰 함수 분해, `data/` 패키지와 자료 폴더 분리, 옛 모델의 일일 단계 유지 여부 결정, 위원회 `_MEMO` 잠금, DART 같은 날 저녁 TTL, 캐시 폴더 분할.
