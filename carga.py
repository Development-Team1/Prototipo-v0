"""Reglas de carga diaria (US-07 y US-12), sin dependencias de FastAPI ni de la base de datos."""
from collections import defaultdict
from datetime import date

EPS = 1e-9
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_corta(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]}"


def horas_txt(h: float) -> str:
    return f"{round(float(h), 2):g}".replace(".", ",")


def sumar_por_dia(items) -> dict:
    """items: pares (dia, horas). Devuelve {dia: horas_totales}."""
    totales = defaultdict(float)
    for dia, horas in items:
        totales[dia] += float(horas)
    return dict(totales)


def dia_que_empeora(otros: dict, propias_antes: dict, nuevas: dict, limite: float):
    """Primer día (de menor a mayor) en el que el evento guardado supera el límite
    y, además, aporta más horas que antes. Devuelve (dia, total) o None.

    Un evento puede guardarse si no agrava la carga: así se pueden corregir días
    que ya estaban sobrecargados antes de existir esta regla."""
    for dia in sorted(nuevas):
        total = otros.get(dia, 0.0) + nuevas[dia]
        if total > limite + EPS and nuevas[dia] > propias_antes.get(dia, 0.0) + EPS:
            return dia, total
    return None


def dias_sobre_limite(totales: dict, limite: float, desde: date) -> list:
    """Días desde `desde` cuyo total supera el límite, de menor a mayor."""
    return sorted((d, t) for d, t in totales.items() if d >= desde and t > limite + EPS)
