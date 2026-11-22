"""Chart analysis (CHART-1, 2026-11-23): the classic chart indicators drawn over a stock's daily bars.

Reference only.  Nothing here enters a QSF score, a band, an entry rule, an order plan or a reading, and no QSF module imports
it.  The score's own technical factors live in ``terminal/qsf/technicals.py`` and are left as they are (frozen maths); the two may
differ on purpose: RSI here is Wilder's (what securities apps show, user decision 2026-11-23), the score's is a 14-day simple
average.

User decisions (2026-11-23): a 'chart' group with this tab and the compare tab; classic signals marked on the chart, each said
to be untested; moving averages by market (KR 5/20/60/120, US 20/50/200) that the user can switch; Wilder RSI.
No forward statistics of the signals are computed or shown.

Every series is computed on the whole fetched history and then cut to the asked range, so the first bars of a range are not
warming up.  A value that cannot be computed is None, never 0.
"""
import math
from typing import Any, Dict, List, Optional, Sequence

MA_CHOICES = (5, 10, 20, 50, 60, 120, 200)
MA_DEFAULT = {"KR": (5, 20, 60, 120), "US": (20, 50, 200)}
MA_MAX = 5
CROSS_PAIR = {"KR": (20, 60), "US": (50, 200)}         # the pair whose crossing is called golden / dead in each market's habit
RANGES = {"3mo": ("2y", 63), "6mo": ("2y", 126), "1y": ("2y", 252), "3y": ("10y", 756), "5y": ("10y", 1260), "10y": ("10y", 2520)}
RSI_N, RSI_LOW, RSI_HIGH = 14, 30.0, 70.0
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BB_N, BB_K = 20, 2.0
VOL_N, VOL_SPIKE = 20, 2.0
OBV_N = 20
SIGNAL_LIMIT = 400                    # the most recent signals sent to the screen (ten years of crossings fit)

CAVEAT = ("아래 지표와 신호는 차트를 읽는 오래된 관습이며, 이 프로그램이 하나하나 검증한 적이 없습니다. 이 프로그램의 검증에서 한국 스윙 점수의 "
          "차트 요인 묶음은 오히려 반대로 움직여(IC 음수) 점수에서 뺐습니다. 이 화면은 점수와 섞지 않고, 매매 지시가 아닙니다.")

SIGNAL_TEXT = {
    "GOLDEN_CROSS": ("up", "골든크로스", "짧은 이동평균이 긴 이동평균을 위로 넘었습니다. 관습적으로 오름세가 시작되는 표시로 읽습니다."),
    "DEAD_CROSS": ("down", "데드크로스", "짧은 이동평균이 긴 이동평균 아래로 내려갔습니다. 관습적으로 내림세가 시작되는 표시로 읽습니다."),
    "RSI_OVERSOLD": ("up", "RSI 30 아래", "RSI가 30 아래로 들어갔습니다. 관습적으로 '많이 팔렸다(과매도)'로 읽습니다. 내림세가 이어지는 동안 오래 머물기도 합니다."),
    "RSI_OVERBOUGHT": ("down", "RSI 70 위", "RSI가 70 위로 올라갔습니다. 관습적으로 '많이 샀다(과매수)'로 읽습니다. 강한 오름세에서는 오래 머물기도 합니다."),
    "MACD_UP": ("up", "MACD 상향 교차", "MACD선이 시그널선을 위로 넘었습니다. 관습적으로 오름 힘이 커지는 표시로 읽습니다."),
    "MACD_DOWN": ("down", "MACD 하향 교차", "MACD선이 시그널선 아래로 내려갔습니다. 관습적으로 오름 힘이 약해지는 표시로 읽습니다."),
    "BB_UPPER": ("down", "볼린저 위 띠 돌파", "종가가 볼린저밴드 위 띠 밖으로 나갔습니다. 관습적으로 '단기 과열'로도, '강한 돌파'로도 읽어 해석이 갈립니다."),
    "BB_LOWER": ("up", "볼린저 아래 띠 이탈", "종가가 볼린저밴드 아래 띠 밖으로 나갔습니다. 관습적으로 '단기 과매도'로도, '약세 돌파'로도 읽어 해석이 갈립니다."),
    "VOLUME_SPIKE": (None, "거래량 급증", "거래량이 지난 20거래일 평균의 2배를 넘었습니다. 관습적으로 그날 가격 움직임에 무게를 더 두는 표시로 읽습니다."),
}


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def sma(vals: Sequence[Optional[float]], n: int) -> List[Optional[float]]:
    """Simple moving average; None until n values and wherever the window holds a missing value."""
    out: List[Optional[float]] = []
    for i in range(len(vals)):
        w = vals[i - n + 1:i + 1] if i >= n - 1 else []
        out.append(sum(w) / n if len(w) == n and all(v is not None for v in w) else None)
    return out


