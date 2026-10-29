-- Staging: one row per price observation, inside the study window.
-- Only renames and type casts here; no business logic.
-- Column names are country-neutral so another country's data can share later models.

with source as (

    select * from {{ source('pricecatcher', 'prices') }}

),

renamed as (

    select
        cast(date as date)            as price_date,
        cast(premise_code as integer) as premise_id,
        cast(item_code as integer)    as item_id,
        cast(price as decimal(12, 2)) as price
    from source

)

select *
from renamed
where price_date between date '{{ var("study_start_date") }}'
                     and date '{{ var("study_end_date") }}'
