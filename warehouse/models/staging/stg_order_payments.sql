select
    cast(order_id as text) as order_id,
    cast(payment_sequential as integer) as payment_sequential,
    cast(payment_type as text) as payment_type,
    cast(payment_installments as integer) as payment_installments,
    cast(payment_value as numeric) as payment_value

from {{ source('olist', 'order_payments') }}
