-- Warehouse performance: delivery reliability and fill rate.
SELECT warehouse,
       region,
       COUNT(*)                                                  AS due_orders,
       ROUND(100.0 * SUM(is_on_time) / COUNT(*), 1)              AS otd_pct,
       ROUND(100.0 * SUM(qty_shipped) / SUM(qty_ordered), 1)     AS fill_rate_pct,
       ROUND(AVG(CASE WHEN days_late > 0 THEN days_late END), 1) AS avg_days_late
FROM v_orders
WHERE is_due = 1
GROUP BY warehouse, region
ORDER BY otd_pct;
