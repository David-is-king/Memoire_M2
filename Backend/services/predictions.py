"""Logique metier des predictions."""

from fastapi import HTTPException, status
from typing import Any

from Backend.repositories.predictions import PredictionRepository


class PredictionService:
    """Prepare les resultats ML pour l'ecran detail moteur."""

    @staticmethod
    def get_latest(conn: Any, motor_id: str) -> dict:
        """Retourne la derniere prediction d'un moteur."""
        prediction = PredictionRepository.get_latest_for_motor(conn, motor_id)
        if not prediction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aucune prediction disponible pour ce moteur",
            )

        prediction["failure_probability"] = float(prediction["failure_probability"])
        prediction["anomaly_features"] = prediction["anomaly_features"] or []
        return prediction
