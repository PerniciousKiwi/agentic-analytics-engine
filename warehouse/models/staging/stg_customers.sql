select
    cast(customer_id as text) as customer_id,
    cast(customer_unique_id as text) as customer_unique_id,
    cast(customer_zip_code_prefix as text) as customer_zip_code_prefix,
    cast(customer_city as text) as customer_city,
    cast(customer_state as text) as customer_state

from {{ source('olist', 'customers') }}
