# Pump to Pasar

Did the June 2024 diesel price rise in Peninsular Malaysia reach grocery prices, and where?

Diesel went to RM3.35 per litre in Peninsular Malaysia on 10 June 2024, while Sabah, Sarawak and Labuan stayed at RM2.15. This project compares shop-level grocery prices across the two regions (a difference-in-differences design) using the government's PriceCatcher data.

**Status:** work in progress. Data feasibility checked; building the data warehouse.

## Data

PriceCatcher daily item prices by premise, from KPDN and DOSM via [OpenDOSM](https://open.dosm.gov.my/data-catalogue/pricecatcher), licensed CC BY 4.0. Data files are not stored in this repo; `scripts/download_data.py` downloads them.

## Stack

Python, DuckDB, dbt (dbt-duckdb), Parquet.

## Project layout

```
scripts/     download and feasibility-check scripts
warehouse/   dbt project (staging, core and mart models)
outputs/     small result tables from the checks
```