def ema(vals: Sequence[Optional[float]], n: int) -> List[Optional[float]]:
    """Exponential moving average seeded with the simple average of the first n values (the usual chart convention).
    It starts at the first run of n present values; a missing value later stops it (None) and it restarts from a new seed."""
    out: List[Optional[float]] = [None] * len(vals)
    k, prev, run = 2.0 / (n + 1), None, []
    for i, v in enumerate(vals):
        if v is None:
            prev, run = None, []
            continue
        if prev is None:
            run.append(v)
            if len(run) == n:
                prev = sum(run) / n
                out[i] = prev
            continue
        prev = v * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi_wilder(closes: Sequence[float], n: int = RSI_N) -> List[Optional[float]]:
    """Wilder's RSI: the first average gain and loss are simple means of n changes, then each is smoothed by (prev*(n-1)+x)/n."""
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= n:
        return out
    ch = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gain = sum(max(c, 0.0) for c in ch[:n]) / n
    loss = sum(max(-c, 0.0) for c in ch[:n]) / n

    def value(g: float, lo: float) -> float:
        return 100.0 if lo == 0 else 100.0 - 100.0 / (1.0 + g / lo)
    out[n] = value(gain, loss)
    for i in range(n, len(ch)):
        gain = (gain * (n - 1) + max(ch[i], 0.0)) / n
        loss = (loss * (n - 1) + max(-ch[i], 0.0)) / n
        out[i + 1] = value(gain, loss)
    return out


def macd(closes: Sequence[float]) -> Dict[str, List[Optional[float]]]:
    fast, slow = ema(closes, MACD_FAST), ema(closes, MACD_SLOW)
    line = [f - s if f is not None and s is not None else None for f, s in zip(fast, slow)]
    sig = ema(line, MACD_SIGNAL)
    hist = [m - s if m is not None and s is not None else None for m, s in zip(line, sig)]
    return {"macd": line, "signal": sig, "hist": hist}


def bollinger(closes: Sequence[float], n: int = BB_N, k: float = BB_K) -> Dict[str, List[Optional[float]]]:
    """Middle = n-day simple average; bands = middle +- k population standard deviations (Bollinger's own definition)."""
    mid = sma(closes, n)
    up: List[Optional[float]] = []
    lo: List[Optional[float]] = []
    for i, m in enumerate(mid):
        if m is None:
            up.append(None)
            lo.append(None)
            continue
        w = closes[i - n + 1:i + 1]
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
        up.append(m + k * sd)
        lo.append(m - k * sd)
    return {"mid": mid, "upper": up, "lower": lo}


def obv(closes: Sequence[float], vols: Sequence[Optional[float]]) -> List[Optional[float]]:
    """On-balance volume from the first bar; a day without volume adds nothing and is marked None in the output."""
    out: List[Optional[float]] = []
    run = 0.0
    for i, c in enumerate(closes):
        v = vols[i]
        if i and v is not None:
            run += v if c > closes[i - 1] else -v if c < closes[i - 1] else 0.0
        out.append(run if v is not None else None)
    return out


def _crossed(a0: Optional[float], b0: Optional[float], a1: Optional[float], b1: Optional[float]) -> int:
    """+1 when a goes from at-or-below b to above it, -1 for the reverse, 0 otherwise or when a value is missing."""
    if None in (a0, b0, a1, b1):
        return 0
    if a0 <= b0 and a1 > b1:
        return 1
    if a0 >= b0 and a1 < b1:
        return -1
    return 0


