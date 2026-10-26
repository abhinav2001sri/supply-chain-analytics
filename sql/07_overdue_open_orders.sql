-- Fulfillment risk: 50 largest open lines already past their promised date.
SELECT order_id,
       customer_name,
       warehouse,
       status,
       promised_date,
       CAST(julianday(as_of) - julianday(promised_date) AS INTEGER) AS days_overdue,
       open_qty,
       ROUND(backlog_value, 2)                                       AS backlog_value
FROM v_orders
WHERE open_qty > 0
  AND promised_date < as_of
ORDER BY backlog_value DESC
LIMIT 50;
