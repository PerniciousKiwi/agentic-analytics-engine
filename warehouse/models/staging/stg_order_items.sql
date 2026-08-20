select
    cast(order_id as text) as order_id,
    cast(order_item_id as integer) as order_item_id,
    cast(product_id as text) as product_id,
    cast(seller_id as text) as seller_id,
    cast(shipping_limit_date as timestamp) as shipping_limit_date,
    cast(price as numeric) as price,
    cast(freight_value as numeric) as freight_value

from {{ source('olist', 'order_items') }}
