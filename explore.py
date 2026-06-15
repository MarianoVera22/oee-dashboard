"""Script exploratorio para ver las métricas de OEE (temporal)."""

from pathlib import Path

import polars as pl

from oee_dashboard.metrics import (
    add_oee_columns,
    oee_by_machine,
    oee_by_shift,
    overall_oee,
)

production = pl.read_csv(Path("data") / "production.csv")
production = add_oee_columns(production)

print("=== OEE GLOBAL ===")
for key, value in overall_oee(production).items():
    print(f"  {key}: {value:.1%}")

print("\n=== OEE POR MÁQUINA ===")
print(oee_by_machine(production))

print("\n=== OEE POR TURNO ===")
print(oee_by_shift(production))