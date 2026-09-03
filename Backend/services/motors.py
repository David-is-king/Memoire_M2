"""Logique metier des moteurs."""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from Backend.repositories.motors import MotorRepository


class MotorService:
    """Transforme les lignes SQL des moteurs en JSON attendu par Flutter."""

    @staticmethod
    def _format_motor(row: dict) -> dict:
        """Convertit une ligne SQL moteur + mesure en dictionnaire API."""
        last_reading = None
        if row.get("reading_timestamp") is not None:
            last_reading = {
                "timestamp": row["reading_timestamp"],
                "temperature": float(row["temperature"]),
                "vibration_rms": float(row["vibration_rms"]),
                "current": float(row["current"]),
                "voltage": float(row["voltage"]),
                "acoustic_db": float(row["acoustic_db"]),
            }

        return {
            "id": row["id"],
            "name": row["name"],
            "location": row["location"],
            "status": row["status"],
            "health_score": float(row["health_score"]),
            "failure_probability": float(row["failure_probability"]),
            "estimated_rul_days": row["estimated_rul_days"],
            "last_reading": last_reading,
            "last_seen": row["last_seen"],
        }

    @staticmethod
    def list_motors(conn: Any) -> list[dict]:
        """Retourne tous les moteurs pour le dashboard."""
        return [MotorService._format_motor(row) for row in MotorRepository.list_motors(conn)]

    @staticmethod
    def get_motor(conn: Any, motor_id: str) -> dict:
        """Retourne un moteur precis ou leve une 404."""
        row = MotorRepository.get_motor(conn, motor_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Moteur introuvable")
        return MotorService._format_motor(row)

    @staticmethod
    def get_readings(conn: Any, motor_id: str, since: datetime | None) -> list[dict]:
        """Retourne l'historique des mesures depuis une date."""
        since_value = since or datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        return MotorRepository.get_readings_since(conn, motor_id=motor_id, since=since_value)
