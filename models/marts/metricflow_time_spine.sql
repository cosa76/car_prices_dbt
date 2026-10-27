-- Time spine requis par MetricFlow (granularité jour).
select cast(range as date) as date_day
from range(date '2013-01-01', date '2017-01-01', interval 1 day)
