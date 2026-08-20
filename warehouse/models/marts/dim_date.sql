with date_spine as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2016-09-04' as date)",
        end_date="cast('2018-10-18' as date)"
    ) }}

),

dates as (

    select
        cast(date_day as date) as date_day
    from date_spine

)

select
    date_day,

    extract(year from date_day)::integer as year,

    extract(month from date_day)::integer as month,

    extract(quarter from date_day)::integer as quarter,

    case
        when extract(month from date_day) between 4 and 6 then 1
        when extract(month from date_day) between 7 and 9 then 2
        when extract(month from date_day) between 10 and 12 then 3
        when extract(month from date_day) between 1 and 3 then 4
    end as fiscal_quarter

from dates
