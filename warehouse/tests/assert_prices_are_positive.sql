-- A singular test: dbt runs this query and the test FAILS if it returns any rows.
-- A zero or negative price is impossible, so any row here is a data error.

select *
from {{ ref('stg_pricecatcher__prices') }}
where price <= 0
