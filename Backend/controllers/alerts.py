"""Controller alertes."""

from typing import Any

from Backend.services.alerts import AlertService


class AlertController:
    """Expose les actions alertes au router."""

    @staticmethod
    def list_alerts(conn: Any, unread_only: bool = False) -> list[dict]:
        """Recupere les alertes."""
        return AlertService.list_alerts(conn, unread_only=unread_only)

    @staticmethod
    def mark_read(conn: Any, alert_id: str) -> dict:
        """Marque une alerte comme lue."""
        return AlertService.mark_read(conn, alert_id)

    @staticmethod
    def mark_all_read(conn: Any) -> dict:
        """Marque toutes les alertes comme lues."""
        return AlertService.mark_all_read(conn)
