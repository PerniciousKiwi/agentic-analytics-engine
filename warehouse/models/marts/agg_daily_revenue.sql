select
    date_day,
    count(distinct order_id) as order_count,
    sum(calculated_order_value) as revenue,
    sum(item_value) as gmv,
    sum(freight_value) as freight_revenue

from {{ ref('fct_orders') }}

group by date_day
