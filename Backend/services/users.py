"""Logique metier des utilisateurs."""

from fastapi import HTTPException, status
from typing import Any

from Backend.core.security import hash_password
from Backend.repositories.users import UserRepository
from Backend.schemas.users import UserCreate


class UserService:
    """Service qui prepare les donnees utilisateur pour les controllers."""

    @staticmethod
    def _format_user(row: dict) -> dict:
        """Convertit l'UUID PostgreSQL en chaine lisible par l'API."""
        return {
            "id": str(row["id"]),
            "email": row["email"],
            "full_name": row["full_name"],
            "role": row["role"],
            "is_active": row["is_active"],
        }

    @staticmethod
    def list_users(conn: Any) -> list[dict]:
        """Retourne tous les utilisateurs publics."""
        return [UserService._format_user(row) for row in UserRepository.list_all(conn)]

    @staticmethod
    def get_user(conn: Any, user_id: str) -> dict:
        """Retourne un utilisateur ou leve une 404."""
        user = UserRepository.get_by_id(conn, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
        return UserService._format_user(user)

    @staticmethod
    def create_user(conn: Any, payload: UserCreate) -> dict:
        """Cree un utilisateur avec un mot de passe hash en base."""
        try:
            user = UserRepository.create(
                conn,
                email=str(payload.email),
                password_hash=hash_password(payload.password),
                full_name=payload.full_name,
                role=payload.role,
            )
            return UserService._format_user(user)
        except Exception as exc:
            conn.rollback()
            if exc.__class__.__name__ != "UniqueViolation":
                raise
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cet email existe deja") from exc
