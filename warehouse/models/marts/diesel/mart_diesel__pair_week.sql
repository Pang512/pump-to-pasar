-- Mart: one row per premise-item "pair" per week, for the diesel analysis.
--
-- Steps:
--  1. Daily prices -> weekly average of log price for each premise and item.
--     Log prices turn differences into percentage changes.
--  2. Keep only pairs seen both before and after the policy week, so we compare
--     the same shops selling the same items over time.
--  3. Subtract each pair's own average before the policy. This removes everything
--     fixed about that shop and item (location, brand, pack size), which is what
--     "premise and item fixed effects" means. What's left is how far the pair's
--     price has moved from its own pre-policy level.

with weekly as (

    select
        f.premise_id,
        f.item_id,
        d.week_start,
        p.region,
        p.premise_type,
        p.state,
        avg(ln(f.price))   as log_price,
        count(*)           as n_days
    from {{ ref('fct_prices') }} f
    join {{ ref('dim_premise') }} p using (premise_id)
    join {{ ref('dim_date') }}    d on d.date_day = f.price_date
    where p.region in ('Peninsular', 'East')
      and d.week_start between date '{{ var("first_full_week") }}'
                           and date '{{ var("last_full_week") }}'
    group by all

),

flagged as (

    select
        *,
        (week_start >= date '{{ var("diesel_policy_date") }}') as is_post
    from weekly

),

pair_stats as (

    select
        premise_id,
        item_id,
        avg(log_price) filter (where not is_post) as pre_mean_log_price,
        count(*)       filter (where not is_post) as pre_weeks,
        count(*)       filter (where is_post)     as post_weeks
    from flagged
    group by premise_id, item_id

)

select
    f.premise_id,
    f.item_id,
    f.week_start,
    -- whole weeks since the policy week: 0 = week of 10 June 2024, -1 = the week before
    cast(date_diff('day', date '{{ var("diesel_policy_date") }}', f.week_start) / 7 as integer) as event_week,
    f.is_post,
    f.region,
    (f.region = 'Peninsular')                         as is_peninsular,
    f.premise_type,
    f.state,
    i.item_category,
    i.is_in_lookup,
    f.n_days,
    f.log_price,
    f.log_price - s.pre_mean_log_price                as log_price_vs_pre
from flagged f
join pair_stats s using (premise_id, item_id)
join {{ ref('dim_item') }} i using (item_id)
where s.pre_weeks > 0 and s.post_weeks > 0
