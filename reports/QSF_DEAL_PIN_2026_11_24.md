# Deal pin: merger-bound stocks out of the buy band (2026-11-24)

Decision 14 (가) of 2026-11-22 ("합병 위임장이 올라온 가격 고정 종목을 매수 후보와 상위 3종목에서 뺄지") was delegated by the user on 2026-11-24 ("너의 추천대로 해"), after asking why TECH (Bio-Techne) led the US swing ranking at about 76 points with a cost-adjusted reward-to-risk of −0.15.

## Why TECH scored 76

US swing points (80 counted; the regime domain is shown apart): technical 35.1/40, fundamental 8.6/10, risk 10.0/20, events 7.3/10 → 61.0/80 = 76.3. The reward-to-risk factor is worth 6 points and gave 0. The technical points came from the deal, not from a trend: the price moved up to the deal price after the announcement (trend 6/6, six-month return in the top 2%), then stopped moving (Bollinger width in the lowest 2% of its year, ATR 0.2%). The 1-year high (72.88) sat 0.1% above the price, under the round-trip cost of 0.40%, hence the negative ratio. The entry rule already said "wait for a pullback"; the band still said "매수 후보".

## What a filing alone says

On the 2026-11-23 scan 13 US stocks had a merger or tender-offer filing in the last 365 days (`events.DEAL_FORMS`). Four (BIIB, GILD, MRK, LLY) were buyers: a bidder files SC TO-T, and a buyer whose holders vote files a merger proxy. Excluding by filing alone would have removed them.

20-session annualised volatility of the 13 (Yahoo daily closes, 2026-11-23): TECH 1.6%, PTC 4.9%, AES 6.2%; the other ten 20.3% (D) to 58.7% (SKYD).

## Rule

`terminal/qsf/deal_pin.py`: a US stock is pinned when it has a deal filing of the last 365 days **and** a 20-session annualised volatility under 10%. The line sits in the gap between 6.2% and 20.3%. It was read from this split of filings and prices, not from any return, and is not to be tuned.

A pinned stock:
- keeps its score (no factor, weight or formula changed; `MODEL_VERSION` stays QSF-1.5.2 because no score moves);
- gets no buy band: the band becomes `HOLD_WATCH` with a label naming the filing and the volatility, and a buy action becomes watch;
- gets no entry (`NO_VALID_ENTRY_SETUP`, reason names the deal), so it leaves the order plan;
- is recorded with `deal_pin` and `deal_held` (new ledger fields from 2026-11-24; earlier lines are not rewritten).

Not changed: the pre-registered top-3 record (`reports/QSF_TOP3_TRACKING_PROTOCOL.md`) ranks by score and keeps doing so; changing its members mid-record would change what it tests. Korean stocks: no deal filing list is read, so no pin.

Live check after the change (stock screen, 2026-11-24): TECH swing 76.8 → 보유·관찰, PTC swing 72.3 and long 72.9 → 보유·관찰, AES (under 70) unchanged band but no entry; BIIB and GILD keep their buy bands.

Tests: `tests/test_price_fill_and_deal_pin.py`.
