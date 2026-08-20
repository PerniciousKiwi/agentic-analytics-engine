select
    order_id,
    order_item_id,

    product_id,
    seller_id,

    product_category_name,

    price,
    freight_value,

    seller_city,
    seller_state

from {{ ref('int_order_items_priced') }}