def _level(prev: Optional[float], now: Optional[float], line: float) -> int:
    if prev is None or now is None:
        return 0
    if prev >= line > now:
        return -1
    if prev <= line < now:
        return 1
    return 0


def signals(dates: Sequence[str], closes: Sequence[float], vols: Sequence[Optional[float]],
            ma: Dict[int, List[Optional[float]]], rsi: List[Optional[float]], mc: Dict[str, List[Optional[float]]],
            bb: Dict[str, List[Optional[float]]], vol_avg: List[Optional[float]], pair: Sequence[int]) -> List[Dict[str, Any]]:
    """Every classic signal over the whole history, oldest first.  A signal is the day a condition starts, not each day it holds."""
    out: List[Dict[str, Any]] = []
    short, long_ = ma.get(pair[0]), ma.get(pair[1])

    def add(i: int, kind: str, side: Optional[str] = None) -> None:
        d, label, text = SIGNAL_TEXT[kind]
        out.append({"i": i, "date": dates[i], "kind": kind, "side": side or d, "label": label, "text": text, "close": closes[i]})
    for i in range(1, len(closes)):
        if short is not None and long_ is not None:
            x = _crossed(short[i - 1], long_[i - 1], short[i], long_[i])
            if x:
                add(i, "GOLDEN_CROSS" if x > 0 else "DEAD_CROSS")
        lv = _level(rsi[i - 1], rsi[i], RSI_LOW)
        if lv < 0:
            add(i, "RSI_OVERSOLD")
        if _level(rsi[i - 1], rsi[i], RSI_HIGH) > 0:
            add(i, "RSI_OVERBOUGHT")
        x = _crossed(mc["macd"][i - 1], mc["signal"][i - 1], mc["macd"][i], mc["signal"][i])
        if x:
            add(i, "MACD_UP" if x > 0 else "MACD_DOWN")
        if _crossed(closes[i - 1], bb["upper"][i - 1], closes[i], bb["upper"][i]) > 0:
            add(i, "BB_UPPER")
        if _crossed(closes[i - 1], bb["lower"][i - 1], closes[i], bb["lower"][i]) < 0:
            add(i, "BB_LOWER")
        avg = vol_avg[i - 1]                     # the average of the 20 days BEFORE this one: the spike day does not lift its own bar
        if vols[i] is not None and avg and vols[i] >= VOL_SPIKE * avg:
            add(i, "VOLUME_SPIKE", "up" if closes[i] > closes[i - 1] else "down" if closes[i] < closes[i - 1] else "flat")      # the day's change
    return out


def _fmt(v: float, market: str) -> str:
    return f"{v:,.0f}" if market == "KR" or abs(v) >= 1000 else f"{v:,.2f}"


