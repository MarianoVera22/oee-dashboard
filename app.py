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

# --- KPIs principales ---
overall = overall_oee(filtered)

col1, col2, col3, col4 = st.columns(4)
col1.metric("OEE Global", f"{overall['oee']:.1%}")
col2.metric("Disponibilidad", f"{overall['availability']:.1%}")
col3.metric("Rendimiento", f"{overall['performance']:.1%}")
col4.metric("Calidad", f"{overall['quality']:.1%}")

st.divider()

# --- OEE por máquina ---
st.subheader("OEE por máquina")
by_machine = oee_by_machine(filtered)
st.dataframe(by_machine, use_container_width=True)

# --- OEE por turno ---
st.subheader("OEE por turno")
by_shift = oee_by_shift(filtered)
st.dataframe(by_shift, use_container_width=True)

st.divider()

# --- Pareto de causas de paro ---
st.subheader("Causas de paro (Pareto)")

# Cargar paros y aplicar los mismos filtros de máquina y turno.
downtime = load_downtime()
downtime_filtered = downtime.filter(
    pl.col("machine_id").is_in(selected_machines)
    & pl.col("shift").is_in(selected_shifts)
)

if downtime_filtered.height == 0:
    st.info("No hay eventos de paro para los filtros seleccionados.")
else:
    pareto = downtime_by_reason(downtime_filtered)

    # Construir el gráfico combinado: barras + línea acumulada.
    fig = go.Figure()

    # Barras: tiempo total por causa.
    fig.add_trace(
        go.Bar(
            x=pareto["reason"].to_list(),
            y=pareto["total_min"].to_list(),
            name="Tiempo de paro (min)",
            marker_color="#1985a1",
        )
    )

    # Línea: porcentaje acumulado (eje Y secundario).
    fig.add_trace(
        go.Scatter(
            x=pareto["reason"].to_list(),
            y=pareto["cumulative_pct"].to_list(),
            name="% acumulado",
            yaxis="y2",
            mode="lines+markers",
            marker_color="#ef8354",
        )
    )

    # Configurar los dos ejes Y.
    fig.update_layout(
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

    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()

# --- Tendencia temporal del OEE ---
st.subheader("Tendencia de OEE en el tiempo")

# Importá oee_by_date arriba (lo agregamos al import de metrics)
trend = oee_by_date(filtered)

fig_trend = go.Figure()

fig_trend.add_trace(
    go.Scatter(
        x=trend["date"].to_list(),
        y=trend["oee"].to_list(),
        name="OEE",
        mode="lines",
        line=dict(color="#1985a1", width=2),
    )
)

# Línea de referencia: el umbral "clase mundial" (85%).
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