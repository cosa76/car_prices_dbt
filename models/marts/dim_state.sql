select
    state_code,
    state_name,
    country,
    region
from {{ ref('us_states') }}
