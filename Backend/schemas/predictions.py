"""Schemas de prediction maintenance."""

from datetime import datetime

from pydantic import BaseModel, Field


class PredictionResult(BaseModel):
    """Resultat retourne a l'ecran detail moteur."""

    motor_id: str
    predicted_at: datetime
    failure_probability: float = Field(ge=0, le=1)
    recommended_status: str = Field(pattern="^(healthy|warning|critical|offline)$")
    maintenance_recommendation: str
    anomaly_features: list[str]
    estimated_rul_days: int = Field(ge=0)
