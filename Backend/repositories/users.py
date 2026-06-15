"""Requetes SQL liees aux utilisateurs."""

from typing import Any


class UserRepository:
    """Centralise toutes les requetes SQL de la table users."""

    @staticmethod
    def get_by_email(conn: Any, email: str) -> dict | None:
        """Retourne un utilisateur complet depuis son email."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, password_hash, full_name, role, is_active
                FROM users
                WHERE email = %s
                """,
                (email,),
            )
            return cur.fetchone()

    @staticmethod
    def get_by_id(conn: Any, user_id: str) -> dict | None:
        """Retourne un utilisateur public depuis son identifiant."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, full_name, role, is_active
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            return cur.fetchone()

    @staticmethod
    def list_all(conn: Any) -> list[dict]:
        """Liste tous les utilisateurs actifs ou inactifs."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, full_name, role, is_active
                FROM users
                ORDER BY created_at DESC
                """
            )
            return list(cur.fetchall())

    @staticmethod
    def create(
        conn: Any,
        *,
        email: str,
        password_hash: str,
        full_name: str | None,
        role: str,
    ) -> dict:
        """Cree un utilisateur puis retourne sa version publique."""
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES (%s, %s, %s, %s)
                RETURNING id, email, full_name, role, is_active
                """,
                (email, password_hash, full_name, role),
            )
            user = cur.fetchone()
            conn.commit()
            return user
