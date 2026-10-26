-- Backlog aging buckets, based on days since order date.
SELECT CASE WHEN backlog_age_days <= 30 THEN '0-30'
            WHEN backlog_age_days <= 60 THEN '31-60'
            WHEN backlog_age_days <= 90 THEN '61-90'
            ELSE '90+' END                 AS age_bucket,
       COUNT(*)                            AS open_orders,
       SUM(open_qty)                       AS open_qty,
       ROUND(SUM(backlog_value), 2)        AS backlog_value
FROM v_orders
WHERE open_qty > 0
GROUP BY age_bucket
ORDER BY MIN(backlog_age_days);
