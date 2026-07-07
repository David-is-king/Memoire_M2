"""Routes predictions."""

from fastapi import APIRouter, Depends
from typing import Any

from Backend.controllers.predictions import PredictionController
from Backend.database import get_db
from Backend.schemas.predictions import PredictionResult


router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.get("/{motor_id}", response_model=PredictionResult)
def get_prediction(motor_id: str, conn: Any = Depends(get_db)) -> dict:
    """Retourne la derniere prediction ML pour un moteur."""
    return PredictionController.get_latest(conn, motor_id)
