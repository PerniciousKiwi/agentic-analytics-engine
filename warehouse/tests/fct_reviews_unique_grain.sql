select
    order_id,
    review_id,
    count(*) as row_count
from {{ ref('fct_reviews') }}
group by
    order_id,
    review_id
having count(*) > 1
