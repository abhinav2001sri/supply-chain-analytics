"""Generate a synthetic customer-order dataset with planted data-quality issues."""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_ORDERS = 60_000
N_CUSTOMERS = 400
N_PRODUCTS = 120
START = pd.Timestamp("2025-01-01")
AS_OF = pd.Timestamp("2026-10-26")  # snapshot date for open/backlog status
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

rng = np.random.default_rng(SEED)

REGIONS = ["North America", "Europe", "APAC", "LATAM", "MEA"]
WAREHOUSES = {"North America": ["WH-US-East", "WH-US-West"], "Europe": ["WH-DE-Frankfurt", "WH-NL-Rotterdam"],
              "APAC": ["WH-SG-Singapore", "WH-CN-Shanghai"], "LATAM": ["WH-BR-SaoPaulo"], "MEA": ["WH-AE-Dubai"]}
CATEGORIES = ["Electronics", "Industrial", "Consumer Goods", "Automotive", "Medical"]
SEGMENTS = ["Enterprise", "Mid-Market", "SMB"]
# Per-warehouse chance of a late shipment, so dashboards show meaningful differences.
LATE_RATE = {"WH-US-East": 0.12, "WH-US-West": 0.15, "WH-DE-Frankfurt": 0.10, "WH-NL-Rotterdam": 0.18,
             "WH-SG-Singapore": 0.20, "WH-CN-Shanghai": 0.28, "WH-BR-SaoPaulo": 0.30, "WH-AE-Dubai": 0.22}


def build_customers() -> pd.DataFrame:
    return pd.DataFrame({
        "customer_id": [f"C{i:04d}" for i in range(1, N_CUSTOMERS + 1)],
        "customer_name": [f"Customer {i:04d}" for i in range(1, N_CUSTOMERS + 1)],
        "segment": rng.choice(SEGMENTS, N_CUSTOMERS, p=[0.15, 0.35, 0.50]),
        "region": rng.choice(REGIONS, N_CUSTOMERS, p=[0.35, 0.25, 0.20, 0.10, 0.10]),
    })


def build_products() -> pd.DataFrame:
    return pd.DataFrame({
        "product_id": [f"P{i:04d}" for i in range(1, N_PRODUCTS + 1)],
        "product_name": [f"Product {i:04d}" for i in range(1, N_PRODUCTS + 1)],
        "category": rng.choice(CATEGORIES, N_PRODUCTS),
        "unit_price": np.round(rng.lognormal(mean=4.0, sigma=0.8, size=N_PRODUCTS), 2),
    })


