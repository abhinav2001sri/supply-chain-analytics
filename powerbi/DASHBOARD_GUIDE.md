# Power BI Dashboard Build Guide

Power BI Desktop files (`.pbix`) cannot be generated from code, so build it in Desktop using the exported data and the measures in `measures.dax`.

## 1. Load the data
1. Run `python src/export_powerbi.py` (or `python src/run_pipeline.py`) to refresh `powerbi/data/`.
2. Power BI Desktop > Get Data > Text/CSV, and load all five files: `fact_orders`, `dim_date`, `dim_customer`, `dim_product`, `dim_warehouse`.
3. In Power Query confirm date columns are type Date. In `dim_date` mark `date` as the date table (Table tools > Mark as date table).

## 2. Model (star schema)
| From (many) | To (one) | Active |
|---|---|---|
| `fact_orders[order_date]` | `dim_date[date]` | Yes |
| `fact_orders[promised_date]` | `dim_date[date]` | No |
| `fact_orders[actual_ship_date]` | `dim_date[date]` | No |
| `fact_orders[customer_id]` | `dim_customer[customer_id]` | Yes |
| `fact_orders[product_id]` | `dim_product[product_id]` | Yes |
| `fact_orders[warehouse]` | `dim_warehouse[warehouse]` | Yes |

Set filter direction to single. Sort `backlog_age_bucket` by `backlog_age_bucket_sort` and `month_name` by `month_num`.

## 3. Measures
Create an empty table `_Measures` (Enter data) and paste every measure from `measures.dax`. Format: OTD/OTIF/fill/growth as percentages, values as currency.

## 4. Pages

**Page 1 - Demand Trends**
- Cards: Booked Value, Total Orders, Booked Value YoY %, Cancellation Rate %.
- Line chart: `dim_date[year_month]` vs Booked Value and Booked Value 3M Avg.
- Column chart: Booked Value MoM % by month.
- Bar chart: Booked Value by `dim_product[category]`; donut by `dim_customer[segment]`.
- Map or bar: Booked Value by `dim_customer[region]`.
- Slicers: year, region, segment, category.

**Page 2 - Backlog & Aging**
- Cards: Backlog Value, Open Orders, Overdue Backlog %, Avg Backlog Age (days).
- Column chart: Backlog Value by `backlog_age_bucket` (sorted by bucket sort column).
- Stacked bar: Backlog Value by warehouse, split by `risk_tier`.
- Table: top open orders with `order_id`, customer, promised date, backlog value, risk score (filter `risk_tier` = High).
- Note: do not filter backlog visuals by order date; the measures already remove the date filter.

**Page 3 - Service Levels**
- Gauge or KPI: OTD % (target OTD Target), OTIF %, Fill Rate %.
- Line chart: `dim_date[year_month]` vs OTD % (by Promised Date) and OTIF % (by Promised Date).
- Bar chart: OTD % by warehouse (sorted ascending to show the worst first).
- Table: top late customers with Due Orders, Late Orders, Avg Days Late.

**Page 4 - Exceptions**
- Table of High risk orders (`risk_tier` = High), conditional formatting on days late and backlog value.
- Card: High Risk Orders and High Risk Value.
- Drill-through from warehouse or customer to this page.

## 5. Polish
- One consistent theme (View > Themes), a navigation bar with page buttons, and tooltips on charts.
- Add a text box with KPI definitions: OTD = shipped on or before the promised date; OTIF = on time and fully shipped; Fill rate = shipped qty / ordered qty; Backlog = ordered minus shipped on open and partially shipped orders.
- Save as `powerbi/supply_chain_dashboard.pbix`, export a PDF and screenshots into `powerbi/screenshots/` for the README.
