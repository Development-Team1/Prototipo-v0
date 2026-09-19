import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from database import Base


class StatusEnum(str, enum.Enum):
    pendiente = "pendiente"
    en_progreso = "en_progreso"
    completada = "completada"


class User(Base):
    __tablename__ = "user"

    user_id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Activity(Base):
    __tablename__ = "activity"

    activity_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("user.user_id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(200), nullable=False)
    course = Column(String(100))
    due_date = Column(Date)
    status = Column(
        Enum(StatusEnum, name="status"), nullable=False, default=StatusEnum.pendiente
    )


class Subtask(Base):
    __tablename__ = "subtask"

    subtask_id = Column(BigInteger, primary_key=True, autoincrement=True)
    activity_id = Column(
        BigInteger, ForeignKey("activity.activity_id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(200), nullable=False)
    estimated_minutes = Column(Integer)
    is_done = Column(Boolean, nullable=False, default=False)


class DailyCapacity(Base):
    __tablename__ = "daily_capacity"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_user_day"),)

    capacity_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger, ForeignKey("user.user_id", ondelete="CASCADE"), nullable=False
    )
    day = Column(Date, nullable=False)
    available_minutes = Column(Integer, nullable=False)