def build_orders(customers: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    days = pd.date_range(START, AS_OF - pd.Timedelta(days=7), freq="D")
    # Weekly demand weight: yearly seasonality (Q4 peak), growth trend, quieter weekends.
    doy = days.dayofyear.to_numpy()
    seasonal = 1 + 0.25 * np.sin((doy - 120) / 365 * 2 * np.pi) + np.where(days.month >= 10, 0.15, 0)
    trend = 1 + 0.4 * np.arange(len(days)) / len(days)
    weekend = np.where(days.dayofweek >= 5, 0.3, 1.0)
    weights = seasonal * trend * weekend
    order_date = pd.to_datetime(rng.choice(days, N_ORDERS, p=weights / weights.sum()))

    cust = customers.iloc[rng.choice(N_CUSTOMERS, N_ORDERS, p=_zipf_weights(N_CUSTOMERS))].reset_index(drop=True)
    prod = products.iloc[rng.integers(0, N_PRODUCTS, N_ORDERS)].reset_index(drop=True)

    warehouse = np.array([rng.choice(WAREHOUSES[r]) for r in cust["region"]])
    qty = np.clip(rng.lognormal(3.0, 0.9, N_ORDERS).round().astype(int), 1, 2000)

    requested = order_date + pd.to_timedelta(rng.integers(7, 31, N_ORDERS), unit="D")
    promised = requested + pd.to_timedelta(rng.choice([0, 1, 2, 3], N_ORDERS, p=[0.6, 0.2, 0.15, 0.05]), unit="D")

    is_late = rng.random(N_ORDERS) < pd.Series(warehouse).map(LATE_RATE).to_numpy()
    delay = np.where(is_late, rng.integers(1, 21, N_ORDERS), -rng.integers(0, 4, N_ORDERS))
    actual_ship = promised + pd.to_timedelta(delay, unit="D")

    status = np.full(N_ORDERS, "Shipped", dtype=object)
    qty_shipped = qty.copy()

    # Orders whose ship date falls after the snapshot are still open.
    not_yet = actual_ship > AS_OF
    # A small share of older orders stalls and never ships (drives 90+ day backlog).
    stalled = (order_date < AS_OF - pd.Timedelta(days=45)) & (rng.random(N_ORDERS) < 0.004)
    open_mask = not_yet | stalled
    status[open_mask] = "Open"
    qty_shipped[open_mask] = 0

    partial = ~open_mask & (rng.random(N_ORDERS) < 0.08)
    status[partial] = "Partially Shipped"
    qty_shipped[partial] = np.maximum(1, (qty[partial] * rng.uniform(0.3, 0.9, partial.sum())).astype(int))
    # Older short shipments are closed out as short-shipped, so only recent ones remain backlog.
    closed_short = partial & (order_date < AS_OF - pd.Timedelta(days=60)) & (rng.random(N_ORDERS) < 0.9)
    status[closed_short] = "Shipped"

    cancelled = rng.random(N_ORDERS) < 0.03
    status[cancelled] = "Cancelled"
    qty_shipped[cancelled] = 0

    actual_ship = pd.Series(actual_ship)
    actual_ship[open_mask | cancelled] = pd.NaT

    orders = pd.DataFrame({
        "order_id": [f"SO{100000 + i}" for i in range(N_ORDERS)],
        "customer_id": cust["customer_id"],
        "product_id": prod["product_id"],
        "order_date": order_date,
        "requested_date": requested,
        "promised_date": promised,
        "actual_ship_date": actual_ship,
        "qty_ordered": qty,
        "qty_shipped": qty_shipped,
        "unit_price": (prod["unit_price"] * rng.uniform(0.9, 1.1, N_ORDERS)).round(2),
        "region": cust["region"],
        "warehouse": warehouse,
        "status": status,
    }).sort_values("order_date").reset_index(drop=True)
    return _inject_quality_issues(orders)


def _zipf_weights(n: int) -> np.ndarray:
    w = 1 / np.arange(1, n + 1) ** 0.7
    rng.shuffle(w)
    return w / w.sum()


def _inject_quality_issues(df: pd.DataFrame) -> pd.DataFrame:
    """Plant known defects so the cleaning step has real work to do."""
    n = len(df)

    def pick(frac):
        return rng.choice(n, int(n * frac), replace=False)

    df.loc[pick(0.005), "customer_id"] = np.nan                      # missing keys
    df.loc[pick(0.004), "unit_price"] = np.nan                       # missing price
    df.loc[pick(0.003), "qty_ordered"] = -df["qty_ordered"].abs()    # negative quantities
    df.loc[pick(0.004), "region"] = df["region"].str.upper() + " "   # inconsistent casing/whitespace
    df.loc[pick(0.003), "status"] = df["status"].str.lower()         # inconsistent status labels

    shipped = df.index[df["actual_ship_date"].notna()]
    bad_dates = rng.choice(shipped, int(n * 0.003), replace=False)
    df.loc[bad_dates, "actual_ship_date"] = df.loc[bad_dates, "order_date"] - pd.Timedelta(days=3)   # ship before order

    over = rng.choice(shipped, int(n * 0.003), replace=False)
    df.loc[over, "qty_shipped"] = df.loc[over, "qty_ordered"].abs() + rng.integers(1, 20, len(over))  # over-shipment

    dupes = df.sample(int(n * 0.008), random_state=SEED)             # exact duplicate rows
    return pd.concat([df, dupes], ignore_index=True).sample(frac=1, random_state=SEED).reset_index(drop=True)


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    customers, products = build_customers(), build_products()
    orders = build_orders(customers, products)
    customers.to_csv(OUT_DIR / "customers.csv", index=False)
    products.to_csv(OUT_DIR / "products.csv", index=False)
    orders.to_csv(OUT_DIR / "orders.csv", index=False)
    print(f"customers={len(customers)} products={len(products)} orders={len(orders)} -> {OUT_DIR}")
