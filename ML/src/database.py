"""
src/database.py

Connexion PostgreSQL centralisée.
Tables existantes : UserProfil, alerts, machine, prediction, sensor_data
"""

import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, Column, String, Float, Integer, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from loguru import logger
import pandas as pd

# ── Config connexion ──────────────────────────────────────
DB_USER     = os.getenv("DB_USER",     "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Admin")
DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_PORT     = os.getenv("DB_PORT",     "5432")
DB_NAME     = os.getenv("DB_NAME",     "predictive_maintenance")
DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"connect_timeout": DB_CONNECT_TIMEOUT},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── Modèles ORM ───────────────────────────────────────────

class UserProfil(Base):
    __tablename__ = "UserProfil"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    email      = Column(String, unique=True, nullable=False)
    password   = Column(String, nullable=False)
    firstname  = Column(String)
    lastname   = Column(String)
    poste      = Column(String)
    superAdmin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Machine(Base):
    __tablename__ = "machine"
    id           = Column(String, primary_key=True)
    name         = Column(String)
    location     = Column(String)
    status       = Column(String, default="healthy")
    health_score = Column(Integer, default=100)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SensorData(Base):
    __tablename__ = "sensor_data"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    motor_id    = Column(String, nullable=False)
    timestamp   = Column(DateTime, nullable=False)
    temperature = Column(Float)
    vibration_x = Column(Float)
    vibration_y = Column(Float)
    vibration_z = Column(Float)
    current     = Column(Float)
    voltage     = Column(Float)
    acoustic_db = Column(Float)
    source      = Column(String, default="simulator")


class Prediction(Base):
    __tablename__ = "prediction"
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    motor_id            = Column(String, nullable=False)
    predicted_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    health_score        = Column(Integer)
    failure_probability = Column(Float)
    rul_days            = Column(Float)
    status              = Column(String)
    anomaly_score       = Column(Float)
    confidence          = Column(Float)
    recommendation      = Column(String)


class Alert(Base):
    __tablename__ = "alerts"
    id          = Column(String, primary_key=True)
    device_id   = Column(String, nullable=False)
    device_name = Column(String)
    severity    = Column(String)
    title       = Column(String)
    message     = Column(String)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_read     = Column(Boolean, default=False)


# ── Utilitaires ───────────────────────────────────────────

def get_session():
    return SessionLocal()


def test_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(f"✓ PostgreSQL OK : {DB_HOST}:{DB_PORT}/{DB_NAME}")
        return True
    except Exception as e:
        logger.error(f"✗ Connexion échouée : {e}")
        return False


def create_tables():
    Base.metadata.create_all(bind=engine)
    logger.info("✓ Tables créées / vérifiées")


def save_sensor_data(df: pd.DataFrame):
    cols = ["motor_id","timestamp","temperature","vibration_x",
            "vibration_y","vibration_z","current","voltage","acoustic_db"]
    df_db = df[[c for c in cols if c in df.columns]].copy()
    df_db["source"] = "dataset"
    df_db.to_sql("sensor_data", engine, if_exists="append", index=False)
    logger.info(f"✓ {len(df_db)} lignes → sensor_data")


def save_prediction_to_db(prediction):
    with SessionLocal() as session:
        record = Prediction(
            motor_id=prediction.motor_id,
            predicted_at=prediction.timestamp,
            health_score=prediction.health_score,
            failure_probability=prediction.failure_probability,
            rul_days=prediction.rul_days,
            status=prediction.status,
            anomaly_score=prediction.anomaly_score,
            confidence=prediction.confidence,
            recommendation=prediction.recommendation,
        )
        session.add(record)
        session.commit()
    logger.info(f"✓ Prédiction sauvée pour {prediction.motor_id}")


def save_alert_to_db(alert: dict):
    with SessionLocal() as session:
        valid_cols = {c.name for c in Alert.__table__.columns}
        record = Alert(**{k: v for k, v in alert.items() if k in valid_cols})
        session.merge(record)
        session.commit()


def upsert_machine(motor_id: str, name: str = None, location: str = None,
                   status: str = "healthy", health_score: int = 100):
    with SessionLocal() as session:
        machine = session.get(Machine, motor_id)
        if machine is None:
            machine = Machine(
                id=motor_id,
                name=name or f"Motor {motor_id}",
                location=location or "Unknown",
            )
            session.add(machine)
        machine.status       = status
        machine.health_score = health_score
        machine.updated_at   = datetime.now(timezone.utc)
        session.commit()


def load_from_db(query: str) -> pd.DataFrame:
    return pd.read_sql(query, engine)
