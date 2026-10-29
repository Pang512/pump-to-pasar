"""
Feasibility check for the diesel treatment (10 June 2024).

Design: diesel rose to RM3.35/litre in Peninsular Malaysia on 10 June 2024,
but stayed at RM2.15 in Sabah, Sarawak and Labuan. So:
  treated region = Peninsular premises, control region = East Malaysia premises.

This script checks whether the control region has enough data:
  1. rows, items and premises per month in 2024 (spot collection breaks)
  2. premises and observations per region, before vs after 10 June
  3. how many items are observed in BOTH regions, BOTH periods,
     at enough premises to compare (the "usable items")

Run from the project root (after downloading 2024-01 to 2024-12):
  python scripts/diesel_feasibility.py
Writes: outputs/diesel_item_coverage.csv
"""

from pathlib import Path

import duckdb

RAW_DIR = Path("data/raw")
OUT_DIR = Path("outputs")
POLICY_DATE = "2024-06-10"
MIN_PREMISES = 20  # premises per region per period for an item to count as usable

PRICES = (RAW_DIR / "pricecatcher_2024-*.parquet").as_posix()
ITEMS = (RAW_DIR / "lookup_item.parquet").as_posix()
PREMISES = (RAW_DIR / "lookup_premise.parquet").as_posix()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    con = duckdb.connect()

    # Label each price as East or Peninsular, and as before or after the policy.
    con.execute(f"""
        CREATE VIEW p AS
        SELECT CAST(pr.date AS DATE) AS date,
               CAST(pr.premise_code AS INTEGER) AS premise_code,
               CAST(pr.item_code AS INTEGER) AS item_code,
               CAST(pr.price AS DOUBLE) AS price,
               pm.state,
               CASE
                 WHEN pm.state IS NULL THEN 'Unknown'
                 WHEN lower(pm.state) LIKE '%sabah%'
                   OR lower(pm.state) LIKE '%sarawak%'
                   OR lower(pm.state) LIKE '%labuan%' THEN 'East'
                 ELSE 'Peninsular'
               END AS region,
               CASE WHEN CAST(pr.date AS DATE) < DATE '{POLICY_DATE}'
                    THEN 'pre' ELSE 'post' END AS period
        FROM read_parquet('{PRICES}') pr
        LEFT JOIN read_parquet('{PREMISES}') pm
          ON CAST(pr.premise_code AS INTEGER) = pm.premise_code
    """)

    print("\n1. Rows per month in 2024 (look for sudden drops or jumps)")
    print(con.sql("""
        SELECT strftime(date, '%Y-%m') AS month, COUNT(*) AS rows,
               COUNT(DISTINCT item_code) AS items,
               COUNT(DISTINCT premise_code) AS premises
        FROM p GROUP BY 1 ORDER BY 1
    """).df().to_string(index=False))

    print("\n2. States found and how they were grouped (check East = Sabah, Sarawak, Labuan only)")
    print(con.sql("""
        SELECT region, state, COUNT(DISTINCT premise_code) AS premises, COUNT(*) AS rows
        FROM p GROUP BY 1, 2 ORDER BY 1, 2
    """).df().to_string(index=False))

    print(f"\n3. Region x period (policy date {POLICY_DATE})")
    print(con.sql("""
        SELECT region, period, COUNT(DISTINCT premise_code) AS premises,
               COUNT(DISTINCT item_code) AS items, COUNT(*) AS rows
        FROM p WHERE region <> 'Unknown'
        GROUP BY 1, 2 ORDER BY 1, 2 DESC
    """).df().to_string(index=False))

    # Per item: premises reporting it in each region x period.
    coverage = con.sql(f"""
        WITH c AS (
            SELECT item_code,
                   COUNT(DISTINCT premise_code) FILTER (WHERE region='East' AND period='pre')        AS east_pre,
                   COUNT(DISTINCT premise_code) FILTER (WHERE region='East' AND period='post')       AS east_post,
                   COUNT(DISTINCT premise_code) FILTER (WHERE region='Peninsular' AND period='pre')  AS pen_pre,
                   COUNT(DISTINCT premise_code) FILTER (WHERE region='Peninsular' AND period='post') AS pen_post,
                   COUNT(*) AS rows
            FROM p GROUP BY item_code
        )
        SELECT c.item_code, i.item, i.unit, i.item_category,
               c.east_pre, c.east_post, c.pen_pre, c.pen_post, c.rows,
               (LEAST(c.east_pre, c.east_post, c.pen_pre, c.pen_post) >= {MIN_PREMISES}) AS usable
        FROM c LEFT JOIN read_parquet('{ITEMS}') i USING (item_code)
        ORDER BY i.item_category, i.item
    """).df()

    out = OUT_DIR / "diesel_item_coverage.csv"
    coverage.to_csv(out, index=False, encoding="utf-8-sig")

    usable = coverage[coverage.usable]
    print(f"\n4. Usable items (>= {MIN_PREMISES} premises in each region, before and after): "
          f"{len(usable)} of {len(coverage)}")
    print(usable.groupby("item_category", dropna=False).size().rename("usable_items").to_string())

    missing = coverage.item.isna().sum()
    if missing:
        print(f"\nNote: {missing} item codes have no name in lookup_item (kept, flagged for later).")
    print(f"\nFull table saved to {out}")


if __name__ == "__main__":
    main()
