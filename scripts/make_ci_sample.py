"""Génère l'échantillon CI ci/car_prices_sample.csv à partir du CSV complet.

L'échantillon est déterministe : pas d'aléatoire, un tri par hash md5 de la ligne.
Il garde tous les cas limites qui exercent les règles métier, plus un fond de lignes ordinaires.

Usage (depuis le dossier du projet dbt) :
    python scripts/make_ci_sample.py [chemin_csv_complet] [chemin_sortie]
"""

import sys
from pathlib import Path

import duckdb

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "../car_prices.csv")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "ci/car_prices_sample.csv")

# Tailles des tranches. Modifier ici pour grossir ou réduire l'échantillon.
N_BACKGROUND = 5000      # lignes ordinaires
N_LOW_PRICE = 50         # prix manquant ou < 500 $
N_NULL_DATE = 50         # date de vente manquante ou illisible
N_DUP_VINS = 300         # VIN vendus plusieurs fois (toutes leurs ventes sont gardées)
N_ODO_SENTINEL = 20      # odomètre sentinelle 999999

QUERY = f"""
with src as (
    select t.*, md5(t::varchar) as _h
    from read_csv('{SRC.as_posix()}', header=true, all_varchar=true) as t
),
dup_vins as (
    select vin from src
    where vin is not null
    group by vin having count(*) > 1
    order by md5(vin) limit {N_DUP_VINS}
),
picked as (
    -- 1. lignes décalées : toutes
    select _h from src where length(state) <> 2
    union
    -- 2. prix manquant ou < 500 $
    (select _h from src
     where try_cast(sellingprice as double) is null or try_cast(sellingprice as double) < 500
     order by _h limit {N_LOW_PRICE})
    union
    -- 3. date de vente manquante ou illisible
    (select _h from src
     where try_strptime(substr(saledate, 5, 11), '%b %d %Y') is null
     order by _h limit {N_NULL_DATE})
    union
    -- 4. VIN en doublon : toutes leurs ventes
    select _h from src where vin in (select vin from dup_vins)
    union
    -- 5. odomètre sentinelle
    (select _h from src where try_cast(odometer as double) >= 999999
     order by _h limit {N_ODO_SENTINEL})
    union
    -- 6. fond ordinaire
    (select _h from src order by _h limit {N_BACKGROUND})
)
select src.* exclude (_h)
from src
where _h in (select _h from picked)
order by src._h
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
con = duckdb.connect()
con.execute(f"copy ({QUERY}) to '{OUT.as_posix()}' (header, delimiter ',')")
n = con.execute(f"select count(*) from read_csv('{OUT.as_posix()}', header=true, all_varchar=true)").fetchone()[0]
print(f"{OUT} : {n} lignes")
