"""Rapport Streamlit branché sur la semantic layer MetricFlow.

Aucun SQL métier ici : chaque chiffre vient de `mf query`, donc des définitions
gouvernées dans models/semantic/. L'app ne fait que choisir métriques, dimensions et filtres.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATE_MIN, DATE_MAX = "2014-12-01", "2015-07-31"  # plage où la source est dense

METRICS = {
    "revenue": "Chiffre d'affaires",
    "sales_count": "Nombre de ventes",
    "avg_selling_price": "Prix de vente moyen",
    "below_mmr_rate": "Taux de ventes sous cote MMR",
    "price_vs_mmr": "Écart prix vendu vs MMR",
    "avg_odometer": "Kilométrage moyen (miles)",
}
DIMENSIONS = {
    "vehicle_model__make": "Marque",
    "vehicle_model__body_type": "Carrosserie",
    "vehicle_model__model_year": "Année-modèle",
    "seller__seller_type": "Type de vendeur",
    "state__region": "Région",
    "state__state_name": "État",
    "transmission": "Transmission",
}
RATE_METRICS = {"below_mmr_rate", "price_vs_mmr"}


# --- Accès à la semantic layer ---------------------------------------------

def _mf_bin() -> str:
    found = shutil.which("mf")
    if found:
        return found
    scripts = Path(sys.executable).parent
    for name in ("mf.exe", "mf"):
        if (scripts / name).exists():
            return str(scripts / name)
    raise FileNotFoundError("Commande `mf` introuvable. Active le venv du projet.")


def _run_mf(args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "DBT_PROFILES_DIR": str(PROJECT_DIR), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [_mf_bin(), "query", *args],
        cwd=PROJECT_DIR, env=env, capture_output=True, text=True, encoding="utf-8",
    )


def _build_args(metrics, group_by=(), where=(), order=(), limit=None, start=None, end=None, saved_query=None):
    args = ["--saved-query", saved_query] if saved_query else ["--metrics", ",".join(metrics)]
    if group_by:
        args += ["--group-by", ",".join(group_by)]
    for w in where:
        args += ["--where", w]
    if order:
        args += ["--order", ",".join(order)]
    if limit:
        args += ["--limit", str(limit)]
    if start:
        args += ["--start-time", start]
    if end:
        args += ["--end-time", end]
    return args


@st.cache_data(show_spinner="Requête MetricFlow…")
def mf_query(metrics=(), group_by=(), where=(), order=(), limit=None, start=None, end=None, saved_query=None) -> pd.DataFrame:
    args = _build_args(metrics, group_by, where, order, limit, start, end, saved_query)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.csv"
        res = _run_mf(args + ["--csv", str(out)])
        if res.returncode != 0 or not out.exists():
            raise RuntimeError(res.stdout + res.stderr)
        return pd.read_csv(out)


@st.cache_data(show_spinner=False)
def mf_sql(metrics=(), group_by=(), where=(), order=(), limit=None, start=None, end=None, saved_query=None) -> str:
    args = _build_args(metrics, group_by, where, order, limit, start, end, saved_query)
    res = _run_mf(args + ["--explain"])
    lines = (res.stdout or res.stderr).splitlines()
    start_idx = next((i for i, l in enumerate(lines) if l.lstrip().upper().startswith(("SELECT", "WITH"))), 0)
    return "\n".join(lines[start_idx:]).strip()


def in_filter(dim: str, values: list[str]) -> str:
    quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return "{{ Dimension('" + dim + "') }} IN (" + quoted + ")"


# --- Mise en forme -----------------------------------------------------------

def fmt(metric: str, v: float) -> str:
    if pd.isna(v):
        return "n/a"
    if metric in RATE_METRICS or metric == "revenue_mom_growth":
        return f"{v * 100:,.1f} %".replace(",", " ").replace(".", ",")
    if metric == "revenue":
        return f"{v / 1e6:,.1f} M$".replace(",", " ").replace(".", ",")
    if metric == "avg_selling_price":
        return f"{v:,.0f} $".replace(",", " ")
    return f"{v:,.0f}".replace(",", " ")


# --- Page --------------------------------------------------------------------

st.set_page_config(page_title="car_prices · semantic layer", layout="wide")
st.title("Ventes de véhicules : rapport sur la semantic layer")
st.caption("Chaque chiffre vient de `mf query`. Les définitions vivent dans `models/semantic/`, pas dans cette app.")

with st.sidebar:
    st.header("Filtres")
    period = st.date_input(
        "Période de vente",
        value=(pd.Timestamp(DATE_MIN), pd.Timestamp(DATE_MAX)),
        min_value=pd.Timestamp("2014-01-01"), max_value=pd.Timestamp("2015-07-31"),
    )
    start, end = (str(period[0]), str(period[1])) if len(period) == 2 else (DATE_MIN, DATE_MAX)

    try:
        regions_all = mf_query(metrics=("sales_count",), group_by=("state__region",))["state__region"].dropna().tolist()
        types_all = mf_query(metrics=("sales_count",), group_by=("seller__seller_type",))["seller__seller_type"].dropna().tolist()
    except Exception as e:  # noqa: BLE001
        st.error("MetricFlow ne répond pas. As-tu lancé `dbt build` ?")
        st.code(str(e))
        st.stop()

    regions = st.multiselect("Région", sorted(regions_all))
    seller_types = st.multiselect("Type de vendeur", sorted(types_all))
    st.caption("Vide = pas de filtre. `seller_type` est une heuristique (voir seeds/seller_type_rules.csv).")

where = []
if regions:
    where.append(in_filter("state__region", regions))
if seller_types:
    where.append(in_filter("seller__seller_type", seller_types))
where = tuple(where)

tab_kpi, tab_dim, tab_time, tab_sql = st.tabs(["Vue d'ensemble", "Explorer par dimension", "Cumulés", "Sous le capot"])

# --- Vue d'ensemble ---
with tab_kpi:
    kpi_metrics = ("revenue", "sales_count", "avg_selling_price", "below_mmr_rate", "price_vs_mmr")
    tot = mf_query(metrics=kpi_metrics, where=where, start=start, end=end)
    cols = st.columns(len(kpi_metrics))
    for c, m in zip(cols, kpi_metrics):
        c.metric(METRICS[m], fmt(m, tot[m].iloc[0]))

    monthly = mf_query(
        metrics=("revenue", "sales_count", "avg_selling_price", "below_mmr_rate", "revenue_mom_growth"),
        group_by=("metric_time__month",), where=where, order=("metric_time__month",), start=start, end=end,
    )
    monthly["mois"] = pd.to_datetime(monthly["metric_time__month"])
    monthly["couverture"] = monthly["sales_count"].apply(lambda n: "partielle (< 5 000 ventes)" if n < 5000 else "normale")

    left, right = st.columns(2)
    with left:
        st.subheader("CA par mois")
        st.altair_chart(
            alt.Chart(monthly).mark_bar().encode(
                x=alt.X("yearmonth(mois):T", title=None),
                y=alt.Y("revenue:Q", title="revenue ($)"),
                color=alt.Color("couverture:N", scale=alt.Scale(domain=["normale", "partielle (< 5 000 ventes)"], range=["#2a9fd6", "#f0ad4e"])),
                tooltip=["yearmonth(mois):T", alt.Tooltip("revenue:Q", format=",.0f"), "sales_count:Q"],
            ),
            width="stretch",
        )
    with right:
        st.subheader("Prix moyen et taux sous MMR")
        long = monthly.melt(id_vars="mois", value_vars=["avg_selling_price", "below_mmr_rate"])
        base = alt.Chart(monthly).encode(x=alt.X("yearmonth(mois):T", title=None))
        st.altair_chart(
            alt.layer(
                base.mark_line(point=True, color="#2a9fd6").encode(y=alt.Y("avg_selling_price:Q", title="avg_selling_price ($)")),
                base.mark_line(point=True, color="#d9534f", strokeDash=[4, 3]).encode(
                    y=alt.Y("below_mmr_rate:Q", title="below_mmr_rate", axis=alt.Axis(format="%"))),
            ).resolve_scale(y="independent"),
            width="stretch",
        )
        st.caption("Trait plein : prix moyen. Pointillés : taux sous cote MMR.")

    st.subheader("Détail mensuel")
    show = monthly[["mois", "revenue", "sales_count", "avg_selling_price", "below_mmr_rate", "revenue_mom_growth"]].copy()
    show["mois"] = show["mois"].dt.strftime("%Y-%m")
    st.dataframe(
        show, hide_index=True, width="stretch",
        column_config={
            "revenue": st.column_config.NumberColumn(format="%.0f $"),
            "avg_selling_price": st.column_config.NumberColumn(format="%.0f $"),
            "below_mmr_rate": st.column_config.NumberColumn(format="percent"),
            "revenue_mom_growth": st.column_config.NumberColumn("revenue_mom_growth", format="percent"),
        },
    )
    if (monthly["couverture"] != "normale").any():
        st.warning("Certains mois ont moins de 5 000 ventes. La croissance mois sur mois autour de ces mois n'a pas de sens métier.")

# --- Explorer par dimension ---
with tab_dim:
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    metric = c1.selectbox("Métrique", list(METRICS), format_func=lambda m: f"{METRICS[m]} ({m})", index=3)
    dim = c2.selectbox("Dimension", list(DIMENSIONS), format_func=lambda d: f"{DIMENSIONS[d]} ({d})", index=1)
    top_n = c3.number_input("Top N", 5, 50, 15)
    min_sales = c4.number_input("Ventes min.", 0, 100000, 1000, step=500,
                                help="Écarte les catégories trop petites. Indispensable pour les taux.")

    metrics_needed = tuple(dict.fromkeys((metric, "sales_count")))
    df = mf_query(metrics=metrics_needed, group_by=(dim,), where=where, start=start, end=end)
    df = df[df["sales_count"] >= min_sales].sort_values(metric, ascending=False).head(int(top_n))
    df[dim] = df[dim].astype(str)

    st.altair_chart(
        alt.Chart(df).mark_bar(color="#2a9fd6").encode(
            x=alt.X(f"{metric}:Q", title=metric, axis=alt.Axis(format="%") if metric in RATE_METRICS else alt.Axis()),
            y=alt.Y(f"{dim}:N", sort="-x", title=DIMENSIONS[dim]),
            tooltip=[dim, alt.Tooltip(f"{metric}:Q", format=",.4f"), "sales_count:Q"],
        ).properties(height=max(250, 24 * len(df))),
        width="stretch",
    )
    st.dataframe(df, hide_index=True, width="stretch")
    if metric in RATE_METRICS:
        spread = df[metric].max() - df[metric].min() if len(df) else 0
        st.info(f"Écart entre la 1re et la dernière catégorie affichée : {spread * 100:.1f} points. "
                "Un classement sur des écarts de l'ordre du point est fragile.")

# --- Cumulés ---
with tab_time:
    st.subheader("CA cumulé et CA du mois à date")
    cum = mf_query(metrics=("revenue_cumulative", "revenue_mtd"), group_by=("metric_time__day",),
                   where=where, order=("metric_time__day",), start=start, end=end)
    cum["jour"] = pd.to_datetime(cum["metric_time__day"])
    st.altair_chart(
        alt.Chart(cum.melt(id_vars="jour", value_vars=["revenue_cumulative", "revenue_mtd"]))
        .mark_line().encode(x=alt.X("jour:T", title=None), y=alt.Y("value:Q", title="$"), color="variable:N"),
        width="stretch",
    )
    st.caption("`revenue_cumulative` part du début de l'historique, pas du début de la période filtrée.")

    st.subheader("Ventes sur 7 jours glissants")
    roll = mf_query(metrics=("sales_count_7d", "sales_count"), group_by=("metric_time__day",),
                    where=where, order=("metric_time__day",), start=start, end=end)
    roll["jour"] = pd.to_datetime(roll["metric_time__day"])
    st.altair_chart(
        alt.layer(
            alt.Chart(roll).mark_bar(color="#c8d6e5").encode(x="jour:T", y=alt.Y("sales_count:Q", title="ventes")),
            alt.Chart(roll).mark_line(color="#2a9fd6").encode(x="jour:T", y="sales_count_7d:Q"),
        ),
        width="stretch",
    )
    st.caption("Barres : ventes du jour. Ligne : `sales_count_7d`.")

# --- Sous le capot ---
with tab_sql:
    st.markdown(
        "Le SQL ci-dessous est **généré par MetricFlow** pour la requête de l'onglet « Explorer par dimension ». "
        "Change la métrique ou la dimension là-bas et regarde la jointure et les filtres apparaître ici."
    )
    st.code(
        f"mf query --metrics {','.join(metrics_needed)} --group-by {dim}"
        + "".join(f' --where "{w}"' for w in where)
        + f" --start-time {start} --end-time {end}",
        language="bash",
    )
    st.code(mf_sql(metrics=metrics_needed, group_by=(dim,), where=where, start=start, end=end), language="sql")
