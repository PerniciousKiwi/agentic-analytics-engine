select
    p.product_id,
    p.product_category_name,
    t.product_category_name_english,

    p.product_name_lenght,
    p.product_description_lenght,
    p.product_photos_qty,

    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm

from {{ ref('stg_products') }} as p

left join {{ ref('stg_product_category_translation') }} as t
    on p.product_category_name = t.product_category_name
