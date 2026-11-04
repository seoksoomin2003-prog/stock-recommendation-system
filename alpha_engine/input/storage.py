import sqlite3
import json
import time
from typing import List, Dict, Optional, Tuple, Any
from utils.logger import setup_logger

logger = setup_logger("TickerStorage")

class TickerStorage:
    """
    SECTION 1: Production-Ready SQLite Storage Layer
    - Multi-table schema for tickers, aliases, and tokens.
    - Tiered cache for usage-aware resolution.
    """
    def __init__(self, db_path: str = "data/tickers.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes production schema and indexes."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. CORE: TICKER MASTER TABLE
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL UNIQUE,
                    company_name TEXT NOT NULL,
                    exchange TEXT,
                    country TEXT,
                    sector TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 2. ALIAS TABLE
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker_id INTEGER NOT NULL,
                    alias TEXT NOT NULL,
                    source TEXT,  -- "news", "sec", "api", "manual"
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ticker_id) REFERENCES tickers(id)
                )
            """)
            
            # 3. TOKEN INDEX TABLE
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alias_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias_id INTEGER NOT NULL,
                    token TEXT NOT NULL,
                    FOREIGN KEY (alias_id) REFERENCES aliases(id)
                )
            """)
            
            # 4. LOOKUP CACHE (Tiered TTL Support)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lookup_cache (
                    query TEXT PRIMARY KEY,
                    ticker TEXT,
                    confidence REAL,
                    last_used REAL,
                    hit_count INTEGER DEFAULT 0,
                    usage_tier TEXT DEFAULT 'COLD' -- 'HOT', 'WARM', 'COLD'
                )
            """)
            
            # Indexes for extreme performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticker ON tickers(ticker)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_company ON tickers(company_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias ON aliases(alias)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_token ON alias_tokens(token)")
            
            conn.commit()
        logger.info(f"Production TickerStorage initialized at {self.db_path}")

    def add_ticker(self, ticker: str, company_name: str, exchange: str = None, sector: str = None) -> int:
        """Adds a ticker and returns its ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tickers WHERE ticker = ?", (ticker.upper(),))
            row = cursor.fetchone()
            if row:
                return row[0]
            cursor.execute("""
                INSERT OR REPLACE INTO tickers (ticker, company_name, exchange, sector)
                VALUES (?, ?, ?, ?)
            """, (ticker.upper(), company_name, exchange, sector))
            conn.commit()
            return cursor.lastrowid

    def add_alias(self, ticker_id: int, alias: str, source: str = "manual", confidence: float = 1.0) -> int:
        """Adds an alias and returns its ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO aliases (ticker_id, alias, source, confidence)
                VALUES (?, ?, ?, ?)
            """, (ticker_id, alias.lower().strip(), source, confidence))
            conn.commit()
            return cursor.lastrowid

    def add_token(self, alias_id: int, token: str):
        """Adds a searchable token for an alias."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO alias_tokens (alias_id, token) VALUES (?, ?)", (alias_id, token.lower().strip()))
            conn.commit()

    def get_cache(self, query: str) -> Optional[Dict]:
        """Retrieves cached resolution result."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM lookup_cache WHERE query = ?", (query.lower().strip(),))
            row = cursor.fetchone()
            if row:
                # Update hit count for hit-based TTL
                cursor.execute("""
                    UPDATE lookup_cache SET 
                    hit_count = hit_count + 1,
                    last_used = ?,
                    usage_tier = CASE WHEN hit_count + 1 > 50 THEN 'HOT' 
                                      WHEN hit_count + 1 > 10 THEN 'WARM' 
                                      ELSE 'COLD' END
                    WHERE query = ?
                """, (time.time(), query.lower().strip()))
                conn.commit()
                return dict(row)
        return None

    def set_cache(self, query: str, ticker: str, confidence: float):
        """Saves resolution result to cache."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO lookup_cache (query, ticker, confidence, last_used, hit_count)
                VALUES (?, ?, ?, ?, COALESCE((SELECT hit_count FROM lookup_cache WHERE query = ?), 0))
            """, (query.lower().strip(), ticker, confidence, time.time(), query.lower().strip()))
            conn.commit()

    def search_by_token(self, token: str) -> List[Dict]:
        """Inverted index lookup."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Multi-layered search: exact ticker OR token hit
            cursor.execute("""
                SELECT t.ticker, t.company_name, a.alias, a.confidence
                FROM tickers t
                LEFT JOIN aliases a ON t.id = a.ticker_id
                LEFT JOIN alias_tokens at ON a.id = at.alias_id
                WHERE at.token = ? OR t.ticker = ?
            """, (token.lower().strip(), token.upper().strip()))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_aliases_for_fuzzy(self, min_confidence: float = 0.5) -> List[Dict]:
        """Returns name/alias and ticker for fuzzy ranking."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.alias, t.ticker, a.confidence
                FROM aliases a
                JOIN tickers t ON a.ticker_id = t.id
                WHERE a.confidence >= ?
            """, (min_confidence,))
            return [dict(row) for row in cursor.fetchall()]

    def get_company_name(self, ticker: str) -> str:
        """Retrieves company name for a given ticker."""
        if not ticker:
            return "Unknown"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT company_name FROM tickers WHERE ticker = ?", (ticker.upper().strip(),))
            row = cursor.fetchone()
            return row[0] if row else "Unknown"
