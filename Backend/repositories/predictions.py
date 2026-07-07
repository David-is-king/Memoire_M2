"""Requetes SQL liees aux predictions."""

from typing import Any


class PredictionRepository:
    """Centralise les lectures de resultats ML."""

    @staticmethod
    def get_latest_for_motor(conn: Any, motor_id: str) -> dict | None:
        """Retourne la derniere prediction disponible pour un moteur."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    motor_id,
                    predicted_at,
                    failure_probability,
                    recommended_status,
                    maintenance_recommendation,
                    anomaly_features,
                    estimated_rul_days
                FROM predictions
                WHERE motor_id = %s
                ORDER BY predicted_at DESC
                LIMIT 1
                """,
                (motor_id,),
            )
            return cur.fetchone()
