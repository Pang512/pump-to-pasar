-- Mart: one row per item, region, premise type and week.
-- Same as mart_diesel__item_region_week, but split by shop type
-- (wet market, supermarket, hypermarket, ...) so step 3b can ask WHERE
-- any diesel cost showed up.

select
    item_id,
    region,
    is_peninsular,
    premise_type,
    week_start,
    event_week,
    is_post,
    any_value(item_category)  as item_category,
    avg(log_price_vs_pre)     as y,
    count(*)                  as n_pairs
from {{ ref('mart_diesel__pair_week') }}
where premise_type is not null
group by item_id, region, is_peninsular, premise_type, week_start, event_week, is_post
