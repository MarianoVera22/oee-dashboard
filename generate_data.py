"""Generador de datos sintéticos de producción para el dashboard de OEE.

Crea dos datasets relacionados (uno-a-muchos):
  - production.csv: una fila por (fecha, turno, máquina) con métricas agregadas.
  - downtime_events.csv: múltiples filas por turno, una por evento de paro.

Los datos incluyen patrones realistas (variación por turno y máquina,
causas de paro con distribución Pareto) para que el dashboard tenga
'historias' que descubrir. Reproducible vía seed fijo.
"""

from __future__ import annotations

import datetime
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl

# --- Parámetros de la simulación ---
SEED = 42
START_DATE = datetime.date(2025, 1, 1)
NUM_DAYS = 180  # ~6 meses
MACHINES = ["M-01", "M-02", "M-03", "M-04", "M-05"]
SHIFTS = ["Mañana", "Tarde", "Noche"]
SHIFT_MINUTES = 480  # 8 horas por turno

# Tiempo de ciclo ideal por máquina (segundos por unidad).
# Distinto por máquina = distinta capacidad nominal.
IDEAL_CYCLE_SEC = {
    "M-01": 0.30,
    "M-02": 0.30,
    "M-03": 0.45,  # máquina más lenta
    "M-04": 0.25,  # la más rápida
    "M-05": 0.35,
}

# Factor de "salud" por máquina: multiplica la probabilidad de paros.
# M-03 es la máquina problemática (más paros).
MACHINE_HEALTH = {
    "M-01": 1.0,
    "M-02": 1.1,
    "M-03": 1.8,  # problemática
    "M-04": 0.9,
    "M-05": 1.2,
}

# Penalización de rendimiento por turno (el turno noche rinde peor).
SHIFT_PERFORMANCE_FACTOR = {
    "Mañana": 1.00,
    "Tarde": 0.97,
    "Noche": 0.92,  # menos supervisión, fatiga
}

# Causas de paro con sus pesos relativos (distribución tipo Pareto:
# pocas causas concentran la mayoría del tiempo perdido).
DOWNTIME_REASONS = {
    "Falla mecánica": 30,
    "Cambio de formato": 25,
    "Falta de material": 18,
    "Ajuste de calidad": 12,
    "Falla eléctrica": 8,
    "Limpieza no programada": 4,
    "Otros": 3,
}

# Rango de duración (minutos) típico por causa: (min, max).
REASON_DURATION_RANGE = {
    "Falla mecánica": (15, 90),
    "Cambio de formato": (20, 45),
    "Falta de material": (10, 60),
    "Ajuste de calidad": (5, 25),
    "Falla eléctrica": (20, 120),
    "Limpieza no programada": (10, 30),
    "Otros": (5, 20),
}


@dataclass(frozen=True, slots=True)
class DowntimeEvent:
    """Un evento de paro individual."""

    date: datetime.date
    shift: str
    machine_id: str
    reason: str
    duration_min: int


@dataclass(frozen=True, slots=True)
class ProductionRecord:
    """Métricas de producción de un turno (fecha, turno, máquina)."""

    date: datetime.date
    shift: str
    machine_id: str
    planned_time_min: int
    downtime_min: int
    units_produced: int
    units_rejected: int
    ideal_cycle_time_sec: float


def _pick_reason(rng: random.Random) -> str:
    """Elige una causa de paro según los pesos definidos (distribución Pareto)."""
    reasons = list(DOWNTIME_REASONS.keys())
    weights = list(DOWNTIME_REASONS.values())
    return rng.choices(reasons, weights=weights, k=1)[0]


def _generate_downtime_events(
    rng: random.Random,
    current_date: datetime.date,
    shift: str,
    machine: str,
) -> list[DowntimeEvent]:
    """Genera los eventos de paro de un turno concreto.

    La cantidad de eventos depende de la 'salud' de la máquina: máquinas
    problemáticas tienen más paros.
    """
    health = MACHINE_HEALTH[machine]
    # Cantidad base de eventos (0 a 4), escalada por la salud de la máquina.
    num_events = rng.choices(
        [0, 1, 2, 3, 4],
        weights=[40, 30 * health, 20 * health, 8 * health, 2 * health],
        k=1,
    )[0]

    events: list[DowntimeEvent] = []
    for _ in range(num_events):
        reason = _pick_reason(rng)
        low, high = REASON_DURATION_RANGE[reason]
        duration = rng.randint(low, high)
        events.append(
            DowntimeEvent(
                date=current_date,
                shift=shift,
                machine_id=machine,
                reason=reason,
                duration_min=duration,
            )
        )
    return events


def generate_datasets(
    output_dir: Path, seed: int = SEED
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Genera los datasets de producción y eventos de paro.

    Args:
        output_dir: carpeta donde escribir los CSV.
        seed: semilla para reproducibilidad.

    Returns:
        Tupla (production_df, downtime_df).
    """
    rng = random.Random(seed)

    production_records: list[ProductionRecord] = []
    downtime_events: list[DowntimeEvent] = []

    for day_offset in range(NUM_DAYS):
        current_date = START_DATE + datetime.timedelta(days=day_offset)

        for machine in MACHINES:
            for shift in SHIFTS:
                # 1. Generar eventos de paro de este turno.
                events = _generate_downtime_events(rng, current_date, shift, machine)
                downtime_events.extend(events)

                # 2. Downtime total = suma de los eventos.
                total_downtime = sum(e.duration_min for e in events)

                # 3. Tiempo de operación neto.
                operating_time = SHIFT_MINUTES - total_downtime

                # 4. Unidades producidas: depende del tiempo operativo,
                #    el ciclo ideal y un factor de rendimiento (<1, nunca se
                #    alcanza el ideal por microparos y pérdidas de velocidad).
                ideal_cycle = IDEAL_CYCLE_SEC[machine]
                perf_factor = SHIFT_PERFORMANCE_FACTOR[shift] * rng.uniform(0.85, 0.97)
                theoretical_units = (operating_time * 60) / ideal_cycle
                units_produced = int(theoretical_units * perf_factor)

                # 5. Rechazos: típicamente 1-4% de la producción.
                reject_rate = rng.uniform(0.01, 0.04)
                units_rejected = int(units_produced * reject_rate)

                production_records.append(
                    ProductionRecord(
                        date=current_date,
                        shift=shift,
                        machine_id=machine,
                        planned_time_min=SHIFT_MINUTES,
                        downtime_min=total_downtime,
                        units_produced=units_produced,
                        units_rejected=units_rejected,
                        ideal_cycle_time_sec=ideal_cycle,
                    )
                )

    # Construir los DataFrames de polars a partir de las dataclasses.
    production_df = pl.DataFrame([asdict(r) for r in production_records])
    downtime_df = pl.DataFrame([asdict(e) for e in downtime_events])

    # Escribir a disco.
    output_dir.mkdir(parents=True, exist_ok=True)
    production_df.write_csv(output_dir / "production.csv")
    downtime_df.write_csv(output_dir / "downtime_events.csv")

    return production_df, downtime_df


def main() -> None:
    """Genera los datasets y muestra un resumen."""
    output_dir = Path("data")
    production_df, downtime_df = generate_datasets(output_dir)

    print(f"Generado production.csv: {production_df.height} filas")
    print(f"Generado downtime_events.csv: {downtime_df.height} filas")
    print("\nPrimeras filas de producción:")
    print(production_df.head())
    print("\nPrimeras filas de paros:")
    print(downtime_df.head())


if __name__ == "__main__":
    main()
