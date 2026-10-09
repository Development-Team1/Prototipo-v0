from typing import List, Optional

import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
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


def _build_tasks(event: schemas.EventCreate) -> list[models.Task]:
    return [
        models.Task(
            nombre=t.nombre, plazo=t.plazo, horas_estimadas=t.horas_estimadas
        )
        for t in event.tareas
    ]


@app.post("/events", response_model=schemas.EventOut, status_code=201)
def create_event(
    event: schemas.EventCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
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
    db_event.nombre = event.nombre
    db_event.tipo = event.tipo
    db_event.fecha = event.fecha
    # Reemplaza las gestiones: las anteriores se eliminan (delete-orphan)
    db_event.tareas = _build_tasks(event)
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


# ---------- Activities (prototipo anterior; ahora también privadas por usuario) ----------
def _own_activity(db: Session, activity_id: int, user: models.User) -> models.Activity:
    activity = (
        db.query(models.Activity)
        .filter(
            models.Activity.activity_id == activity_id,
            models.Activity.user_id == user.user_id,
        )
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    return activity


@app.post("/activities", response_model=schemas.ActivityOut)
def create_activity(
    activity: schemas.ActivityCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    data = activity.model_dump()
    data["user_id"] = user.user_id
    db_activity = models.Activity(**data)
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    return db_activity


@app.get("/activities", response_model=List[schemas.ActivityOut])
def list_activities(
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    return (
        db.query(models.Activity).filter(models.Activity.user_id == user.user_id).all()
    )


@app.get("/activities/{activity_id}", response_model=schemas.ActivityOut)
def get_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return _own_activity(db, activity_id, user)


@app.put("/activities/{activity_id}", response_model=schemas.ActivityOut)
def update_activity(
    activity_id: int,
    activity: schemas.ActivityCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db_activity = _own_activity(db, activity_id, user)
    for key, value in activity.model_dump(exclude={"user_id"}).items():
        setattr(db_activity, key, value)
    db.commit()
    db.refresh(db_activity)
    return db_activity


@app.delete("/activities/{activity_id}")
def delete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db.delete(_own_activity(db, activity_id, user))
    db.commit()
    return {"mensaje": "Actividad eliminada"}


# ---------- Subtasks (se validan a través de la actividad dueña) ----------
def _own_subtask(db: Session, subtask_id: int, user: models.User) -> models.Subtask:
    subtask = (
        db.query(models.Subtask)
        .join(models.Activity, models.Activity.activity_id == models.Subtask.activity_id)
        .filter(
            models.Subtask.subtask_id == subtask_id,
            models.Activity.user_id == user.user_id,
        )
        .first()
    )
    if not subtask:
        raise HTTPException(status_code=404, detail="Subtarea no encontrada")
    return subtask


@app.post("/subtasks", response_model=schemas.SubtaskOut)
def create_subtask(
    subtask: schemas.SubtaskCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _own_activity(db, subtask.activity_id, user)
    db_subtask = models.Subtask(**subtask.model_dump())
    db.add(db_subtask)
    db.commit()
    db.refresh(db_subtask)
    return db_subtask


@app.get("/subtasks", response_model=List[schemas.SubtaskOut])
def list_subtasks(
    activity_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    query = (
        db.query(models.Subtask)
        .join(models.Activity, models.Activity.activity_id == models.Subtask.activity_id)
        .filter(models.Activity.user_id == user.user_id)
    )
    if activity_id is not None:
        query = query.filter(models.Subtask.activity_id == activity_id)
    return query.all()


@app.put("/subtasks/{subtask_id}", response_model=schemas.SubtaskOut)
def update_subtask(
    subtask_id: int,
    subtask: schemas.SubtaskCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db_subtask = _own_subtask(db, subtask_id, user)
    _own_activity(db, subtask.activity_id, user)
    for key, value in subtask.model_dump().items():
        setattr(db_subtask, key, value)
    db.commit()
    db.refresh(db_subtask)
    return db_subtask


@app.delete("/subtasks/{subtask_id}")
def delete_subtask(
    subtask_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db.delete(_own_subtask(db, subtask_id, user))
    db.commit()
    return {"mensaje": "Subtarea eliminada"}


# ---------- Daily capacity ----------
@app.post("/daily-capacity", response_model=schemas.DailyCapacityOut)
def create_daily_capacity(
    capacity: schemas.DailyCapacityCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    data = capacity.model_dump()
    data["user_id"] = user.user_id
    db_capacity = models.DailyCapacity(**data)
    db.add(db_capacity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, detail="Ya existe capacidad registrada para ese usuario y día"
        )
    db.refresh(db_capacity)
    return db_capacity


@app.get("/daily-capacity", response_model=List[schemas.DailyCapacityOut])
def list_daily_capacity(
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    return (
        db.query(models.DailyCapacity)
        .filter(models.DailyCapacity.user_id == user.user_id)
        .all()
    )