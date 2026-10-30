from typing import List, Optional

import logging
from datetime import date
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
from carga import (
    calcular_progreso,
    dias_sobre_limite,
    emparejar_gestiones,
    evaluar_reapertura,
    evaluar_sobrecarga,
    fecha_corta,
    horas_txt,
    totales_activos,
)
from auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from database import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_origin_regex=r"https://frontend-miniproyecto1.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_request_origin(request: Request, call_next):
    response = await call_next(request)
    origin = request.headers.get("origin") or request.headers.get("referer") or "sin origen"
    logger.info(f'{request.method} {request.url.path} -> {response.status_code} | origen: {origin}')
    return response


@app.get("/")
def read_root():
    return {"mensaje": "Hola, mi API funciona"}


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# ---------- Auth ----------
def _token_response(user: models.User) -> dict:
    return {
        "access_token": create_access_token(user.user_id),
        "token_type": "bearer",
        "user": schemas.UserOut.model_validate(user),
    }


@app.post("/auth/register", response_model=schemas.TokenOut, status_code=201)
def register(data: schemas.UserRegister, db: Session = Depends(get_db)):
    user = models.User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe una cuenta con ese correo. Inicia sesión o usa otro correo.",
        )
    db.refresh(user)
    return _token_response(user)


@app.post("/auth/login", response_model=schemas.TokenOut)
def login(data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == data.email).first()
    # Mismo mensaje para "no existe" y "clave incorrecta": no revela qué correos tienen cuenta
    if (
        not user
        or not user.password_hash
        or not verify_password(data.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    return _token_response(user)


@app.get("/auth/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ---------- Límite diario de horas (US-12) ----------
DEFAULT_DAILY_LIMIT = 6.0


@app.get("/settings/daily-limit", response_model=schemas.DailyLimitOut)
def get_daily_limit(user: models.User = Depends(get_current_user)):
    horas = user.daily_hours_limit
    return {"horas": float(horas) if horas is not None else DEFAULT_DAILY_LIMIT}


@app.put("/settings/daily-limit", response_model=schemas.DailyLimitOut)
def set_daily_limit(
    data: schemas.DailyLimitIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    # No se puede bajar el límite por debajo de lo que ya hay planificado en algún día
    # (se revisan los días desde hoy: los pasados ya no se pueden reprogramar)
    # Las gestiones hechas no cuentan: ya no ocupan horas
    filas = _gestiones_del_usuario(db, user)
    excedidos = dias_sobre_limite(totales_activos(filas), data.horas, date.today())
    if excedidos:
        lista = ", ".join(f"{fecha_corta(d)} ({horas_txt(t)}h)" for d, t in excedidos[:3])
        if len(excedidos) > 3:
            lista += "…"
        raise HTTPException(
            status_code=409,
            detail=(
                f"No puedes fijar un límite de {horas_txt(data.horas)}h porque hay días con más "
                f"horas planificadas: {lista}. Reprograma o reduce esas gestiones primero."
            ),
        )
    user.daily_hours_limit = data.horas
    db.commit()
    db.refresh(user)
    return {"horas": float(user.daily_hours_limit)}


# ---------- Events (cada usuario solo accede a los suyos) ----------
def _own_event(db: Session, event_id: int, user: models.User) -> models.Event:
    event = (
        db.query(models.Event)
        .filter(models.Event.id == event_id, models.Event.user_id == user.user_id)
        .first()
    )
    # 404 (y no 403) para no revelar que el evento existe en otra cuenta
    if not event:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return event


def _limite_de(user: models.User) -> float:
    horas = user.daily_hours_limit
    return float(horas) if horas is not None else DEFAULT_DAILY_LIMIT


def _gestiones_del_usuario(db: Session, user: models.User):
    """Todas las gestiones del usuario, con lo necesario para contar horas por día."""
    return (
        db.query(
            models.Task.id,
            models.Task.event_id,
            models.Task.nombre,
            models.Task.plazo,
            models.Task.horas_estimadas,
            models.Task.status,
        )
        .join(models.Event, models.Event.id == models.Task.event_id)
        .filter(models.Event.user_id == user.user_id)
        .all()
    )


def _verificar_sobrecarga(
    db: Session, user: models.User, tareas, event_id: Optional[int] = None
) -> None:
    """Rechaza guardar un evento si alguno de sus días supera el límite diario del usuario.
    Las gestiones ya hechas no cuentan."""
    limite = _limite_de(user)
    hallado = evaluar_sobrecarga(_gestiones_del_usuario(db, user), tareas, event_id, limite)
    if hallado:
        dia, total = hallado
        raise HTTPException(
            status_code=409,
            detail=(
                f"El {fecha_corta(dia)} quedaría con {horas_txt(total)}h de gestión "
                f"planificadas (límite {horas_txt(limite)}h). "
                "Mueve gestiones a otro día o reduce sus horas."
            ),
        )


def _verificar_reapertura(db: Session, user: models.User, task: models.Task) -> None:
    """Una gestión hecha vuelve a ocupar horas al reabrirla: no puede sobrecargar su día."""
    limite = _limite_de(user)
    hallado = evaluar_reapertura(_gestiones_del_usuario(db, user), task, limite)
    if hallado:
        dia, total = hallado
        raise HTTPException(
            status_code=409,
            detail=(
                f"No puedes reabrir esta gestión: el {fecha_corta(dia)} quedaría con "
                f"{horas_txt(total)}h de gestión planificadas (límite {horas_txt(limite)}h). "
                "Edita el evento para moverla a otro día antes de reabrirla."
            ),
        )


def _build_tasks(event: schemas.EventCreate, previous=None) -> list[models.Task]:
    """Gestiones del evento. Las que ya existían (por id o, si no hay id, por nombre) se
    reutilizan: conservan su id, estado, nota y fecha de finalización aunque cambien su
    plazo u horas. Las demás se crean como pendientes."""
    previas = list(previous or [])
    tareas = []
    for t, previa in zip(event.tareas, emparejar_gestiones(previas, event.tareas)):
        if previa is None:
            tareas.append(
                models.Task(
                    nombre=t.nombre, plazo=t.plazo, horas_estimadas=t.horas_estimadas
                )
            )
        else:
            previa.nombre = t.nombre
            previa.plazo = t.plazo
            previa.horas_estimadas = t.horas_estimadas
            tareas.append(previa)
    return tareas


@app.post("/events", response_model=schemas.EventOut, status_code=201)
def create_event(
    event: schemas.EventCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _verificar_sobrecarga(db, user, event.tareas)
    db_event = models.Event(
        user_id=user.user_id,
        nombre=event.nombre,
        tipo=event.tipo,
        fecha=event.fecha,
        tareas=_build_tasks(event),
    )
    db.add(db_event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="No se pudo guardar el evento")
    db.refresh(db_event)
    return db_event


@app.get("/events", response_model=List[schemas.EventOut])
def list_events(
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    return (
        db.query(models.Event)
        .filter(models.Event.user_id == user.user_id)
        .order_by(models.Event.fecha, models.Event.id)
        .all()
    )


@app.get("/events/{event_id}", response_model=schemas.EventOut)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return _own_event(db, event_id, user)


@app.put("/events/{event_id}", response_model=schemas.EventOut)
def update_event(
    event_id: int,
    event: schemas.EventCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db_event = _own_event(db, event_id, user)
    _verificar_sobrecarga(db, user, event.tareas, event_id)
    db_event.nombre = event.nombre
    db_event.tipo = event.tipo
    db_event.fecha = event.fecha
    # Reemplaza las gestiones: las anteriores se eliminan (delete-orphan)
    db_event.tareas = _build_tasks(event, list(db_event.tareas))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="No se pudo guardar el evento")
    db.refresh(db_event)
    return db_event


@app.delete("/events/{event_id}")
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db_event = _own_event(db, event_id, user)
    db.delete(db_event)
    db.commit()
    return {"mensaje": "Evento eliminado"}

@app.get("/events/{event_id}/progress", response_model=schemas.ProgressOut)
def get_event_progress(
    event_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Barra de progreso de preparación (US-10): gestiones hechas respecto al total."""
    event = _own_event(db, event_id, user)
    return calcular_progreso(t.status for t in event.tareas)


# ---------- Registrar avance de una gestión (hecha / pospuesta + nota) ----------
def _own_task(db: Session, task_id: int, user: models.User) -> models.Task:
    task = (
        db.query(models.Task)
        .join(models.Event, models.Event.id == models.Task.event_id)
        .filter(models.Task.id == task_id, models.Event.user_id == user.user_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Gestión no encontrada")
    return task


@app.patch("/tasks/{task_id}", response_model=schemas.TaskOut)
def update_task_progress(
    task_id: int,
    data: schemas.TaskProgressUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    task = _own_task(db, task_id, user)
    changes = data.model_dump(exclude_unset=True)

    # Reabrir una gestión hecha vuelve a sumar sus horas: no puede sobrecargar su día
    if task.status == "hecha" and changes.get("status") in ("pendiente", "pospuesta"):
        _verificar_reapertura(db, user, task)

    # La nota solo cambia si se envía: cambiar el estado no la borra
    if "note" in changes:
        task.note = changes["note"]

    new_status = changes.get("status")
    if new_status is not None:
        if new_status == "hecha" and task.status != "hecha":
            task.done_at = datetime.now(timezone.utc)  # lo llena el servidor
        elif new_status != "hecha":
            task.done_at = None
        task.status = new_status

    db.commit()
    db.refresh(task)
    return task