def state_lines(market: str, closes: Sequence[float], vols: Sequence[Optional[float]], ma: Dict[int, List[Optional[float]]],
                rsi: List[Optional[float]], mc: Dict[str, List[Optional[float]]], bb: Dict[str, List[Optional[float]]],
                vol_avg: List[Optional[float]], ob: List[Optional[float]]) -> List[Dict[str, str]]:
    """The last bar in plain words, one line per indicator: what the value is, then how the custom reads it."""
    lines: List[Dict[str, str]] = []
    i, c = len(closes) - 1, closes[-1]
    have = [(n, ma[n][i]) for n in sorted(ma) if ma[n][i] is not None]
    if have:
        above = [n for n, v in have if c > v]
        words = ", ".join(f"{n}일선 {'위' if c > v else '아래'}" for n, v in have)
        order = [v for _, v in have]
        if len(order) >= 3 and all(order[k] > order[k + 1] for k in range(len(order) - 1)):
            shape = " 짧은 선이 긴 선보다 차례로 위에 있는 정배열로, 관습적으로 오름세로 읽습니다."
        elif len(order) >= 3 and all(order[k] < order[k + 1] for k in range(len(order) - 1)):
            shape = " 짧은 선이 긴 선보다 차례로 아래에 있는 역배열로, 관습적으로 내림세로 읽습니다."
        else:
            shape = " 선들이 섞여 있어 방향이 뚜렷하지 않은 상태로 읽습니다."
        lines.append({"name": "이동평균", "text": f"마지막 종가({_fmt(c, market)})는 {words}에 있습니다({len(above)}/{len(have)}개 위).{shape}"})
    else:
        lines.append({"name": "이동평균", "text": "고른 이동평균을 계산할 만큼 가격 기록이 길지 않습니다."})
    r = rsi[i]
    if r is None:
        lines.append({"name": "RSI", "text": "RSI를 계산할 만큼 가격 기록이 길지 않습니다."})
    else:
        zone = "30 아래라 관습적으로 과매도로 읽는 구간" if r < RSI_LOW else "70 위라 관습적으로 과매수로 읽는 구간" if r > RSI_HIGH else "30과 70 사이의 보통 구간"
        lines.append({"name": "RSI", "text": f"RSI(14, 와일더 방식) 값은 {r:.1f}, {zone}입니다. 점수 카드의 RSI는 단순 평균 방식이라 몇 점 다를 수 있습니다."})
    m, s, h = mc["macd"][i], mc["signal"][i], mc["hist"][i]
    if m is None or s is None:
        lines.append({"name": "MACD", "text": "MACD를 계산할 만큼 가격 기록이 길지 않습니다."})
    else:
        hp = mc["hist"][i - 1] if i else None
        grow = "" if hp is None or h is None else (" 막대가 전날보다 커졌습니다." if abs(h) > abs(hp) else " 막대가 전날보다 줄었습니다.")
        lines.append({"name": "MACD", "text": f"MACD선이 시그널선 {'위' if m > s else '아래'}에 있고, 0선 {'위' if m > 0 else '아래'}입니다.{grow} "
                                             f"관습적으로 시그널선 위는 오름 힘, 아래는 내림 힘으로 읽습니다."})
    up, lo, mid = bb["upper"][i], bb["lower"][i], bb["mid"][i]
    if up is None or lo is None or up == lo:
        lines.append({"name": "볼린저밴드", "text": "볼린저밴드를 계산할 만큼 가격 기록이 길지 않습니다."})
    else:
        pb = (c - lo) / (up - lo)
        widths = [(bb["upper"][k] - bb["lower"][k]) / bb["mid"][k] for k in range(max(0, i - 251), i + 1)
                  if bb["upper"][k] is not None and bb["mid"][k]]
        wnow = (up - lo) / mid if mid else None
        squeeze = ""
        if wnow is not None and len(widths) >= 120:
            rank = sum(1 for w in widths if w <= wnow) / len(widths)
            if rank <= 0.2:
                squeeze = " 띠 폭이 지난 1년 중 좁은 편(하위 20%)이라, 관습적으로 큰 움직임을 앞둔 '수축'으로 읽습니다."
            elif rank >= 0.8:
                squeeze = " 띠 폭이 지난 1년 중 넓은 편(상위 20%)이라 변동이 큰 상태입니다."
        where = "위 띠 밖" if c > up else "아래 띠 밖" if c < lo else "띠 안"
        lines.append({"name": "볼린저밴드", "text": f"종가가 {where}에 있고, 띠 안의 위치는 {pb * 100:.0f}%입니다(0%=아래 띠, 100%=위 띠).{squeeze}"})
    v, a = vols[i], vol_avg[i - 1] if i else None
    if v is None or not a:
        lines.append({"name": "거래량", "text": "거래량 자료가 없어 비교하지 않았습니다."})
    else:
        ratio = v / a
        word = "많은" if ratio >= 1.5 else "적은" if ratio <= 0.67 else "보통"
        obv_txt = ""
        if len(closes) > OBV_N and ob[i] is not None and ob[i - OBV_N] is not None:
            po, pp = ob[i] - ob[i - OBV_N], c - closes[i - OBV_N]
            if po > 0 > pp or po < 0 < pp:
                obv_txt = (f" 지난 {OBV_N}거래일 가격은 {'올랐는데' if pp > 0 else '내렸는데'} OBV(거래량 누적)는 {'줄어' if po < 0 else '늘어'}, "
                           "관습적으로 가격과 거래량이 엇갈리는 '다이버전스'로 읽습니다.")
            else:
                obv_txt = f" 지난 {OBV_N}거래일 가격과 OBV(거래량 누적)가 같은 쪽으로 움직였습니다."
        lines.append({"name": "거래량", "text": f"마지막 날 거래량은 지난 {VOL_N}거래일 평균의 {ratio:.1f}배로 {word} 편입니다.{obv_txt}"})
    return lines


