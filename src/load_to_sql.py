"""Build the SQLite database from the cleaned CSVs."""
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
DB_PATH = ROOT / "data" / "supply_chain.db"
SCHEMA = ROOT / "sql" / "schema.sql"
AS_OF = "2026-10-26"  # must match the snapshot date used by generate_data.py


def main() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO config (as_of_date) VALUES (?)", (AS_OF,))
        # Load parents before children to satisfy foreign keys.
        for table, file in [("customers", "customers_clean.csv"), ("products", "products_clean.csv"),
                            ("orders", "orders_clean.csv")]:
            df = pd.read_csv(CLEAN / file)  # dates stay ISO strings
            df.to_sql(table, conn, if_exists="append", index=False)
            print(f"{table}: {len(df)} rows loaded")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert not violations, f"foreign key violations: {violations[:5]}"
    print(f"database ready -> {DB_PATH}")


if __name__ == "__main__":
    main()
