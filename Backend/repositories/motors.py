"""Requetes SQL liees aux moteurs et mesures capteurs."""

from datetime import datetime
from typing import Any


class MotorRepository:
    """Centralise les lectures de moteurs et d'historique capteur."""

    @staticmethod
    def list_motors(conn: Any) -> list[dict]:
        """Liste les moteurs avec leur derniere mesure connue."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    m.id,
                    m.name,
                    m.location,
                    m.status,
                    m.health_score,
                    m.failure_probability,
                    m.estimated_rul_days,
                    m.last_seen,
                    lr.timestamp AS reading_timestamp,
                    lr.temperature,
                    lr.vibration_rms,
                    lr.current,
                    lr.voltage,
                    lr.acoustic_db
                FROM motors m
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM sensor_readings sr
                    WHERE sr.motor_id = m.id
                    ORDER BY sr.timestamp DESC
                    LIMIT 1
                ) lr ON TRUE
                ORDER BY
                    CASE m.status
                        WHEN 'critical' THEN 1
                        WHEN 'warning' THEN 2
                        WHEN 'healthy' THEN 3
                        ELSE 4
                    END,
                    m.name
                """
            )
            return list(cur.fetchall())

    @staticmethod
    def get_motor(conn: Any, motor_id: str) -> dict | None:
        """Recupere un seul moteur avec sa derniere mesure."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    m.id,
                    m.name,
                    m.location,
                    m.status,
                    m.health_score,
                    m.failure_probability,
                    m.estimated_rul_days,
                    m.last_seen,
                    lr.timestamp AS reading_timestamp,
                    lr.temperature,
                    lr.vibration_rms,
                    lr.current,
                    lr.voltage,
                    lr.acoustic_db
                FROM motors m
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM sensor_readings sr
                    WHERE sr.motor_id = m.id
                    ORDER BY sr.timestamp DESC
                    LIMIT 1
                ) lr ON TRUE
                WHERE m.id = %s
                """,
                (motor_id,),
            )
            return cur.fetchone()

    @staticmethod
    def get_readings_since(conn: Any, *, motor_id: str, since: datetime) -> list[dict]:
        """Retourne l'historique capteur d'un moteur depuis une date."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT timestamp, temperature, vibration_rms, current, voltage, acoustic_db
                FROM sensor_readings
                WHERE motor_id = %s AND timestamp >= %s
                ORDER BY timestamp ASC
                """,
                (motor_id, since),
            )
            return list(cur.fetchall())

    @staticmethod
    def get_latest_reading(conn: Any, motor_id: str) -> dict | None:
        """Retourne la toute derniere mesure d'un moteur."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT timestamp, temperature, vibration_rms, current, voltage, acoustic_db
                FROM sensor_readings
                WHERE motor_id = %s
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (motor_id,),
            )
            return cur.fetchone()

    @staticmethod
    def list_statuses(conn: Any) -> dict[str, str]:
        """Retourne une map {motor_id: status} pour le WebSocket dashboard."""
        with conn.cursor() as cur:
            cur.execute("SELECT id, status FROM motors")
            return {row["id"]: row["status"] for row in cur.fetchall()}
