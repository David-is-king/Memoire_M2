"""Controller predictions."""

from typing import Any

from Backend.services.predictions import PredictionService


class PredictionController:
    """Expose les predictions au router."""

    @staticmethod
    def get_latest(conn: Any, motor_id: str) -> dict:
        """Recupere la derniere prediction d'un moteur."""
        return PredictionService.get_latest(conn, motor_id)
