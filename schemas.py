from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

class StatusEnum(str, Enum):
    pendiente = "pendiente"
    en_progreso = "en_progreso"
    completada = "completada"


# ---------- User ----------
class UserCreate(BaseModel):
    name: str
    email: EmailStr


class UserOut(UserCreate):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    created_at: datetime


# ---------- Activity ----------
class ActivityCreate(BaseModel):
    user_id: int
    title: str
    course: Optional[str] = None
    due_date: Optional[date] = None
    status: StatusEnum = StatusEnum.pendiente


class ActivityOut(ActivityCreate):
    model_config = ConfigDict(from_attributes=True)
    activity_id: int


# ---------- Subtask ----------
class SubtaskCreate(BaseModel):
    activity_id: int
    title: str
    estimated_minutes: Optional[int] = None
    is_done: bool = False


class SubtaskOut(SubtaskCreate):
    model_config = ConfigDict(from_attributes=True)
    subtask_id: int


# ---------- DailyCapacity ----------
class DailyCapacityCreate(BaseModel):
    user_id: int
    day: date
    available_minutes: int


class DailyCapacityOut(DailyCapacityCreate):
    model_config = ConfigDict(from_attributes=True)
    capacity_id: int


# ---------- Event ----------
class TaskCreate(BaseModel):
    nombre: str
    plazo: date
    horas_estimadas: float

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El nombre de la subtarea es obligatorio")
        return v.strip()

    @field_validator("horas_estimadas")
    @classmethod
    def horas_positivas(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Las horas estimadas deben ser mayores a 0")
        return v


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int
    nombre: str
    plazo: date
    horas_estimadas: float


class EventCreate(BaseModel):
    nombre: str
    tipo: str
    fecha: date
    tareas: list[TaskCreate] = []

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El nombre del evento es obligatorio")
        return v.strip()

    @field_validator("tipo")
    @classmethod
    def tipo_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El tipo de evento es obligatorio")
        return v.strip()


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    tipo: str
    fecha: date
    created_at: datetime
    tareas: list[TaskOut] = []