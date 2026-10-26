"""Build the weekly Excel report with KPIs, charts, an exceptions list and auto-generated commentary."""
import sqlite3
from pathlib import Path

import pandas as pd

from analysis import (DB_PATH, ROOT, demand_by_dimension, kpi_summary, load_orders, monthly_demand,
                      risk_scored_open_orders)

CLEAN = ROOT / "data" / "clean"
REPORTS = ROOT / "reports"

KPI_LABELS = {
    "orders_booked": ("Orders booked", "int"), "booked_value": ("Booked value", "usd"),
    "cancellation_rate_pct": ("Cancellation rate", "pct"), "otd_pct": ("On-time delivery (OTD)", "pct"),
    "otif_pct": ("On-time in-full (OTIF)", "pct"), "fill_rate_pct": ("Fill rate", "pct"),
    "avg_order_to_ship_days": ("Avg order-to-ship (days)", "dec"), "avg_days_late_when_late": ("Avg days late (late orders)", "dec"),
    "open_orders": ("Open orders", "int"), "backlog_value": ("Backlog value", "usd"),
    "overdue_backlog_value": ("Overdue backlog value", "usd"), "avg_backlog_age_days": ("Avg backlog age (days)", "dec"),
}
REJECT_ACTIONS = {
    "missing/unknown customer_id": "Confirm customer with sales ops and correct the order header in the source system.",
    "ship date before order date": "Validate ship/order dates with the warehouse and correct the timestamp.",
}


def run_sql(conn: sqlite3.Connection, name: str) -> pd.DataFrame:
    return pd.read_sql_query((ROOT / "sql" / name).read_text(encoding="utf-8"), conn)


def pct_change(cur: float, prev: float) -> str:
    return "n/a" if not prev else f"{(cur - prev) / prev * 100:+.1f}%"


def weekly_commentary(df, kpis, aging, warehouses, risk, rejected) -> list[str]:
    as_of = df["as_of"].iloc[0]
    latest = df["order_date"].max()
    week = pd.Timedelta(days=7)

    live = df[df["status"] != "Cancelled"]
    cur = live[(live["order_date"] > latest - week) & (live["order_date"] <= latest)]
    prev = live[(live["order_date"] > latest - 2 * week) & (live["order_date"] <= latest - week)]

    due = df[df["is_due"] == 1]
    cur_due = due[(due["promised_date"] > as_of - week) & (due["promised_date"] <= as_of)]
    prev_due = due[(due["promised_date"] > as_of - 2 * week) & (due["promised_date"] <= as_of - week)]

    worst = warehouses.sort_values("otd_pct").iloc[0]
    old_backlog = aging.loc[aging["age_bucket"] == "90+"]
    old_value = float(old_backlog["backlog_value"].sum())
    overdue_share = kpis["overdue_backlog_value"] / kpis["backlog_value"] * 100
    high = risk[risk["risk_tier"] == "High"]

    return [
        f"Bookings: {len(cur):,} orders / ${cur['order_value'].sum():,.0f} in the 7 days to {latest:%d %b %Y} "
        f"({pct_change(cur['order_value'].sum(), prev['order_value'].sum())} value vs prior 7 days).",
        f"Service: OTD {cur_due['is_on_time'].mean() * 100:.1f}% for orders promised in the last 7 days "
        f"(prior week {prev_due['is_on_time'].mean() * 100:.1f}%); overall OTD {kpis['otd_pct']:.1f}%, OTIF {kpis['otif_pct']:.1f}%.",
        f"Backlog: ${kpis['backlog_value']:,.0f} across {int(kpis['open_orders']):,} open orders; "
        f"{overdue_share:.0f}% is already past its promised date and ${old_value:,.0f} is older than 90 days.",
        f"Weakest warehouse: {worst['warehouse']} with {worst['otd_pct']:.1f}% OTD and {worst['avg_days_late']:.1f} average days late.",
        f"Fulfillment risk: {len(high):,} high-risk open orders worth ${high['backlog_value'].sum():,.0f} need expediting.",
        f"Data quality: {len(rejected):,} rows were quarantined from this load and need correction at source.",
    ]


