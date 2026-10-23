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


def calcular_progreso(estados) -> dict:
    """Progreso de preparación de un evento a partir del estado de sus gestiones (US-10).

    - hechas: gestiones con estado "hecha".
    - pospuestas: gestiones con estado "pospuesta" (siguen sin estar listas).
    - pendientes: el resto (cualquier otro estado cuenta como pendiente).
    - faltan: todo lo que no está hecho, es decir, pendientes + pospuestas.
    - porcentaje: hechas / total, redondeado al entero más cercano (0 si no hay gestiones).
    - completo: True solo si hay gestiones y todas están hechas.
    """
    estados = list(estados)
    total = len(estados)
    hechas = sum(1 for e in estados if e == "hecha")
    pospuestas = sum(1 for e in estados if e == "pospuesta")
    return {
        "total": total,
        "hechas": hechas,
        "pospuestas": pospuestas,
        "pendientes": total - hechas - pospuestas,
        "faltan": total - hechas,
        "porcentaje": int(hechas * 100 / total + 0.5) if total else 0,
        "completo": total > 0 and hechas == total,
    }


def emparejar_gestiones(previas, solicitadas) -> list:
    """Para cada gestión solicitada devuelve la gestión previa que le corresponde (o None).

    Sirve para que, al editar un evento, cada gestión conserve su estado, nota y fecha de
    finalización. Primero se empareja por id y, si no hay id, por nombre (en orden).
    Cada gestión previa se usa una sola vez."""
    por_id = {p.id: p for p in previas}
    usadas = set()
    resultado = [None] * len(solicitadas)

    for i, s in enumerate(solicitadas):
        sid = getattr(s, "id", None)
        previa = por_id.get(sid) if sid is not None else None
        if previa is not None and previa.id not in usadas:
            resultado[i] = previa
            usadas.add(previa.id)

    libres = defaultdict(list)
    for p in previas:
        if p.id not in usadas:
            libres[p.nombre].append(p)
    for i, s in enumerate(solicitadas):
        if resultado[i] is None and libres.get(s.nombre):
            previa = libres[s.nombre].pop(0)
            resultado[i] = previa
            usadas.add(previa.id)
    return resultado


# ---------- Las gestiones hechas ya no cuentan en las horas del día ----------

def esta_activa(fila) -> bool:
    """Una gestión hecha ya no ocupa horas del día: solo cuentan las pendientes y pospuestas."""
    return getattr(fila, "status", "pendiente") != "hecha"


def totales_activos(filas) -> dict:
    """Horas por día de las gestiones activas. filas: objetos con plazo, horas_estimadas y status."""
    return sumar_por_dia((f.plazo, f.horas_estimadas) for f in filas if esta_activa(f))


def evaluar_sobrecarga(filas, tareas, event_id, limite: float):
    """Al guardar un evento: primer día (dia, total) que quedaría sobrecargado, o None.

    filas: gestiones del usuario (id, event_id, nombre, plazo, horas_estimadas, status).
    tareas: gestiones que llegan en la petición. Las que ya estaban hechas no cuentan."""
    previas = [f for f in filas if event_id is not None and f.event_id == event_id]
    otros = totales_activos(f for f in filas if f.event_id != event_id)
    antes = totales_activos(previas)
    pares = emparejar_gestiones(previas, tareas)
    nuevas = sumar_por_dia(
        (t.plazo, t.horas_estimadas)
        for t, previa in zip(tareas, pares)
        if previa is None or esta_activa(previa)
    )
    return dia_que_empeora(otros, antes, nuevas, limite)


def evaluar_reapertura(filas, tarea, limite: float):
    """Al reabrir una gestión hecha (volver a pendiente o pospuesta): (dia, total) si su día
    quedaría sobrecargado, o None."""
    otros = totales_activos(f for f in filas if f.id != tarea.id)
    return dia_que_empeora(otros, {}, {tarea.plazo: float(tarea.horas_estimadas)}, limite)