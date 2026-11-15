# 미국 기관 보유 공시(13F) 자료 조사 (2026-11-15)

사용자 지시("큰 손 따라가기 … 진행해")로 공개 페이지만 읽어 조사했다. 자료 파일과 안내 PDF는 내려받지 않았고, 가입이나 키 신청도 하지 않았다. 수익률은 계산하지 않았다. 이 엔진에서 13F는 시험한 적이 없다(내부자 매매, 공매도 잔고, 뉴스·심리, 문헌 주제 결합은 이미 시험해 기준 미달).

> 덧붙임(2026-11-15, 같은 날): 1단계 표본 확인을 사용자 승인 뒤 실행했다. 결과는 `reports/QSF_US_13F_SAMPLE_2026_11_15.md`. 아래 본문과 미리 정한 표는 바꾸지 않았다.

## 결론

**자료는 무료로 구할 수 있고 이 Mac에서 처리할 수 있다. 그러나 대형주에서 45일 지연 뒤에도 통한다는 공개된 근거는 약하고, 같은 변수에 대해 논문의 방향이 서로 반대다.** 과거 시험을 하더라도 표본은 2013년 이후 약 50개 분기뿐이다. 통과 가능성은 낮다고 본다. 그래도 미국 쪽에서 재무제표와 가격에서 나오지 않는 무료 자료로는 남은 유일한 후보다.

다음 단계는 분기 파일 하나와 안내 PDF를 받아 실제 항목을 확인하는 것이다. 파일을 내려받는 일이라 사용자 확인이 필요하다(결정 목록 9번).

## 확인한 사실

| 항목 | 내용 | 확인 |
|---|---|---|
| 자료 | SEC "Form 13F Data Sets". 분기마다 zip 하나, 탭으로 나눈 표 7개 | 페이지에서 확인 |
| 기간 | 2013년 3분기부터 완전한 분기. 가장 최근은 2026년 6~8월 접수분 | 페이지에서 확인 |
| 묶는 기준 | 보고 기준일이 아니라 **접수 시점**. 2024-03부터 2·5·8·11월에 끝나는 석 달씩 | 페이지에서 확인 |
| 크기 | zip 54개, 합계 약 2.9GB(2013년 약 35MB, 2026년 약 75~96MB) | 페이지의 크기를 더함 |
| 공개일 항목 | `SUBMISSION` 표의 `FILING_DATE`(날짜만) | 검색 결과로 확인, 원문 미확인 |
| 정정 공시 | 전체를 바꾸는 것과 종목을 더하는 것 두 종류. 자료는 접수된 그대로라 직접 합쳐야 함 | SEC FAQ에서 확인 |
| 금액 단위 | 2023-01-03부터 달러, 그 전은 천 달러 | SEC FAQ에서 확인 |
| 재사용 | SEC 자료는 공공 정보로 복제·재배포 가능(출처 표시) | SEC 안내에서 확인 |
| 접근 규칙 | 초당 10회 이하, User-Agent에 연락처 표시. 이 프로젝트는 이미 `.env`의 `SEC_USER_AGENT`로 SEC를 읽고 있다 | SEC 안내에서 확인 |
| 누가 내는가 | 운용 자산 1억 달러 이상의 기관. 분기 말 보유를 45일 안에 공시 | SEC FAQ에서 확인 |
| 담기지 않는 것 | 공매도, 매도한 옵션, 작은 보유(1만 주 미만이면서 20만 달러 미만), 비공개 승인을 받은 보유 | SEC FAQ에서 확인 |
| 종목 식별 | CUSIP만 있고 종목 기호가 없다 | 페이지에서 확인 |

## 따져 본 것

- **종목 기호 연결.** 방법은 둘이다. (1) SEC의 결제 불이행(fails-to-deliver) 파일은 CUSIP과 기호를 날짜와 함께 싣는다(2004년부터). 다만 불이행 잔고가 있는 종목만 나오므로 503종목을 모두 덮는지는 확인하지 못했다. (2) OpenFIGI는 키 없이 분당 25회까지 CUSIP을 받는다. 지금의 기호만 줄 가능성이 크다.
- **CUSIP 이용 조건.** CUSIP 체계의 권리는 미국은행협회에 있다. 받은 CUSIP과 연결표는 내부에서만 쓰고 저장소에 올리지 않는다(`data/`와 `research_data/`는 git이 무시한다). 법률 판단은 아니다.
- **지연.** 분기 말 뒤 45일에 공시가 나오고, 묶음 파일은 그보다 몇 주 더 늦게 올라온다. 매일 쓰려면 EDGAR에서 개별 공시를 직접 읽어야 한다.
- **디스크와 메모리.** 압축을 다 풀 수는 없다(탭 문서는 5~8배로 커진다). zip을 하나씩 열어 보유 표를 한 줄씩 읽고 503종목만 남기면 메모리는 거의 들지 않는다. 지금 디스크 여유는 약 25GB다.
- **표본.** 완전한 분기가 약 52개라 분기 변화는 최대 50개 남짓이다. 모두 2013년 이후이고, 이 구간은 다른 미국 시험에 이미 썼다.

