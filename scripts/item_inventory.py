"""
Step 1b: build an inventory of every PriceCatcher item in the sample.

For each item it counts price observations before (Apr-Jun 2025) and after
(Jul-Sep 2025) the SST change, plus how many premises and states report it.
The output CSV is what we use to map items to the official tax orders.

Run from the project root:  python scripts/item_inventory.py
Writes:  outputs/item_inventory.csv
"""

from pathlib import Path

import duckdb

RAW_DIR = Path("data/raw")
OUT_DIR = Path("outputs")
SST_DATE = "2025-07-01"

PRICES = (RAW_DIR / "pricecatcher_*.parquet").as_posix()
ITEMS = (RAW_DIR / "lookup_item.parquet").as_posix()
PREMISES = (RAW_DIR / "lookup_premise.parquet").as_posix()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    con = duckdb.connect()  # in-memory database; DuckDB reads Parquet directly

    # A view is a saved query: every later query can use "prices" as a table.
    con.execute(f"""
        CREATE VIEW prices AS
        SELECT CAST(date AS DATE) AS date,
               CAST(premise_code AS INTEGER) AS premise_code,
               CAST(item_code AS INTEGER) AS item_code,
               CAST(price AS DOUBLE) AS price
        FROM read_parquet('{PRICES}')
    """)

    print("\n1. Rows per month (sanity check: expect over a million each)")
    print(con.sql("""
        SELECT strftime(date, '%Y-%m') AS month,
               COUNT(*) AS rows,
               COUNT(DISTINCT item_code) AS items,
               COUNT(DISTINCT premise_code) AS premises
        FROM prices GROUP BY 1 ORDER BY 1
    """).df().to_string(index=False))

    print("\n2. Data quality: missing or non-positive prices")
    print(con.sql("""
        SELECT COUNT(*) FILTER (WHERE price IS NULL) AS null_prices,
               COUNT(*) FILTER (WHERE price <= 0)    AS zero_or_negative,
               MIN(date) AS first_date, MAX(date) AS last_date
        FROM prices
    """).df().to_string(index=False))

    # Per-item inventory joined to the item and premise lookups.
    inventory = con.sql(f"""
        WITH p AS (
            SELECT pr.*, pm.state
            FROM prices pr
            LEFT JOIN read_parquet('{PREMISES}') pm USING (premise_code)
        )
        SELECT p.item_code,
               i.item, i.unit, i.item_group, i.item_category,
               COUNT(*) FILTER (WHERE date <  DATE '{SST_DATE}') AS obs_pre,
               COUNT(*) FILTER (WHERE date >= DATE '{SST_DATE}') AS obs_post,
               COUNT(DISTINCT premise_code) AS n_premises,
               COUNT(DISTINCT state)        AS n_states,
               ROUND(MEDIAN(price), 2)      AS median_price
        FROM p
        LEFT JOIN read_parquet('{ITEMS}') i USING (item_code)
        GROUP BY ALL
        ORDER BY i.item_category, i.item_group, i.item
    """).df()

    out = OUT_DIR / "item_inventory.csv"
    inventory.to_csv(out, index=False, encoding="utf-8-sig")  # utf-8-sig opens cleanly in Excel

    print(f"\n3. Items by category (full list saved to {out})")
    print(
        inventory.groupby("item_category", dropna=False)
        .agg(items=("item_code", "count"), obs_pre=("obs_pre", "sum"), obs_post=("obs_post", "sum"))
        .to_string()
    )

    both = inventory[(inventory.obs_pre > 0) & (inventory.obs_post > 0)]
    print(f"\nItems in sample: {len(inventory)}")
    print(f"Items observed both before and after 1 July 2025: {len(both)}")
    unmatched = inventory.item.isna().sum()
    if unmatched:
        print(f"WARNING: {unmatched} item codes have no match in lookup_item")


if __name__ == "__main__":
    main()
