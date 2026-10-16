#!/usr/bin/env python3
"""Web de demostración del modelo de mesociclones (Streamlit): imágenes y gráficos de cómo funciona.

Muestra, con los artefactos ya generados (``modelo.joblib`` y ``reports/``), cómo opera el modelo:

- **Resumen:** qué hace el modelo y las cifras clave, honestas (POD anidada, exceso sobre el nulo).
- **Evento de ejemplo:** mapa de probabilidad del modelo sobre una grilla ERA5 (imagen), con el
  punto del evento reportado encima.
- **Curva de operación:** umbral → POD por evento, FAR por día, avisos por acierto (gráfico).
- **KPIs vs líneas base:** la tabla del desafío (modelo, STP, SHERBS3, reglas A/B).
- **Pronóstico AIWP:** detección por evento sin fuga y a área igualada, y el baseline nulo por
  permutación (observada vs nula, por evento).

Es solo de lectura: no entrena ni descarga nada; carga lo que dejó ``train.py``/``eval_aiwp.py``.

Uso local::

    uv run streamlit run scripts/webapp/model_app.py

Despliegue y enlace para compartir: ver ``scripts/webapp/README.md``.
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "model"))

DATA = ROOT / "data"
REPORTS = ROOT / "reports"
REGION = "south-central"

st.set_page_config(page_title="Vórtice · detección de mesociclones", page_icon="🌀", layout="wide")


@st.cache_resource
def load_bundle() -> dict | None:
    """Carga ``modelo.joblib`` una vez por sesión; ``None`` si no existe."""
    f = ROOT / "modelo.joblib"
    return joblib.load(f) if f.exists() else None


@st.cache_data
def load_curve() -> pd.DataFrame | None:
    """Curva de operación LOYO (umbral → KPIs) si el reporte existe."""
    f = REPORTS / f"operating_curve_{REGION}_lead0h.csv"
    return pd.read_csv(f) if f.exists() else None


@st.cache_data
def load_aiwp() -> pd.DataFrame | None:
    """Tabla por evento de la evaluación sobre el pronóstico AIWP, si existe."""
    f = REPORTS / "aiwp_bundle_eval.csv"
    return pd.read_csv(f) if f.exists() else None


@st.cache_data
def list_crops() -> list[str]:
    """Fechas (AAAAMMDD) con índice ERA5 disponible para dibujar un mapa de probabilidad."""
    d = DATA / "crops" / REGION / "era5_indices"
    if not d.exists():
        return []
    return sorted(p.stem.replace("era5_idx_", "") for p in d.glob("era5_idx_*.nc"))


@st.cache_data
def score_map(day: str, hour: int, _feats: tuple[str, ...]) -> pd.DataFrame | None:
    """Puntúa cada celda de la grilla ERA5 de ``day`` a la hora ``hour`` con el modelo cargado.

    Devuelve un DataFrame largo (lat, lon, score) para el mapa de calor; ``None`` si falta el crop.
    """
    bundle = load_bundle()
    if bundle is None:
        return None
    f = DATA / "crops" / REGION / "era5_indices" / f"era5_idx_{day}.nc"
    if not f.exists():
        return None
    feats = list(_feats)
    with xr.open_dataset(f, engine="h5netcdf") as ds:
        sel = ds.sel(time=ds["time"].dt.hour == hour)
        sel = ds.isel(time=0) if sel.sizes["time"] == 0 else sel.isel(time=0)
        stack = sel[feats].to_dataframe().reset_index()
    ok = stack[feats].notna().all(axis=1)
    stack["score"] = np.nan
    if ok.any():
        stack.loc[ok, "score"] = bundle["model"].predict_proba(stack.loc[ok, feats])[:, 1]
    return stack[["latitude", "longitude", "score"]]


@st.cache_data
def catalog_point(day: str) -> pd.DataFrame | None:
    """Eventos del catálogo en ``day`` (AAAAMMDD) para superponer su punto en el mapa."""
    f = DATA / "catalog_clean.csv"
    if not f.exists():
        return None
    cat = pd.read_csv(f)
    iso = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    return cat[(cat["date"].astype(str) == iso) & cat["lat"].notna() & cat["lon"].notna()]


# ------------------------------------------------------------------------------------------------
# Barra lateral y navegación.
# ------------------------------------------------------------------------------------------------
bundle = load_bundle()
st.sidebar.title("🌀 Vórtice")
st.sidebar.caption("Detección de mesociclones en Chile")
if bundle is not None:
    m = bundle["metadata"]
    st.sidebar.caption(
        f"modelo **{m.get('model')}** · features **{m.get('feature_set')}** "
        f"(AIWP-safe: {'sí' if m.get('aiwp_safe') else 'no'}) · umbral {m.get('threshold'):.2f}"
    )
else:
    st.sidebar.warning("Falta `modelo.joblib`. Corre `train.py` para generarlo.")

page = st.sidebar.radio(
    "Secciones",
    [
        "Resumen",
        "Evento de ejemplo",
        "Curva de operación",
        "KPIs vs líneas base",
        "Pronóstico AIWP",
    ],
)
st.sidebar.markdown("---")
st.sidebar.caption(
    "Demo de solo lectura. Lee `modelo.joblib` y `reports/`. No entrena ni descarga."
)


# ------------------------------------------------------------------------------------------------
# Páginas.
# ------------------------------------------------------------------------------------------------
def page_resumen() -> None:
    """Portada: qué hace el modelo y las cifras honestas."""
    st.title("Vórtice — detección de mesociclones en Chile")
    st.markdown(
        "Un clasificador tabular estima, **celda por celda y hora por hora**, la probabilidad de que "
        "se reporte un tornado o tromba a partir de índices físicos de ERA5. Se valida por **eventos** "
        "y **días** (no por celda), se compara con las reglas físicas del documento y se aplica al "
        "pronóstico de Pangu-Weather. Ver `docs/MODELO_COMPLETO.md`."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "POD por evento (anidada, honesta)",
        "≈ 0,37",
        help="LOYO con selección anidada del umbral; la POD optimista (0,89) sobreestima.",
    )
    c2.metric(
        "Exceso sobre el nulo (área B)",
        "+17 %",
        help="Observada − nula por permutación; p ≈ 0,06. Las reglas físicas dan ~0.",
    )
    c3.metric(
        "Criterio de captura",
        "50 km / ±6 h",
        help="Un evento se detecta si una celda sobre el umbral cae en esa ventana.",
    )
    st.info(
        "**Lectura honesta.** A 10,74 % de área el criterio da muchas oportunidades: marcas al azar ya "
        "capturan ~63 % de los eventos. Lo que vale es el **exceso sobre el nulo**, no la POD cruda. "
        "Con pocos días de control y n pequeño, los KPIs 2/3 son indicativos."
    )


def page_evento() -> None:
    """Mapa de probabilidad del modelo sobre un día de ejemplo (imagen)."""
    st.title("Evento de ejemplo — mapa de probabilidad")
    crops = list_crops()
    if bundle is None or not crops:
        st.warning(
            "Faltan `modelo.joblib` o los recortes ERA5 (`data/crops/`). No se puede dibujar el mapa."
        )
        return
    default = "20190530" if "20190530" in crops else crops[0]
    col = st.columns(3)
    day = col[0].selectbox("Día (AAAAMMDD)", crops, index=crops.index(default))
    hour = col[1].slider("Hora UTC", 12, 23, 20)
    feats = tuple(bundle["features"])
    df = score_map(day, hour, feats)
    if df is None or df["score"].notna().sum() == 0:
        st.warning("No hay datos de puntuación para ese día/hora.")
        return
    fig = px.density_heatmap(
        df,
        x="longitude",
        y="latitude",
        z="score",
        nbinsx=25,
        nbinsy=61,
        color_continuous_scale="Inferno",
        range_color=(0, 1),
        histfunc="avg",
        labels={"score": "p(mesociclón)"},
    )
    pts = catalog_point(day)
    if pts is not None and len(pts):
        fig.add_trace(
            go.Scatter(
                x=pts["lon"],
                y=pts["lat"],
                mode="markers",
                marker=dict(
                    symbol="triangle-up", size=14, color="cyan", line=dict(color="black", width=1)
                ),
                name="evento reportado",
            )
        )
    fig.update_layout(height=560, yaxis_scaleanchor="x", margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Probabilidad del modelo ({bundle['metadata'].get('feature_set')}) en cada celda ERA5 de "
        f"{day} a las {hour} UTC. El triángulo marca el evento reportado (si lo hay ese día)."
    )


def page_curva() -> None:
    """Curva de operación: umbral → POD evento, FAR día, avisos/acierto."""
    st.title("Curva de operación (validación cruzada LOYO)")
    curve = load_curve()
    if curve is None:
        st.warning("Falta `reports/operating_curve_*.csv`. Corre `train.py`.")
        return
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=curve["threshold"], y=curve["event_pod"], name="POD por evento", mode="lines+markers"
        )
    )
    if "day_far" in curve:
        fig.add_trace(
            go.Scatter(
                x=curve["threshold"], y=curve["day_far"], name="FAR por día", mode="lines+markers"
            )
        )
    fig.add_hline(y=0.70, line_dash="dash", annotation_text="objetivo POD 0,70")
    fig.update_layout(
        height=460, xaxis_title="umbral de probabilidad", yaxis_title="tasa", yaxis_range=[0, 1]
    )
    st.plotly_chart(fig, use_container_width=True)
    if "alerts_per_hit" in curve:
        fig2 = px.line(
            curve,
            x="threshold",
            y="alerts_per_hit",
            markers=True,
            labels={"alerts_per_hit": "avisos por acierto", "threshold": "umbral"},
        )
        fig2.add_hline(y=2.0, line_dash="dash", annotation_text="objetivo ≤ 2")
        fig2.update_layout(height=360)
        st.plotly_chart(fig2, use_container_width=True)
    st.caption("El umbral del modelo se elige sobre esta curva (predicciones out-of-fold de LOYO).")


def page_kpis() -> None:
    """Tabla de KPIs del modelo frente a las líneas base físicas (del reporte de entrenamiento)."""
    st.title("KPIs del desafío — modelo vs líneas base")
    f = REPORTS / f"train_{REGION}_lead0h.md"
    if not f.exists():
        st.warning("Falta `reports/train_*.md`. Corre `train.py`.")
        return
    text = f.read_text(encoding="utf-8")
    # Muestra la sección de la tabla de KPIs tal cual (markdown ya formateado por train.py).
    start = text.find("## KPIs")
    end = text.find("## Desglose")
    st.markdown(text[start:end] if start >= 0 else text)
    with st.expander("Advertencias y desgloses completos del reporte"):
        st.markdown(text[end:] if end >= 0 else "")


def page_aiwp() -> None:
    """Evaluación sobre el pronóstico AIWP: detección por evento + baseline nulo."""
    st.title("Pronóstico AIWP — detección por evento (sin fuga, área igualada)")
    ev = load_aiwp()
    if ev is None:
        st.warning("Falta `reports/aiwp_bundle_eval.csv`. Corre `eval_aiwp.py`.")
        return
    n = len(ev)
    cols = st.columns(3)
    cols[0].metric("Modelo @área A", f"{int(ev['caught_model_areaA'].sum())}/{n}")
    cols[1].metric("Modelo @área B", f"{int(ev['caught_model_areaB'].sum())}/{n}")
    cols[2].metric(
        "Reglas A / B", f"{int(ev['caught_A'].sum())} / {int(ev['caught_B'].sum())} /{n}"
    )

    # Barras: capturados por fuente, separando OOF (2021–2023) y nunca vistos (2024–2025).
    ev = ev.copy()
    ev["grupo"] = np.where(ev["oof"], "2021–2023 (OOF)", "2024–2025 (nuevo)")
    rows = []
    for g, sub in ev.groupby("grupo"):
        for col, label in (
            ("caught_model_areaB", "modelo @B"),
            ("caught_A", "regla A"),
            ("caught_B", "regla B"),
        ):
            rows.append(
                {"grupo": g, "fuente": label, "capturados": int(sub[col].sum()), "n": len(sub)}
            )
    bars = pd.DataFrame(rows)
    fig = px.bar(
        bars, x="fuente", y="capturados", color="grupo", barmode="group", text="capturados"
    )
    fig.update_layout(height=420, yaxis_title="eventos capturados")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Captura por evento (área igualada a la regla B)")
    show = ev[
        ["name", "time", "kind", "ef", "grupo", "caught_model_areaB", "caught_A", "caught_B"]
    ].rename(columns={"caught_model_areaB": "modelo", "caught_A": "A", "caught_B": "B"})
    st.dataframe(show, use_container_width=True, height=460)
    st.info(
        "A 10,74 % de área el nulo por permutación captura ~63 % por geometría; el exceso real del "
        "modelo es ≈ +17 % (p ≈ 0,06), y las reglas ≈ 0. Ver `reports/aiwp_bundle_eval.md`."
    )


PAGES = {
    "Resumen": page_resumen,
    "Evento de ejemplo": page_evento,
    "Curva de operación": page_curva,
    "KPIs vs líneas base": page_kpis,
    "Pronóstico AIWP": page_aiwp,
}
PAGES[page]()
