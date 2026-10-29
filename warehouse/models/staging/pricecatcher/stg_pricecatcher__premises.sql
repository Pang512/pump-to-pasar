-- Staging: one row per premise, with a region label for the diesel comparison.
-- Region is a simple geographic grouping: Sabah, Sarawak and Labuan form East Malaysia.

with source as (

    select * from {{ source('pricecatcher', 'premises') }}

)

select
    cast(premise_code as integer) as premise_id,
    trim(premise)                 as premise_name,
    trim(address)                 as address,
    trim(premise_type)            as premise_type,
    trim(state)                   as state,
    trim(district)                as district,
    case
        when state is null or trim(state) = ''              then 'Unknown'
        when lower(state) similar to '.*(sabah|sarawak|labuan).*' then 'East'
        else 'Peninsular'
    end                           as region
from source
where premise_code > 0   -- the lookup has a blank placeholder row with code -1
