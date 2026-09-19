import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Carga las variables del archivo .env (solo tiene efecto en local;
# en Render las variables de entorno ya vienen configuradas del panel)
load_dotenv()

# La URL de conexión se lee de una variable de entorno (nunca hardcodeada)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "La variable de entorno DATABASE_URL no está definida. "
        "Configúrala en Render (o en tu .env local) con la cadena de "
        "conexión de Supabase (Connection Pooling, puerto 6543)."
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependencia de FastAPI: abre una sesión y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
