"""Pandas analysis on top of v_orders: KPIs, demand trends, demand forecast accuracy and open-order risk scoring."""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "supply_chain.db"
OUT = ROOT / "data" / "analysis"
DATE_COLS = ["order_date", "requested_date", "promised_date", "actual_ship_date", "as_of"]


def load_orders() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query("SELECT * FROM v_orders", conn, parse_dates=DATE_COLS)


def kpi_summary(df: pd.DataFrame) -> pd.DataFrame:
    live = df[df["status"] != "Cancelled"]
    due = df[df["is_due"] == 1]
    open_ = df[df["open_qty"] > 0]
    shipped = df[df["actual_ship_date"].notna()]
    otif = ((due["is_on_time"] == 1) & (due["qty_shipped"] >= due["qty_ordered"])).mean()
    kpis = {
        "orders_booked": len(live),
        "booked_value": live["order_value"].sum(),
        "cancellation_rate_pct": (df["status"] == "Cancelled").mean() * 100,
        "otd_pct": due["is_on_time"].mean() * 100,
        "otif_pct": otif * 100,
        "fill_rate_pct": due["qty_shipped"].sum() / due["qty_ordered"].sum() * 100,
        "avg_order_to_ship_days": (shipped["actual_ship_date"] - shipped["order_date"]).dt.days.mean(),
        "avg_days_late_when_late": due.loc[due["days_late"] > 0, "days_late"].mean(),
        "open_orders": len(open_),
        "backlog_value": open_["backlog_value"].sum(),
        "overdue_backlog_value": open_.loc[open_["promised_date"] < open_["as_of"], "backlog_value"].sum(),
        "avg_backlog_age_days": open_["backlog_age_days"].mean(),
    }
    return pd.Series(kpis, name="value").round(2).rename_axis("kpi").reset_index()


def monthly_demand(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly bookings plus a trailing 3-month-average forecast to measure forecast accuracy."""
    live = df[df["status"] != "Cancelled"]
    m = (live.groupby(live["order_date"].dt.to_period("M"))
             .agg(orders=("order_id", "count"), qty_ordered=("qty_ordered", "sum"), booked_value=("order_value", "sum"))
             .reset_index())
    m["month"] = m["order_date"].dt.to_timestamp()
    m = m.drop(columns="order_date")
    # The snapshot month is incomplete, so it would distort trend and accuracy.
    as_of = df["as_of"].iloc[0]
    m = m[m["month"] < as_of.to_period("M").to_timestamp()].reset_index(drop=True)
    m["forecast_qty"] = m["qty_ordered"].shift(1).rolling(3).mean()
    m["forecast_error_pct"] = (m["qty_ordered"] - m["forecast_qty"]) / m["qty_ordered"] * 100
    m["mom_growth_pct"] = m["booked_value"].pct_change() * 100
    m["yoy_growth_pct"] = m["booked_value"].pct_change(12) * 100
    cols = ["month", "orders", "qty_ordered", "booked_value", "mom_growth_pct", "yoy_growth_pct",
            "forecast_qty", "forecast_error_pct"]
    return m[cols].round(2)


def demand_by_dimension(df: pd.DataFrame, dim: str) -> pd.DataFrame:
    live = df[df["status"] != "Cancelled"]
    g = (live.groupby(dim)
             .agg(orders=("order_id", "count"), qty_ordered=("qty_ordered", "sum"), booked_value=("order_value", "sum"))
             .sort_values("booked_value", ascending=False))
    g["value_share_pct"] = g["booked_value"] / g["booked_value"].sum() * 100
    return g.round(2).reset_index()


def risk_scored_open_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Score open lines on overdue status, near-term due date, size and the warehouse/customer late history."""
    due = df[df["is_due"] == 1]
    wh_late = (1 - due.groupby("warehouse")["is_on_time"].mean()).rename("warehouse_late_rate")
    cust_late = (1 - due.groupby("customer_id")["is_on_time"].mean()).rename("customer_late_rate")

    open_ = df[df["open_qty"] > 0].copy()
    open_ = open_.join(wh_late, on="warehouse").join(cust_late, on="customer_id")
    open_["days_overdue"] = (open_["as_of"] - open_["promised_date"]).dt.days.clip(lower=0)
    due_soon = (open_["promised_date"] >= open_["as_of"]) & (open_["promised_date"] <= open_["as_of"] + pd.Timedelta(days=7))
    big = open_["backlog_value"] >= open_["backlog_value"].quantile(0.75)

    score = (np.where(open_["days_overdue"] > 0, 40, 0)
             + np.where(open_["days_overdue"] > 30, 15, 0)
             + np.where(due_soon, 15, 0)
             + open_["warehouse_late_rate"].fillna(0) * 50
             + np.where(open_["customer_late_rate"].fillna(0) > 0.25, 10, 0)
             + np.where(big, 15, 0))
    open_["risk_score"] = np.round(score, 1)
    open_["risk_tier"] = pd.cut(open_["risk_score"], [-1, 39.99, 64.99, 1000], labels=["Low", "Medium", "High"])
    cols = ["order_id", "customer_id", "customer_name", "warehouse", "region", "status", "promised_date",
            "days_overdue", "backlog_age_days", "open_qty", "backlog_value", "warehouse_late_rate",
            "customer_late_rate", "risk_score", "risk_tier"]
    return open_[cols].sort_values(["risk_score", "backlog_value"], ascending=False).round(3)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_orders()

    results = {
        "kpi_summary": kpi_summary(df),
        "monthly_demand": monthly_demand(df),
        "demand_by_category": demand_by_dimension(df, "category"),
        "demand_by_region": demand_by_dimension(df, "region"),
        "demand_by_segment": demand_by_dimension(df, "segment"),
        "risk_scored_open_orders": risk_scored_open_orders(df),
    }
    for name, frame in results.items():
        frame.to_csv(OUT / f"{name}.csv", index=False)

    print(results["kpi_summary"].to_string(index=False))
    md = results["monthly_demand"].dropna(subset=["forecast_error_pct"])
    print(f"\nForecast MAPE (3-mo trailing avg): {md['forecast_error_pct'].abs().mean():.1f}%")
    risk = results["risk_scored_open_orders"]
    print("\nOpen orders by risk tier:")
    print(risk.groupby("risk_tier", observed=True).agg(orders=("order_id", "count"),
                                                       backlog_value=("backlog_value", "sum")).round(0))
    print(f"\nOutputs written to {OUT}")


if __name__ == "__main__":
    main()
