-- Une ligne par configuration véhicule (marque, modèle, finition, carrosserie, année-modèle).

with sales as (
    select * from {{ ref('int_vehicle_sales_deduped') }}
)

select
    vehicle_model_id,
    make,
    model,
    trim_level,
    body_type,
    model_year,
    count(*) as sales_in_scope
from sales
group by all
