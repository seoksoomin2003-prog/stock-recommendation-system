"""SQLite, indexed and lazy P5 historical financial/market data repository."""

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from contracts.historical_data import (
    CorporateActionEvent, CorporateActionType, FactPeriodType,
    HistoricalFinancialFact, HistoricalFinancialSnapshot, HistoricalPriceBar,
    PITInformationSet,
)
from contracts.normalized_data import DataStatus


SUPPORTED_METRICS = (
    "revenue", "net_income", "operating_income", "gross_profit", "total_assets",
    "total_liabilities", "shareholders_equity", "cash", "debt", "eps",
    "shares_outstanding", "roe", "profit_margin", "pe", "pb",
)
_INSTANT_METRICS = {"total_assets", "total_liabilities", "shareholders_equity", "cash", "debt", "shares_outstanding"}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return _utc(value).isoformat().replace("+00:00", "Z") if value else None


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class HistoricalDataRepository:
    """Stores only acquired records; it never synthesizes market history."""

    def __init__(self, db_path: str = "data/historical_data.db", *, allow_synthetic: bool = False):
        self.db_path = db_path
        self.allow_synthetic = allow_synthetic
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS historical_financial_facts (
              fact_id INTEGER PRIMARY KEY, security_id TEXT NOT NULL, provider TEXT NOT NULL, source TEXT NOT NULL,
              accession_number TEXT, taxonomy TEXT NOT NULL, concept TEXT NOT NULL, normalized_metric TEXT NOT NULL,
              period_start TEXT, period_end TEXT NOT NULL, filed_at TEXT NOT NULL, accepted_at TEXT, value REAL NOT NULL,
              unit TEXT NOT NULL, form_type TEXT NOT NULL, fiscal_year INTEGER, fiscal_period TEXT, is_amended INTEGER NOT NULL,
              is_restated INTEGER NOT NULL, source_url TEXT, observed_at TEXT, ingested_at TEXT NOT NULL,
              schema_version TEXT NOT NULL, period_type TEXT NOT NULL, source_id TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_financial_fact_identity ON historical_financial_facts
              (security_id, provider, source_id, accession_number, concept, period_end, unit);
            CREATE INDEX IF NOT EXISTS idx_financial_pit ON historical_financial_facts
              (security_id, normalized_metric, period_end, filed_at, accepted_at);
            CREATE TABLE IF NOT EXISTS historical_price_bars (
              security_id TEXT NOT NULL, provider TEXT NOT NULL, date TEXT NOT NULL, open REAL, high REAL, low REAL,
              close REAL, adjusted_close REAL, volume REAL, source TEXT NOT NULL, observed_at TEXT, ingested_at TEXT NOT NULL,
              schema_version TEXT NOT NULL, source_id TEXT, PRIMARY KEY (security_id, provider, date, source_id)
            );
            CREATE INDEX IF NOT EXISTS idx_price_pit ON historical_price_bars (security_id, date);
            CREATE TABLE IF NOT EXISTS historical_corporate_actions (
              event_id TEXT PRIMARY KEY, security_id TEXT NOT NULL, event_type TEXT NOT NULL, effective_at TEXT NOT NULL,
              announced_at TEXT, old_value TEXT, new_value TEXT, ratio REAL, cash_amount REAL, shares_affected REAL,
              source TEXT NOT NULL, source_url TEXT, observed_at TEXT, is_verified INTEGER NOT NULL, schema_version TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_action_pit ON historical_corporate_actions (security_id, announced_at, effective_at);
            """)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(historical_financial_facts)")
            columns = [info[1] for info in cursor.fetchall()]
            if "prevrpt" not in columns:
                conn.execute("ALTER TABLE historical_financial_facts ADD COLUMN prevrpt INTEGER DEFAULT 0")

    def add_financial_fact(self, fact: HistoricalFinancialFact) -> None:
        self._reject_synthetic(fact.source)
        self._validate_provenance(fact.security_id, fact.provider, fact.source, fact.source_id)
        if fact.normalized_metric not in SUPPORTED_METRICS:
            raise ValueError("unsupported_normalized_metric")
        if fact.period_end > _utc(fact.filed_at).date():
            raise ValueError("period_end_after_filing")
        if fact.accepted_at and _utc(fact.accepted_at) < _utc(fact.filed_at):
            raise ValueError("accepted_before_filed")
        expected = FactPeriodType.INSTANT if fact.normalized_metric in _INSTANT_METRICS else FactPeriodType.DURATION
        if fact.period_type != expected:
            raise ValueError("metric_period_type_mismatch")
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute("""SELECT value, filed_at, accepted_at FROM historical_financial_facts
                WHERE security_id=? AND provider=? AND source_id IS ? AND accession_number IS ?
                  AND concept=? AND period_end=? AND unit=?""", (fact.security_id, fact.provider, fact.source_id,
                fact.accession_number, fact.concept, fact.period_end.isoformat(), fact.unit)).fetchone()
            canonical = (fact.value, _iso(fact.filed_at), _iso(fact.accepted_at))
            if existing:
                if tuple(existing) == canonical:
                    return  # immutable source record: idempotent repeated acquisition
                raise ValueError("duplicate_historical_financial_record_conflict")
            conn.execute("""INSERT INTO historical_financial_facts (
              security_id, provider, source, accession_number, taxonomy, concept, normalized_metric,
              period_start, period_end, filed_at, accepted_at, value, unit, form_type, fiscal_year,
              fiscal_period, is_amended, is_restated, source_url, observed_at, ingested_at,
              schema_version, period_type, source_id, prevrpt
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                fact.security_id, fact.provider, fact.source, fact.accession_number, fact.taxonomy, fact.concept,
                fact.normalized_metric, fact.period_start.isoformat() if fact.period_start else None, fact.period_end.isoformat(),
                _iso(fact.filed_at), _iso(fact.accepted_at), fact.value, fact.unit, fact.form_type, fact.fiscal_year,
                fact.fiscal_period, int(fact.is_amended), int(fact.is_restated), fact.source_url, _iso(fact.observed_at),
                _iso(fact.ingested_at or datetime.now(timezone.utc)), fact.schema_version, fact.period_type.value, fact.source_id,
                fact.prevrpt or 0))

    def add_price_bar(self, bar: HistoricalPriceBar) -> None:
        self._reject_synthetic(bar.source)
        self._validate_provenance(bar.security_id, bar.provider, bar.source, bar.source_id)
        self._validate_price_bar(bar)
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute("""SELECT open, high, low, close, adjusted_close, volume FROM historical_price_bars
                WHERE security_id=? AND provider=? AND date=? AND source_id=?""",
                (bar.security_id, bar.provider, bar.date.isoformat(), bar.source_id or "")).fetchone()
            canonical = (bar.open, bar.high, bar.low, bar.close, bar.adjusted_close, bar.volume)
            if existing:
                if tuple(existing) == canonical:
                    return
                raise ValueError("duplicate_historical_price_record_conflict")
            conn.execute("INSERT INTO historical_price_bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                bar.security_id, bar.provider, bar.date.isoformat(), bar.open, bar.high, bar.low, bar.close,
                bar.adjusted_close, bar.volume, bar.source, _iso(bar.observed_at),
                _iso(bar.ingested_at or datetime.now(timezone.utc)), bar.schema_version, bar.source_id or ""))

    def add_corporate_action(self, event: CorporateActionEvent) -> None:
        self._reject_synthetic(event.source)
        self._validate_provenance(event.security_id, "corporate_action", event.source, event.event_id)
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute("SELECT event_id FROM historical_corporate_actions WHERE event_id=?", (event.event_id,)).fetchone()
            if existing:
                return
            conn.execute("INSERT INTO historical_corporate_actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                event.event_id, event.security_id, event.event_type.value, _iso(event.effective_at), _iso(event.announced_at),
                event.old_value, event.new_value, event.ratio, event.cash_amount, event.shares_affected, event.source,
                event.source_url, _iso(event.observed_at), int(event.is_verified), event.schema_version))

    def financial_snapshot(self, security_id: str, as_of: datetime) -> HistoricalFinancialSnapshot:
        as_of = _utc(as_of)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""SELECT * FROM historical_financial_facts WHERE security_id=?
              AND period_end <= ? AND filed_at <= ? AND (accepted_at IS NULL OR accepted_at <= ?)
              ORDER BY normalized_metric, period_end DESC, COALESCE(accepted_at, filed_at) DESC,
                       filed_at DESC, is_amended DESC, is_restated DESC, COALESCE(accession_number,'' ) DESC, fact_id DESC""",
              (security_id, as_of.date().isoformat(), _iso(as_of), _iso(as_of))).fetchall()
        facts: Dict[str, HistoricalFinancialFact] = {}
        for row in rows:
            metric = row["normalized_metric"]
            if metric not in facts:  # first row is deterministic selection, never arbitrary DB order
                facts[metric] = self._fact(row)
        metrics = {metric: facts[metric].value if metric in facts else None for metric in SUPPORTED_METRICS}
        # Derived metrics require every input fact to be PIT-available (the selected facts already are).
        derived_lineage = {}
        if metrics["roe"] is None and metrics["net_income"] is not None and metrics["shareholders_equity"] not in (None, 0):
            metrics["roe"] = metrics["net_income"] / metrics["shareholders_equity"]
            derived_lineage["roe"] = {"formula": "net_income / shareholders_equity", "inputs": ["net_income", "shareholders_equity"],
                                      "accession_numbers": [facts["net_income"].accession_number, facts["shareholders_equity"].accession_number],
                                      "as_of": _iso(as_of)}
        if metrics["profit_margin"] is None and metrics["net_income"] is not None and metrics["revenue"] not in (None, 0):
            metrics["profit_margin"] = metrics["net_income"] / metrics["revenue"]
            derived_lineage["profit_margin"] = {"formula": "net_income / revenue", "inputs": ["net_income", "revenue"],
                                                "accession_numbers": [facts["net_income"].accession_number, facts["revenue"].accession_number],
                                                "as_of": _iso(as_of)}
        present = len(facts)
        status = DataStatus.REAL if present else DataStatus.UNAVAILABLE
        selected = list(facts.values())
        latest = max((_utc(f.filed_at) for f in selected), default=None)
        accepted = max((_utc(f.accepted_at) for f in selected if f.accepted_at), default=None)
        observed = max((_utc(f.observed_at) for f in selected if f.observed_at), default=None)
        return HistoricalFinancialSnapshot(security_id, as_of, metrics, facts, status,
            ",".join(sorted({f.source for f in selected})) if selected else "unavailable", 1.0 if present else 0.0,
            observed, latest, accepted, False, False,
            {**{m: {"accession_number": f.accession_number, "source_id": f.source_id, "filed_at": _iso(f.filed_at),
                      "accepted_at": _iso(f.accepted_at), "unit": f.unit, "period_type": f.period_type.value} for m, f in facts.items()},
             "derived_metrics": derived_lineage},
            present / len(SUPPORTED_METRICS))

    def price_bars(self, security_id: str, as_of: datetime, start: Optional[date] = None) -> List[HistoricalPriceBar]:
        params = [security_id, _utc(as_of).date().isoformat()]
        sql = "SELECT * FROM historical_price_bars WHERE security_id=? AND date <= ?"
        if start:
            sql += " AND date >= ?"; params.append(start.isoformat())
        sql += " ORDER BY date ASC, provider ASC, source_id ASC"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [self._bar(r) for r in conn.execute(sql, params).fetchall()]

    def corporate_actions(self, security_id: str, as_of: datetime) -> List[CorporateActionEvent]:
        as_of = _iso(_utc(as_of))
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""SELECT * FROM historical_corporate_actions WHERE security_id=?
              AND COALESCE(announced_at, effective_at) <= ? ORDER BY COALESCE(announced_at,effective_at), event_id""",
              (security_id, as_of)).fetchall()
        return [self._action(r) for r in rows]

    def information_set(self, security_id: str, as_of: datetime, universe_state=None) -> PITInformationSet:
        financials = self.financial_snapshot(security_id, as_of)
        prices = self.price_bars(security_id, as_of)
        actions = self.corporate_actions(security_id, as_of)
        statuses = [financials.availability_status, DataStatus.REAL if prices else DataStatus.UNAVAILABLE]
        status = DataStatus.REAL if all(s == DataStatus.REAL for s in statuses) else DataStatus.UNAVAILABLE
        provenance = {"financials": financials.provenance, "prices": [{"source": p.source, "source_id": p.source_id} for p in prices],
                      "corporate_actions": [{"event_id": a.event_id, "source": a.source, "information_available_at": _iso(a.information_available_at())} for a in actions]}
        payload = json.dumps({"security_id": security_id, "as_of": _iso(_utc(as_of)), "provenance": provenance,
                              "metrics": financials.metrics, "prices": [asdict(p) for p in prices]}, default=str, sort_keys=True)
        return PITInformationSet(security_id, _utc(as_of), universe_state, financials, prices, actions, provenance,
            (financials.completeness + (1.0 if prices else 0.0)) / 2, status, min(financials.confidence, 1.0 if prices else 0.0),
            hashlib.sha256(payload.encode()).hexdigest())

    def production_historical_repository_contains_no_synthetic_records(self) -> bool:
        """Invariant for production repositories; fixtures must opt in explicitly."""
        with sqlite3.connect(self.db_path) as conn:
            for table in ("historical_financial_facts", "historical_price_bars", "historical_corporate_actions"):
                if conn.execute(f"SELECT 1 FROM {table} WHERE upper(source) LIKE '%SYNTHETIC%' LIMIT 1").fetchone():
                    return False
        return True

    def coverage_summary(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            return {
                "financial_facts": conn.execute("SELECT count(*) FROM historical_financial_facts").fetchone()[0],
                "price_bars": conn.execute("SELECT count(*) FROM historical_price_bars").fetchone()[0],
                "corporate_actions": conn.execute("SELECT count(*) FROM historical_corporate_actions").fetchone()[0],
                "securities": conn.execute("""SELECT count(*) FROM (SELECT security_id FROM historical_financial_facts
                    UNION SELECT security_id FROM historical_price_bars UNION SELECT security_id FROM historical_corporate_actions)""").fetchone()[0],
            }

    def _reject_synthetic(self, source: str) -> None:
        if not self.allow_synthetic:
            s_upper = (source or "").upper()
            if any(marker in s_upper for marker in ("SYNTHETIC", "TEST FIXTURE", "TEST_FIXTURE", "MOCK", "GENERATED")):
                raise ValueError("synthetic_records_forbidden_in_production_repository")

    @staticmethod
    def _validate_provenance(security_id: str, provider: str, source: str, source_id: Optional[str]) -> None:
        if not security_id or not security_id.strip():
            raise ValueError("historical_security_id_required")
        if not provider or not provider.strip() or not source or not source.strip() or not source_id or not source_id.strip():
            raise ValueError("historical_provenance_incomplete")

    @staticmethod
    def _validate_price_bar(bar: HistoricalPriceBar) -> None:
        prices = [v for v in (bar.open, bar.high, bar.low, bar.close, bar.adjusted_close) if v is not None]
        if any(v < 0 for v in prices) or (bar.volume is not None and bar.volume < 0):
            raise ValueError("negative_price_or_volume")
        if bar.high is not None and any(v is not None and v > bar.high for v in (bar.open, bar.low, bar.close)):
            raise ValueError("ohlc_above_high")
        if bar.low is not None and any(v is not None and v < bar.low for v in (bar.open, bar.high, bar.close)):
            raise ValueError("ohlc_below_low")

    @staticmethod
    def _fact(r: sqlite3.Row) -> HistoricalFinancialFact:
        prevrpt_val = 0
        try:
            prevrpt_val = r["prevrpt"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            pass
        return HistoricalFinancialFact(r["security_id"], r["provider"], r["source"], r["accession_number"], r["taxonomy"],
            r["concept"], r["normalized_metric"], date.fromisoformat(r["period_start"]) if r["period_start"] else None,
            date.fromisoformat(r["period_end"]), _dt(r["filed_at"]), _dt(r["accepted_at"]), r["value"], r["unit"], r["form_type"],
            r["fiscal_year"], r["fiscal_period"], bool(r["is_amended"]), bool(r["is_restated"]), r["source_url"],
            _dt(r["observed_at"]), _dt(r["ingested_at"]), r["schema_version"], FactPeriodType(r["period_type"]), r["source_id"], prevrpt=prevrpt_val)

    @staticmethod
    def _bar(r: sqlite3.Row) -> HistoricalPriceBar:
        return HistoricalPriceBar(r["security_id"], r["provider"], date.fromisoformat(r["date"]), r["open"], r["high"], r["low"],
            r["close"], r["adjusted_close"], r["volume"], r["source"], _dt(r["observed_at"]), _dt(r["ingested_at"]), r["schema_version"], r["source_id"])

    @staticmethod
    def _action(r: sqlite3.Row) -> CorporateActionEvent:
        return CorporateActionEvent(r["security_id"], r["event_id"], CorporateActionType(r["event_type"]), _dt(r["effective_at"]),
            _dt(r["announced_at"]), r["old_value"], r["new_value"], r["ratio"], r["cash_amount"], r["shares_affected"],
            r["source"], r["source_url"], _dt(r["observed_at"]), bool(r["is_verified"]), r["schema_version"])
