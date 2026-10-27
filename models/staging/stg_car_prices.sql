-- Staging : typage, normalisation, flags qualité.
-- Aucune ligne n'est exclue ici. Les exclusions métier vivent dans fct_vehicle_sales.

with src as (
    select * from {{ source('raw', 'car_prices') }}
),

aliases as (
    select * from {{ ref('make_aliases') }}
),

typed as (
    select
        lower(trim(vin))                                        as vin,
        try_cast(year as integer)                               as model_year,
        lower(trim(make))                                       as make_lower,
        model,
        "trim"                                                  as trim_level,
        lower(trim(body))                                       as body_type,
        lower(trim(transmission))                               as transmission,
        lower(trim(state))                                      as state,
        try_cast(condition as double)                           as condition_raw,
        try_cast(odometer as double)                            as odometer,
        lower(trim(color))                                      as color,
        lower(trim(interior))                                   as interior,
        lower(trim(seller))                                     as seller,
        try_cast(mmr as double)                                 as mmr,
        try_cast(sellingprice as double)                        as selling_price,
        -- 'Tue Dec 16 2014 12:30:00 GMT-0800 (PST)' -> on garde la date locale
        try_strptime(substr(saledate, 5, 11), '%b %d %Y')::date as sale_date,
        saledate                                                as sale_date_raw
    from src
)

select
    typed.* exclude (make_lower),
    coalesce(aliases.make, typed.make_lower)                    as make,
    typed.make_lower                                            as make_raw,

    -- Flags qualité (documentés, pas filtrés)
    length(typed.state) <> 2                                    as is_shifted_row,
    case
        when typed.condition_raw between 1 and 5   then '1-5'
        when typed.condition_raw between 10 and 50 then '10-50'
        else 'unknown'
    end                                                         as condition_scale,
    typed.odometer >= 999999                                    as is_odometer_sentinel
from typed
left join aliases on typed.make_lower = aliases.raw_make
