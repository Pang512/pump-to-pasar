-- Dimension: one row per item that appears in the lookup OR in the price data.
-- About 1 million price rows use item codes missing from the lookup. Rather than
-- drop them, we keep them as "unnamed" items: the overall analysis can still use
-- them (it compares each item with itself over time), but category breakdowns can't.

with lookup as (

    select * from {{ ref('stg_pricecatcher__items') }}

),

codes_in_prices as (

    select distinct item_id from {{ ref('stg_pricecatcher__prices') }}

),

all_items as (

    select item_id from lookup
    union
    select item_id from codes_in_prices

)

select
    'MY'                                                         as country_code,
    a.item_id,
    coalesce(l.item_name, 'UNNAMED ITEM ' || a.item_id)          as item_name,
    l.unit,
    coalesce(l.item_group, 'UNMAPPED')                           as item_group,
    coalesce(l.item_category, 'UNMAPPED')                        as item_category,
    (l.item_id is not null)                                      as is_in_lookup
from all_items a
left join lookup l using (item_id)
