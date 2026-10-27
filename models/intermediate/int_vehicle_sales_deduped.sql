-- Règles métier appliquées ici, une seule fois :
--   1. lignes décalées exclues
--   2. prix de vente manquant ou < var('min_selling_price') exclu
--   3. date de vente manquante exclue
--   4. une ligne par VIN : la vente la plus récente

with stg as (
    select * from {{ ref('stg_car_prices') }}
),

filtered as (
    select *
    from stg
    where not is_shifted_row
      and selling_price >= {{ var('min_selling_price') }}
      and sale_date is not null
      and vin is not null
)

select
    *,
    md5(concat_ws('|',
        coalesce(make, ''), coalesce(model, ''), coalesce(trim_level, ''),
        coalesce(body_type, ''), coalesce(cast(model_year as varchar), '')
    ))                          as vehicle_model_id,
    md5(coalesce(seller, ''))   as seller_id
from filtered
qualify row_number() over (
    partition by vin
    order by sale_date desc, selling_price desc, seller
) = 1