## 공개된 근거 (대부분 2010년 이전 표본, 상당수는 13F가 아니라 펀드 자료)

| 연구 | 신호 | 결과 |
|---|---|---|
| Chen·Hong·Stein 2002 | 보유 펀드 수의 변화 | 줄어든 종목이 12개월 동안 약 5~6%포인트 부진(1979~1998) |
| Nagel 2005 | 같은 신호, 5년 연장 | 평균적으로 관계 없음 |
| Edelen·Ince·Kadlec 2016 | 보유 기관 수의 변화 | **반대 방향**: 기관이 사는 쪽이 장기적으로 부진 |
| Dasgupta·Prat·Verardo 2011 | 여러 분기 연속 순매수·순매도 | 계속 판 종목이 계속 산 종목보다 나음(주로 소형주) |
| Lewellen 2011, Griffin·Xu 2009 | 기관·헤지펀드 보유 전체 | 종목 선택 능력이 거의 없음 |
| Cohen·Polk·Silli | 펀드별 가장 큰 초과 비중 | 연 2.8~4.5%(주로 뮤추얼 펀드, 2005년까지) |
| Agarwal 외 2013 | 비공개 보유 | 공개 보유보다 연 5~7% 나음. 즉 우위의 일부는 공개 공시에 없다 |
| Iqbal·Jivraj·Angelini 2019 | 헤지펀드 합의 종목 | 운용사를 미리 고르지 않으면 초과 수익 0 |

- 같은 변수(보유 기관 수 변화)에 대해 방향이 서로 반대인 결과가 있다. 부호를 미리 가정할 수 없다.
- 2010년 이후 대형주에서 45일 지연 뒤에도 넓은 13F 신호가 남는다는 깨끗한 공개 시험은 찾지 못했다.

## 확인하지 못한 것

- 표의 항목 이름 대부분(안내 PDF를 열지 않았다), `FILING_DATE`에 시각이 있는지, 2023년 이전 금액을 SEC가 다시 맞췄는지.
- 분기당 행 수, 압축을 푼 크기, 503종목만 남겼을 때의 비율.
- 결제 불이행 파일이 503종목을 모두 덮는지, OpenFIGI가 없어진 CUSIP을 어떻게 답하는지.

## 다음 단계 (자료를 보기 전에 정함)

| 단계 | 하는 일 | 멈추는 조건 |
|---|---|---|
| 1. 표본 확인 (사용자 확인 필요) | 안내 PDF와 가장 최근 분기 zip 하나(약 90MB)를 받아 항목, 공개일, 행 수, 503종목 연결 비율을 본다. 수익률은 계산하지 않는다 | 공개일 항목이 없거나, 503종목 중 95% 미만만 연결되면 여기서 끝낸다 |
| 2. 계획서 | 신호 하나(많아야 둘)와 부호, 공개일 규칙(접수 다음 거래일), 정정 처리, 지평, 통과 기준을 수익 계산 전에 커밋한다 | 사용자가 신호 선택을 승인하지 않으면 끝낸다 |
| 3. 과거 시험 1회 | 전체 54개 분기(약 2.9GB)를 받아 한 번 시험한다. 조건 A, 돈 조건, 독립성 조건 C(기존 주제를 뺀 잔차 IC 0.02 이상, t 2.24 이상)를 그대로 쓴다 | 한 번만. 기준 미달이면 신호를 바꿔 다시 찾지 않는다 |

- 신호가 둘이면 t 기준은 2.24(두 번 시험)를 쓴다.
- 대상은 그 시점의 S&P 500 구성 종목이어야 한다. 지금의 503종목만 쓰면 살아남은 종목만 보게 된다.
- 표본이 약 50개 분기뿐이라 통과하더라도 "약한 근거"까지만 말할 수 있다. 이 표는 자료를 보기 전에 정했고, 결과를 본 뒤에 바꾸지 않는다.

## 출처

- SEC Form 13F Data Sets: https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
- SEC 13F FAQ: https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f
- SEC 접근 규칙: https://www.sec.gov/privacy , https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- SEC 13(f) 증권 공식 목록: https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/official-list-section-13f-securities
- SEC 결제 불이행 자료: https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data
- OpenFIGI: https://www.openfigi.com/api/documentation
- CUSIP 이용 조건: https://www.cusip.com/services/license-fees.html
- Chen·Hong·Stein: https://www.nber.org/papers/w8151 · Edelen·Ince·Kadlec: https://econpapers.repec.org/RePEc:eee:jfinec:v:119:y:2016:i:3:p:472-488 · Lewellen: https://econpapers.repec.org/RePEc:eee:jfinec:v:102:y:2011:i:1:p:62-80 · Griffin·Xu: https://ideas.repec.org/a/oup/rfinst/v22y2009i7p2331-2370.html · Agarwal 외: https://ideas.repec.org/a/bla/jfinan/v68y2013i2p739-783.html
