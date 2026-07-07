"""Controller utilisateurs."""

from typing import Any

from Backend.schemas.users import UserCreate
from Backend.services.users import UserService


class UserController:
    """Expose les actions utilisateurs au router."""

    @staticmethod
    def list_users(conn: Any) -> list[dict]:
        """Recupere la liste des utilisateurs."""
        return UserService.list_users(conn)

    @staticmethod
    def get_user(conn: Any, user_id: str) -> dict:
        """Recupere un utilisateur par id."""
        return UserService.get_user(conn, user_id)

    @staticmethod
    def create_user(conn: Any, payload: UserCreate) -> dict:
        """Cree un nouvel utilisateur."""
        return UserService.create_user(conn, payload)
