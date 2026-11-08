"""Korean broad sectors: every KRX industry has exactly one group; holding companies and cosmetics are placed by rule."""
import gzip
import json

from terminal import kr_sectors as ks


def test_each_industry_once_and_only_known_groups():
    names = [i for v in ks._BY_SECTOR.values() for i in v]
    assert len(names) == len(set(names))
    assert set(ks._BY_SECTOR) <= set(ks.SECTORS)
    assert ks.HOLDCO_INDUSTRY not in ks.INDUSTRY_SECTOR


def test_holding_companies_and_exceptions():
    assert ks.broad_sector("105560", "기타 금융업", "KB금융") == "금융"
    assert ks.broad_sector("316140", "기타 금융업", "우리금융지주") == "금융"
    assert ks.broad_sector("003550", "기타 금융업", "LG") == "지주회사"
    assert ks.broad_sector("090430", "기타 화학제품 제조업", "아모레퍼시픽") == "필수소비재"
    assert ks.broad_sector("357780", "기타 화학제품 제조업", "솔브레인") == "소재"
    assert ks.broad_sector("000660", "반도체 제조업", "SK하이닉스") == "기술"


def test_unknown_or_missing_industry_is_not_guessed():
    assert ks.broad_sector("999999", "새로 생긴 업종", "x") is None
    assert ks.broad_sector("999999", None, "x") is None


def test_service_reads_master_industry_and_sector(tmp_path):
    from terminal.qsf.service import QSF
    sdir = tmp_path / "data" / "kr" / "security_master"
    sdir.mkdir(parents=True)
    csv = "canonical_ticker,company_name,industry\n105560,KB금융,기타 금융업\n000660,SK하이닉스,반도체 제조업\n"
    (sdir / "m.csv.gz").write_bytes(gzip.compress(csv.encode("utf-8")))
    (sdir / "LATEST.json").write_text(json.dumps({"file": "m.csv.gz"}), encoding="utf-8")
    q = QSF(tmp_path)
    assert q.kr_sector("000660") == {"industry": "반도체 제조업", "sector": "기술"}
    assert q.kr_sector("105560")["sector"] == "금융"
    assert q.kr_sector("123456") == {"industry": None, "sector": None}