def build_exceptions(risk: pd.DataFrame, rejected: pd.DataFrame) -> pd.DataFrame:
    high = risk[risk["risk_tier"] == "High"]
    overdue = pd.DataFrame({
        "exception_type": "High-risk open order",
        "severity": "High",
        "order_id": high["order_id"],
        "customer": high["customer_name"],
        "detail": ("$" + high["backlog_value"].round(0).astype(int).map("{:,}".format) + " open, "
                   + high["days_overdue"].astype(int).astype(str) + " days overdue, " + high["warehouse"]),
        "suggested_action": "Expedite or confirm a revised ship date with the customer.",
    })
    reasons = rejected["reject_reason"].str.rstrip("; ")
    dq = pd.DataFrame({
        "exception_type": "Data discrepancy",
        "severity": "Medium",
        "order_id": rejected["order_id"],
        "customer": rejected["customer_id"].fillna("(missing)"),
        "detail": reasons,
        "suggested_action": reasons.map(lambda r: next((a for k, a in REJECT_ACTIONS.items() if k in r), "Review at source.")),
    })
    return pd.concat([overdue, dq], ignore_index=True)


def write_table(writer, df: pd.DataFrame, sheet: str, hdr) -> "xlsxwriter.worksheet.Worksheet":
    wb = writer.book
    fmts = {"usd": wb.add_format({"num_format": "$#,##0"}), "pct": wb.add_format({"num_format": "0.0"}),
            "frac": wb.add_format({"num_format": "0.0%"})}
    df = df.copy()
    for c in df.select_dtypes("category").columns:
        df[c] = df[c].astype(str)
    df.to_excel(writer, sheet_name=sheet, index=False)
    ws = writer.sheets[sheet]
    for i, col in enumerate(df.columns):
        ws.write(0, i, col, hdr)
        longest = df[col].astype(str).str.len().max() if len(df) else 0
        fmt = fmts["usd"] if "value" in col else fmts["frac"] if "rate" in col and "late" in col else fmts["pct"] if "pct" in col else None
        ws.set_column(i, i, min(max(len(col), longest) + 2, 60), fmt)
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(len(df), 1), len(df.columns) - 1)
    return ws


