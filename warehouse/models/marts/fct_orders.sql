select
    order_id,
    customer_id,
    customer_unique_id,

    customer_zip_code_prefix,
    customer_city,
    customer_state,

    order_status,

    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    cast(order_purchase_timestamp as date) as date_day,

    item_count,
    distinct_product_count,
    distinct_seller_count,

    item_value,
    freight_value,
    calculated_order_value,

    payment_value,
    payment_reconciliation_difference,
    payment_reconciliation_status,
    max_payment_installments,
    payment_record_count,

    average_review_score,
    review_count,

    delivery_days,
    delivery_delay_days

from {{ ref('int_orders_enriched') }}
