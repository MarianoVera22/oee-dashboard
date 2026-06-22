"""Dashboard de OEE — aplicación Streamlit."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import polars as pl
import streamlit as st

from oee_dashboard.metrics import (
    add_oee_columns,
    downtime_by_reason,
    oee_by_machine,
    oee_by_shift,
    overall_oee,
    oee_by_date,
    add_rolling_oee,
)

# --- Configuración de la página ---
st.set_page_config(
    page_title="Dashboard OEE",
    page_icon="📊",
    layout="wide",
)


@st.cache_data
def load_data() -> pl.DataFrame:
    """Carga los datos de producción y agrega las columnas de OEE.

    El decorador @st.cache_data evita recargar/recalcular en cada
    interacción: Streamlit guarda el resultado y lo reutiliza.
    """
    production = pl.read_csv(Path("data") / "production.csv")
    return add_oee_columns(production)


@st.cache_data
def load_downtime() -> pl.DataFrame:
    """Carga los eventos de paro."""
    return pl.read_csv(Path("data") / "downtime_events.csv")


# --- Carga de datos ---
data = load_data()

# --- SIDEBAR: filtros ---
st.sidebar.header("Filtros")

# Filtro de máquinas (multiselect: podés elegir varias)
all_machines = sorted(data["machine_id"].unique().to_list())
selected_machines = st.sidebar.multiselect(
    "Máquinas",
    options=all_machines,
    default=all_machines,  # por defecto, todas seleccionadas
    key="machine_filter",
)

# Filtro de turnos
# Orden lógico de turnos, no alfabético.
SHIFT_ORDER = ["Mañana", "Tarde", "Noche"]
available_shifts = set(data["shift"].unique().to_list())
all_shifts = [s for s in SHIFT_ORDER if s in available_shifts]
selected_shifts = st.sidebar.multiselect(
    "Turnos",
    options=all_shifts,
    default=all_shifts,
    key="shift_filter",
)

# --- Aplicar los filtros a los datos ---
filtered = data.filter(
    pl.col("machine_id").is_in(selected_machines)
    & pl.col("shift").is_in(selected_shifts)
)

# Guarda de seguridad: si el usuario deselecciona todo, evitar errores.
if filtered.height == 0:
    st.warning("No hay datos para los filtros seleccionados. Ajustá la selección.")
    st.stop()

# --- Título ---
st.title("📊 Dashboard OEE")
st.caption("Overall Equipment Effectiveness — datos sintéticos de producción")

# --- Cargar paros (filtrados igual que producción) ---
downtime = load_downtime()
downtime_filtered = downtime.filter(
    pl.col("machine_id").is_in(selected_machines)
    & pl.col("shift").is_in(selected_shifts)
)

# --- Pestañas ---
tab_resumen, tab_comparativo, tab_paros = st.tabs(
    ["Resumen", "Por máquina / turno", "Análisis de paros"]
)

# ===== PESTAÑA 1: RESUMEN =====
with tab_resumen:
    overall = overall_oee(filtered)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("OEE Global", f"{overall['oee']:.1%}")
    col2.metric("Disponibilidad", f"{overall['availability']:.1%}")
    col3.metric("Rendimiento", f"{overall['performance']:.1%}")
    col4.metric("Calidad", f"{overall['quality']:.1%}")

    st.divider()

    st.subheader("Tendencia de OEE en el tiempo")
    trend = oee_by_date(filtered)
    trend = add_rolling_oee(trend, window=7)

    fig_trend = go.Figure()
    fig_trend.add_trace(
        go.Scatter(
            x=trend["date"].to_list(),
            y=trend["oee"].to_list(),
            name="OEE diario",
            mode="lines",
            line=dict(color="#b0bec5", width=1),
            opacity=0.5,
        )
    )
    fig_trend.add_trace(
        go.Scatter(
            x=trend["date"].to_list(),
            y=trend["oee_rolling"].to_list(),
            name="Promedio móvil (7 días)",
            mode="lines",
            line=dict(color="#1985a1", width=3),
        )
    )
    fig_trend.add_hline(
        y=0.85,
        line_dash="dash",
        line_color="#ef8354",
        annotation_text="Clase mundial (85%)",
        annotation_position="top right",
    )
    fig_trend.update_layout(
        yaxis=dict(title="OEE", tickformat=".0%", range=[0, 1]),
        xaxis=dict(title="Fecha"),
        height=400,
    )
    st.plotly_chart(fig_trend, use_container_width=True)

# ===== PESTAÑA 2: COMPARATIVO =====
with tab_comparativo:
    st.subheader("OEE por máquina")
    st.dataframe(oee_by_machine(filtered), use_container_width=True)

    st.subheader("OEE por turno")
    st.dataframe(oee_by_shift(filtered), use_container_width=True)

# ===== PESTAÑA 3: ANÁLISIS DE PAROS =====
with tab_paros:
    st.subheader("Causas de paro (Pareto)")

    if downtime_filtered.height == 0:
        st.info("No hay eventos de paro para los filtros seleccionados.")
    else:
        pareto = downtime_by_reason(downtime_filtered)

        fig_pareto = go.Figure()
        fig_pareto.add_trace(
            go.Bar(
                x=pareto["reason"].to_list(),
                y=pareto["total_min"].to_list(),
                name="Tiempo de paro (min)",
                marker_color="#1985a1",
            )
        )
        fig_pareto.add_trace(
            go.Scatter(
                x=pareto["reason"].to_list(),
                y=pareto["cumulative_pct"].to_list(),
                name="% acumulado",
                yaxis="y2",
                mode="lines+markers",
                marker_color="#ef8354",
            )
        )
        fig_pareto.update_layout(
            yaxis=dict(title="Minutos de paro"),
            yaxis2=dict(
                title="% acumulado",
                overlaying="y",
                side="right",
                range=[0, 105],
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            height=450,
        )
        st.plotly_chart(fig_pareto, use_container_width=True)