def build_report() -> Path:
    df = load_orders()
    as_of = df["as_of"].iloc[0]
    kpis = kpi_summary(df).set_index("kpi")["value"]
    monthly = monthly_demand(df)
    risk = risk_scored_open_orders(df)
    rejected = pd.read_csv(CLEAN / "orders_rejected.csv")
    quality = pd.read_csv(CLEAN / "data_quality_report.csv")
    with sqlite3.connect(DB_PATH) as conn:
        aging = run_sql(conn, "03_backlog_aging.sql")
        warehouses = run_sql(conn, "06_warehouse_performance.sql")
        late_customers = run_sql(conn, "05_late_customers.sql")
    exceptions = build_exceptions(risk, rejected)

    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"weekly_report_{as_of:%Y-%m-%d}.xlsx"

    with pd.ExcelWriter(path, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        wb = writer.book
        hdr = wb.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "white", "border": 1})
        title = wb.add_format({"bold": True, "font_size": 16, "font_color": "#1F4E78"})
        section = wb.add_format({"bold": True, "font_size": 12, "bottom": 1})
        wrap = wb.add_format({"text_wrap": True, "valign": "top"})
        num = {"int": wb.add_format({"num_format": "#,##0"}), "usd": wb.add_format({"num_format": "$#,##0"}),
               "pct": wb.add_format({"num_format": '0.0"%"'}), "dec": wb.add_format({"num_format": "0.0"})}

        summary = wb.add_worksheet("Summary")
        writer.sheets["Summary"] = summary
        summary.set_column(0, 0, 34)
        summary.set_column(1, 2, 20)
        summary.set_column(3, 3, 70)
        summary.write(0, 0, "Customer Demand & Supply Chain - Weekly Report", title)
        summary.write(1, 0, f"Snapshot date: {as_of:%Y-%m-%d}   |   Latest order date: {df['order_date'].max():%Y-%m-%d}")

        row = 3
        summary.write(row, 0, "Highlights", section)
        for line in weekly_commentary(df, kpis, aging, warehouses, risk, rejected):
            row += 1
            summary.merge_range(row, 0, row, 3, line, wrap)
            summary.set_row(row, 32)

        row += 2
        summary.write(row, 0, "Key KPIs", section)
        for key, (label, kind) in KPI_LABELS.items():
            row += 1
            summary.write(row, 0, label)
            summary.write_number(row, 1, float(kpis[key]), num[kind])

        row += 2
        summary.write_row(row, 0, ["Exception summary", "Count", "Value at stake", "Recommended action"], hdr)
        old = df[(df["open_qty"] > 0) & (df["backlog_age_days"] > 90)]
        overdue30 = risk[risk["days_overdue"] > 30]
        high = risk[risk["risk_tier"] == "High"]
        rows = [
            ("High-risk open orders", len(high), high["backlog_value"].sum(), "Expedite; confirm revised dates with customers."),
            ("Open orders > 30 days overdue", len(overdue30), overdue30["backlog_value"].sum(), "Escalate to warehouse leads; cancel or re-promise."),
            ("Open backlog older than 90 days", len(old), old["backlog_value"].sum(), "Review for cancellation or stock allocation."),
        ]
        for reason, action in REJECT_ACTIONS.items():
            n = rejected["reject_reason"].str.contains(reason, regex=False).sum()
            rows.append((f"Quarantined: {reason}", int(n), None, action))
        for label, count, value, action in rows:
            row += 1
            summary.write(row, 0, label)
            summary.write_number(row, 1, count, num["int"])
            if value is None:
                summary.write(row, 2, "n/a")
            else:
                summary.write_number(row, 2, float(value), num["usd"])
            summary.write(row, 3, action)

        ws = write_table(writer, monthly, "Monthly Trend", hdr)
        n = len(monthly)
        chart = wb.add_chart({"type": "line"})
        chart.add_series({"name": "Booked value", "categories": ["Monthly Trend", 1, 0, n, 0],
                          "values": ["Monthly Trend", 1, 3, n, 3]})
        chart.set_title({"name": "Monthly booked value"})
        chart.set_x_axis({"num_format": "mmm-yy", "date_axis": True})
        chart.set_y_axis({"num_format": "$#,##0"})
        chart.set_size({"width": 720, "height": 340})
        ws.insert_chart("J2", chart)

        ws = write_table(writer, aging, "Backlog Aging", hdr)
        chart = wb.add_chart({"type": "column"})
        chart.add_series({"name": "Backlog value", "categories": ["Backlog Aging", 1, 0, len(aging), 0],
                          "values": ["Backlog Aging", 1, 3, len(aging), 3]})
        chart.set_title({"name": "Backlog value by age (days)"})
        chart.set_legend({"none": True})
        chart.set_y_axis({"num_format": "$#,##0"})
        ws.insert_chart("G2", chart)

        write_table(writer, warehouses, "Warehouse Performance", hdr)
        write_table(writer, late_customers, "Late Customers", hdr)
        write_table(writer, demand_by_dimension(df, "category"), "Demand by Category", hdr)

        ws = write_table(writer, exceptions, "Exceptions", hdr)
        ws.conditional_format(1, 1, len(exceptions), 1, {"type": "cell", "criteria": "==", "value": '"High"',
                                                           "format": wb.add_format({"bg_color": "#F8CBAD"})})
        ws.conditional_format(1, 1, len(exceptions), 1, {"type": "cell", "criteria": "==", "value": '"Medium"',
                                                           "format": wb.add_format({"bg_color": "#FFE699"})})
        write_table(writer, risk, "Open Order Risk", hdr)
        write_table(writer, quality, "Data Quality", hdr)

    return path


if __name__ == "__main__":
    print(f"Report written -> {build_report()}")
