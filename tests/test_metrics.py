"""Tests del cálculo de métricas de OEE."""

from __future__ import annotations

import polars as pl
import pytest

from oee_dashboard.metrics import (
    add_oee_columns,
    oee_by_machine,
    #oee_by_shift,
    overall_oee,
)


@pytest.fixture
def simple_production() -> pl.DataFrame:
    """Un caso de producción con números elegidos para cálculo a mano.

    Un solo turno, valores 'redondos' para verificar el OEE manualmente:
      - planned: 480 min, downtime: 80 min -> operativo: 400 min
      - Disponibilidad = 400/480 = 0.8333...
      - ciclo ideal: 0.6 seg/u -> teórico = 400*60/0.6 = 40000 unidades
      - producidas: 36000 -> Rendimiento = 36000/40000 = 0.9
      - rechazadas: 3600 -> Calidad = (36000-3600)/36000 = 0.9
      - OEE = 0.8333 * 0.9 * 0.9 = 0.675
    """
    return pl.DataFrame(
        {
            "date": ["2025-01-01"],
            "shift": ["Mañana"],
            "machine_id": ["M-01"],
            "planned_time_min": [480],
            "downtime_min": [80],
            "units_produced": [36000],
            "units_rejected": [3600],
            "ideal_cycle_time_sec": [0.6],
        }
    )


def test_availability_calculation(simple_production: pl.DataFrame) -> None:
    """Disponibilidad = tiempo operativo / tiempo planificado."""
    result = add_oee_columns(simple_production)
    availability = result["availability"][0]
    assert availability == pytest.approx(400 / 480)


def test_performance_calculation(simple_production: pl.DataFrame) -> None:
    """Rendimiento = producción real / producción teórica."""
    result = add_oee_columns(simple_production)
    performance = result["performance"][0]
    # Teórico = 400 min * 60 seg / 0.6 seg/u = 40000 u; 36000/40000 = 0.9
    assert performance == pytest.approx(0.9)


def test_quality_calculation(simple_production: pl.DataFrame) -> None:
    """Calidad = unidades buenas / unidades totales."""
    result = add_oee_columns(simple_production)
    quality = result["quality"][0]
    # (36000 - 3600) / 36000 = 0.9
    assert quality == pytest.approx(0.9)


def test_oee_is_product_of_components(simple_production: pl.DataFrame) -> None:
    """OEE = Disponibilidad × Rendimiento × Calidad."""
    result = add_oee_columns(simple_production)
    oee = result["oee"][0]
    expected = (400 / 480) * 0.9 * 0.9
    assert oee == pytest.approx(expected)


def test_oee_value_is_known(simple_production: pl.DataFrame) -> None:
    """El OEE de este caso conocido debe dar 0.675."""
    result = add_oee_columns(simple_production)
    assert result["oee"][0] == pytest.approx(0.675)


def test_add_oee_columns_does_not_mutate_input(simple_production: pl.DataFrame) -> None:
    """add_oee_columns no debe modificar el DataFrame original."""
    original_columns = simple_production.columns
    add_oee_columns(simple_production)
    # El original sigue sin las columnas nuevas.
    assert simple_production.columns == original_columns
    assert "oee" not in simple_production.columns


def test_oee_components_between_zero_and_one(simple_production: pl.DataFrame) -> None:
    """Todos los componentes del OEE deben estar en el rango [0, 1]."""
    result = add_oee_columns(simple_production)
    for col in ("availability", "performance", "quality", "oee"):
        value = result[col][0]
        assert 0.0 <= value <= 1.0


@pytest.fixture
def multi_machine_production() -> pl.DataFrame:
    """Dos máquinas con distinto rendimiento, para probar agregaciones."""
    return pl.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-01"],
            "shift": ["Mañana", "Mañana"],
            "machine_id": ["M-01", "M-02"],
            "planned_time_min": [480, 480],
            "downtime_min": [0, 240],  # M-02 tiene la mitad del tiempo parada
            "units_produced": [40000, 20000],
            "units_rejected": [0, 0],
            "ideal_cycle_time_sec": [0.6, 0.6],
        }
    )


def test_oee_by_machine_sorts_best_first(
    multi_machine_production: pl.DataFrame,
) -> None:
    """oee_by_machine ordena de mejor a peor OEE."""
    result = add_oee_columns(multi_machine_production)
    by_machine = oee_by_machine(result)
    # M-01 (sin paros) debe tener mejor OEE que M-02 (50% parada).
    assert by_machine["machine_id"][0] == "M-01"
    assert by_machine["oee"][0] > by_machine["oee"][1]


def test_oee_by_machine_one_row_per_machine(
    multi_machine_production: pl.DataFrame,
) -> None:
    """Debe haber exactamente una fila por máquina."""
    result = add_oee_columns(multi_machine_production)
    by_machine = oee_by_machine(result)
    assert by_machine.height == 2


def test_overall_oee_returns_all_keys(simple_production: pl.DataFrame) -> None:
    """overall_oee devuelve las cuatro métricas."""
    result = add_oee_columns(simple_production)
    overall = overall_oee(result)
    assert set(overall.keys()) == {"availability", "performance", "quality", "oee"}


def test_overall_oee_values_are_floats(simple_production: pl.DataFrame) -> None:
    """Los valores de overall_oee son floats de Python, no tipos de polars."""
    result = add_oee_columns(simple_production)
    overall = overall_oee(result)
    for value in overall.values():
        assert isinstance(value, float)
        
def test_downtime_by_reason_sorted_descending() -> None:
    """Las causas se ordenan de mayor a menor tiempo total."""
    from oee_dashboard.metrics import downtime_by_reason

    downtime = pl.DataFrame(
        {
            "reason": ["A", "B", "A", "C"],
            "duration_min": [10, 50, 20, 5],
        }
    )
    result = downtime_by_reason(downtime)
    # A = 30, B = 50, C = 5 -> orden esperado: B, A, C
    assert result["reason"].to_list() == ["B", "A", "C"]
    assert result["total_min"].to_list() == [50, 30, 5]


def test_downtime_cumulative_reaches_100() -> None:
    """El porcentaje acumulado de la última fila debe ser 100%."""
    from oee_dashboard.metrics import downtime_by_reason

    downtime = pl.DataFrame(
        {
            "reason": ["A", "B"],
            "duration_min": [75, 25],
        }
    )
    result = downtime_by_reason(downtime)
    assert result["cumulative_pct"][-1] == pytest.approx(100.0)