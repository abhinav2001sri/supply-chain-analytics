-- Top 15 customers by number of late orders (shipped late, or overdue and still unshipped).
SELECT customer_id,
       customer_name,
       segment,
       COUNT(*)                                          AS due_orders,
       COUNT(*) - SUM(is_on_time)                        AS late_orders,
       ROUND(100.0 * (COUNT(*) - SUM(is_on_time)) / COUNT(*), 1) AS late_pct,
       ROUND(AVG(CASE WHEN days_late > 0 THEN days_late END), 1) AS avg_days_late
FROM v_orders
WHERE is_due = 1
GROUP BY customer_id, customer_name, segment
ORDER BY late_orders DESC
LIMIT 15;
