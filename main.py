from typing import List, Optional

import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db

logger = logging.getLogger("app")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://frontend-miniproyecto1-fe1u-one.vercel.app"],
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


@app.get("/api/health/")
def health_check():
    return {"status": "ok"}


# ---------- Users ----------
@app.post("/users", response_model=schemas.UserOut)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = models.User(**user.model_dump())
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    db.refresh(db_user)
    return db_user


@app.get("/users", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()


@app.get("/users/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


# ---------- Activities ----------
@app.post("/activities", response_model=schemas.ActivityOut)
def create_activity(activity: schemas.ActivityCreate, db: Session = Depends(get_db)):
    db_activity = models.Activity(**activity.model_dump())
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    return db_activity


@app.get("/activities", response_model=List[schemas.ActivityOut])
def list_activities(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(models.Activity)
    if user_id is not None:
        query = query.filter(models.Activity.user_id == user_id)
    return query.all()


@app.get("/activities/{activity_id}", response_model=schemas.ActivityOut)
def get_activity(activity_id: int, db: Session = Depends(get_db)):
    activity = (
        db.query(models.Activity)
        .filter(models.Activity.activity_id == activity_id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    return activity


@app.put("/activities/{activity_id}", response_model=schemas.ActivityOut)
def update_activity(
    activity_id: int, activity: schemas.ActivityCreate, db: Session = Depends(get_db)
):
    db_activity = (
        db.query(models.Activity)
        .filter(models.Activity.activity_id == activity_id)
        .first()
    )
    if not db_activity:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    for key, value in activity.model_dump().items():
        setattr(db_activity, key, value)
    db.commit()
    db.refresh(db_activity)
    return db_activity


@app.delete("/activities/{activity_id}")
def delete_activity(activity_id: int, db: Session = Depends(get_db)):
    db_activity = (
        db.query(models.Activity)
        .filter(models.Activity.activity_id == activity_id)
        .first()
    )
    if not db_activity:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    db.delete(db_activity)
    db.commit()
    return {"mensaje": "Actividad eliminada"}


# ---------- Subtasks ----------
@app.post("/subtasks", response_model=schemas.SubtaskOut)
def create_subtask(subtask: schemas.SubtaskCreate, db: Session = Depends(get_db)):
    db_subtask = models.Subtask(**subtask.model_dump())
    db.add(db_subtask)
    db.commit()
    db.refresh(db_subtask)
    return db_subtask


@app.get("/subtasks", response_model=List[schemas.SubtaskOut])
def list_subtasks(activity_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(models.Subtask)
    if activity_id is not None:
        query = query.filter(models.Subtask.activity_id == activity_id)
    return query.all()


@app.put("/subtasks/{subtask_id}", response_model=schemas.SubtaskOut)
def update_subtask(
    subtask_id: int, subtask: schemas.SubtaskCreate, db: Session = Depends(get_db)
):
    db_subtask = (
        db.query(models.Subtask).filter(models.Subtask.subtask_id == subtask_id).first()
    )
    if not db_subtask:
        raise HTTPException(status_code=404, detail="Subtarea no encontrada")
    for key, value in subtask.model_dump().items():
        setattr(db_subtask, key, value)
    db.commit()
    db.refresh(db_subtask)
    return db_subtask


@app.delete("/subtasks/{subtask_id}")
def delete_subtask(subtask_id: int, db: Session = Depends(get_db)):
    db_subtask = (
        db.query(models.Subtask).filter(models.Subtask.subtask_id == subtask_id).first()
    )
    if not db_subtask:
        raise HTTPException(status_code=404, detail="Subtarea no encontrada")
    db.delete(db_subtask)
    db.commit()
    return {"mensaje": "Subtarea eliminada"}


# ---------- Daily capacity ----------
@app.post("/daily-capacity", response_model=schemas.DailyCapacityOut)
def create_daily_capacity(
    capacity: schemas.DailyCapacityCreate, db: Session = Depends(get_db)
):
    db_capacity = models.DailyCapacity(**capacity.model_dump())
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
def list_daily_capacity(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(models.DailyCapacity)
    if user_id is not None:
        query = query.filter(models.DailyCapacity.user_id == user_id)
    return query.all()
