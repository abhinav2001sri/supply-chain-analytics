# Customer Demand & Supply Chain Analytics Dashboard

End-to-end analytics workflow on a customer-order dataset to monitor demand, backlog, order-booking trends and fulfillment risk.

**Tech:** Python (Pandas, NumPy), SQL (SQLite), Power BI (DAX), Excel (xlsxwriter)

## Architecture
```
generate_data.py -> data/raw -> clean_data.py -> data/clean -> load_to_sql.py -> SQLite (v_orders)
                                                                  |-> sql/*.sql queries
                                                                  |-> analysis.py -> data/analysis
                                                                  |-> export_powerbi.py -> powerbi/data -> Power BI
                                                                  |-> weekly_report.py -> reports/*.xlsx
```

## Quick start
```
pip install -r requirements.txt
python src/run_pipeline.py            # full run
python src/run_pipeline.py --skip-generate   # reuse data/raw (e.g. real extracts)
```
Individual steps: `generate_data.py`, `clean_data.py`, `load_to_sql.py`, `run_queries.py`, `analysis.py`, `export_powerbi.py`, `weekly_report.py`.

## What each part does
| Area | Details |
|---|---|
| Data | 60k synthetic orders (2025-01 to 2026-10) with seasonality, growth, per-warehouse late rates and planted data defects. |
| Cleaning | Dedupe, standardise labels, fix signs, impute prices, cap over-shipments, quarantine untrusted rows with reasons; assertions confirm the clean data. |
| SQL | Schema + `v_orders` view with shared metric definitions; 7 queries (bookings with MoM via `LAG`, backlog, aging buckets, OTD/fill/OTIF, late customers, warehouses, overdue orders). |
| Pandas | KPI summary, demand trends, 3-month forecast baseline, demand by dimension, risk scoring of open orders. |
| Excel | Weekly workbook with highlights, KPIs, charts and an exceptions list with suggested actions. |
| Power BI | Star-schema export, DAX measures (`powerbi/measures.dax`) and page-by-page build guide (`powerbi/DASHBOARD_GUIDE.md`). |

## KPI definitions
- **OTD:** shipped on or before the promised date, as a share of due orders (cancelled excluded).
- **OTIF:** on time and shipped quantity at least the ordered quantity.
- **Fill rate:** shipped quantity / ordered quantity on due orders.
- **Backlog:** unshipped quantity x price on Open and Partially Shipped orders; aged from order date.
- **Risk score:** points for overdue status, due within 7 days, order size, and warehouse and customer late history. High is 65 or more.

## Sample findings (synthetic data)
- OTD 80.7%, OTIF 74.4%, fill rate 95.9%.
- Backlog $4.89M, 35% already past promised date; $0.74M is older than 90 days.
- Sao Paulo and Shanghai warehouses have the lowest OTD (about 69% and 71%).
- 485 open orders ($1.03M) are scored high risk; 480 rows were quarantined for data issues.

## Validation
Used AI coding tools for drafting and boilerplate; all logic was reviewed and validated:
- Cleaning rules were confirmed by assertions and the data quality log.
- SQL results were reconciled against the Pandas KPIs (same OTD, backlog and booking totals).
- Weekly commentary is generated from the data, not typed by hand, so figures always match the workbook.
- A generated dataset showed an unrealistic 90+ day backlog; the logic was reviewed and corrected.

## Scheduling the weekly report
```
schtasks /Create /SC WEEKLY /D MON /ST 08:00 /TN "SupplyChainWeeklyReport" /TR "python \"<path>\src\run_pipeline.py\" --skip-generate"
```

## Résumé bullets
- Built an analytics workflow on a 60k-order customer dataset to monitor demand, backlog, order-booking trends and fulfillment risk.
- Wrote SQL and Python (Pandas) to clean, validate and analyse order data; built Power BI dashboards for demand trends, backlog aging and service-level KPIs (OTD, OTIF, fill rate).
- Automated weekly Excel reports with an exceptions summary that flags data discrepancies and overdue high-risk orders to support corrective action and stakeholder updates.
