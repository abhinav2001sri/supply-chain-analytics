-- Monthly service levels by promised month: on-time delivery (OTD), fill rate and OTIF.
SELECT substr(promised_date, 1, 7)                                        AS promised_month,
       COUNT(*)                                                           AS due_orders,
       ROUND(100.0 * SUM(is_on_time) / COUNT(*), 1)                       AS otd_pct,
       ROUND(100.0 * SUM(qty_shipped) / SUM(qty_ordered), 1)              AS fill_rate_pct,
       ROUND(100.0 * SUM(CASE WHEN is_on_time = 1 AND qty_shipped >= qty_ordered THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                               AS otif_pct
FROM v_orders
WHERE is_due = 1
GROUP BY 1
ORDER BY 1;
