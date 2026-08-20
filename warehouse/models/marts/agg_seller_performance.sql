with seller_orders as (

    select
        seller_id,
        order_id

    from {{ ref('fct_order_items') }}

    group by
        seller_id,
        order_id

),

seller_sales as (

    select
        seller_id,

        count(*) as total_orders,

        sum(order_sales) as total_sales

    from (

        select
            seller_id,
            order_id,
            sum(price + freight_value) as order_sales

        from {{ ref('fct_order_items') }}

        group by
            seller_id,
            order_id

    ) x

    group by seller_id

),

seller_reviews as (

    select
        so.seller_id,
        avg(r.review_score) as average_review_score

    from seller_orders so

    inner join {{ ref('fct_reviews') }} r
        on so.order_id = r.order_id

    group by so.seller_id

),

seller_delivery as (

    select
        so.seller_id,

        avg(
            case
                when o.delivery_delay_days > 0
                then 1.0
                else 0.0
            end
        ) as late_delivery_rate

    from seller_orders so

    inner join {{ ref('fct_orders') }} o
        on so.order_id = o.order_id

    group by so.seller_id

)

select
    s.seller_id,
    s.total_orders,
    s.total_sales,
    r.average_review_score,
    d.late_delivery_rate

from seller_sales s

left join seller_reviews r
    on s.seller_id = r.seller_id

left join seller_delivery d
    on s.seller_id = d.seller_id
