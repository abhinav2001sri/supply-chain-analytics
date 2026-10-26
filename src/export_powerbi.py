"""Export a Power BI-ready star schema (dimensions + one fact table) from the SQLite view."""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from analysis import DB_PATH, ROOT, load_orders, risk_scored_open_orders

OUT = ROOT / "powerbi" / "data"
BUCKETS = [(30, "0-30", 1), (60, "31-60", 2), (90, "61-90", 3)]


def age_bucket(days: pd.Series) -> pd.DataFrame:
    label = pd.Series(np.where(days.isna(), None, "90+"), index=days.index, dtype=object)
    sort = pd.Series(np.where(days.isna(), np.nan, 4), index=days.index)
    for limit, name, order in reversed(BUCKETS):
        hit = days <= limit
        label[hit], sort[hit] = name, order
    return pd.DataFrame({"backlog_age_bucket": label, "backlog_age_bucket_sort": sort})


def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    d = pd.DataFrame({"date": pd.date_range(start.normalize(), end.normalize(), freq="D")})
    d["year"] = d["date"].dt.year
    d["quarter"] = "Q" + d["date"].dt.quarter.astype(str)
    d["month_num"] = d["date"].dt.month
    d["month_name"] = d["date"].dt.strftime("%b")
    d["year_month"] = d["date"].dt.strftime("%Y-%m")
    d["week_start"] = (d["date"] - pd.to_timedelta(d["date"].dt.dayofweek, unit="D")).dt.date
    d["is_weekend"] = (d["date"].dt.dayofweek >= 5).astype(int)
    return d


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_orders()
    risk = risk_scored_open_orders(df)[["order_id", "risk_score", "risk_tier"]]
    risk["risk_tier"] = risk["risk_tier"].astype(str)

    fact = df.merge(risk, on="order_id", how="left")
    fact["is_otif"] = ((fact["is_on_time"] == 1) & (fact["qty_shipped"] >= fact["qty_ordered"])).astype(int)
    fact["is_overdue_open"] = ((fact["open_qty"] > 0) & (fact["promised_date"] < fact["as_of"])).astype(int)
    fact[["order_value", "backlog_value"]] = fact[["order_value", "backlog_value"]].round(2)
    fact = pd.concat([fact, age_bucket(fact["backlog_age_days"])], axis=1)
    fact_cols = ["order_id", "customer_id", "product_id", "warehouse", "order_date", "requested_date",
                 "promised_date", "actual_ship_date", "status", "qty_ordered", "qty_shipped", "unit_price",
                 "order_value", "open_qty", "backlog_value", "backlog_age_days", "backlog_age_bucket",
                 "backlog_age_bucket_sort", "days_late", "is_due", "is_on_time", "is_otif", "is_overdue_open",
                 "risk_score", "risk_tier"]

    with sqlite3.connect(DB_PATH) as conn:
        dim_customer = pd.read_sql_query("SELECT customer_id, customer_name, segment, region FROM customers", conn)
        dim_product = pd.read_sql_query("SELECT product_id, product_name, category FROM products", conn)
        dim_warehouse = pd.read_sql_query(
            "SELECT DISTINCT warehouse, region AS warehouse_region FROM orders ORDER BY warehouse", conn)

    last = max(df["as_of"].max(), df["promised_date"].max(), df["actual_ship_date"].max())
    dim_date = build_dim_date(df["order_date"].min(), last)

    tables = {"fact_orders": fact[fact_cols], "dim_date": dim_date, "dim_customer": dim_customer,
              "dim_product": dim_product, "dim_warehouse": dim_warehouse}
    for name, frame in tables.items():
        frame.to_csv(OUT / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        print(f"{name}: {len(frame):,} rows")
    print(f"Power BI data -> {OUT}")


if __name__ == "__main__":
    main()
