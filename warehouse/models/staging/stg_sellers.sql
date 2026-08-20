select
    cast(seller_id as text) as seller_id,
    cast(seller_zip_code_prefix as text) as seller_zip_code_prefix,
    cast(seller_city as text) as seller_city,
    cast(seller_state as text) as seller_state

from {{ source('olist', 'sellers') }}
