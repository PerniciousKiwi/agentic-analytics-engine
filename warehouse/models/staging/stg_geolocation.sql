select
    cast(geolocation_zip_code_prefix as text) as geolocation_zip_code_prefix,
    cast(geolocation_lat as numeric) as geolocation_lat,
    cast(geolocation_lng as numeric) as geolocation_lng,
    cast(geolocation_city as text) as geolocation_city,
    cast(geolocation_state as text) as geolocation_state

from {{ source('olist', 'geolocation') }}
