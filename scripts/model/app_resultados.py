"""App Streamlit con los resultados del sistema de selección de modelos de tornados.

Muestra el modelo elegido (el mejor), la comparación de modelos por validación cruzada, la prueba
ciega 2025 y el mapa de candidatos 2026. Lee los CSV/MD de ``data/outputs/``.

Ejecutar::
    uv run streamlit run scripts/model/app_resultados.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

OUT = Path(__file__).resolve().parents[2] / "data" / "outputs"

st.set_page_config(page_title="Tornados Chile — Selección de modelo", layout="wide")


@st.cache_data
def read_csv(name: str) -> pd.DataFrame:
    """Lee un CSV de data/outputs (vacío si no existe)."""
    f = OUT / name
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


def read_text(name: str) -> str:
    """Lee un archivo de texto de data/outputs."""
    f = OUT / name
    return f.read_text(encoding="utf-8") if f.exists() else ""


st.title("🌪️ Detección y anticipación de tornados en Chile")
st.caption(
    "Hackatón CR2 · selección de modelo sobre ERA5 (2018–2026), unidad celda 1° × día UTC. "
    "Sistema de apoyo a la revisión, no un pronóstico operativo."
)

cv = read_csv("cv_report.csv")
decision_dia = read_text("decision_dia.md")

# --- Encabezado con el modelo elegido y sus cifras ---------------------------------------------
best_cut = "dia"
cv_dia = cv[cv["corte"] == best_cut] if not cv.empty else pd.DataFrame()
elegido = "M2"
m2 = cv_dia[cv_dia["modelo"] == "M2"]
m1 = cv_dia[cv_dia["modelo"] == "M1"]

st.header(f"Modelo elegido: **{elegido}** (logística penalizada, corte del día)")
if not m2.empty and not m1.empty:
    r2, r1 = m2.iloc[0], m1.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("POD (detección)", f"{r2['POD']:.0%}", help="Fracción de tornados detectados (tolerante)")
    c2.metric("FAR (falsas alarmas)", f"{r2['FAR']:.0%}",
              delta=f"{(r2['FAR'] - r1['FAR']):.0%} vs regla física", delta_color="inverse")
    c3.metric("Días de alerta / detección", f"{r2['dias_por_deteccion']:.1f}",
              delta=f"{(r2['dias_por_deteccion'] - r1['dias_por_deteccion']):.1f} vs M1",
              delta_color="inverse")
    c4.metric("Alertas totales", f"{int(r2['alertas'])}",
              delta=f"{int(r2['alertas'] - r1['alertas'])} vs M1", delta_color="inverse")
    st.info(
        f"Frente a la regla física de Marín et al. (M1), **M2 mantiene la misma detección "
        f"({r2['POD']:.0%}) pero reduce las alertas de {int(r1['alertas'])} a {int(r2['alertas'])}** "
        f"y los días de alerta por tornado de {r1['dias_por_deteccion']:.1f} a "
        f"{r2['dias_por_deteccion']:.1f}."
    )

tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 Comparación de modelos", "🎯 Prueba ciega 2025", "🗺️ Candidatos 2026", "📄 Decisión"]
)

# --- Tab 1: comparación de modelos (CV) --------------------------------------------------------
with tab1:
    st.subheader("Validación cruzada dejando un año fuera (2018–2024)")
    if not cv.empty:
        corte = st.radio("Corte temporal", sorted(cv["corte"].unique()), horizontal=True)
        sub = cv[cv["corte"] == corte].copy()
        show = sub[["modelo", "POD", "FAR", "dias_por_deteccion", "PR_AUC", "detectados",
                    "eventos", "alertas"]].rename(columns={
            "dias_por_deteccion": "días/detección", "detectados": "detectados",
            "eventos": "eventos", "alertas": "alertas"})
        st.dataframe(show.style.format({
            "POD": "{:.0%}", "FAR": "{:.0%}", "días/detección": "{:.1f}", "PR_AUC": "{:.3f}"
        }), use_container_width=True, hide_index=True)
        fig = px.scatter(
            sub, x="FAR", y="POD", text="modelo", size="PR_AUC", color="modelo",
            labels={"FAR": "FAR (falsas alarmas)", "POD": "POD (detección)"},
            title=f"POD vs FAR por modelo — corte {corte}",
        )
        fig.add_hline(y=0.70, line_dash="dash", annotation_text="meta POD 70%")
        fig.add_vline(x=0.50, line_dash="dash", annotation_text="meta FAR 50%")
        fig.update_traces(textposition="top center")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("El tamaño del punto es el PR-AUC. El FAR se mide sobre días de evento y de "
                   "control, por lo que sobrestima el real.")

# --- Tab 2: prueba ciega 2025 ------------------------------------------------------------------
with tab2:
    st.subheader("Prueba ciega 2025 — una sola evaluación, sin reajuste")
    bd = read_csv("blind_2025_dia.csv")
    b12 = read_csv("blind_2025_12utc.csv")
    blind = pd.concat([bd, b12], ignore_index=True)
    if not blind.empty:
        show = blind[["corte", "modelo", "POD", "FAR", "dias_por_deteccion", "detectados", "eventos"]]
        st.dataframe(show.style.format({"POD": "{:.0%}", "FAR": "{:.0%}", "dias_por_deteccion": "{:.1f}"}),
                     use_container_width=True, hide_index=True)
        if not bd.empty:
            r = bd.iloc[0]
            st.success(
                f"En el corte del día, M2 detectó **{int(r['detectados'])} de {int(r['eventos'])}** "
                f"tornados de 2025 (POD {r['POD']:.0%}) en datos nunca vistos durante el ajuste."
            )

# --- Tab 3: candidatos 2026 --------------------------------------------------------------------
with tab3:
    st.subheader("Candidatos 2026 (abril–julio) — corte del día, modelo M2")
    cand = read_csv("candidatos_2026_dia.csv")
    if cand.empty:
        cand = read_csv("candidatos_2026_dia_top300.csv")
    if not cand.empty:
        cand["fecha"] = pd.to_datetime(cand["fecha"])
        solo_alertas = st.checkbox("Mostrar solo celdas-día en alerta", value=True)
        view = cand[cand["alerta"] == 1] if solo_alertas else cand
        st.caption(f"{len(view)} celdas-día ({int(cand['alerta'].sum())} alertas en total). "
                   f"ERA5 disponible hasta {cand['fecha'].max().date()}.")
        fig = px.scatter_geo(
            view.head(500), lat="lat", lon="lon", color="score", size="score",
            hover_data=["fecha", "neg_stp_max", "sherbe_max", "vgp_max"],
            color_continuous_scale="YlOrRd", scope="south america",
            title="Candidatos 2026 (color = puntaje de propensión)",
        )
        fig.update_geos(lataxis_range=[-44, -21], lonaxis_range=[-76, -68], resolution=50,
                        showland=True, landcolor="rgb(240,240,235)")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("**Top 15 candidatos por puntaje**")
        top = view.sort_values("score", ascending=False).head(15)
        cols = ["fecha", "lat", "lon", "score", "neg_stp_max", "sherbe_max", "vgp_max",
                "top1", "top2", "top3"]
        cols = [c for c in cols if c in top.columns]
        st.dataframe(top[cols], use_container_width=True, hide_index=True)
    else:
        st.warning("No se encontraron candidatos 2026.")

# --- Tab 4: decisión -----------------------------------------------------------------------------
with tab4:
    st.subheader("Documento de decisión (regla fijada de antemano)")
    corte_d = st.radio("Corte", ["dia", "12utc"], horizontal=True, key="dec")
    st.markdown(read_text(f"decision_{corte_d}.md") or "_No disponible._")
    st.divider()
    st.subheader("Resumen para el pitch")
    st.markdown(read_text("resumen_pitch.md") or "_No disponible._")
