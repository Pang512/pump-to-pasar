-- Fact: one row per premise, item and day (the "grain"), with the observed price.
-- Stored as a table, because the analysis reads it many times.
-- The country code lets another country's prices be added later with the same shape.

{{ config(materialized = 'table') }}

select
    'MY'        as country_code,
    price_date,
    premise_id,
    item_id,
    price,
    'MYR'       as currency
from {{ ref('stg_pricecatcher__prices') }}
