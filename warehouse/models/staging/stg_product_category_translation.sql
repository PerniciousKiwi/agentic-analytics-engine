select
    cast(product_category_name as text) as product_category_name,
    cast(product_category_name_english as text) as product_category_name_english

from {{ source('olist', 'product_category_translation') }}
