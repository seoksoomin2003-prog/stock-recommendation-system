"""Capital entered on screen is saved in .env without touching any other line, and one market never fills the other."""
import pytest

from terminal.services import Terminal


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("QPP_CAPITAL", raising=False)
    monkeypatch.delenv("QPP_CAPITAL_KRW", raising=False)


def test_capital_is_saved_without_touching_other_env_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# note\nSEC_USER_AGENT=keep me\n# QPP_CAPITAL=1\nQPP_CAPITAL=\nQPP_CAPITAL=2\n", encoding="utf-8")
    env.chmod(0o600)
    t = Terminal(tmp_path)
    assert t.capital("US")["amount"] is None
    assert t.capital_set({"market": "US", "amount": "50,000"})["amount"] == 50000
    assert env.read_text(encoding="utf-8") == "# note\nSEC_USER_AGENT=keep me\n# QPP_CAPITAL=1\nQPP_CAPITAL=50000\n"
    assert env.stat().st_mode & 0o777 == 0o600
    assert t.capital("US")["amount"] == 50000
    assert t.capital("KR")["amount"] is None


def test_each_market_has_its_own_line_and_can_be_cleared(tmp_path):
    env = tmp_path / ".env"
    t = Terminal(tmp_path)
    t.capital_set({"market": "US", "amount": 50000.5})
    assert t.capital_set({"market": "KR", "amount": 10000000})["currency"] == "KRW"
    assert env.read_text(encoding="utf-8") == "QPP_CAPITAL=50000.5\nQPP_CAPITAL_KRW=10000000\n"
    assert t.capital_set({"market": "US", "amount": ""})["amount"] is None
    assert env.read_text(encoding="utf-8") == "QPP_CAPITAL_KRW=10000000\n"


def test_bad_capital_changes_nothing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("QPP_CAPITAL=100\n", encoding="utf-8")
    t = Terminal(tmp_path)
    for bad in ("-5", "abc", "0", "nan"):
        with pytest.raises(ValueError):
            t.capital_set({"market": "US", "amount": bad})
    with pytest.raises(ValueError):
        t.capital_set({"market": "JP", "amount": 5})
    assert env.read_text(encoding="utf-8") == "QPP_CAPITAL=100\n"


def test_unreadable_saved_value_reads_as_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL", "abc")
    c = Terminal(tmp_path).capital("US")
    assert c["amount"] is None and c["invalid"] is True
