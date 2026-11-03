-- Mart: one row per item, region and week: the analysis panel.
--
-- y = average, across all premise-item pairs, of how far log prices have moved
-- from each pair's own pre-policy level. Comparing Peninsular with East for the
-- SAME item in the SAME week is the core of the difference-in-differences design.
-- About 150,000 rows, small enough for a regression on a laptop.

select
    item_id,
    region,
    is_peninsular,
    week_start,
    event_week,
    is_post,
    any_value(item_category)      as item_category,
    any_value(is_in_lookup)       as is_in_lookup,
    avg(log_price_vs_pre)         as y,
    count(*)                      as n_pairs
from {{ ref('mart_diesel__pair_week') }}
group by item_id, region, is_peninsular, week_start, event_week, is_post
