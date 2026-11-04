import sqlite3
import os
import json
import pandas as pd
import numpy as np

def analyze_db(db_path):
    if not os.path.exists(db_path):
        return {"status": "missing"}
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Get tables
        c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in c.fetchall()]
        
        db_info = {
            "status": "exists",
            "size_bytes": os.path.getsize(db_path),
            "tables": {}
        }
        
        for table in tables:
            c.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in c.fetchall()]
            
            c.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = c.fetchone()[0]
            
            table_info = {
                "columns": columns,
                "row_count": row_count
            }
            
            if 'ticker' in columns or 'symbol' in columns:
                col_name = 'ticker' if 'ticker' in columns else 'symbol'
                c.execute(f"SELECT COUNT(DISTINCT {col_name}) FROM {table}")
                table_info['distinct_tickers'] = c.fetchone()[0]
                
            if 'date' in columns or 'timestamp' in columns:
                col_name = 'date' if 'date' in columns else 'timestamp'
                c.execute(f"SELECT MIN({col_name}), MAX({col_name}) FROM {table}")
                min_dt, max_dt = c.fetchone()
                table_info['min_date'] = min_dt
                table_info['max_date'] = max_dt
                
            db_info["tables"][table] = table_info
            
        conn.close()
        return db_info
    except Exception as e:
        return {"status": "error", "message": str(e)}

def run_forensic():
    results = {}
    dbs = [
        "data/historical_data.db",
        "data/historical_security.db",
        "data/research_cache.db",
        "data/tickers.db"
    ]
    
    for db in dbs:
        results[db] = analyze_db(db)
        
    with open("db_forensic_results.json", "w") as f:
        json.dump(results, f, indent=4)
        
if __name__ == "__main__":
    run_forensic()
