"""Schemas des moteurs et mesures capteurs."""

from datetime import datetime

from pydantic import BaseModel, Field


class SensorReading(BaseModel):
    """Mesure capteur compatible avec app_flutter/lib/sensor_data.dart."""

    timestamp: datetime
    temperature: float
    vibration_rms: float
    current: float
    voltage: float
    acoustic_db: float


class MotorDevice(BaseModel):
    """Etat complet d'un moteur tel que le dashboard Flutter l'attend."""

    id: str
    name: str
    location: str
    status: str = Field(pattern="^(healthy|warning|critical|offline)$")
    health_score: float = Field(ge=0, le=1)
    failure_probability: float = Field(ge=0, le=1)
    estimated_rul_days: int = Field(ge=0)
    last_reading: SensorReading | None = None
    last_seen: datetime
