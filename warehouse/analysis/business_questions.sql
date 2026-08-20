-- Business Question 1
-- What is total revenue by month?
select
    date_trunc('month', date_day)::date as month,
    sum(calculated_order_value) as revenue
from marts.fct_orders
where calculated_order_value is not null
group by 1
order by 1;


-- Business Question 2
-- What is total GMV by month?
select
    date_trunc('month', date_day)::date as month,
    sum(item_value) as gmv
from marts.fct_orders
where item_value is not null
group by 1
order by 1;


-- Business Question 3
-- Who are the top 10 sellers by total sales?
select
    seller_id,
    total_sales
from marts.agg_seller_performance
order by total_sales desc
limit 10;


-- Business Question 4
-- What is revenue by customer state?
select
    customer_state,
    sum(calculated_order_value) as revenue
from marts.fct_orders
where calculated_order_value is not null
  and customer_state is not null
group by customer_state
order by revenue desc;


-- Business Question 5
-- What is the late-delivery rate by customer state?
select
    customer_state,
    avg(
        case
            when delivery_delay_days > 0 then 1.0
            else 0.0
        end
    ) as late_delivery_rate
from marts.fct_orders
where delivery_delay_days is not null
  and customer_state is not null
group by customer_state
order by late_delivery_rate desc;


-- Business Question 6
-- What is the average order value by month?
select
    date_trunc('month', date_day)::date as month,
    avg(calculated_order_value) as average_order_value
from marts.fct_orders
where calculated_order_value is not null
group by 1
order by 1;


-- Business Question 7
-- What percentage of business customers are repeat customers?
select
    count(*) filter (where total_orders > 1)::numeric
        / nullif(count(*), 0) as repeat_customer_rate
from marts.agg_customer_lifetime;


-- Business Question 8
-- What is the customer lifetime value distribution?
select
    percentile_cont(0.25) within group (order by total_revenue) as p25_ltv,
    percentile_cont(0.50) within group (order by total_revenue) as median_ltv,
    percentile_cont(0.75) within group (order by total_revenue) as p75_ltv,
    percentile_cont(0.90) within group (order by total_revenue) as p90_ltv,
    max(total_revenue) as max_ltv
from marts.agg_customer_lifetime
where total_revenue is not null;


-- Business Question 9
-- What percentage of item value comes from each product category?
select
    product_category_name,
    sum(price) as category_item_value,
    sum(price)
        / nullif(sum(sum(price)) over (), 0) as category_revenue_share
from marts.fct_order_items
where product_category_name is not null
group by product_category_name
order by category_revenue_share desc;


-- Business Question 10
-- What percentage of orders have reconciled payment values?
select
    count(*) filter (
        where payment_reconciliation_status = 'matched'
    )::numeric
    / nullif(count(*), 0) as payment_reconciliation_rate
from marts.fct_orders;
