with customer_history as (

    select
        c.customer_unique_id,
        min(c.customer_id) as customer_id,
        c.customer_zip_code_prefix,
        c.customer_city,
        c.customer_state,
        min(o.order_purchase_timestamp) as valid_from

    from {{ ref('stg_customers') }} as c

    left join {{ ref('stg_orders') }} as o
        on c.customer_id = o.customer_id

    group by
        c.customer_unique_id,
        c.customer_zip_code_prefix,
        c.customer_city,
        c.customer_state

),

customer_versions as (

    select
        customer_unique_id,
        customer_id,
        customer_zip_code_prefix,
        customer_city,
        customer_state,
        valid_from,

        lead(valid_from) over (
            partition by customer_unique_id
            order by valid_from
        ) as valid_to

    from customer_history

)

select
    customer_unique_id,
    customer_id,
    customer_zip_code_prefix,
    customer_city,
    customer_state,
    valid_from,
    valid_to,

    case
        when valid_to is null then true
        else false
    end as is_current

from customer_versions
