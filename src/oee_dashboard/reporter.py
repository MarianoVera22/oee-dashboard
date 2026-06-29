"""Generación de reportes descargables en Excel."""

from __future__ import annotations

import io

import polars as pl
import xlsxwriter


def build_excel_report(
    by_machine: pl.DataFrame,
    by_shift: pl.DataFrame,
    downtime_pareto: pl.DataFrame,
) -> bytes:
    """Genera un reporte Excel multi-hoja en memoria.

    Args:
        by_machine: OEE agregado por máquina.
        by_shift: OEE agregado por turno.
        downtime_pareto: causas de paro (Pareto).

    Returns:
        Los bytes del archivo .xlsx, listos para descargar.
    """
    buffer = io.BytesIO()

    with xlsxwriter.Workbook(buffer) as workbook:
        by_machine.write_excel(workbook=workbook, worksheet="OEE por máquina")
        by_shift.write_excel(workbook=workbook, worksheet="OEE por turno")
        downtime_pareto.write_excel(workbook=workbook, worksheet="Causas de paro")

    buffer.seek(0)
    return buffer.getvalue()