def analyse(rows: List[Dict[str, Any]], market: str, keep: int, ma_periods: Sequence[int]) -> Dict[str, Any]:
    """Daily bars (oldest first) -> per-bar indicators for the last ``keep`` bars, the classic signals inside them and the last bar
    in plain words.  Rows without a usable close are dropped; a missing open/high/low/volume stays None."""
    rows = [r for r in rows if _num(r.get("close")) is not None and r.get("date")]
    if len(rows) < 2:
        return {"status": "UNAVAILABLE", "bars": [], "signals": [], "lines": []}
    dates = [r["date"] for r in rows]
    closes = [float(r["close"]) for r in rows]
    opens = [_num(r.get("open")) for r in rows]
    vols = [_num(r.get("volume")) for r in rows]
    ma = {n: sma(closes, n) for n in sorted(set(ma_periods) | set(CROSS_PAIR.get(market, CROSS_PAIR["US"])))}
    rsi = rsi_wilder(closes)
    mc = macd(closes)
    bb = bollinger(closes)
    vol_avg = sma(vols, VOL_N)
    ob = obv(closes, vols)
    pair = CROSS_PAIR.get(market, CROSS_PAIR["US"])
    start = max(0, len(rows) - keep)

    def rnd(v: Optional[float], d: int = 6) -> Optional[float]:
        return None if v is None else round(v, d)
    bars = []
    for i in range(start, len(rows)):
        r = rows[i]
        bars.append({"date": dates[i], "open": opens[i], "high": _num(r.get("high")), "low": _num(r.get("low")), "close": closes[i], "volume": vols[i],
                     "ma": {str(n): rnd(ma[n][i]) for n in ma_periods},
                     "bb_mid": rnd(bb["mid"][i]), "bb_up": rnd(bb["upper"][i]), "bb_low": rnd(bb["lower"][i]),
                     "rsi": rnd(rsi[i], 2), "macd": rnd(mc["macd"][i]), "macd_signal": rnd(mc["signal"][i]), "macd_hist": rnd(mc["hist"][i]),
                     "vol_avg": rnd(vol_avg[i], 1), "obv": ob[i]})
    sig = [{**s, "i": s["i"] - start} for s in signals(dates, closes, vols, ma, rsi, mc, bb, vol_avg, pair) if s["i"] >= start]
    return {"status": "REAL", "bars": bars, "signals": sig[-SIGNAL_LIMIT:], "signal_count": len(sig),
            "lines": state_lines(market, closes, vols, ma, rsi, mc, bb, vol_avg, ob), "cross_pair": list(pair), "ma": list(ma_periods)}


def ma_periods(raw: str, market: str) -> List[int]:
    """The asked moving averages: known lengths only, at most MA_MAX, in order; nothing usable gives the market's default."""
    got: List[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) in MA_CHOICES and int(part) not in got:
            got.append(int(part))
    return sorted(got[:MA_MAX]) or list(MA_DEFAULT.get(market, MA_DEFAULT["US"]))


def settings() -> Dict[str, Any]:
    """What the screen shows as fixed settings, so the page never repeats a number of its own."""
    return {"ma_choices": list(MA_CHOICES), "ma_default": {k: list(v) for k, v in MA_DEFAULT.items()}, "ma_max": MA_MAX,
            "cross_pair": {k: list(v) for k, v in CROSS_PAIR.items()}, "ranges": list(RANGES),
            "rsi": {"n": RSI_N, "low": RSI_LOW, "high": RSI_HIGH, "method": "WILDER"}, "macd": [MACD_FAST, MACD_SLOW, MACD_SIGNAL],
            "bollinger": {"n": BB_N, "k": BB_K}, "volume": {"n": VOL_N, "spike": VOL_SPIKE}, "caveat": CAVEAT,
            "signal_names": {k: v[1] for k, v in SIGNAL_TEXT.items()}}
