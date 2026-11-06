"""Short selling research: nothing is used before publication, missing stays empty, a second test is refused.  No network."""
import gzip
import json

import numpy as np
import pytest

from terminal.qsf import research_short as sh


def test_symbols_are_matched_without_punctuation():
    assert sh.norm("BRK-B") == "BRKB" == sh.norm("BRK.B")


def test_short_interest_waits_for_publication_and_expires():
    days = ["2024-01-15", "2024-01-31"]
    assert sh.latest_usable(days, "2024-01-30") is None
    assert sh.latest_usable(days, "2024-01-31") == 0        # 15th + 16 days
    assert sh.latest_usable(days, "2024-02-15") == 0        # the 31st is not out yet
    assert sh.latest_usable(days, "2024-02-16") == 1
    assert sh.latest_usable(days, "2024-03-17") is None     # more than 45 days old


SI = "\n".join(["accountingYearMonthNumber|symbolCode|currentShortPositionQuantity|averageDailyVolumeQuantity|settlementDate",
                "20240115|BRKB|100|50|2024-01-15", "20240115|ZZZZ|5|5|2024-01-15", "20240115|AAA||7|2024-01-15"])


def test_parse_keeps_the_sample_and_leaves_a_blank_empty():
    out = sh.parse_si(SI, {"BRKB": "BRK-B", "AAA": "AAA"})
    assert out == {"BRK-B": [100.0, 50.0], "AAA": [None, 7.0]}


def test_parse_volume_and_empty_file():
    text = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n20240102|AAA|30|0|60|B,Q\n20240102|ZZZ|1|0|2|B"
    assert sh.parse_sv(text, {"AAA": "AAA"}) == {"AAA": [30.0, 60.0]}
    assert sh.parse_sv("", {"AAA": "AAA"}) == {} and sh.parse_si("", {"AAA": "AAA"}) == {}


def test_settlement_candidates_step_back_over_a_weekend():
    tries = sh.settlement_candidates("2023-07-01", "2023-07-31")
    assert tries[0][0] == "2023-07-14" and tries[1][0] == "2023-07-31"      # the 15th was a Saturday


def save(path, rows):
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(rows, fh)


def test_a_missing_share_count_or_volume_stays_empty_not_zero(tmp_path):
    save(tmp_path / "si_2024-01-15.json.gz", {"AAA": [100.0, 0.0], "BBB": [100.0, 50.0]})
    days, dtc, ratio = sh.si_series(tmp_path, ["AAA", "BBB"], lambda t, d: 1000.0 if t == "BBB" else None)
    assert days == ["2024-01-15"] and np.isnan(dtc[0, 0]) and dtc[0, 1] == 2
    assert np.isnan(ratio[0, 0]) and ratio[0, 1] == pytest.approx(0.1)


def test_shares_are_asked_as_of_each_settlement(tmp_path):
    for d in ("2024-01-15", "2024-01-31"):
        save(tmp_path / f"si_{d}.json.gz", {"AAA": [10.0, 1.0]})
    asked = []
    sh.si_series(tmp_path, ["AAA"], lambda t, d: asked.append(d) or 100.0)
    assert asked == ["2024-01-15", "2024-01-31"]


def features(day, i=99):
    settle = [f"2023-{m:02d}-15" for m in range(1, 10)]
    dtc, ratio = np.arange(9.0)[:, None] + 1, np.arange(9.0)[:, None] / 10
    sv = np.full((100, 1), 0.5, dtype=np.float32)
    sv[95:] = 0.7
    return sh.features_at(day, i, [0], settle, dtc, ratio, sv)[0]


def test_features_read_only_the_published_settlement():
    f = features("2023-08-31")       # 08-15 + 16 days; 09-15 is not out
    assert f[0] == 8 and f[1] == pytest.approx(0.7) and f[2] == pytest.approx(0.6)
    assert f[3] == pytest.approx((15 * 0.5 + 5 * 0.7) / 20) and f[4] == pytest.approx(0.7 - (55 * 0.5 + 5 * 0.7) / 60)


def test_change_needs_the_older_settlement_and_a_stock_outside_the_sample_is_empty():
    assert np.isnan(features("2023-02-01")[2])
    out = sh.features_at("2023-08-31", 99, [], ["2023-08-15"], np.ones((1, 1)), np.ones((1, 1)), np.ones((100, 1), dtype=np.float32))
    assert np.isnan(out).all()


def test_too_few_volume_days_leave_the_ratio_empty():
    sv = np.full((100, 1), np.nan, dtype=np.float32)
    sv[-3:] = 0.5
    f = sh.features_at("2023-08-31", 99, [0], [], np.empty((0, 1)), np.empty((0, 1)), sv)[0]
    assert np.isnan(f).all()


class Resp:
    def __init__(self, code, body=""):
        self.status_code, self.content = code, body.encode()


def test_a_rate_limit_stops_the_download(tmp_path):
    with pytest.raises(sh.Refused):
        sh.download(tmp_path, ["AAA"], ["2018-08-01"], lambda u, headers, timeout: Resp(429), sleep=lambda s: None)


def test_a_kept_file_is_not_asked_again_and_no_address_is_sent(tmp_path):
    urls = []

    def get(url, headers, timeout):
        urls.append(url)
        assert "@" not in headers["User-Agent"]
        return Resp(200, "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n20180801|AAA|1|0|2|B" if "regsho" in url else "symbolCode|currentShortPositionQuantity|averageDailyVolumeQuantity\nAAA|1|2")
    sh.download(tmp_path, ["AAA"], ["2018-08-01"], get, sleep=lambda s: None)
    n = len(urls)
    assert n and (tmp_path / "sv_2018-08-01.json.gz").exists()
    sh.download(tmp_path, ["AAA"], ["2018-08-01"], get, sleep=lambda s: None)
    assert len(urls) == n


def test_the_second_test_is_refused(tmp_path):
    p = tmp_path / sh.TEST_REPORT
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    with pytest.raises(RuntimeError):
        sh.test_once(tmp_path)
