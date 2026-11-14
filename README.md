# 퀀트 종목 추천 (개인용, 무료 데이터, 고정 모델 P6-11B)

개인 투자자를 위한 로컬 프로그램입니다. 고정된 계량 모델로 현재 미국 대형주의 순위를 매기고, 어떤 후보가 통과했고
나머지는 왜 떨어졌는지를 그대로 보여 줍니다. 공개 데이터만 씁니다(`yfinance`를 통한 Yahoo Finance, SEC EDGAR, Wikipedia).
**주문은 보내지 않으며**, 투자 자문이 아닙니다.

두 가지 방식이 **하나의** 공통 파이프라인(`pipeline/canonical.py`)을 함께 씁니다.

| 방식 | 명령 | 하는 일 |
|---|---|---|
| A. 시장 전체 자동 스캔 | `python app.py scan --capital 50000` | 현재 S&P 500 → 데이터 → 관문 → 고정 채점 → MODEL_RANK_E → 포트폴리오 관문 → 상위 5종목 / 관심 목록 |
| B. 종목 직접 평가 | `python app.py evaluate NVDA AAPL --capital 50000` | 입력한 종목을 같은 S&P 500 단면 안에서 같은 규칙으로 채점하고, 종목별 판정과 포트폴리오 수준 상태를 함께 보고 |

**여러 시장 (P6-21..25).** 완전히 독립된 두 번째 엔진이 **한국**(KOSPI + KOSDAQ 거래대금 상위 300, 원화)을 다룹니다.
데이터, 대상 종목, 모델(`KR-EXP-0.1`, 상태 **EXPERIMENTAL**), 모의 추적을 따로 가집니다. 미국 엔진과는 기반 코드만 함께 쓰고
모델 가정은 함께 쓰지 않습니다. 5절의 "한국" 항목과 `reports/P6-21_ARCHITECTURE.md`를 보세요. 미국 엔진은 바뀌지 않았고,
기존 명령은 모두 기본값이 `--market US`입니다.

> **REAL RECOMMENDATION의 뜻:** 데이터와 판단의 모든 관문을 통과했다는 뜻입니다. 종목이 오른다는 뜻도, 순위가 수익을
> 예측한다는 뜻도, 전략이 돈을 번다는 뜻도 **아닙니다**. 예측력은 입증되지 않았습니다. 그 뒤에 실제로 어떻게 됐는지는
> `python app.py track`이 기록합니다.

---

## 1. 프로젝트 위치

프로젝트는 **`~/Developer/quant-stock-engine`**에 있습니다. P6-19에서 `~/Desktop/퀀트 예측 프로그램`에서 옮겼습니다.
디스크가 거의 찬 상태에서 iCloud "데스크탑 및 문서" 동기화가 소스 파일을 클라우드로만 남겨 두었고(590개, 그중 `.py` 202개),
macOS가 그 파일을 다시 받는 동안 Python이 멈췄기 때문입니다. `~/Developer`는 iCloud가 동기화하지 않습니다.

원래 데스크탑 폴더는 **바꾸거나 지우지 않았습니다**. 새 위치를 확인한 뒤에 직접 보관하거나 지우면 됩니다(7절).
`app.py doctor`는 프로젝트가 iCloud 동기화 폴더에서 실행되면 경고합니다.

## 2. 설치 (macOS Apple Silicon)

Python 3.10 이상(python.org **Python 3.14.2**에서 확인)과 인터넷 연결이 필요합니다.

```bash
cd ~/Developer/quant-stock-engine
```

```bash
python3 -m venv .venv
```

```bash
.venv/bin/python -m pip install -r requirements.txt
```

