"""
Print headline numbers from the built warehouse (run after `dbt build`).

These are the real figures for the README, memo and resume:
total price rows, items, premises, and how much data the known gaps affect.

Run from the project root:  python scripts/warehouse_summary.py
"""

from pathlib import Path

import duckdb

DB = Path("warehouse/pump_to_pasar.duckdb")


def show(con, title, sql):
    print(f"\n{title}")
    print(con.sql(sql).df().to_string(index=False))


def main() -> None:
    # read_only so this never changes or locks the warehouse
    con = duckdb.connect(str(DB), read_only=True)

    show(con, "1. Warehouse totals", """
        select count(*)                      as price_rows,
               count(distinct item_id)       as items,
               count(distinct premise_id)    as premises,
               min(price_date)               as first_date,
               max(price_date)               as last_date
        from fct_prices
    """)

    show(con, "2. Rows by region", """
        select p.region,
               count(*) as price_rows,
               round(100.0 * count(*) / sum(count(*)) over (), 2) as pct_rows,
               count(distinct f.premise_id) as premises
        from fct_prices f join dim_premise p using (premise_id)
        group by 1 order by 2 desc
    """)

    show(con, "3. Items missing from the lookup (kept as UNNAMED)", """
        select i.is_in_lookup,
               count(distinct f.item_id) as items,
               count(*) as price_rows,
               round(100.0 * count(*) / sum(count(*)) over (), 2) as pct_rows
        from fct_prices f join dim_item i using (item_id)
        group by 1 order by 1 desc
    """)

    show(con, "4. Premise types by region (premises)", """
        select premise_type,
               count(*) filter (where region = 'Peninsular') as peninsular,
               count(*) filter (where region = 'East')       as east
        from dim_premise
        where premise_id in (select distinct premise_id from fct_prices)
        group by 1 order by 2 desc
    """)


if __name__ == "__main__":
    main()
