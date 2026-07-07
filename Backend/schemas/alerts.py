"""Schemas d'alertes."""

from datetime import datetime

from pydantic import BaseModel, Field


class AlertModel(BaseModel):
    """Alerte compatible avec le modele AlertModel Flutter."""

    id: str
    motor_id: str
    motor_name: str
    severity: str = Field(pattern="^(info|warning|critical)$")
    title: str
    message: str
    created_at: datetime
    is_read: bool


class MarkReadResponse(BaseModel):
    """Reponse simple apres marquage en lu."""

    status: str
    updated: int
