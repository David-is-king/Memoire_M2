"""Controller moteurs."""

from datetime import datetime
from typing import Any

from Backend.services.motors import MotorService


class MotorController:
    """Expose les actions moteurs au router."""

    @staticmethod
    def list_motors(conn: Any) -> list[dict]:
        """Recupere tous les moteurs."""
        return MotorService.list_motors(conn)

    @staticmethod
    def get_motor(conn: Any, motor_id: str) -> dict:
        """Recupere un moteur precis."""
        return MotorService.get_motor(conn, motor_id)

    @staticmethod
    def get_readings(conn: Any, motor_id: str, since: datetime | None) -> list[dict]:
        """Recupere l'historique capteur d'un moteur."""
        return MotorService.get_readings(conn, motor_id, since)
