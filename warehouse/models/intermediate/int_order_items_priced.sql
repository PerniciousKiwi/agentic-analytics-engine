select
    oi.order_id,
    oi.order_item_id,
    oi.product_id,
    oi.seller_id,

    oi.shipping_limit_date,
    oi.price,
    oi.freight_value,
    oi.price + oi.freight_value as item_total,

    p.product_category_name,
    p.product_name_lenght,
    p.product_description_lenght,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm,

    s.seller_zip_code_prefix,
    s.seller_city,
    s.seller_state

from {{ ref('stg_order_items') }} as oi

left join {{ ref('stg_products') }} as p
    on oi.product_id = p.product_id

left join {{ ref('stg_sellers') }} as s
    on oi.seller_id = s.seller_id
