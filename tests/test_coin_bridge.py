"""The coin part (terminal/coin_bridge.py): a read-only reader of another project's predictor files.  Made-up files, no network."""
import json
from pathlib import Path

import numpy as np
import pytest

from terminal import assistant as A, coin_bridge as cb, server

ROOT = Path(__file__).resolve().parents[1]
H = cb.BAR_MS
CLOSE = 1_795_233_600_000                     # a four-hour close
COINS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "TRX", "LTC", "LINK", "DOT", "1000SHIB"]


def make(folder: Path, bars: int = 400, extra_bars: int = 2, alpha=lambda k: 0.004 - 0.001 * k, closes=(CLOSE - H, CLOSE)):
    """Bars that had closed by CLOSE, plus ``extra_bars`` after it; funding every eight hours; a score line per coin and close."""
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    market = rng.normal(0, 0.01, bars + extra_bars)
    lines = []
    for k, coin in enumerate(COINS):
        ret = (0.5 + 0.25 * k) * market + rng.normal(0, 0.002, bars + extra_bars)
        px = 100.0 * (k + 1) * np.exp(np.cumsum(ret))
        t = CLOSE - H * (bars - np.arange(bars + extra_bars))          # open times: the last closed bar opens at CLOSE - H
        np.save(folder / f"{coin}USDT.bars.npy", np.column_stack([t, px, px * 1.01, px * 0.99, px, np.full(len(px), 1000.0)]))
        ft = CLOSE - 2 * H * (60 - np.arange(62))
        np.save(folder / f"{coin}USDT.funding.npy", np.column_stack([ft, np.full(62, 0.0001 * (k - 3))]))
        for c in closes:
            lines.append(json.dumps({"close_ms": c, "symbol": f"{coin}USDT", "alpha": alpha(k) if c == closes[-1] else 0.0, "weight": 0.05, "version": 15}))
    (folder / "shadow_alpha.jsonl").write_text("\n".join(lines) + '\n{"close_ms": 17952', encoding="utf-8")      # the last line was cut by a crash
    (folder / "shadow_state.json").write_text(json.dumps({"equity": 123456.0}), encoding="utf-8")
    return folder


def test_the_newest_scored_close_is_read_ranked_and_carries_no_book_value(tmp_path):
    d = cb.read(now_ms=CLOSE + H, folder=make(tmp_path / "p"))
    assert d["status"] == "REAL" and d["close_ms"] == CLOSE and d["age_hours"] == 4.0 and d["version"] == 15 and d["cost_round_trip"] == 0.002 and len(d["rows"]) == 12
    rows = d["rows"]
    assert [r["coin"] for r in rows[:3]] == ["BTC", "ETH", "SOL"] and [r["rank"] for r in rows] == list(range(1, 13)) and rows[0]["score"] == 100.0 and rows[-1]["score"] == 0.0
    assert rows[0]["alpha"] == pytest.approx(0.004) and rows[0]["beats_cost"] and not rows[2]["beats_cost"] and rows[0]["name"] == "비트코인"
    assert rows[-1]["coin"] == "SHIB" and rows[-1]["per_thousand"] is True and rows[-1]["symbol"] == "1000SHIBUSDT"
    text = json.dumps(d)
    assert "weight" not in text and "equity" not in text and "123456" not in text          # the paper books of that project are never read
    assert d["caveats"] == cb.CAVEATS and "오를지 내릴지를 말하지 않으며" in d["caveats"][0] and "현물" in d["caveats"][1]


def test_figures_are_as_of_the_scored_close_and_follow_that_projects_definitions(tmp_path):
    folder = make(tmp_path / "p")
    d = cb.read(now_ms=CLOSE + H, folder=folder)
    bars = np.load(folder / "BTCUSDT.bars.npy")
    last = bars[bars[:, 0] + H <= CLOSE]
    btc = next(r for r in d["rows"] if r["coin"] == "BTC")
    assert len(bars) - len(last) == 2 and btc["price"] == pytest.approx(last[-1, 4])        # the two bars after the close are not looked at
    assert btc["change_7d"] == pytest.approx(last[-1, 4] / last[-43, 4] - 1) and btc["change_1d"] == pytest.approx(last[-1, 4] / last[-7, 4] - 1)
    assert btc["funding"] == pytest.approx(-0.0003) and btc["funding_year"] == pytest.approx(-0.0003 * 3 * 365) and btc["funding_place"] == 1
    betas = [r["beta"] for r in sorted(d["rows"], key=lambda r: COINS.index(("1000" if r["per_thousand"] else "") + r["coin"]))]
    assert betas == sorted(betas) and betas[0] < 0.7 < 1.3 < betas[-1] and btc["beta_place"] == 1         # each coin was built to move more with the market than the one before
    assert btc["above_200d"] is None and d["market"]["above_200d_of"] == 0 and d["market"]["coins"] == 12  # 400 four-hour bars are not 200 days: unknown, never guessed
    assert cb.sigma(np.tile([0.01, -0.01], 50)) == pytest.approx(0.01) and cb.sigma(np.array([0.01] * 10)) is None
    m = np.random.default_rng(1).normal(0, 0.01, 400)
    assert cb.beta(2 * m, m) == pytest.approx(2.0) and cb.beta(m[:100], m[:100]) is None
    assert cb.coin_of("BTCUSDT") == "BTC" and cb.coin_of("1000SHIBUSDT") == "SHIB"


