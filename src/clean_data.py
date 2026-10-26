"""Clean and validate raw order data; write clean tables, quarantined rows and a quality report."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, CLEAN = ROOT / "data" / "raw", ROOT / "data" / "clean"
DATE_COLS = ["order_date", "requested_date", "promised_date", "actual_ship_date"]

report: list[dict] = []


def log(check: str, rows: int, action: str) -> None:
    report.append({"check": check, "rows_affected": int(rows), "action": action})


def main() -> None:
    CLEAN.mkdir(parents=True, exist_ok=True)
    orders = pd.read_csv(RAW / "orders.csv", parse_dates=DATE_COLS)
    customers = pd.read_csv(RAW / "customers.csv")
    products = pd.read_csv(RAW / "products.csv")
    log("raw rows loaded", len(orders), "none")

    dupes = orders.duplicated()
    log("exact duplicate rows", dupes.sum(), "dropped")
    orders = orders[~dupes]
    log("duplicate order_id after exact-dup removal", orders["order_id"].duplicated().sum(), "dropped (keep first)")
    orders = orders.drop_duplicates("order_id")

    # Text normalisation first so later lookups and comparisons are reliable.
    region_map = {r.lower(): r for r in customers["region"].unique()}
    norm_region = orders["region"].str.strip().str.lower().map(region_map)
    log("region casing/whitespace variants", (norm_region != orders["region"]).sum(), "standardised")
    orders["region"] = norm_region

    norm_status = orders["status"].str.strip().str.title()
    log("status label variants", (norm_status != orders["status"]).sum(), "standardised")
    orders["status"] = norm_status

    neg = orders["qty_ordered"] < 0
    log("negative qty_ordered", neg.sum(), "sign corrected (abs)")
    orders["qty_ordered"] = orders["qty_ordered"].abs()

    missing_price = orders["unit_price"].isna()
    log("missing unit_price", missing_price.sum(), "imputed from product list price")
    list_price = orders["product_id"].map(products.set_index("product_id")["unit_price"])
    orders["unit_price"] = orders["unit_price"].fillna(list_price)

    over = orders["qty_shipped"] > orders["qty_ordered"]
    log("qty_shipped > qty_ordered", over.sum(), "capped at qty_ordered")
    orders.loc[over, "qty_shipped"] = orders.loc[over, "qty_ordered"]

    # Rows that can't be trusted or attributed are quarantined, not silently fixed.
    reasons = pd.Series("", index=orders.index)
    no_cust = orders["customer_id"].isna() | ~orders["customer_id"].isin(customers["customer_id"])
    no_prod = ~orders["product_id"].isin(products["product_id"])
    ship_before_order = orders["actual_ship_date"] < orders["order_date"]
    promised_before_order = orders["promised_date"] < orders["order_date"]
    for mask, reason in [(no_cust, "missing/unknown customer_id"), (no_prod, "unknown product_id"),
                         (ship_before_order, "ship date before order date"),
                         (promised_before_order, "promised date before order date"),
                         (orders["unit_price"].isna() | (orders["unit_price"] <= 0), "invalid unit_price")]:
        log(reason, mask.sum(), "quarantined")
        reasons[mask] += reason + "; "

    rejected = orders[reasons != ""].assign(reject_reason=reasons[reasons != ""])
    clean = orders[reasons == ""].copy()

    # Post-clean assertions: fail loudly if a rule is still violated.
    assert clean["order_id"].is_unique
    assert clean[["customer_id", "product_id", "order_date", "qty_ordered", "unit_price"]].notna().all().all()
    assert (clean["qty_ordered"] > 0).all()
    assert (clean["qty_shipped"] <= clean["qty_ordered"]).all()
    assert (clean["actual_ship_date"].dropna() >= clean["order_date"][clean["actual_ship_date"].notna()]).all()
    assert clean["status"].isin(["Shipped", "Partially Shipped", "Open", "Cancelled"]).all()
    assert clean["region"].isin(customers["region"].unique()).all()

    log("clean rows written", len(clean), "orders_clean.csv")
    log("quarantined rows written", len(rejected), "orders_rejected.csv")

    clean.to_csv(CLEAN / "orders_clean.csv", index=False)
    rejected.to_csv(CLEAN / "orders_rejected.csv", index=False)
    customers.to_csv(CLEAN / "customers_clean.csv", index=False)
    products.to_csv(CLEAN / "products_clean.csv", index=False)
    pd.DataFrame(report).to_csv(CLEAN / "data_quality_report.csv", index=False)
    print(pd.DataFrame(report).to_string(index=False))


if __name__ == "__main__":
    main()
