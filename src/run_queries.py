"""Run every numbered SQL query against the database and print a preview of each result."""
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "supply_chain.db"


def main() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        for sql_file in sorted((ROOT / "sql").glob("0*.sql")):
            df = pd.read_sql_query(sql_file.read_text(encoding="utf-8"), conn)
            print(f"\n=== {sql_file.name} ({len(df)} rows) ===")
            print(df.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
