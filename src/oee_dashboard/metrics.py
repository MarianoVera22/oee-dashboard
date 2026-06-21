"""Cálculo de métricas de OEE sobre datos de producción.

OEE (Overall Equipment Effectiveness) = Disponibilidad × Rendimiento × Calidad.
Todas las funciones reciben y devuelven DataFrames de polars, sin mutar la entrada.
"""

from __future__ import annotations

import polars as pl


def add_oee_columns(production: pl.DataFrame) -> pl.DataFrame:
    """Agrega columnas de OEE y sus componentes al DataFrame de producción.

    Espera las columnas: planned_time_min, downtime_min, units_produced,
    units_rejected, ideal_cycle_time_sec.

    Args:
        production: DataFrame de producción crudo.

    Returns:
        Un DataFrame nuevo con columnas adicionales:
        availability, performance, quality, oee.
    """
    return production.with_columns(
        # Tiempo operativo en minutos (lo usamos en varios cálculos).
        operating_time_min=(
            pl.col("planned_time_min") - pl.col("downtime_min")
        ),
    ).with_columns(
        # Disponibilidad = tiempo operativo / tiempo planificado.
        availability=(
            pl.col("operating_time_min") / pl.col("planned_time_min")
        ),
        # Producción teórica = tiempo operativo (en seg) / ciclo ideal (seg/unidad).
        theoretical_units=(
            (pl.col("operating_time_min") * 60) / pl.col("ideal_cycle_time_sec")
        ),
    ).with_columns(
        # Rendimiento = producción real / producción teórica.
        performance=(
            pl.col("units_produced") / pl.col("theoretical_units")
        ),
        # Calidad = unidades buenas / unidades totales.
        quality=(
            (pl.col("units_produced") - pl.col("units_rejected"))
            / pl.col("units_produced")
        ),
    ).with_columns(
        # OEE = disponibilidad × rendimiento × calidad.
        oee=(
            pl.col("availability") * pl.col("performance") * pl.col("quality")
        ),
    )


def oee_by_machine(production_with_oee: pl.DataFrame) -> pl.DataFrame:
    """Promedia el OEE y sus componentes por máquina.

    Args:
        production_with_oee: DataFrame que ya pasó por add_oee_columns.

    Returns:
        DataFrame con una fila por máquina, ordenado por OEE descendente.
    """
    return (
        production_with_oee.group_by("machine_id")
        .agg(
            pl.col("availability").mean().alias("availability"),
            pl.col("performance").mean().alias("performance"),
            pl.col("quality").mean().alias("quality"),
            pl.col("oee").mean().alias("oee"),
        )
        .sort("oee", descending=True)
    )


def oee_by_shift(production_with_oee: pl.DataFrame) -> pl.DataFrame:
    """Promedia el OEE por turno.

    Args:
        production_with_oee: DataFrame que ya pasó por add_oee_columns.

    Returns:
        DataFrame con una fila por turno.
    """
    return (
        production_with_oee.group_by("shift")
        .agg(
            pl.col("availability").mean().alias("availability"),
            pl.col("performance").mean().alias("performance"),
            pl.col("quality").mean().alias("quality"),
            pl.col("oee").mean().alias("oee"),
        )
        .sort("oee", descending=True)
    )
    
    
def oee_by_date(production_with_oee: pl.DataFrame) -> pl.DataFrame:
    """Promedia el OEE y sus componentes por fecha.

    Args:
        production_with_oee: DataFrame que ya pasó por add_oee_columns.

    Returns:
        DataFrame con una fila por fecha, ordenado cronológicamente.
    """
    return (
        production_with_oee.group_by("date")
        .agg(
            pl.col("availability").mean().alias("availability"),
            pl.col("performance").mean().alias("performance"),
            pl.col("quality").mean().alias("quality"),
            pl.col("oee").mean().alias("oee"),
        )
        .sort("date")
    )


def overall_oee(production_with_oee: pl.DataFrame) -> dict[str, float]:
    """Calcula el OEE global promedio y sus componentes.

    Args:
        production_with_oee: DataFrame que ya pasó por add_oee_columns.

    Returns:
        Diccionario con availability, performance, quality y oee promedio.
    """
    means = production_with_oee.select(
        pl.col("availability").mean(),
        pl.col("performance").mean(),
        pl.col("quality").mean(),
        pl.col("oee").mean(),
    ).row(0, named=True)
    return {key: float(value) for key, value in means.items()}

def downtime_by_reason(downtime: pl.DataFrame) -> pl.DataFrame:
    """Suma el tiempo de paro total por causa, ordenado de mayor a menor.

    Args:
        downtime: DataFrame de eventos de paro (columnas: reason, duration_min).

    Returns:
        DataFrame con columnas: reason, total_min, pct, cumulative_pct.
        Ordenado por total_min descendente (formato Pareto).
    """
    by_reason = (
        downtime.group_by("reason")
        .agg(pl.col("duration_min").sum().alias("total_min"))
        .sort("total_min", descending=True)
    )

    total = by_reason["total_min"].sum()

    return by_reason.with_columns(
        # Porcentaje que representa cada causa sobre el total.
        pct=(pl.col("total_min") / total * 100),
    ).with_columns(
        # Porcentaje acumulado (la línea del Pareto).
        cumulative_pct=(pl.col("pct").cum_sum()),
    )

def add_rolling_oee(daily_oee: pl.DataFrame, window: int = 7) -> pl.DataFrame:
    """Agrega una columna de promedio móvil del OEE.

    Suaviza el ruido diario para revelar la tendencia de fondo.

    Args:
        daily_oee: DataFrame con OEE por fecha (salida de oee_by_date),
            ordenado cronológicamente.
        window: cantidad de días de la ventana móvil (por defecto 7).

    Returns:
        El DataFrame con una columna adicional 'oee_rolling'.
    """
    return daily_oee.with_columns(
        oee_rolling=pl.col("oee").rolling_mean(window_size=window),
    )