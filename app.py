"""Dashboard de OEE — aplicación Streamlit."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import streamlit as st

from oee_dashboard.metrics import (
    add_oee_columns,
    oee_by_machine,
    oee_by_shift,
    overall_oee,
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


# --- Carga de datos ---
data = load_data()

# --- Título ---
st.title("📊 Dashboard OEE")
st.caption("Overall Equipment Effectiveness — datos sintéticos de producción")

# --- KPIs principales ---
overall = overall_oee(data)

col1, col2, col3, col4 = st.columns(4)
col1.metric("OEE Global", f"{overall['oee']:.1%}")
col2.metric("Disponibilidad", f"{overall['availability']:.1%}")
col3.metric("Rendimiento", f"{overall['performance']:.1%}")
col4.metric("Calidad", f"{overall['quality']:.1%}")

st.divider()

# --- OEE por máquina ---
st.subheader("OEE por máquina")
by_machine = oee_by_machine(data)
st.dataframe(by_machine, use_container_width=True)

# --- OEE por turno ---
st.subheader("OEE por turno")
by_shift = oee_by_shift(data)
st.dataframe(by_shift, use_container_width=True)