with orders as (

    select
        order_id,
        customer_id,
        order_status,
        order_purchase_timestamp,
        order_approved_at,
        order_delivered_carrier_date,
        order_delivered_customer_date,
        order_estimated_delivery_date
    from {{ ref('stg_orders') }}

),

customers as (

    select
        customer_id,
        customer_unique_id,
        customer_zip_code_prefix,
        customer_city,
        customer_state
    from {{ ref('stg_customers') }}

),

order_items as (

    select
        order_id,
        count(*) as item_count,
        count(distinct product_id) as distinct_product_count,
        count(distinct seller_id) as distinct_seller_count,
        sum(price) as item_value,
        sum(freight_value) as freight_value
    from {{ ref('int_order_items_priced') }}
    group by order_id

),

payments as (

    select
        order_id,
        sum(payment_value) as payment_value,
        max(payment_installments) as max_payment_installments,
        count(*) as payment_record_count
    from {{ ref('stg_order_payments') }}
    group by order_id

),

reviews as (

    select
        order_id,
        avg(review_score) as average_review_score,
        count(*) as review_count
    from {{ ref('stg_order_reviews') }}
    group by order_id

)

select
    o.order_id,
    o.customer_id,

    c.customer_unique_id,
    c.customer_zip_code_prefix,
    c.customer_city,
    c.customer_state,

    o.order_status,

    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,

    oi.item_count,
    oi.distinct_product_count,
    oi.distinct_seller_count,
    oi.item_value,
    oi.freight_value,

    case
    when oi.item_count is not null
    then oi.item_value + oi.freight_value
end as calculated_order_value,

p.payment_value,

case
    when oi.item_count is null then null
    when p.payment_value is null then null
    else p.payment_value - (
        oi.item_value + oi.freight_value
    )
end as payment_reconciliation_difference,

case
    when oi.item_count is null then 'missing_order_items'
    when p.payment_value is null then 'missing_payment'
    when abs(
        p.payment_value - (
            oi.item_value + oi.freight_value
        )
    ) <= 0.01 then 'matched'
    when p.payment_value > (
        oi.item_value + oi.freight_value
    ) then 'payment_greater'
    when p.payment_value < (
        oi.item_value + oi.freight_value
    ) then 'payment_lower'
end as payment_reconciliation_status,

p.max_payment_installments,
p.payment_record_count,

    r.average_review_score,
    r.review_count,

    case
        when o.order_delivered_customer_date is not null
         and o.order_purchase_timestamp is not null
        then extract(
            epoch from (
                o.order_delivered_customer_date
                - o.order_purchase_timestamp
            )
        ) / 86400.0
    end as delivery_days,

    case
        when o.order_delivered_customer_date is not null
         and o.order_estimated_delivery_date is not null
        then extract(
            epoch from (
                o.order_delivered_customer_date
                - o.order_estimated_delivery_date
            )
        ) / 86400.0
    end as delivery_delay_days

from orders o

left join customers c
    on o.customer_id = c.customer_id

left join order_items oi
    on o.order_id = oi.order_id

left join payments p
    on o.order_id = p.order_id

left join reviews r
    on o.order_id = r.order_id