시험을 돌리려면 추가로:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
```

## 3. 설정 (`.env`)

견본을 복사해서 채웁니다. `.env`는 git이 무시하는 파일이며, 절대 커밋하지 마세요.

```bash
cp .env.example .env
```

| 변수 | 필수 여부 | 용도 |
|---|---|---|
| `SEC_USER_AGENT` | SEC 자료에 **필수** | SEC의 공정 접근 정책은 자동 접속에 신원 표시를 요구합니다: `"<앱이름>/<버전> <실제 이메일>"`, 예: `QuantStockEngine/1.0 you@yourmail.com`. 예시 도메인(`example.com` 등)은 거부됩니다. 설정하지 않으면 SEC에 **아예 접속하지 않고**, ROE와 이익률은 Yahoo에서만 가져오며 모든 보고서에 그렇게 적힙니다. 이 값은 화면에 찍히거나 결과 파일에 쓰이지 않습니다. |
| `QPP_CAPITAL` | `--capital`을 주지 않으면 필수 | 포지션 크기 계산에 쓰는 투자 자본(달러). **기본값이 없습니다.** |
| `NEWS_API_KEY` | 아니요 | 예전 NewsAPI 연동용. 추천 파이프라인은 쓰지 않습니다. |
| `QPP_LOG_LEVEL` | 아니요 | `WARNING`(기본) 또는 `INFO` |
| `QPP_FINANCIAL_WORKERS` | 아니요 | 재무 자료를 동시에 받는 개수(기본 4. SEC는 초당 8회, Yahoo는 초당 약 3회로 속도 제한) |
| `QPP_PROVIDER_TESTS` | 아니요 | `1`이면 실제 데이터 제공처에 접속하는 시험을 켭니다 |
| `QPP_CAPITAL_KRW` | 한국용, `--capital`을 주지 않으면 필수 | 한국 자본(**원화**). 달러 `QPP_CAPITAL`은 한국에 절대 쓰이지 않습니다. |
| `OPENDART_API_KEY` | 아니요 (한국 재무) | <https://opendart.fss.or.kr/>에서 무료 발급(인증키 신청). 없으면 한국 엔진은 가격만으로 돌고 DART를 UNAVAILABLE로 표시합니다. |
| `KRX_API_KEY` | 아니요 (한국 공식 시세) | <https://openapi.krx.co.kr/>에서 무료 발급(가입 후 유가증권/코스닥 일별매매정보 서비스 신청). 없으면 한국 시세는 Yahoo(보조)에서 받고, 거래대금은 종가 × 거래량 추정치로 표시합니다. 지수 서비스는 별도 신청이라 지금 키로는 조회되지 않습니다(2026-11-14 확인). |
| `ECOS_API_KEY` | 아니요 (한국 거시) | 한국은행 ECOS 키. 4절 아래 "터미널의 한국 시장"을 보세요. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | 아니요 | 일일 작업 요약을 텔레그램으로 받을 때 |

셸에 이미 설정된 변수(예: `~/.zprofile`)가 `.env`보다 우선합니다.

### 자본금

자본금은 매번 명시해야 하며, 다음 중 하나로 줍니다.

* 명령줄의 `--capital 50000` (가장 우선)
* 터미널 모델 탭의 자본금 입력칸(`.env`에 `QPP_CAPITAL` 또는 `QPP_CAPITAL_KRW`로 저장)
* `.env`의 `QPP_CAPITAL=50000`
* 대화형 메뉴가 물어볼 때 입력

자본금이 없거나 0, 음수, 숫자가 아니면 데이터를 받기 *전에* 멈춥니다(종료 코드 2). 쓰인 자본금과 그 출처는 화면에 찍히고
`validation_result.json`에 저장됩니다. 고정 한도(종목당 20%, 절대 상한 30%, 기술 업종 40%)는 그대로입니다.

## 4. 실행

환경 점검(`--network`를 붙이면 데이터 제공처 접속도 확인):

```bash
.venv/bin/python app.py doctor --network
```

대화형 메뉴:

```bash
.venv/bin/python app.py
```

| 명령 | 용도 |
|---|---|
| `app.py scan --capital 50000 [--limit 25] [--open]` | 방식 A. `--limit`은 범위를 줄인 점검 스캔(`bounded`로 표시) |
| `app.py evaluate 종목… --capital 50000 [--open]` | 방식 B |
| `app.py status [RUN_ID]` | 최근 실행 또는 지정한 실행 보기 |
| `app.py tracking status` | 사전 기록 장부 내용, 집단, 최근 결과 갱신 |
| `app.py tracking update` | 완성된 일봉을 받아 모의 결과를 다시 계산하고 보고서 작성(다시 돌려도 안전) |
| `app.py tracking report [--open]` | `tracking/reports/latest.md` / `latest.html` 작성 |
| `app.py tracking verify` | 해시 사슬, 실행 결과 파일 무결성, 재구성, 재현 점검 |
| `app.py tracking exclusions [--add RUN_ID --category PRE_FIX\|DATA_INVALID --reason "…"]` | 제외 목록 보기 또는 추가(지우지 않음) |
| `app.py tracking replay [UPDATE_ID]` | 저장된 시세 스냅샷으로 갱신 하나를 다시 계산(오프라인) |
| `app.py track` | `tracking update` + `tracking report`를 한 번에 |
| `app.py doctor [--network]` | 환경, 설정, 위치, 디스크, 데이터 제공처 점검 |

**VSCode:** `~/Developer/quant-stock-engine`을 열고 인터프리터로 `./.venv/bin/python`을 고른 뒤 **Run and Debug**를 씁니다
("App: …"은 자본금을 묻고, "Tests: full suite"는 전체 시험).

각 명령은 앞에서 한 번 돌고 끝납니다. 뒤에 남는 프로세스는 없습니다. Ctrl+C로 멈추면 진단 기록이 `INTERRUPTED`로 남습니다.

## 5. 사용 안내

### 시장 전체 자동 스캔

```bash
.venv/bin/python app.py scan --capital 50000 --open
```

* 캐시가 없는 첫 전체 스캔은 약 500종목의 재무 자료를 받아 몇 분 걸립니다. 재무 자료는 20시간 캐시되므로(`CACHED`로 표시)
  같은 날 다음 실행은 빠릅니다.
* REAL RECOMMENDATION으로 끝난 전체 스캔은 모두 변경 불가 사전 기록 장부 `tracking/ledger/observations.jsonl`(P6-20)에
  기록됩니다. 기록은 그 실행 자체의 결과 파일로 만든 상위 5종목과 관심 목록입니다. 범위를 줄인 스캔과 종목 직접 평가는
  기록하지 않습니다.

### 사전 모의 추적 (P6-20)

권장 순서: 거래일 **미국 동부 09:30 전**(겨울 한국 시각 23:30, 미국 서머타임 중 22:30)에 전체 스캔을 돌리면 모의 진입이 그날
시가가 됩니다. **미국 동부 17:00 뒤**(겨울에는 다음 날 아침 07:00, 여름에는 06:00)에 다음을 돌립니다.

```bash
.venv/bin/python app.py tracking update
```

```bash
.venv/bin/python app.py tracking report --open
```

* 모의 진입은 추천 시각 *뒤의* 첫 정규장 시가입니다. 장 전 추천은 그날 시가, 정규장·장 마감 후·주말 추천은 다음 거래일
  시가입니다. 추천 전의 종가는 절대 쓰지 않습니다.
* 각 종목은 고정 엔진을 그대로 써서 고정 규칙(손절, EMA20, ATR 추적 손절, 2차 진입, 30일 재검토)을 따릅니다. 신호는 다음 시가에
  체결합니다. 기간은 청산이나 고정된 30일 재검토에서 끝납니다.
* SPY도 같은 기간으로 잽니다. 비용 시나리오는 가정입니다. 연율 환산과 유의성 주장은 하지 않습니다. 완료된 관측이 30건이
  될 때까지 결과는 `INSUFFICIENT_SAMPLE`입니다.
* **이것은 원래 추천을 따른 모의 결과이며, 실제 수익이 아닙니다.** 나중에 잘못된 것으로 밝혀진 실행은 기록을 고치거나 지우지
  않고, 제외 사건을 덧붙여서 뺍니다.
* 전체 방법: `reports/P6-20_TRACKING_SPECIFICATION.md`.

### 종목 직접 평가

```bash
.venv/bin/python app.py evaluate NVDA AAPL TSLA PLTR --capital 50000 --open
```

* 고정 모델은 *단면*으로 순위를 매기므로, 입력한 종목은 현재 S&P 500 구성 종목과 함께 채점됩니다(같은 규약, 관문, 가중치,
  MODEL_RANK_E). S&P 500 밖의 종목도 빼지 않고 `in_sp500: false`로 표시합니다.
* 종목마다 **개별 평가**(알파, 백분위, 요인 z점수, MODEL_RANK_E 순위, ADV20, 데이터 상태)가 나옵니다. 포트폴리오 전체가 유효한
  추천이 될 수 없어도 종목 하나는 평가됩니다. 포트폴리오 수준 상태는 따로 보고합니다.
* 판정: `TOP5`, `WATCHLIST`, `RANKED_NOT_SELECTED`, `BEAR_REJECTED`, `QUARANTINED`(PER 없음, `LIQUIDITY_REJECTED`,
  `NON_EQUITY_INSTRUMENT_ETF`, `SYMBOL_NOT_FOUND_OR_NO_PROVIDER_DATA` 같은 이유와 함께), `NOT_EVALUATED`(종목 기호 형식 오류).

### 결과 읽는 법

| 결과 | 뜻 |
|---|---|
| **REAL RECOMMENDATION** | 포트폴리오에 넣을 수 있는 다섯 종목이 모든 관문(데이터, 신선도, 출처, 유동성, 고정 채점, 약세 필터, 업종 한도, 크기 계산)을 통과했습니다. |
| **DATA-INCOMPLETE / NO VALID RECOMMENDATION** | 파이프라인은 돌았지만 남은 종목이 다섯 개보다 적습니다. 추천하지 않으며, 이유를 보여 줍니다. |
| **LIVE DATA UNAVAILABLE** | 대상 종목이나 시세를 받지 못했습니다. 아무것도 채점하지 않습니다. |

선택된 종목마다 보고서에 나오는 것: 종목 기호와 이름, MODEL_RANK_E 순위와 점수, 알파와 단면 백분위, 요인 z점수, 업종,
ADV20과 유동성 상태, 가격·거래량·재무 상태와 마지막 일봉 날짜, 목표 비중, 주식 수, 2×ATR 손절선, 고정 진입·청산 규칙.
제외된 후보는 이유와 함께 나옵니다. 기술 업종이 아닌 업종이 40%를 넘으면 안내가 붙습니다. 고정 엔진은 "Technology"만
제한하므로 이 경우는 알리기만 하고 막지 않습니다.

### 한국 (P6-21..25, EXPERIMENTAL)

```bash
python app.py --market KR scan --capital 10000000      # 거래대금 상위 300 스캔, 상위 10종목 (원화)
python app.py --market KR scan --capital 10000000 --limit 60   # 범위를 줄인 점검 (추적하지 않음)
python app.py --market KR evaluate 005930 035720       # 상위 300 기준으로 직접 평가
python app.py --market KR tracking update               # 한국 모의 결과 (원화, ^KS11/^KQ11)
python app.py --market KR tracking verify
python app.py --market KR tracking exclusions          # 같은 거래일을 두 번 스캔한 실행 보기; --add RUN_ID로 집계에서만 제외(지우지 않음)
python app.py dashboard --open                          # 미국과 한국을 나란히 (읽기 전용)
```

* **대상 종목:**
  * KRX KIND 목록의 코스피 + 코스닥 보통주. 스팩, 리츠, 펀드, 외국 기업은 이유를 적고 뺍니다.
  * 20거래일 평균 거래대금 상위 300종목.
* **모델 `KR-EXP-0.1`:** 사전 등록한 연구(`reports/KR_MODEL_RESEARCH_SPECIFICATION.md`)가 정한 대로 가격 요인만 씁니다.
  * 극단값을 자른 z점수, 같은 가중치
  * 상위 10종목 같은 비중, KRX 업종당 최대 3종목, 정수 주식 수
  * 보유 기간 20거래일. 상태는 **EXPERIMENTAL**로, 검증되지 않았고 모의 관찰용입니다.
* **추적:**
  * `tracking/kr/`, 원화만, 집단 `EXPERIMENTAL_PROSPECTIVE`
  * 미국 관측과 절대 합치지 않습니다.
  * 비교 지수(코스피 ^KS11, 코스닥 ^KQ11)의 일봉은 시가와 종가가 모두 있을 때만 씁니다. 아침에는 Yahoo의 마지막 지수 일봉이
    시가만 있고 종가가 빈 채로 오기도 해서(2026-11-14 09:01 확인), 그런 날은 아직 거래일로 치지 않고 종가가 올라온 다음
    갱신에서 따라잡습니다. 보류한 날짜는 갱신 결과와 보고서에 적힙니다.
* 한국 전체 스캔은 하루 첫 실행에 Yahoo에서 약 2,500종목을 받습니다(느린 회선에서 40분 정도). 같은 날 다음 실행은
  `data/kr/cache/`를 다시 씁니다.
* **일일 작업 편입(2026-11-12, 사용자 결정):** 한국 모델 스캔은 아침 실행의 마지막 단계(백업 바로 앞)로 돌아, 다운로드가 아침
  기록을 늦추지 않습니다.
  * 저녁이 아니라 아침인 이유: Yahoo는 그날의 한국 일봉을 다음 날 아침까지 일부 종목만 냅니다(2026-11-14 00:08 측정: 대상
    전 종목의 그날 일봉이 비어 있었음).
  * 아침에는 반대로 Yahoo 코스피 지수가 종목보다 하루 늦습니다. 그래서 스캔의 거래일 달력은 점수 스캔처럼 대형주
    (005930.KS)의 일봉도 함께 봅니다. 이것이 없던 2026-11-13 아침 스캔은 마지막 거래일보다 하루 앞을 채점했습니다.
  * 채점할 거래일까지 닿지 않는 저장된 다운로드는 다시 받고, 이미 스캔한 거래일은 다시 스캔하지 않으며, 추적 기록에는
    채점한 거래일당 한 번만 들어갑니다.
  * `QPP_CAPITAL_KRW`가 없으면 건너뛰고, 화면에서 시작한 스캔이 도는 동안은 기다리며, 90분까지 허용하고, 끝나면
    `--market KR tracking update`가 이어서 돕니다. 서울 시각 09:00 뒤에 끝난 실행은 다음 거래일 시가 진입으로 기록됩니다.
  * 모델 탭(한국)의 자본금 입력칸 옆 **스캔 실행** 버튼은 저장된 자본금으로 같은 명령을 시작합니다. 한 번에 하나만 돌고 일일
    작업의 실행과 겹치지 않습니다. 저녁에 누르면 그날 일봉이 아직 없어 0종목이 채점될 수 있는데, 그때 탭은 마지막 유효
    목록을 그대로 보여 주고 그 사실을 알립니다(`terminal/model_scan.py`, `/api/model/scan`).

### 개인 터미널 (TERMINAL-1)

이 Mac 안에서만(`127.0.0.1`) 열리는 로컬 웹 앱이며 화면은 한국어입니다. 무료 공개 데이터만 쓰고 주문 기능은 없습니다.

```bash
python app.py terminal --open          # http://127.0.0.1:8765 ; Ctrl+C로 멈춤 ; 다른 포트는 --port N
```

| 탭 | 내용 | 출처 |
|---|---|---|
| 시장 개요 | 지수, 금리·환율·원자재, 업종 ETF 11개(일간 변화, 1개월 변화, 30일 작은 그래프) | Yahoo Finance (지연 일봉) |
| 종목 | 기업 개요와 가치 지표, SMA 20/50/200과 거래량이 있는 캔들 차트(3개월 / 1년 / 5년), 5년 연간 재무, 최근 SEC 공시 | Yahoo, SEC EDGAR companyfacts / submissions |
| 거시 | 미국 국채 10년·2년 금리, 10년-2년 차이, 실효 연방기금금리, CPI 전년 대비, 실업률, 비농업 고용, 원/달러 | FRED 공개 CSV (개인·비상업 용도, 출처 표기) |
| 관심종목 | 로컬 관심 목록(`data/terminal/watchlist.json`) | Yahoo |
| 모델 | 고정 P6-11B 기준 모델: 최근 전체 스캔 상위 5종목과 추적 상태(읽기 전용), 도전자 모델(3단계) | `runs/`, `tracking/` |

* 모든 값에 상태가 붙습니다: **실데이터**, **지연·오래됨**(제공처 실패로 캐시 사본을 보여 주거나 일봉이 5일보다 오래됨),
  **데이터 없음**.
* 미국 정규장 중 최신 일봉은 **장중·미확정**으로 표시합니다.
* 없는 값은 "—"로 보이며 0으로 채우지 않습니다. 은행의 영업이익 같은 항목은 비워 둡니다.
* 응답은 `data/terminal/cache/`에 캐시됩니다. git이 무시하는 폴더이며 지워도 됩니다.
  * 시세와 차트: 15분
  * 기업 개요와 재무: 20시간
  * 공시: 1시간
  * 거시: 6시간
* 재무 표는 화면 표시용이며 P6-20-A 모델 입력과 별개입니다.
* SEC 신원(`SEC_USER_AGENT`)은 상태 단어로만 보고됩니다.
* 명세: `reports/TERMINAL_1_SPECIFICATION.md`.

**2단계 (TERMINAL-2): 실제 포트폴리오와 매매 보조.** 탭 두 개가 더 있고, 여전히 주문 기능은 없습니다.

| 탭 | 내용 |
|---|---|
| 포트폴리오 | 실제 체결 기록(입금, 출금, 매수, 매도, 배당, 수수료, 손절·목표 계획)과 결과(아래 참고) |
| 매매 보조 | 포지션 크기 계산기, 위험 설정, P6-11B 계획 점검(아래 참고) |

포트폴리오 탭에 나오는 것:
* 보유 종목, 이동평균 단가, 평가 손익과 실현 손익
* 달러 계좌 평가액과 원화 환산액
* 업종 비중
* 알림: 손절 도달·근접, 목표 도달, 손절 미설정, 종목·업종 한도 초과
* SPY 대비 시간가중 수익률
* 청산 거래 통계

매매 보조 탭이 하는 일:
* **포지션 크기 계산기:** 주식 수 = 아래 세 한도 중 가장 작은 값, 내림
  * 위험 한도: 평가액 × 위험 % ÷ (진입가 − 손절가)
  * 비중 한도: 평가액 × 최대 비중 ÷ 진입가
  * 현금 한도: 현금 ÷ 진입가

  손절가를 비워 두면 진입가보다 2 × ATR(14) 아래를 제안합니다.
* **위험 설정:** 거래당 위험 1%, 종목 최대 20%, 업종 최대 40%, 손절 근접 경고 3%.
* **P6-11B 계획 점검(읽기 전용):** 최근 상위 5종목을 내 계좌 크기로 환산(목표 주식 수, 1차 진입 주식 수, 모델 손절가).

기록 방식:
* 기록은 `data/terminal/journal.jsonl`에 있습니다. 이 Mac에만 있고 git이 무시합니다.
* 파일은 덧붙이기만 하고 해시 사슬로 묶입니다. 보유보다 많이 팔기, 현금이 음수가 되는 기록, 미래 날짜는 거부됩니다.
* 잘못 넣은 기록은 VOID 기록으로 취소합니다. 원래 줄은 남습니다.
* 설정은 `data/terminal/settings.json`에 저장됩니다.

명세: `reports/TERMINAL_2_SPECIFICATION.md`.

**3단계 (TERMINAL-3): 도전자 모델과 연구실.**

고정 P6-11B가 기준 모델로 남습니다. 규칙 기반 도전자들을 그 옆에서 하나의 공통 잣대로 사전 관찰합니다.

```bash
python app.py lab update     # S&P 500 약 500종목 일봉 갱신(2-3분)과 오늘의 도전자 신호 기록
python app.py lab compare    # 사전 비교 요약
```

`lab update`는 미국 장 마감 뒤(동부 17:00, 한국 약 07:00) 하루 한 번 돌리거나 모델 탭의 버튼을 누릅니다. 같은 날 두 번
돌려도 새로 기록되는 것은 없습니다.

**도전자**(가격만, 변수는 미리 고정, 상위 10종목 같은 비중):
* `MOM_12_1`: 최근 1개월을 뺀 12개월 수익률
* `LOWVOL_252`: 252일 변동성이 가장 낮은 종목
* `TREND_SWING`: 종가가 SMA200 위, SMA50이 SMA200 위, 6개월 수익률 순
* 기준선 `BASE_SPY`와 `BASE_EW`(대상 전체 같은 비중)

**사전 기록:**
* `data/lab/ledger.jsonl`에 덧붙이기만 하고 해시 사슬로 묶어 저장
* 모델마다 완성된 거래일당 한 건
* 진입은 기록 시각 뒤의 첫 정규장 시가로, P6-20과 같은 규칙

**공통 잣대:**
* 진입 거래일 시가에 사서 H번째 거래일 종가에 팜(H = 5, 20, 60)
* 배당 포함, 같은 비중, SPY 대비 초과수익
* P6-11B는 P6-20의 `VALID_PROSPECTIVE` 상위 5종목 중 진입 거래일마다 첫 실행을 읽기만 함
* 날마다의 집단이 겹치므로 화면에는 독립 표본 수(약 만기 수 ÷ H)를 보여 주고, 12개가 되기 전에는 "판단 보류"로 둡니다.

**연구실 탭:**
* 매월 재조정하는 약 5년의 과거 모의 실험
* 비용 시나리오 편도 0bp와 10bp
* 연평균 성장률, 변동성, 샤프 비율, 최대 낙폭, 연도별 초과수익

종목 선택은 그 시점에 이미 지수에 들어와 있던 종목으로 제한합니다(Wikipedia "Date added"). 나중에 지수에서 빠진 종목은 여전히
없으므로 결과는 위로 치우쳐 있습니다. 연구실은 참고로만 보세요.

명세: `reports/TERMINAL_3_SPECIFICATION.md`.

**점수 탭, 당일 점검:**
* 종목을 조회하면 오늘의 지연 가격, 시가 갭, 거래량, 새 공시, 뉴스 제목도 함께 보입니다. 이 점검은 점수에 더하지 않습니다.
* 공시는 점수의 사건 판독기가 쓰는 규칙에 따라 경고가 됩니다. 뉴스 제목은 좋고 나쁨을 판정하지 않습니다.
* 순위에서는 진입 가능한 상위 3종목이 펼쳐져 열리고, 아래 행은 누르면 그 자리에서 열립니다.

뉴스는 무료 피드에서 받습니다: Yahoo Finance RSS(미국)와 Google News RSS(한국). Yahoo의 종목 피드에는 관련 회사 기사가 섞일 수
있고, 한국 회사명 검색은 관계없는 기사와 맞을 수 있습니다.

`python app.py news record`(`--market KR`도 가능)는 스캔한 모든 종목의 새 뉴스 제목을 `data/news/`에 저장합니다. 제목, 링크,
출처, 시각만 저장합니다. 일일 작업에서 돌며, 피드가 요청을 거부하면 바로 멈춥니다.

**4단계 (TERMINAL-4): 일일 작업과 알림.**

```bash
python app.py automation install       # launchd 작업: 한국 시각 07:10부터 23:10까지 매시 (뒤 시간대는 실패한 것만 다시 시도, 끝난 날은 몇 초 만에 끝남)
python app.py automation status        # 일정, 마지막 실행, 빠진 거래일, 텔레그램 상태
python app.py automation uninstall
```

일일 작업은 그날의 점수, 연구실 신호, 추적, 뉴스, 한국 사전 기록을 기록하고, 장부를 `~/QuantEngineBackups`에 백업하며,
마감 시점의 알림을 점검해 요약 하나를 텔레그램(선택, `.env`의 `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID`)과 macOS 알림으로
보냅니다. 각 단계는 거래일당 한 번 돌고, 실패한 단계는 다음 시간대에 다시 시도합니다. 기록: `data/automation/`.
명세: `reports/TERMINAL_4_SPECIFICATION.md`.

**지금 수집(2026-11-10):** 위쪽 막대의 **지금 수집** 버튼은 같은 작업을 바로 시작합니다(`POST /api/automation/run`). 그래서
일정은 필수가 아니라 안전망입니다.
* 그 거래일에 아직 끝나지 않은 단계만 돌며, 모두 최신이면 몇 초 안에 그렇게 알려 줍니다.
* 하나가 도는 동안 두 번째 실행은 시작되지 않고, 준비되지 않은 날은 여전히 기록하지 않습니다.
* 머리글 아래 막대가 진행 중인 단계(예약 실행도 포함)와, 끝났을 때 실패했거나 아직 나오지 않은 것을 보여 줍니다.
* 실행은 서버와 분리되고 유휴 잠자기를 막습니다(`caffeinate -i`). 노트북 덮개를 닫으면 그래도 멈춥니다.
* 마지막 버튼 실행의 출력: `data/automation/manual_run.log`.

**미국 실적 발표일 재집계(2026-11-10):** 2026-12-15(한국 시각) 이후 미국 점수가 기록된 첫 실행에서, 일일 작업이 최신 장부
거래일에 다음 실적 발표일이 없는 미국 종목 수를 한 번 셉니다(`terminal/qsf/earnings_gap.py`). 그 숫자를 텔레그램(텔레그램이
없으면 macOS 알림)으로 보내고 `reports/DECISIONS_FOR_USER.md`의 해당 항목 아래에 한 줄을 적습니다. 전달되지 않은 메시지는
같은 숫자로 다음 실행에서 다시 보냅니다. 채점이나 기록은 달라지지 않으며, 빈칸을 채울지는 사용자 결정으로 남습니다.
지금 세려면: `python app.py qsf us-earnings-gap`.

**터미널 도구 추가(2026-11-08):**
* 명령 막대(`/` 또는 ⌘K, 숫자 1-9로 탭 전환)
* 여러 종목 비교 차트(비교)
* 시장 열지도와 업종 순환 그래프, 업종별 점수 상위 종목(시장 지도)
* 동종 기업 비교와 점수 영역별 A-F 등급(종목)
* 포트폴리오 위험(베타, 변동성, VaR, 상관), 알림 센터(매매 보조)
* 경제 일정(거시: FOMC, 미국 CPI와 고용 보고서, 한국은행 금리 결정, 보유·관심 종목의 실적 발표일). 일정 날짜는 공식 페이지에서
  옮겨 적었고 그 페이지가 끝나는 곳에서 끝납니다. 새 날짜는 `terminal/econ_calendar.py`에 추가합니다.

이 도구들은 점수와 기록을 바꾸지 않습니다. `reports/QSF_TERMINAL_FEATURES_2026_11_08.md`를 보세요.

**터미널 계속 켜 두기.**

```bash
python app.py terminal-agent install   # 로그인할 때 터미널을 시작하고, 멈추면 30초 안에 다시 시작
python app.py terminal-agent status    # 설치 여부, 실행 여부, pid, 시작 횟수
python app.py terminal-agent uninstall # 멈추고 launchd 작업 제거
```

* 에이전트는 `~/Library/LaunchAgents/com.quantengine.terminal.plist`입니다. 같은 `app.py terminal --port 8765`를 돌리며,
  `.env`는 로그인 셸로 읽습니다. plist에는 키를 적지 않습니다.
* 설치되어 있는 동안에는 `pkill`이나 Ctrl+C로 서버를 내려도 launchd가 다시 띄웁니다.
  * 잠시 멈추려면 `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.quantengine.terminal.plist`(다음 로그인 때
    돌아옴) 또는 `uninstall`을 씁니다.
  * 새 코드를 읽히려면 `launchctl kickstart -k gui/$(id -u)/com.quantengine.terminal`을 씁니다.
* 기록, `data/terminal/logs/`:
  * `launchd.log`: 시작 메시지. 1MB가 넘으면 새로 씀
  * `server_errors.log`: 예상하지 못한 요청 오류와 추적 정보. `.env` 값과 이메일 주소는 지우고 기록하며, 1MB마다 돌려 3개를
    남깁니다. 마지막 시작 이후 오류가 있으면 화면 아래 상태 줄에 "서버 오류 N건"이 나옵니다.
* 모델 탭(미국)의 자동 실행 줄에 자동 재시작이 켜져 있는지가 나옵니다.

### 파일 위치

| 경로 | 내용 |
|---|---|
| `runs/<run_id>/` | `run_manifest.json`(변수, 버전, 고정 지문), `execution_status.json`, `checkpoints.jsonl`, `provider_summary.json`, `candidate_flow.json`, `validation_result.json`, `failure.json`(실패 시), `report.md`, `report.html` |
| `runs/LATEST` | 최근 실행의 id |
| `tracking/ledger/` | 변경 불가 사전 기록 장부(`observations.jsonl`)와 사건(`events.jsonl`), 해시 사슬 |
| `tracking/prices/`, `tracking/outcomes/`, `tracking/updates.jsonl` | 시세 스냅샷, 계산된 결과, 갱신 기록(재현 가능) |
| `tracking/reports/latest.html` | 사전 성과 보고서 |
| `tracking/recommendation_ledger.jsonl`, `tracking/outcomes.json` | P6-19 스키마 1 추적 파일(보존, 대체됨, 더 이상 쓰지 않음) |
| `cache.nosync/provider/` | 재무 캐시(지워도 다시 만들어짐) |
| `docs/DATA_INPUT_SPECIFICATION.md` | 승인된 입력 정의, 버전 `P6-20-A`(SEC 시각 적격성, P/B 교차 확인, 총매출, 순이익률, ADV20, 업종, 관문). 실행마다 버전을 기록 |
| `docs/GIT_SETUP_REPORT.md` | 로컬 git 설정, 무시하는 파일, 비밀 값 검사, 비공개 원격 저장소 추가 방법 |
| `tracking/excluded_runs.json` | P6-19 제외 목록(보존, `tracking/ledger/events.jsonl`에 반영) |
| `runs/KR/<run_id>/` | 한국 실행: 매니페스트, 상태, `validation_result.json`, `candidate_flow.json`, `universe_snapshot.csv.gz`, `report.md` |
| `tracking/kr/` | 한국 장부, 시세 스냅샷, 결과, `reports/latest.html`(원화) |
| `data/kr/` | KRX KIND 종목 목록 스냅샷(원본 sha256 포함)과 한국 시세 캐시 |
| `tracking/STORAGE_SCHEMA.json` | 저장 구조 버전 2(덧붙이기 방식, 백업은 `~/Developer/qse-backups/`) |
| `tracking/dashboard.html` | 통합 읽기 전용 대시보드(`python app.py dashboard`) |
| `terminal/` | 개인 터미널: `services.py` 화면 데이터(모델 탭 부분은 `services_model.py`), `sources.py` Yahoo/SEC/FRED 접근, `server.py` 로컬 서버, `static/` 한국어 화면 |
| `terminal/qsf/` | QSF 점수: `service.py` 채점과 스캔, `views.py` 화면용 조회(동종 비교, 열지도, 실적 일정 등), `engine.py`·`factors.py` 계산, `research_*.py` 한 번씩 돌린 과거 시험 |
| `markets/session_data.py` | 거래일 자료가 다 왔는지 판단하는 규칙 한곳 |
| `data/lab/` | 연구실 시세 묶음, 도전자 장부, 구성 종목 캐시, 연구 캐시(로컬, git 무시) |
| `data/terminal/` | 터미널 캐시, 관심 목록, 매매 기록 `journal.jsonl`, 모의 매매 기록 `paper_journal.jsonl`, 위험 설정(로컬, 개인, git 무시) |
| `reports/` | 단계별 보고서, 로드맵, 시험 결과, 사용자 결정 목록 `DECISIONS_FOR_USER.md` |
| `reports/legacy/` | 예전에 프로젝트 최상위에 있던 초기 P3 보고서와 출력 |
| git 태그 `legacy-before-cleanup-2026-11-08` | P3/P5/P6 연구 코드(`entity/`, `providers/`, `research/`, `scripts/run_p*` 등)와 그 시험이 있던 마지막 커밋. 프로그램이 쓰지 않아 2026-11-08에 지웠고, `git checkout <tag> -- <경로>`로 파일을 되살릴 수 있음 |

### 터미널의 한국 시장

터미널 위쪽의 시장 전환(미국 | 한국)이 모든 탭을 바꿉니다. `005930` 같은 6자리 코드나 `삼성전자` 같은 한국 회사명을 입력하면
저절로 한국으로 바뀝니다.

- **계좌:** 달러 계좌와 원화 계좌는 따로 계산합니다. 달러로 한국 주식을 살 수 없습니다. 둘 다 같은
  `data/terminal/journal.jsonl`에 있으며, 한국 계좌 기록에는 `"market": "KR"`이 붙고 예전 기록은 미국으로 남습니다.
  포트폴리오 탭은 원화로 환산한 합계도 보여 주는데, 가격이나 환율이 없으면 비워 둡니다.
- **한도:** 한국 장기 위험 1%·비중 20%, 한국 스윙 위험 0.5%·비중 10%. 모두 매매 보조에서 바꿀 수 있습니다.
- **매도세:** 실제 포트폴리오 기록에는 증권거래세(2026년 0.20%)를 자동으로 더하지 않습니다. 매도 기록의 수수료 칸에 증권사
  수수료와 함께 넣으세요.
- **직접 기록하는 모의 매매(모의 매매 탭):** 시험 삼아 해 보고 싶은 거래만 담는 별도 기록(`data/terminal/paper_journal.jsonl`)입니다.
  - 모의 자금을 넣고, 내가 정한 가격으로 매수와 매도를 기록하면, 낸 돈·돌려받은 돈·수수료·남은 돈을 보여 줍니다.
  - 수수료 칸을 비우면 토스증권이 공시한 수수료와 그 반올림 규칙을 적용해 항목별로 기록합니다(한국 0.015%와 매도 시
    거래세 0.20%, 미국 0.1%와 10달러 이하 주문 무료, 매도 시 SEC 수수료).
  - 슬리피지는 넣지 않습니다. 가격은 입력한 그대로입니다.
  - 실제 계좌는 읽지도 쓰지도 않고, 주문도 보내지 않습니다(`terminal/paper_trade.py`, `/api/paper-trade`).
  - 점수 탭 → 주문 계획·모의 장부의 **모의 체결 장부(자동)**는 다른 것입니다. 그쪽은 프로그램 자신의 계획을 따라갑니다.
- **데이터:** 가격은 Yahoo(지연), 재무제표와 공시는 OpenDART(`OPENDART_API_KEY`), 상장 목록은 KIND, 거시는 한국은행
  ECOS(`ECOS_API_KEY`).
- **ECOS 키:** https://ecos.bok.or.kr/api/ 에서 무료 발급. `.env`에 `ECOS_API_KEY=...`로 넣고 터미널을 다시 시작합니다.
  없으면 한국 거시 카드에 "데이터 없음"이 나오며, 원/달러 카드는 그대로 됩니다.
- **아직 미국 전용:** 도전자 모델, 연구실, P6-11B 계획 점검. 모델 탭은 KR-EXP-0.1을 읽기 전용으로 보여 주며, 이 모델은
  실험 단계이고 검증되지 않았습니다.

### 장기와 스윙 포지션

모든 포지션은 장기 아니면 스윙이며, 한 종목은 한 번에 한 가지 방식만 가집니다. 첫 매수 때 고르고, 나중에는 구분 변경 기록으로
바꿉니다. 기록은 덧붙이기만 합니다. 포트폴리오 탭에 방식별 표가 있고, 매매 보조 탭에 다음 설정이 있습니다.

| 설정 | 장기 | 스윙 |
|---|---:|---:|
| 거래당 위험 | 2% | 1% |
| 종목당 최대 비중 | 25% | 10% |
| 계산기의 제안 손절 | 5 ATR | 2 ATR |
| 주식 평가액 중 목표 비율 | 70% | 30% |

* 두 방식 모두 손절을 둔다고 보고, 손절 없는 포지션은 경고합니다.
* 목표 비율은 구분이 붙은 주식 평가액끼리만 비교하므로 현금은 목표에서 벗어난 것으로 치지 않습니다. 10%p 넘게 벗어나면
  경고합니다.
* 보유 종목마다 자기 방식에 맞는 QSF 판독이 붙습니다. QSF는 실험 단계이며, 어떤 판독도 주문을 내지 않습니다.
* 매일 텔레그램 요약에는 청산 검토, 투자 논리 무효, 비중 축소 검토, 일부 차익 실현 검토, 시간 손절 재평가가 실립니다.
  보유하며 재검토는 화면에만 나옵니다.
* 스윙의 30거래일 시간 제한은 스윙이 된 날부터 셉니다.

### QSF 1.1 종목 점수 (실험)

점수 탭과 `qsf` 명령은 고른 종목을 네 가지 별도 기준으로 0~100점 채점합니다: `US_SWING_V1`, `US_LONG_TERM_V1`,
`KR_SWING_V2`, `KR_LONG_TERM_V1`. 결과마다 요인, 자료 충족도와 신뢰도, 절대 관문, 보유 계획, 청산 조건, 판정을 바꿀 조건이
나옵니다.

```bash
.venv/bin/python app.py qsf evaluate AAPL              # 한 종목, 출력만
.venv/bin/python app.py --market KR qsf evaluate 005930
.venv/bin/python app.py qsf scan                       # 대상 전체, 장부에 덧붙임
.venv/bin/python app.py qsf validate                   # 점수 구간별 만기 결과
.venv/bin/python app.py qsf verify                     # 장부 무결성
```

**기본 원칙**

* **검증된 신호가 아닙니다.** 가격만 쓴 과거 점검에서 점수와 이후 상대 수익 사이에 관계가 나오지 않았습니다
  (`reports/QSF_1_1_IMPLEMENTATION_REPORT.md`). BUY 판정은 매매를 허락하는 것이 아니며, 결정은 사용자가 합니다.
* QSF는 고정 모델 P6-11B와 별개입니다. 고정 핵심에서 아무것도 가져오지 않고, 두 점수는 절대 합치지 않습니다.
* 없는 자료는 충족도를 낮출 뿐 0으로 취급하지 않습니다. 스냅샷은 `data/qsf/ledger/`에 덧붙이기만 하는 해시 사슬 조각으로
  저장합니다. 잘못된 자료로 기록된 조각에는 VOID 행이 붙고 파일은 디스크에 남습니다.
* `qsf scan`의 종료 코드 3은 Yahoo가 그 거래일을 아직 끝내지 않았다는 뜻이고, 4는 시세 요청이 아예 실패했다는 뜻입니다(연결
  없음, 또는 다운로드 중 Mac이 잠듦). 어느 쪽이든 아무것도 기록하지 않고 일일 작업이 다음 시간대에 다시 시도합니다. 출력되는
  `reason`, `download`, `last_dates`가 어느 경우인지 알려 줍니다.
* "이 거래일 자료가 다 왔는가"는 `markets/session_data.py` 한곳에서 판단합니다. 저장된 다운로드를 다시 쓸지, 한국 거래일 달력,
  지수 값으로 쓸 수 있는 일봉, 그날을 기록해도 되는지와 실패 사유가 모두 여기 있고, 규칙마다 그 규칙을 만든 실측이 적혀 있습니다.
* 일일 작업은 실패한 단계에 그동안 Mac이 얼마나 잠들어 있었는지도 적습니다. 잠든 Mac은 짧은 유지 관리 깨어남 동안만 돌아서,
  2026-11-10에는 7분짜리 단계가 2시간 30분으로 늘어나고 미국 다운로드가 끊겼습니다. 한국 시각 07:10 앞뒤로는 Mac을 전원에
  연결해 깨어 있게 두세요.

**검증 기록**

* **한국 검증(2026-11-10):** 현재 한국 점수를 시점별 입력으로 2019-2026에 재현했습니다(`terminal/qsf/research_kr_live.py`).
  장기 점수는 스캔 대상 안에서 순위는 가리지만 상위 5분위가 시장을 이기지 못했고, 스윙 점수는 통과하지 못했으며, 스캔 대상
  자체(거래대금 상위 300)가 시가총액 기준 대상보다 뒤처졌습니다(`reports/QSF_KR_LIVE_REPLAY_RESULTS.md`,
  `reports/QSF_KR_UNIVERSE_TEST_RESULTS.md`). 기술 영역을 뺀 스윙 도전자를 현재 점수와 따로 매일 기록합니다
  (`reports/QSF_KR_SWING_CHALLENGER_PROTOCOL.md`).
* **현재 점수의 사전 판정(2026-11-11):** `reports/QSF_LIVE_FORWARD_PROTOCOL.md`가 수익이 하나도 나오기 전에 장부 기록을
  어떻게 판정할지 정해 두었습니다. 기록된 모든 거래일, Newey-West t, 과거의 다섯 조건과 돈 조건 하나, 그리고 매수 구간의 지수
  대비 수익을 점수 효과와 대상 효과로 나눈 것입니다. 시장·전략마다 정해진 표본에서 한 번만 평가합니다(스윙: 만기 240거래일,
  장기: 756거래일). `qsf live-forward-status`는 거래일만 세고, `live-forward-evaluate-swing|long`은 표본이 차기 전에는
  거부합니다(`terminal/qsf/live_forward.py`). 1년 안에 그 판정이 무엇을 잡아낼 수 있는지는
  `reports/QSF_LIVE_FORWARD_POWER_2026_11_11.md`에 추정했습니다(강한 효과만).
* **한국 시가총액 대상 도전자(2026-11-11):** 거래일마다 그날 적격 종목 중 시가총액 상위 300을 현재 코드로 채점하되, 현재 점수
  파일에는 아무것도 쓰지 않고 따로 저장합니다(`terminal/qsf/kr_cap_universe.py`, `research_data/kr_cap_universe/`, 한국 사전
  기록 단계 안). 만기 240거래일에 한 번 평가합니다(`reports/QSF_KR_CAP_UNIVERSE_PROTOCOL.md`). 피할 표시(고위험, 약한 재무,
  자금 조달)는 같은 표본에서 이미 쌓인 기록으로 한 번 읽습니다(`reports/QSF_KR_AVOID_MARKS_PROTOCOL.md`,
  `terminal/qsf/kr_avoid_marks.py`).
* **한국 기술 영역, 이전 구간(2026-11-11):** 2012-2019에 현재 채점 코드로 가격만 써서 확인을 한 번 돌렸습니다
  (`terminal/qsf/research_kr_tech.py`). 스윙 기술 영역의 20거래일 순위 상관이 다시 음수였고, 위험 영역의 순위 능력을
  상쇄했습니다(`reports/QSF_KR_TECH_EARLY_RESULTS.md`). 현재 점수는 바꾸지 않았습니다.
* **점수 옆 과거 성적(2026-11-11):** 점수 탭은 전략마다 저장된 단발 보고서의 내용(더 높은 점수가 이긴 쌍의 비율, 상위·하위
  5분위, 매수 구간, 대상 대 시장, 판정)을 보여 줍니다. 보고서 파일만 읽습니다(`terminal/qsf/track_record.py`,
  `/api/qsf/track-record`).
* **한국 실적 서프라이즈(2026-11-14):** 최근 분기 영업이익·매출의 1년 전 같은 분기 대비 변화를 시가총액으로 나눈 신호를 한 번
  시험했습니다(`terminal/qsf/research_kr_sue.py`, `qsf kr-sue-prepare|run`). 20거래일 순위는 설명하지만(IC +0.034), 기존 주제
  9개를 빼면 남는 것이 미리 정한 기준에 못 미쳐(IC +0.015, 기준 0.02) `A_NOT_INDEPENDENT`입니다. 점수에 넣지 않았습니다
  (`reports/QSF_KR_SUE_PROTOCOL.md`, `reports/QSF_KR_SUE_RESULTS.md`).
* **날마다의 안정성:** `qsf stability`는 장부에서 같은 모델 버전의 연속된 거래일을 비교합니다(순위 상관, 구간 변화, 매수 구간
  교체율). 가격은 읽지 않습니다(`terminal/qsf/stability.py`).

**점수 변경 이력**

* **재무 입력(QSF-1.1.9, `reports/QSF_FUND_INPUT_AUDIT_2026_11_11.md` 이후):**
  * 모든 수치는 최신 회계연도의 것이거나 빈칸입니다. 비율은 같은 연도의 양쪽 값이 다 있어야 하고, 성장률은 바로 앞 연도가
    있어야 합니다.
  * PER은 주식 수가 현재 기준이면 보고된 EPS를 쓰고, 아니면 시가총액 ÷ 지배주주 이익입니다. EPS 성장률은 주식 수 기준이 다른
    두 해를 잇지 않습니다.
  * 한국 EPS는 합계 줄이 없으면 계속·중단 영업 부분에서 읽습니다. 다른 통화의 재무제표는 원화 가격과 맞대지 않습니다.
  * 산업 그룹 지주회사, 미국 거래소, 건강보험사, 보험 중개사, 부동산 회사는 비금융으로 채점합니다.
  * 추출한 자료는 캐시 키 `annual3`, `krfund3`으로 옮겼습니다(`terminal/qsf/fundamentals.py`, 시험
    `tests/test_qsf_fund_inputs.py`).
* **한국 스윙 구성(QSF-1.2.0, 2026-11-11, 사용자 결정):** 기술 영역은 더 이상 한국 스윙 점수에 들어가지 않습니다. 과거 세 구간에서
  순위를 거꾸로 매겼습니다(`reports/QSF_KR_TECH_EARLY_RESULTS.md`).
  * 다섯 요인은 여전히 계산·표시·저장하되 참고 행(`scored: false`, `reference_weight`)이며, 차트 위치는 진입 평가
    (`holding.entry_status`)에 남습니다.
  * 새 합성 점수 자체는 과거 구간에서 채점한 적이 없습니다. 예전 식을 거래일마다 옆에 기록하며
    (`terminal/qsf/kr_swing_prior.py`, `reports/QSF_KR_SWING_PRIOR_PROTOCOL.md`), 서로 겹치지 않는 20거래일 표본 12개에서 한 번
    평가합니다.
  * 미국 점수와 한국 장기 점수는 바뀌지 않았습니다. 화면 안내와 과거 성적 표에 한국 장기의 두 번째 구간(2016-2019, 확인되지
    않음)을 첫 번째 옆에 함께 싣습니다. `reports/QSF_KR_SWING_V2_2026_11_11.md`.
* **입력 두 번째 수정(QSF-1.2.1, 같은 점검 이후):**
  * 미국 부채는 장기 부채, 그 유동 부분, 단기 차입금을 SEC 태그가 이미 담은 만큼 더한 것입니다. 부채 수치가 없는 미국 회사는
    총부채로 대신하지 않고 부채가 없는 것으로 봅니다.
  * 연간 수치는 더 새 보고서가 늦어지면(12개월 + 90일 + 14일) STALE입니다.
  * 금융 회사에는 현금흐름 대 이익 비율이 없습니다.
  * 결산월이 12월이 아닌 한국 회사는 가장 최근 사업연도까지 읽습니다.
  * 한국 `credit_liquidity` 요인은 한국은행(ECOS 817Y002)의 3년 AA- 회사채와 국고채 금리 차이를 읽습니다.
  * 추출한 미국 자료는 캐시 키 `annual4`로 옮겼습니다(`tests/test_qsf_inputs_2.py`, `reports/QSF_INPUTS_2_2026_11_11.md`).
* **실적 발표일 추정(QSF-1.3.1, 2026-11-11, 사용자 결정):** Yahoo에 다음 실적 발표일이 없으면(한국 대부분, 실적 발표 직후 미국의
  절반 정도) 회사 자신의 과거 날짜에서 1년 뒤 같은 분기로 추정합니다. 과거 날짜는 SEC 8-K item 2.02 공시, DART 잠정 실적 또는
  정기 보고서에서 가져옵니다(`terminal/qsf/earnings_estimate.py`). 추정치에는 표시가 붙고, 5거래일 앞부터와 날짜가 지나도 발표가
  없는 동안 새 스윙 진입을 막으며, `earnings_calendar` 요인을 채웁니다. 점검에서 한국 96%, 미국 90%가 7일 안에 맞았습니다. 이
  규칙이 돈을 번다는 근거는 없습니다(`reports/QSF_EARNINGS_DATE_RESEARCH_2026_11_11.md`, 시험 `tests/test_earnings_estimate.py`).
* **한국 대상 종목(QSF-1.3.0, 2026-11-11, 사용자 결정):** 현재 한국 스캔은 거래대금 상위 300 대신, 가지고 있는 최신 KRX 거래일의
  시가총액 상위 300종목을 채점합니다(`config.KR_UNIVERSE`, `QSF.kr_market_cap_universe`).
  * 예전 대상은 서로 다른 과거 두 구간에서 시장보다 해마다 15~24%p 뒤처졌습니다. 시가총액 쪽 수치는 탐색 시험 하나에서 나온
    것이고 그쪽에서 점수의 순위 근거는 더 약하며, 화면 안내와 과거 성적 표가 이를 밝힙니다.
  * 예전 대상도 자기 규칙대로 고르고 매일 따로 채점해 기록하며, 만기 240거래일 뒤 한 번 평가합니다
    (`terminal/qsf/kr_traded_universe.py`, `reports/QSF_KR_TRADED_UNIVERSE_PROTOCOL.md`). 점수 탭은 그 최신 거래일을 읽기
    전용으로 보여 줍니다(`terminal/qsf/kr_cap_view.py`, `/api/qsf/former-universe`).
    `reports/QSF_KR_UNIVERSE_SWITCH_2026_11_11.md`.
* **세 가지 신뢰도 장치(2026-11-12, 사용자 결정):**
  * **미래 자료 차단 점검과 워크포워드 순서:** 지난 가격을 기록값이나 화면 값으로 바꾸는 함수를 날마다 원래 가격과, 뒤쪽 행을
    지우거나 곱한 사본에 각각 돌립니다. 차이가 나면 미래를 읽은 것입니다. 결과 함수 하나를 대조군으로 돌려 반드시 잡혀야
    합니다(`terminal/qsf/lookahead.py`, `qsf lookahead-audit`, `/api/qsf/lookahead`). 이 점검은 모든 사전 기록 저장소의 해시
    사슬도 읽습니다. `terminal/qsf/walkforward.py`는 학습하는 것이 결과가 끝난 날에서만 배우도록 순서를 지킵니다.
  * **국면 가중치(도전자):** 지수만으로 시장 상태를 셋으로 나누고, 그 상태에서 전에 순위를 잘 매긴 영역 쪽으로 가중치를
    기울입니다. 한 번 돌린 워크포워드 결과는 두 시장 모두 NOT_SUPPORTED(한국 차이 −0.0025, t −0.49; 미국 −0.0010, t −0.26)여서
    현재 점수는 바꾸지 않았습니다. 고정한 표는 2026-11-12 거래일부터 매일 기록하고, 만기 240거래일에 수치만 한 번 읽습니다
    (`terminal/qsf/regime_weights.py`, `reports/QSF_REGIME_WEIGHTS_PROTOCOL.md`, `reports/QSF_REGIME_WEIGHTS_RESULTS.md`).
  * **주문 계획과 모의 체결 장부:** 어디로도 주문을 보내지 않습니다. 계획은 프로그램이 지금 진입 가능하다고 읽는 종목을 점수
    순으로 고르고, 거래당 위험, 종목 비중, 방식별 몫, 업종 비중, 현금, 그 종목 거래대금의 1% 중 가장 빡빡한 한도로 크기를
    정합니다. 이미 보유했거나 계획에 있는 종목은 두 번째 주문을 받지 않습니다(`terminal/qsf/order_plan.py`, 기록된 계좌용
    `/api/qsf/order-plan`). 모의 체결 장부는 1,000만 원과 1만 달러의 가상 계좌로 그 계획을 기계적으로 따라갑니다. 다음 시가가
    지정가 위면 체결하지 않고, 손절·목표·30거래일(스윙)·장기 점수 40 미만으로 청산하며, 거래일마다 한 번 쓰고 사슬로 묶고, 한
    번에 하나만 씁니다(`terminal/qsf/paper_book.py`, `research_data/paper_book_kr|us`, `reports/PAPER_BOOK_RULES.md`). 판정 전
    참고일 뿐이며 점수에 대한 근거가 아닙니다.
  * **비용**은 토스증권이 공시한 수수료입니다(QSF-1.3.2): 미국 편도 0.1%와 매도 시 SEC 수수료, 한국 0.015%와 매도 시 거래세
    0.20%. 슬리피지는 추정치(가정한 스프레드 + 주문 크기에 따른 제곱근 충격)이며 그렇게 표시합니다.
* **예측 층 FC-1(2026-11-15, 사용자 결정):** 점수와 따로, 종목 하나에 대한 숫자를 매일 적고 채점합니다.
  * **가격 범위:** 지수가중 변동성(λ 0.94, 0.97)에 과거 움직임으로 맞춘 폭을 곱해 5거래일과 20거래일 뒤 종가의 80%·50%
    범위를 냅니다. 오를지 내릴지는 말하지 않습니다.
    한 번 돌린 과거 점검은 두 시장 모두 RANGE_CALIBRATED입니다(한국 2011~2026, 미국 2013~2026: 80% 범위가 실제 80.0~80.7%,
    50% 범위가 50.4~50.6%를 담음, `reports/QSF_FORECAST_RESULTS.md`).
  * **기대 초과 수익과 확률:** 순위 설명력 × 변동성 × 표준화 점수(Grinold 식). 과거 시험을 통과한 점수가 없어 네 점수 모두
    설명력 0, 즉 기대 초과 수익 0과 확률 50%로 기록합니다. 가정 값 0.03의 숫자를 "가정"이라는 이름으로 함께 적습니다.
  * 한 번 쓰면 고치지 않는 기록(`research_data/forecast_kr|us`)이며, 지평이 끝난 날부터 범위 포함률을 계산합니다.
    라이브 점수, 한도, 주문 계획은 읽지도 바꾸지도 않습니다(`terminal/qsf/forecast.py`, `reports/QSF_FORECAST_PROTOCOL.md`,
    `qsf forecast-test|forecast-record|forecast-status`).
* **독자 매매법 KR-M1과 한국 위험 등급(2026-11-11, 사용자 결정):** 현재 점수와 떨어뜨려 둔 도전자입니다.
  * 피할 표시가 있는 종목을 빼고, 나머지 중 현재 스윙 점수 상위 5분위를 후보로 삼아, 차트 진입 일곱 가지와 기준선 두 가지를
    하나의 청산 규칙(손절 2 ATR, 목표 3 ATR, 10거래일, 왕복 0.53%)으로 따라갑니다.
  * 2019-2026에 한 번 돌린 선택 시험에서는 주 방식을 정하지 못했습니다. 비용을 빼면 모든 진입과 두 기준선이 0 근처나 그
    아래였습니다(`reports/QSF_KR_METHOD_SELECTION_RESULTS.md`).
  * 아홉 가지 모두 2026-11-11 거래일부터 매일 기록하며(`terminal/qsf/kr_method.py`, `research_data/kr_method`,
    `reports/QSF_KR_METHOD_PROTOCOL.md`), 추적·검증 아래 "판정 전 참고"로 보여 주고, 만기 신호일 120일과 240일에 수치를 한
    번씩 보고합니다.
  * 위험 등급은 다른 질문, 곧 어느 종목이 다음 20거래일에 더 크게 흔들리고 더 잃는지에 답합니다. 한 번의 시험을 통과했습니다
    (시가총액 상위 300에서 실현 변동성과의 순위 상관 +0.51, `reports/QSF_KR_RISK_GRADE_RESULTS.md`,
    `terminal/qsf/kr_risk_grade.py`). 종목 상세에 참고로만 나오며 점수, 순위, 한도, 손절 어디에도 들어가지 않습니다.
* **재무제표 보관 시간(2026-11-11):** 추출한 미국 연간 재무제표는 20시간 보관하므로, 새 10-K가 최대 7일 뒤가 아니라 다음 날
  아침 실행에서 채점됩니다. SEC 읽기가 실패하면 저장된 사본을 씁니다. 한국 재무제표는 7일 보관합니다
  (`terminal/qsf/service.py`의 `TTL["facts"]`, `TTL["kr_facts"]`, 시험 `tests/test_qsf_statement_keep_time.py`).
* **한국 일봉(QSF-1.1.8):** `research_data/krx`의 KRX 일별 스냅샷에서 날마다의 공식 등락률을 이어 붙여 만듭니다. 등락률이 이미
  액면분할을 반영합니다. Yahoo는 KRX가 아직 내지 않은 날과 배당 비율에만 씁니다(`terminal/qsf/kr_bars.py`, 캐시
  `data/qsf/krx_panel.npz`). `qsf price-audit`가 점수가 읽는 일봉을 점검합니다(`reports/QSF_PRICE_AUDIT_2026_11_09.md`).
* **한국 스캔 보호 장치(2026-11-11):** 저장된 한국 일봉 다운로드는 종목의 80% 이상이 채점할 거래일의 일봉을 가질 때만 다시
  쓰고, 아니면 새로 받습니다. 시장 전체 한국 스캔에서 종목이 200개보다 적으면 기록하지 않고(`UNIVERSE_TOO_SMALL`) 다음 실행을
  기다립니다(`markets/kr/acquisition.py`, `tests/test_kr_stale_cache.py`, `reports/QSF_KR_PARTIAL_RECORD_2026_11_11.md`).

## 6. 시험

```bash
.venv/bin/python -m pytest tests -q
```

시험은 오프라인으로, 쓰고 버리는 격리 환경(`tests/conftest.py`) 안에서 돕니다.

* `QPP_PROVIDER_TESTS=1`이 아니면 네트워크 접속을 막습니다.
* 실제 `data/`, `reports/`, `runs/`, `tracking/`에 쓰는 시험은 실패하고, 그 파일은 되돌립니다. 되돌리는 것은 시험이 직접 쓴
  파일뿐입니다. 시험이 도는 동안 일일 작업이나 스캔, 터미널 서버가 같은 폴더에 쓴 파일은 건드리지 않고 실행 끝에 목록으로
  알려 줍니다(2026-11-14 이전에는 그런 파일도 지웠습니다).
* 고정 명세와 맞지 않는 예전 시험은 문서화한 이유와 함께 엄격한 `xfail`로 분리합니다(조용히 건너뛰지 않음).

고정 핵심의 일치 여부만:

```bash
.venv/bin/python -m pytest tests/test_p6_18_frozen_core_parity.py tests/test_p6_19_hardening.py::TestFrozenSourcePinned -q
```

## 7. 문제 해결

| 증상 | 해결 |
|---|---|
| 명령이 시작하자마자 멈춤 | `app.py doctor`를 돌립니다. iCloud 위치나 클라우드에만 있는 파일을 보고하면 `~/Developer/quant-stock-engine`에서 실행하세요. |
| `ERROR: Capital is not configured` | `--capital 50000`을 주거나 `.env`에 `QPP_CAPITAL`을 설정합니다. |
| `NOTE: SEC EDGAR disabled` | `.env`나 셸 프로필에 `SEC_USER_AGENT="QuantStockEngine/1.0 <이메일>"`을 설정합니다. |
| `LIVE DATA UNAVAILABLE` | `app.py doctor --network`를 돌립니다. 보통 연결 문제이거나 Yahoo·Wikipedia가 잠시 안 되는 경우입니다. 나중에 다시 하세요. 속도 제한은 절대 우회하지 않습니다. |
| 디스크가 거의 참(`doctor` WARN) | 지워도 되는 것(다시 만들어짐): `cache.nosync/`, `.venv`(2절대로 다시 만듦). `data/`, `tracking/`, 기록된 실행의 `runs/<id>/` 폴더는 지우지 마세요. `tracking verify`와 진단에 필요합니다. |
| 터미널 페이지가 안 열림 | `app.py terminal-agent status`를 돌립니다. 설치되어 있지 않으면 `app.py terminal`로 시작하거나 에이전트를 설치합니다. 돌고 있는데 페이지가 안 되면 `data/terminal/logs/launchd.log`와 `server_errors.log`를 읽습니다. |
| 화면이 예전 그대로임 | 서버를 다시 시작한 뒤 열려 있던 페이지는 새로고침해야 합니다. 화면 파일이 바뀌면 페이지 위에 "새로고침" 안내가 나옵니다. |
| `tracking update`가 FAILED | 데이터 제공처에 닿지 못했습니다. 이전 기록과 결과는 그대로입니다. 나중에 다시 돌리세요. |
| 모든 관측이 `PENDING_OUTCOME` | 진입 거래일의 일봉이 완성되고(미국 동부 17:00 뒤) 30일 기간이 지날 때까지는 정상입니다. |
| 예전 데스크탑 사본 지우기 | 새 위치를 확인한 뒤에만. Finder에서 `~/Desktop/퀀트 예측 프로그램`을 휴지통으로 옮깁니다(휴지통을 비우기 전까지는 되돌릴 수 있음). |

## 8. 보안

* 소스에는 어떤 인증 정보도 저장하지 않습니다. 비밀 값은 `.env`(git 무시)나 셸에만 둡니다.
* **NewsAPI 키 교체(필수, 한 번):** 예전 버전에 NewsAPI 키가 소스에 적혀 있었으므로 노출된 것으로 봐야 합니다.
  <https://newsapi.org/account>에 로그인해 키를 다시 발급하고, NewsAPI를 계속 쓰려면 새 키를 `.env`의 `NEWS_API_KEY`로 넣으세요.
  NewsAPI는 선택이며 추천 파이프라인은 쓰지 않습니다.
* SEC 연락 이메일은 개인 정보입니다. SEC 요청의 HTTP User-Agent로만 쓰이며 실행 결과 파일이나 보고서에 쓰이지 않습니다.
* API 키(DART, KRX, ECOS, 텔레그램)는 기록, 보고서, 화면에 찍지 않습니다. 요청 오류에는 주소에 키가 들어갈 수 있어 오류 종류
  이름만 남깁니다.

---

개발 현황은 `reports/ROADMAP.md`, 검증·변경·근거는 `reports/P6-19_IMPLEMENTATION_REPORT.md`, 사용자가 정해야 할 것은
`reports/DECISIONS_FOR_USER.md`를 보세요.
