select o.order_id, c.customer_name
from {{ source("raw", "orders") }} o
join {{ ref("customers") }} c on o.customer_id = c.customer_id