def test_an_old_score_is_marked_and_a_missing_source_says_why(tmp_path):
    folder = make(tmp_path / "p")
    assert cb.read(now_ms=CLOSE + 9 * 3600_000, folder=folder)["status"] == "REAL" and cb.read(now_ms=CLOSE + 10 * 3600_000, folder=folder)["status"] == "STALE"
    gone = cb.read(folder=tmp_path / "none")
    assert gone["status"] == "UNAVAILABLE" and cb.ENV in gone["reason"] and gone["caveats"] == cb.CAVEATS
    (tmp_path / "empty").mkdir()
    assert "shadow_alpha.jsonl" in cb.read(folder=tmp_path / "empty")["reason"]
    few = make(tmp_path / "few")
    (few / "shadow_alpha.jsonl").write_text(json.dumps({"close_ms": CLOSE, "symbol": "BTCUSDT", "alpha": 0.001}) + "\n", encoding="utf-8")
    assert cb.read(folder=few)["status"] == "UNAVAILABLE"
    broken = make(tmp_path / "broken")
    (broken / "ETHUSDT.bars.npy").write_bytes(b"not a file numpy wrote")
    eth = next(r for r in cb.read(now_ms=CLOSE + H, folder=broken)["rows"] if r["coin"] == "ETH")
    assert eth["price"] is None and eth["beta"] is None and eth["rank"] == 2                  # one unreadable coin is empty, the others stand


def test_the_bridge_only_reads_and_asks_no_network(monkeypatch, tmp_path):
    src = (ROOT / "terminal" / "coin_bridge.py").read_text(encoding="utf-8")
    for banned in ("requests", "urllib", "http://", "https://", "shadow_state", "topcoin", "open(", ".write", "os.remove", "unlink"):
        assert banned not in src, banned
    monkeypatch.setenv(cb.ENV, str(tmp_path / "other"))
    assert cb.root() == tmp_path / "other" / "runtime" / "predictor"
    monkeypatch.delenv(cb.ENV)
    assert cb.root() == Path.home() / "Projects" / "horizon_bot_beta" / "runtime" / "predictor"
    folder = make(tmp_path / "p")
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    cb.read(now_ms=CLOSE + H, folder=folder)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


# ---------------------------------------------------------------------- the assistant in the coin market
class Clock:
    base = Path(".")

    @staticmethod
    def now():
        from datetime import datetime, timezone
        return datetime(2026, 11, 21, 12, tzinfo=timezone.utc)


@pytest.fixture()
def coins(tmp_path, monkeypatch):
    folder = make(tmp_path / "p")
    state = {"now": CLOSE + H}
    monkeypatch.setattr(A, "_coin_read", lambda: cb.read(now_ms=state["now"], folder=folder))
    return state


def test_the_coin_days_list_and_its_stale_and_missing_cases(coins, monkeypatch):
    b = A.briefing(Clock(), "COIN")
    kinds = [i["kind"] for i in b["items"]]
    assert b["status"] == "REAL" and b["market"] == "COIN" and kinds == ["COIN_MARKET", "COIN_TOP", "COIN_COST", "COIN_CAVEAT"] and b["orders"] == 0 and "horizon_bot_beta" in b["note"]
    top = b["items"][1]["text"]
    assert "비트코인(BTC) +0.40%" in top and "오를지 내릴지를 말하지 않습니다" in top and "왕복 비용(0.20%)을 넘는 코인은 2개" in b["items"][2]["text"]
    coins["now"] = CLOSE + 11 * 3600_000
    old = A.briefing(Clock(), "COIN")
    assert old["items"][0]["kind"] == "COIN_STALE" and old["items"][0]["level"] == "DUE" and "11시간 전 마감" in old["items"][0]["text"] and "오늘 챙길 것이 1건" in old["headline"]
    monkeypatch.setattr(A, "_coin_read", lambda: cb.read(folder=Path("/nonexistent-coin-folder")))
    none = A.briefing(Clock(), "COIN")
    assert [i["kind"] for i in none["items"]] == ["COIN_UNAVAILABLE"] and none["session"] is None
    monkeypatch.setattr(A, "_coin_read", lambda: (_ for _ in ()).throw(OSError("x")))
    assert A.briefing(Clock(), "COIN")["unread_parts"] == [{"part": "coin", "label": "코인 예측기 자료", "error": "OSError"}]


