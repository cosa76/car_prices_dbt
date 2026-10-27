# car_prices_dbt

Projet dbt local (DuckDB) sur `car_prices.csv`, avec une semantic layer MetricFlow en étoile : un fait, trois dimensions.

## Structure

```
seeds/
  make_aliases.csv          alias de marque gouvernés (vw -> volkswagen...)
  us_states.csv             codes état -> nom, pays, région
  seller_type_rules.csv     règles heuristiques de type vendeur (mot-clé -> type)
models/
  staging/stg_car_prices          typage, normalisation, flags qualité. Aucune exclusion.
  intermediate/int_vehicle_sales_deduped   règles métier + clés de substitution
  marts/fct_vehicle_sales         fait : une ligne par vente gouvernée
  marts/dim_vehicle_model         marque, modèle, finition, carrosserie, année-modèle
  marts/dim_seller                vendeur + seller_type
  marts/dim_state                 état, pays, région
  marts/metricflow_time_spine     calendrier requis par MetricFlow
  semantic/sem_vehicle_sales.yml  semantic model du fait (entités foreign vers les dims)
  semantic/sem_dimensions.yml     semantic models des dimensions
  semantic/metrics.yml            métriques
  semantic/saved_queries.yml      questions métier figées
app/
  streamlit_app.py                rapport Streamlit qui consomme la semantic layer
```

```
                 vehicle_models (vehicle_model)
                          ^
 sellers (seller) <- vehicle_sales (sale) -> states (state)
```

MetricFlow fait les jointures tout seul : `--group-by vehicle_model__make` joint `dim_vehicle_model` à la volée. Ajoute `--explain` pour voir le SQL.

## Installation (Windows, PowerShell)

```powershell
cd C:\Users\WIN11\Documents\ai_projects\semantic_layer\car_prices_dbt
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DBT_PROFILES_DIR = "."
dbt build
mf validate-configs
```

Les 3 warnings « OSI document » sur les métriques cumulatives sont attendus : ils concernent un format d'export, pas le calcul.

## Règles métier (int_vehicle_sales_deduped)

1. Lignes décalées exclues (`state` contient un VIN) : 26 lignes dans la source.
2. Prix de vente manquant ou < 500 $ exclu (`var('min_selling_price')`). Seuil choisi pour la démo, à valider.
3. Date de vente manquante exclue.
4. Une ligne par VIN : la vente la plus récente. Choix de démo, à valider (revente réelle vs doublon).

Non résolus volontairement :
- `condition` mélange deux échelles (1-5 et 11-49). Exposé via `condition_scale`.
- `seller_type` est une heuristique par mot-clé. Environ la moitié des vendeurs tombe en `other`. Enrichis `seller_type_rules.csv` pour l'affiner.

## Métriques

| Métrique | Type | Définition |
|---|---|---|
| revenue | simple | somme des prix de vente |
| sales_count | simple | nombre de ventes |
| avg_selling_price | ratio | revenue / sales_count |
| below_mmr_rate | ratio | ventes sous MMR / ventes avec MMR connue |
| price_vs_mmr | derived | revenue / mmr_total - 1 |
| avg_odometer | simple | moyenne hors sentinelles 999999 |
| revenue_cumulative | cumulative | CA cumulé depuis le début |
| revenue_mtd | cumulative | CA du mois à date (grain_to_date: month) |
| sales_count_7d | cumulative | ventes sur 7 jours glissants |
| revenue_prev_month | derived | revenue décalé d'un mois (offset_window) |
| revenue_mom_growth | derived | croissance mois sur mois |

Attention : la source a des mois quasi vides (avril 2015 : 1 347 ventes). La croissance mois sur mois y est sans valeur (+4 969 % en mai 2015).

## Exemples

```bash
mf list metrics
mf list dimensions --metrics revenue

# Saved queries
mf query --saved-query monthly_kpis --order metric_time__month
mf query --saved-query revenue_by_region_and_seller_type --order -revenue
mf query --saved-query below_mmr_by_body_type --order -sales_count --limit 10

# Jointures automatiques
mf query --metrics revenue,avg_selling_price --group-by vehicle_model__make --order -revenue --limit 10 --explain
mf query --metrics revenue,sales_count --group-by seller__seller_type --order -revenue
mf query --metrics below_mmr_rate --group-by state__region,vehicle_model__body_type

# Temps
mf query --metrics revenue,revenue_cumulative,revenue_mom_growth --group-by metric_time__month --order metric_time__month --start-time 2014-12-01 --end-time 2015-07-31
mf query --metrics sales_count_7d --group-by metric_time__day --start-time 2015-06-01 --end-time 2015-06-30

# Le piège « CA 2015 » : année de vente vs année-modèle
mf query --metrics revenue --group-by metric_time__year
mf query --metrics revenue --group-by metric_time__year,vehicle_model__model_year --where "{{ Dimension('vehicle_model__model_year') }} = 2015"
```

Sans `--start-time/--end-time`, les métriques cumulatives s'étendent sur tout le calendrier (2013 à 2016).

## Rapport Streamlit

```powershell
$env:DBT_PROFILES_DIR = "."
dbt build              # la base DuckDB doit exister
streamlit run app/streamlit_app.py
```

L'app ne contient aucun SQL métier. Chaque chiffre vient d'un appel `mf query --csv`, donc des définitions de `models/semantic/`. Les résultats sont mis en cache (chaque requête MetricFlow prend environ 3 s la première fois).

Onglets :
- **Vue d'ensemble** : KPIs, CA mensuel (mois à couverture partielle en orange), prix moyen et taux sous MMR, détail mensuel.
- **Explorer par dimension** : n'importe quelle métrique par n'importe quelle dimension, avec un seuil de ventes minimum pour éviter les taux sur 1 vente.
- **Cumulés** : `revenue_cumulative`, `revenue_mtd`, `sales_count_7d`.
- **Sous le capot** : la commande `mf query` et le SQL généré par MetricFlow pour la requête en cours.

Filtres (barre latérale) : période de vente, région, type de vendeur. Ils passent en `--where` à MetricFlow.
La période par défaut démarre au 2014-12-01 : les 202 ventes de janvier-février 2014 sont donc hors du total par défaut.

Ferme l'app avant de relancer `dbt build` : DuckDB n'accepte qu'un écrivain à la fois.
