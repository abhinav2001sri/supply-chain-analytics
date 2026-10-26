-- Monthly bookings (excluding cancelled) with month-over-month growth.
WITH monthly AS (
    SELECT substr(order_date, 1, 7) AS month,
           COUNT(*)                 AS orders,
           SUM(qty_ordered)         AS qty_ordered,
           ROUND(SUM(order_value), 2) AS booked_value
    FROM v_orders
    WHERE status <> 'Cancelled'
    GROUP BY 1
)
SELECT month, orders, qty_ordered, booked_value,
       ROUND(100.0 * (booked_value - LAG(booked_value) OVER (ORDER BY month))
             / LAG(booked_value) OVER (ORDER BY month), 1) AS mom_growth_pct
FROM monthly
ORDER BY month;
