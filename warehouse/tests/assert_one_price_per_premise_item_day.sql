-- Checks the grain: we expect at most one price per premise, item and day.
-- Returns the duplicated combinations. Set to warn: duplicates tell us how to
-- build the fact table in step 2b, rather than being a reason to stop.

{{ config(severity = 'warn') }}

select
    price_date,
    premise_id,
    item_id,
    count(*)            as n_rows,
    count(distinct price) as n_distinct_prices
from {{ ref('stg_pricecatcher__prices') }}
group by price_date, premise_id, item_id
having count(*) > 1
