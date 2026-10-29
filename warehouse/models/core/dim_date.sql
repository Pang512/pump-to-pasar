-- Dimension: one row per calendar day in the study window (a "date spine").
-- Generic calendar attributes only; policy dates belong in the analysis marts.

with days as (

    select cast(d as date) as date_day
    from range(
        date '{{ var("study_start_date") }}',
        date '{{ var("study_end_date") }}' + interval 1 day,
        interval 1 day
    ) as t(d)

)

select
    date_day,
    year(date_day)                          as year,
    month(date_day)                         as month,
    cast(date_trunc('month', date_day) as date) as month_start,
    cast(date_trunc('week', date_day) as date)  as week_start,   -- weeks start on Monday
    isodow(date_day)                        as day_of_week,      -- 1 = Monday, 7 = Sunday
    (isodow(date_day) >= 6)                 as is_weekend
from days
