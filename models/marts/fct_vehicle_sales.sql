-- Fait gouverné : une ligne par vente retenue. Les attributs descriptifs vivent dans les dimensions.

select
    vin                                                  as sale_id,
    vin,
    sale_date,
    vehicle_model_id,
    seller_id,
    state                                                as state_code,
    transmission,
    condition_raw,
    condition_scale,
    odometer,
    is_odometer_sentinel,
    color,
    interior,
    selling_price,
    mmr,
    case when mmr > 0 and selling_price < mmr then 1 else 0 end as is_below_mmr
from {{ ref('int_vehicle_sales_deduped') }}
