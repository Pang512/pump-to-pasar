-- Staging: one row per item in the lookup table.

with source as (

    select * from {{ source('pricecatcher', 'items') }}

)

select
    cast(item_code as integer) as item_id,
    trim(item)                 as item_name,
    trim(unit)                 as unit,
    trim(item_group)           as item_group,
    trim(item_category)        as item_category
from source
