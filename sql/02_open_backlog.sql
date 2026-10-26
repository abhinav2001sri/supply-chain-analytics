-- Open backlog by region and warehouse, including how much is already past its promised date.
SELECT region,
       warehouse,
       COUNT(*)                                                AS open_orders,
       SUM(open_qty)                                           AS open_qty,
       ROUND(SUM(backlog_value), 2)                            AS backlog_value,
       ROUND(AVG(backlog_age_days), 1)                         AS avg_age_days,
       SUM(CASE WHEN promised_date < as_of THEN 1 ELSE 0 END)  AS overdue_orders
FROM v_orders
WHERE open_qty > 0
GROUP BY region, warehouse
ORDER BY backlog_value DESC;
