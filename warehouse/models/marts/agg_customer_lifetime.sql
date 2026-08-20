select
    customer_unique_id,

    min(order_purchase_timestamp)::date as first_order_date,
    max(order_purchase_timestamp)::date as last_order_date,

    count(distinct order_id) as total_orders,

    sum(calculated_order_value) as total_revenue,

    current_date - max(order_purchase_timestamp)::date
        as days_since_last_order

from {{ ref('fct_orders') }}

group by customer_unique_id
