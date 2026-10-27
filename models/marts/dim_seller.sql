-- Une ligne par vendeur. seller_type vient de règles heuristiques (seed seller_type_rules).

with sellers as (
    select distinct seller_id, seller
    from {{ ref('int_vehicle_sales_deduped') }}
),

rules as (
    select * from {{ ref('seller_type_rules') }}
),

matched as (
    select
        sellers.seller_id,
        sellers.seller,
        rules.seller_type,
        row_number() over (partition by sellers.seller_id order by rules.priority) as rn
    from sellers
    left join rules
        on sellers.seller like '%' || rules.pattern || '%'
)

select
    seller_id,
    seller                              as seller_name,
    coalesce(seller_type, 'other')      as seller_type
from matched
where rn = 1
