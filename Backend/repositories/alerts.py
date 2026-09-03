"""Requetes SQL liees aux alertes."""

from typing import Any


class AlertRepository:
    """Centralise toutes les operations sur les alertes."""

    @staticmethod
    def list_alerts(conn: Any, *, unread_only: bool = False) -> list[dict]:
        """Liste les alertes, avec option pour ne garder que les non lues."""
        where_clause = "WHERE a.is_read = FALSE" if unread_only else ""
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    a.id,
                    a.motor_id,
                    COALESCE(m.name, a.motor_id) AS motor_name,
                    a.severity,
                    a.title,
                    a.message,
                    a.created_at,
                    a.is_read
                FROM alerts a
                LEFT JOIN motors m ON m.id = a.motor_id
                {where_clause}
                ORDER BY a.created_at DESC
                """
            )
            return list(cur.fetchall())

    @staticmethod
    def mark_read(conn: Any, alert_id: str) -> int:
        """Marque une alerte comme lue et retourne le nombre de lignes modifiees."""
        with conn.cursor() as cur:
            cur.execute("UPDATE alerts SET is_read = TRUE WHERE id = %s", (alert_id,))
            updated = cur.rowcount
            conn.commit()
            return updated

    @staticmethod
    def mark_all_read(conn: Any) -> int:
        """Marque toutes les alertes comme lues."""
        with conn.cursor() as cur:
            cur.execute("UPDATE alerts SET is_read = TRUE WHERE is_read = FALSE")
            updated = cur.rowcount
            conn.commit()
            return updated

    @staticmethod
    def get_latest_unread(conn: Any) -> dict | None:
        """Retourne la derniere alerte non lue pour le flux WebSocket."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.id,
                    a.motor_id,
                    COALESCE(m.name, a.motor_id) AS motor_name,
                    a.severity,
                    a.title,
                    a.message,
                    a.created_at,
                    a.is_read
                FROM alerts a
                LEFT JOIN motors m ON m.id = a.motor_id
                WHERE a.is_read = FALSE
                ORDER BY a.created_at DESC
                LIMIT 1
                """
            )
            return cur.fetchone()
