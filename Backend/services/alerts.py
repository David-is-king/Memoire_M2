"""Logique metier des alertes."""

from typing import Any

from Backend.repositories.alerts import AlertRepository


class AlertService:
    """Prepare les alertes pour l'ecran alertes Flutter."""

    @staticmethod
    def _format_alert(row: dict) -> dict:
        """Convertit une ligne PostgreSQL en JSON exactement attendu par Flutter."""
        return {
            "id": str(row["id"]),
            "motor_id": str(row["motor_id"]),
            "motor_name": row["motor_name"],
            "severity": row["severity"],
            "title": row["title"],
            "message": row["message"],
            "created_at": row["created_at"],
            "is_read": row["is_read"],
        }

    @staticmethod
    def list_alerts(conn: Any, unread_only: bool = False) -> list[dict]:
        """Retourne les alertes triees des plus recentes aux plus anciennes."""
        rows = AlertRepository.list_alerts(conn, unread_only=unread_only)
        return [AlertService._format_alert(row) for row in rows]

    @staticmethod
    def mark_read(conn: Any, alert_id: str) -> dict:
        """Marque une alerte comme lue."""
        updated = AlertRepository.mark_read(conn, alert_id)
        return {"status": "success", "updated": updated}

    @staticmethod
    def mark_all_read(conn: Any) -> dict:
        """Marque toutes les alertes comme lues."""
        updated = AlertRepository.mark_all_read(conn)
        return {"status": "success", "updated": updated}
