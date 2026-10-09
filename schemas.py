from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

class StatusEnum(str, Enum):
    pendiente = "pendiente"
    en_progreso = "en_progreso"
    completada = "completada"


# ---------- User / Auth ----------
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

    @field_validator("name")
    @classmethod
    def name_no_vacio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre es obligatorio")
        if len(v) > 100:
            raise ValueError("El nombre no puede superar los 100 caracteres")
        return v

    @field_validator("email")
    @classmethod
    def email_minusculas(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_valida(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        if len(v.encode("utf-8")) > 72:  # límite técnico de bcrypt
            raise ValueError("La contraseña es demasiado larga (máximo 72 bytes)")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def email_minusculas(cls, v: str) -> str:
        return v.lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    name: str
    email: EmailStr
    created_at: datetime


class DailyLimitIn(BaseModel):
    horas: float

    @field_validator("horas")
    @classmethod
    def horas_en_rango(cls, v: float) -> float:
        if not (1 <= v <= 16):
            raise ValueError("El límite debe estar entre 1 y 16 horas")
        return v


class DailyLimitOut(BaseModel):
    horas: float


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Activity ----------
class ActivityCreate(BaseModel):
    user_id: Optional[int] = None  # se ignora: el servidor usa el usuario del token
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
    user_id: Optional[int] = None  # se ignora: el servidor usa el usuario del token
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

    @model_validator(mode="after")
    def plazos_no_posteriores_al_evento(self):
        # Ninguna gestión puede vencer después de la fecha del evento
        for t in self.tareas:
            if t.plazo > self.fecha:
                raise ValueError(
                    f"El plazo de la gestión «{t.nombre}» no puede ser posterior "
                    "a la fecha del evento"
                )
        return self


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    tipo: str
    fecha: date
    created_at: datetime
    tareas: list[TaskOut] = []