from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


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