def test_coin_questions_are_answered_from_the_bridge_and_never_call_a_direction(coins):
    note = A.answer(Clock(), "솔라나 점수 왜 이래?", "COIN")
    assert note["status"] == "REAL" and note["intent"] == "COIN_NOTE" and note["ticker"] == "SOL" and note["market"] == "COIN" and note["tab"] == "coin"
    assert "대상 12개 중 3위" in note["summary"] and "+0.20% 움직일 것으로 본 값" in note["summary"] and "왕복 비용(0.20%)을 넘지 못합니다" in note["summary"] and "오를지 내릴지를 말하는 값이 아닙니다" in note["summary"]
    by = {s["title"]: s["lines"] for s in note["sections"]}
    assert by["점수를 만든 신호 셋"][0].startswith("자금조달비 -0.0100%(8시간마다, 연으로 -1") and "대상 12개 중 낮은 순서로 3위" in by["점수를 만든 신호 셋"][0] and "현물에는 이 비용이 없습니다" in by["점수를 만든 신호 셋"][0]
    assert by["이 점수가 말하지 않는 것"] == cb.CAVEATS and "먼저 알아 둘 것" not in by
    assert A.answer(Clock(), "btc", "COIN")["ticker"] == "BTC" and A.answer(Clock(), "비트코인 분석해 줘", "COIN")["title"] == "비트코인(BTC) 코인 노트"
    top = A.answer(Clock(), "코인 상위는?", "COIN")
    assert top["intent"] == "COIN_TOP" and top["summary"].startswith("상대 순위 1위는 비트코인(BTC)입니다(+0.40%") and "매수 신호가 아닙니다" in top["summary"] and top["follow"][0] == "비트코인 분석해 줘"
    market = A.answer(Clock(), "코인 시장 상태 어때?", "COIN")
    assert market["intent"] == "COIN_MARKET" and "오를지 내릴지를 읽지 마세요" in " ".join(market["lines"])
    trust = A.answer(Clock(), "이 코인 점수 믿어도 돼?", "COIN")
    assert trust["intent"] == "COIN_TRUST" and "-62.7%" in " ".join(trust["lines"]) and "확인된 것은 아닙니다" in trust["summary"]
    helped = A.answer(Clock(), "help", "COIN")
    assert helped["intent"] == "COIN_HELP" and helped["examples"] == A.COIN_EXAMPLES and A.answer(Clock(), "삼성전자 어때", "COIN")["status"] == "UNKNOWN"
    for q in A.COIN_EXAMPLES:
        got = A.answer(Clock(), q, "COIN")
        assert got["status"] == "REAL", q
        for word in ("사세요", "매수하세요", "파세요", "오를 것입니다", "상승할 것"):
            assert word not in json.dumps(got, ensure_ascii=False), (q, word)
    coins["now"] = CLOSE + 12 * 3600_000
    assert A.answer(Clock(), "btc", "COIN")["sections"][0]["title"] == "먼저 알아 둘 것"          # an old score is said first


def test_the_coin_market_is_wired_into_the_server_and_the_screen():
    assert server._market3("COIN") == "COIN" and server._market3("KR") == "KR"
    with pytest.raises(ValueError):
        server._market("COIN")                                                               # stock endpoints still take two markets
    with pytest.raises(ValueError):
        server._market3("JP")
    r = server.routes(Clock())
    assert ("GET", "/api/coin/latest") in r
    html, app, coin = [(server.STATIC / n).read_text(encoding="utf-8") for n in ("index.html", "app.js", "coin.js")]
    assert '<button type="button" data-m="COIN">코인</button>' in html and '<button type="button" data-group="coin" hidden>코인</button>' in html and 'id="tab-coin"' in html
    assert html.index("assistant.js") < html.index("coin.js") < html.index("command.js")
    assert 'const groupShown = (g) => (isCoin() ? g === "today" || g === "coin" : g !== "coin");' in app and 'if (isCoin()) { askAssistant(t);' in app
    assert "RENDER.coin = renderCoin" in coin and "/api/coin/latest" in coin and "esc(r.coin)" in coin and "esc(d.reason" in coin and "주문" in coin.splitlines()[0]
    design = (ROOT / "reports" / "CRYPTO_ENGINE_DESIGN_2026_11_21.md").read_text(encoding="utf-8")
    assert "새 코인 점수를 만들지 않고" in design and "구현 기록" in design
