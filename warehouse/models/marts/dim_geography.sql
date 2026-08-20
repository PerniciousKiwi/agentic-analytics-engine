with geolocation as (

    select
        geolocation_zip_code_prefix,
        geolocation_lat,
        geolocation_lng,
        geolocation_city,
        geolocation_state
    from {{ ref('stg_geolocation') }}

),

coordinates as (

    select
        geolocation_zip_code_prefix,
        avg(geolocation_lat) as latitude,
        avg(geolocation_lng) as longitude
    from geolocation
    group by geolocation_zip_code_prefix

),

city_frequency as (

    select
        geolocation_zip_code_prefix,
        geolocation_city,
        count(*) as city_count,
        row_number() over (
            partition by geolocation_zip_code_prefix
            order by count(*) desc, geolocation_city
        ) as city_rank
    from geolocation
    group by
        geolocation_zip_code_prefix,
        geolocation_city

),

state_frequency as (

    select
        geolocation_zip_code_prefix,
        geolocation_state,
        count(*) as state_count,
        row_number() over (
            partition by geolocation_zip_code_prefix
            order by count(*) desc, geolocation_state
        ) as state_rank
    from geolocation
    group by
        geolocation_zip_code_prefix,
        geolocation_state

)

select
    c.geolocation_zip_code_prefix,
    c.latitude,
    c.longitude,
    city.geolocation_city as city,
    state.geolocation_state as state

from coordinates c

left join city_frequency city
    on c.geolocation_zip_code_prefix = city.geolocation_zip_code_prefix
   and city.city_rank = 1

left join state_frequency state
    on c.geolocation_zip_code_prefix = state.geolocation_zip_code_prefix
   and state.state_rank = 1
