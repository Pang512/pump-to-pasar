-- Dimension: one row per premise that appears in the lookup OR in the price data.
-- A handful of price rows (under 300) use premise codes missing from the lookup.
-- They get region 'Unknown', so every price row still has a matching premise,
-- and the analysis marts simply leave 'Unknown' out.

with lookup as (

    select * from {{ ref('stg_pricecatcher__premises') }}

),

codes_in_prices as (

    select distinct premise_id from {{ ref('stg_pricecatcher__prices') }}

),

all_premises as (

    select premise_id from lookup
    union
    select premise_id from codes_in_prices

)

select
    'MY'                                       as country_code,
    a.premise_id,
    coalesce(l.premise_name, 'UNKNOWN PREMISE ' || a.premise_id) as premise_name,
    l.premise_type,
    l.state,
    l.district,
    coalesce(l.region, 'Unknown')              as region,
    (l.premise_id is not null)                 as is_in_lookup
from all_premises a
left join lookup l using (premise_id)
