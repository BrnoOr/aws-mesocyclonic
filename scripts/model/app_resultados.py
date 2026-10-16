"""App Streamlit con el producto final: candidatos a tornado en Chile, explicados.

Refleja la presentación del producto (`docs/presentacion_producto_final.pptx`): el problema, la
selección de modelos, los resultados por corte, el detalle año a año, la prueba ciega 2025, las metas
del proyecto y la lista priorizada de candidatos 2026 con sus variables explicativas. Lee los CSV/MD
de ``data/outputs/`` que generan `cv.py`, `decide.py`, `score.py` y `resumen_pitch.py`.

Ejecutar::
    uv run streamlit run scripts/model/app_resultados.py --server.port 8502
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

OUT = Path(__file__).resolve().parents[2] / "data" / "outputs"

st.set_page_config(
    page_title="Tornados Chile — Candidatos explicados", layout="wide", page_icon="🌪️"
)


@st.cache_data
def read_csv(name: str) -> pd.DataFrame:
    """Lee un CSV de data/outputs (vacío si no existe)."""
    f = OUT / name
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


def read_text(name: str) -> str:
    """Lee un archivo de texto de data/outputs."""
    f = OUT / name
    return f.read_text(encoding="utf-8") if f.exists() else ""


def row(df: pd.DataFrame, corte: str, modelo: str) -> pd.Series | None:
    """Fila del cv_report para un corte y modelo, o None."""
    sub = df[(df["corte"] == corte) & (df["modelo"] == modelo)]
    return sub.iloc[0] if not sub.empty else None


cv = read_csv("cv_report.csv")
by_fold = read_csv("cv_by_fold.csv")

# Modelo elegido por corte, leído de decision_<corte>.md.
import re  # noqa: E402


def elegido_de(corte: str) -> str:
    """Modelo elegido leído de decision_<corte>.md (M1 por defecto)."""
    txt = read_text(f"decision_{corte}.md")
    m = re.search(r"Modelo elegido:\s*\*\*(M\d)\*\*", txt)
    return m.group(1) if m else "M1"


elegido_dia = elegido_de("dia")

# ================================ Encabezado =====================================================
st.title("🌪️ Encontrar las tormentas que nadie vio")
st.markdown(
    "**Detección y anticipación de tornados en Chile** con ERA5 y aprendizaje automático · "
    "Hackatón Breaking Barriers · CR2 · AWS."
)
st.markdown(
    "> El producto es una **lista priorizada de candidatos** (celda de 1° × día UTC) con su puntaje y "
    "los índices físicos que lo explican. Sirve para **revisar casos y buscar en el archivo histórico "
    "los tornados que nadie reportó**. No es un pronóstico operativo: ERA5 es un reanálisis con días "
    "de latencia y el puntaje no es una probabilidad calibrada."
)

# Métricas destacadas del modelo elegido (corte día).
r2 = row(cv, "dia", elegido_dia)
r1 = row(cv, "dia", "M1")
if r2 is not None and r1 is not None:
    st.subheader(f"Modelo elegido (corte del día): **{elegido_dia}** · logística penalizada")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "POD · detección",
        f"{r2['POD']:.0%}",
        f"{int(r2['detectados'])}/{int(r2['eventos'])} eventos",
    )
    c2.metric(
        "FAR · falsas alarmas",
        f"{r2['FAR']:.0%}",
        f"{(r2['FAR'] - r1['FAR']):.0%} vs regla física",
        delta_color="inverse",
    )
    c3.metric(
        "Días alerta / detección",
        f"{r2['dias_por_deteccion']:.1f}",
        f"{(r2['dias_por_deteccion'] - r1['dias_por_deteccion']):.1f} vs M1",
        delta_color="inverse",
    )
    c4.metric(
        "Alertas totales",
        f"{int(r2['alertas'])}",
        f"{int(r2['alertas'] - r1['alertas'])} vs M1",
        delta_color="inverse",
    )

tabs = st.tabs(
    [
        "🧭 El problema",
        "📊 Modelos",
        "📅 Año a año",
        "🎯 Prueba ciega 2025",
        "🏁 Metas",
        "🗺️ Candidatos 2026",
        "📄 Decisión",
    ]
)

# ================================ Tab: el problema ==============================================
with tabs[0]:
    st.subheader("En Chile hay tornados, pero casi nadie los ve")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Catálogo", "102", "tornados y trombas 1554–2025")
    c2.metric("Desde 2015", "68", "el registro crece con los celulares")
    c3.metric("Brote Biobío 2019", "7", "tornados en 24 h (EF1–EF2)")
    c4.metric("Radares en 2019", "0", "nadie ve girar la tormenta")
    st.markdown(
        "**Por qué es difícil (régimen HSLC: alta cizalle, bajo CAPE).** No es Oklahoma: el CAPE es "
        "bajo (200–1.000 J/kg) y la cizalle alta. En el hemisferio sur la SRH y el STP tornádicos son "
        "**negativos** y las supercélulas favorecidas son *left-movers*; usamos `neg_stp = −STP` y "
        "`neg_srh01 = −SRH₀₋₁`. La vara física de comparación es la regla de **Marín et al. (2024)**: "
        "alerta si STP ≤ −0,3 o SHERBE ≥ 1."
    )
    st.info(
        "El catálogo **solo tiene positivos**: no hay «días sin tornado» confirmados. Se plantea como "
        "aprendizaje con **positivos y no etiquetados (PU)**, con sesgo de reporte (población, hora, año)."
    )

# ================================ Tab: modelos ==================================================
with tabs[1]:
    st.subheader("Cinco modelos, del más simple al más flexible")
    st.markdown(
        "M0 climatología · M1 regla física (Marín et al.) · M2 logística L2 · M3 splines · "
        "M4 boosting monótono. Validación **dejando un año fuera** (2018–2024), umbral con POD ≥ 70 % "
        "en validación interna, acierto **tolerante** (celda o vecinas, mismo día o anterior)."
    )
    if not cv.empty:
        corte = str(
            st.radio(
                "Corte temporal",
                sorted(cv["corte"].unique()),
                horizontal=True,
                help="«día» usa 00–23 UTC; «12utc» solo 00–12 UTC del mismo día (anticipación)",
            )
        )
        sub = cv[cv["corte"] == corte].copy()
        show = sub[
            [
                "modelo",
                "POD",
                "FAR",
                "dias_por_deteccion",
                "PR_AUC",
                "detectados",
                "eventos",
                "alertas",
            ]
        ].rename(columns={"dias_por_deteccion": "días/det"})
        st.dataframe(
            show.style.format(
                {"POD": "{:.0%}", "FAR": "{:.0%}", "días/det": "{:.1f}", "PR_AUC": "{:.3f}"}
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.success(
            f"**Elegido en «{corte}»: {elegido_de(corte)}** — "
            f"{read_text(f'decision_{corte}.md').split('razón')[0][-200:].strip() or 'ver pestaña Decisión'}"
        )
        fig = px.scatter(
            sub,
            x="FAR",
            y="POD",
            text="modelo",
            size="PR_AUC",
            color="modelo",
            labels={"FAR": "FAR", "POD": "POD"},
            title=f"POD vs FAR — corte {corte}",
        )
        fig.add_hline(y=0.70, line_dash="dash", annotation_text="meta POD 70%")
        fig.add_vline(x=0.50, line_dash="dash", annotation_text="meta FAR 50%")
        fig.update_traces(textposition="top center")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Tamaño = PR-AUC. El FAR se mide sobre días de evento y de control, así que "
            "sobrestima el real."
        )

# ================================ Tab: año a año ================================================
with tabs[2]:
    st.subheader("Detección año a año (corte del día)")
    if not by_fold.empty:
        bf = by_fold[by_fold["corte"] == "dia"].copy()
        piv = bf.pivot_table(index="anio", columns="modelo", values="detectados", aggfunc="first")
        ev = bf.groupby("anio")["eventos"].first()
        piv.insert(0, "eventos", ev)
        cols = ["eventos"] + [m for m in ["M1", elegido_dia] if m in piv.columns]
        tabla = piv[cols].fillna(0).astype(int)
        tabla.loc["Suma"] = tabla.sum()
        st.dataframe(tabla, use_container_width=True)
        st.caption(
            "Eventos detectados por año (acierto tolerante). La suma por año difiere del total "
            "agrupado, que junta las predicciones de todos los pliegues de validación."
        )
        bf2 = bf[bf["modelo"].isin(["M1", elegido_dia])]
        fig = px.bar(
            bf2,
            x="anio",
            y="detectados",
            color="modelo",
            barmode="group",
            labels={"anio": "año", "detectados": "eventos detectados"},
            title="Eventos detectados por año: regla física vs modelo elegido",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No hay cv_by_fold.csv todavía.")

# ================================ Tab: prueba ciega 2025 ========================================
with tabs[3]:
    st.subheader("Prueba ciega 2025 — una sola evaluación, sin reajustar nada")
    bd, b12 = read_csv("blind_2025_dia.csv"), read_csv("blind_2025_12utc.csv")
    blind = pd.concat([bd, b12], ignore_index=True)
    if not blind.empty:
        show = blind[
            ["corte", "modelo", "POD", "FAR", "dias_por_deteccion", "detectados", "eventos"]
        ]
        st.dataframe(
            show.style.format({"POD": "{:.0%}", "FAR": "{:.0%}", "dias_por_deteccion": "{:.1f}"}),
            use_container_width=True,
            hide_index=True,
        )
        if not bd.empty:
            r = bd.iloc[0]
            st.success(
                f"Con todo el día, {r['modelo']} detectó **{int(r['detectados'])} de "
                f"{int(r['eventos'])}** eventos de 2025 (POD {r['POD']:.0%}), sin reajuste."
            )
        st.caption(
            "Solo 2 eventos en 2025: confirma la dirección de la validación, no la mide con "
            "precisión."
        )

# ================================ Tab: metas ====================================================
with tabs[4]:
    st.subheader("Dónde estamos frente a las metas comprometidas")
    if r2 is not None and r1 is not None:
        pod, far, dias = r2["POD"], r2["FAR"], r2["dias_por_deteccion"]
        c1, c2, c3 = st.columns(3)
        c1.metric("POD", f"{pod:.0%}", "meta ≥ 70% · " + ("✅ CUMPLE" if pod >= 0.70 else "❌ NO"))
        c2.metric(
            "FAR",
            f"{far:.0%}",
            "meta ≤ 50% · " + ("✅ CUMPLE" if far <= 0.50 else "❌ NO (sobrestimado)"),
            delta_color="off",
        )
        c3.metric(
            "Días/detección",
            f"{dias:.1f}",
            "meta ≤ 2 · " + ("✅ CUMPLE" if dias <= 2 else "🟡 CERCA" if dias <= 3 else "❌ NO"),
            delta_color="off",
        )
        st.markdown(
            f"- **POD {pod:.0%}** ({int(r2['detectados'])}/{int(r2['eventos'])} eventos): cumple la meta de detección.\n"
            f"- **FAR {far:.0%}**: no cumple, pero el control es *sin etiqueta*, así que el FAR real es menor.\n"
            f"- **{dias:.1f} días por detección** frente a {r1['dias_por_deteccion']:.1f} de la regla física: cerca de la meta de 2."
        )
        st.caption("Validación cruzada 2018–2024, corte «día», modelo elegido.")

# ================================ Tab: candidatos 2026 =========================================
with tabs[5]:
    st.subheader(f"Candidatos 2026 — corte del día, modelo {elegido_dia}")
    cand = read_csv("candidatos_2026_dia.csv")
    if cand.empty:
        cand = read_csv("candidatos_2026_dia_top300.csv")
    if not cand.empty:
        cand["fecha"] = pd.to_datetime(cand["fecha"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Celdas-día puntuadas", f"{len(cand):,}")
        c2.metric("Alertas (modelo elegido)", f"{int(cand['alerta'].sum())}")
        c3.metric("Último día con ERA5", f"{cand['fecha'].max().date()}")
        solo = st.checkbox("Mostrar solo celdas-día en alerta", value=True)
        view = cand[cand["alerta"] == 1] if solo else cand
        fig = px.scatter_geo(
            view.head(500),
            lat="lat",
            lon="lon",
            color="score",
            size="score",
            hover_data=["fecha"],
            color_continuous_scale="YlOrRd",
            scope="south america",
            title="Candidatos 2026 (color = puntaje)",
        )
        fig.update_geos(
            lataxis_range=[-44, -21],
            lonaxis_range=[-76, -68],
            resolution=50,
            showland=True,
            landcolor="rgb(240,240,235)",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.warning(
            "⚠️ **Por revisar:** varios candidatos de mayor puntaje caen cerca de la cordillera, donde "
            "los índices de niveles bajos pueden ser **artefactos** (el dominio v1 excede el recorte "
            "ERA5 y aún no hay máscara de terreno). La v2 corrige el dominio y enmascara terreno > 1.500 m."
        )
        st.markdown("**Top 15 candidatos por puntaje** (con las variables que más contribuyen)")
        top = view.sort_values("score", ascending=False).head(15)
        cols = [
            c for c in ["fecha", "lat", "lon", "score", "top1", "top2", "top3"] if c in top.columns
        ]
        st.dataframe(top[cols], use_container_width=True, hide_index=True)
    else:
        st.warning("No se encontraron candidatos 2026.")

# ================================ Tab: decisión =================================================
with tabs[6]:
    st.subheader("Decisión (regla fijada de antemano)")
    corte_d = st.radio("Corte", ["dia", "12utc"], horizontal=True, key="dec")
    st.markdown(read_text(f"decision_{corte_d}.md") or "_No disponible._")
    st.divider()
    st.subheader("Resumen para el pitch")
    st.markdown(read_text("resumen_pitch.md") or "_No disponible._")

st.divider()
st.caption(
    "Visor de datos y caso 2019: puerto 8501. Esta app de resultados: puerto 8502. "
    "Código: scripts/model/ · salidas: data/outputs/. Hackatón CR2 · AWS EC2 Graviton2."
)
