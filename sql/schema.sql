PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS v_orders;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS config;

CREATE TABLE config (
    as_of_date TEXT NOT NULL  -- snapshot date used for backlog/overdue logic
);

CREATE TABLE customers (
    customer_id   TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    segment       TEXT NOT NULL,
    region        TEXT NOT NULL
);

CREATE TABLE products (
    product_id   TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    category     TEXT NOT NULL,
    unit_price   REAL NOT NULL
);

CREATE TABLE orders (
    order_id         TEXT PRIMARY KEY,
    customer_id      TEXT NOT NULL REFERENCES customers (customer_id),
    product_id       TEXT NOT NULL REFERENCES products (product_id),
    order_date       TEXT NOT NULL,
    requested_date   TEXT NOT NULL,
    promised_date    TEXT NOT NULL,
    actual_ship_date TEXT,
    qty_ordered      INTEGER NOT NULL CHECK (qty_ordered > 0),
    qty_shipped      INTEGER NOT NULL CHECK (qty_shipped >= 0),
    unit_price       REAL NOT NULL,
    region           TEXT NOT NULL,
    warehouse        TEXT NOT NULL,
    status           TEXT NOT NULL
);

CREATE INDEX ix_orders_order_date ON orders (order_date);
CREATE INDEX ix_orders_promised_date ON orders (promised_date);
CREATE INDEX ix_orders_customer ON orders (customer_id);
CREATE INDEX ix_orders_status ON orders (status);

-- Single source for derived order metrics so every query and Power BI share the same definitions.
CREATE VIEW v_orders AS
SELECT
    base.*,
    open_qty * unit_price AS backlog_value,
    CASE WHEN open_qty > 0
         THEN CAST(julianday(as_of) - julianday(order_date) AS INTEGER) END AS backlog_age_days,
    CASE WHEN actual_ship_date IS NOT NULL
         THEN CAST(julianday(actual_ship_date) - julianday(promised_date) AS INTEGER) END AS days_late,
    -- is_due: cancelled orders excluded; counted once promised date has passed or it has shipped.
    CASE WHEN status <> 'Cancelled' AND (promised_date <= as_of OR actual_ship_date IS NOT NULL)
         THEN 1 ELSE 0 END AS is_due,
    CASE WHEN status <> 'Cancelled' AND actual_ship_date IS NOT NULL AND actual_ship_date <= promised_date
         THEN 1 ELSE 0 END AS is_on_time
FROM (
    SELECT
        o.*,
        c.customer_name,
        c.segment,
        p.product_name,
        p.category,
        o.qty_ordered * o.unit_price AS order_value,
        CASE WHEN o.status IN ('Open', 'Partially Shipped') THEN o.qty_ordered - o.qty_shipped ELSE 0 END AS open_qty,
        (SELECT as_of_date FROM config) AS as_of
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    JOIN products p ON p.product_id = o.product_id
) AS base;
