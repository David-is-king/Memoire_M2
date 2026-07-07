"""Controller d'authentification."""

from typing import Any

from Backend.schemas.auth import LoginRequest
from Backend.services.auth import AuthService


class AuthController:
    """Expose les methodes appelees par le router auth."""

    @staticmethod
    def login_user(conn: Any, credentials: LoginRequest) -> dict:
        """Delegue la verification des identifiants au service auth."""
        return AuthService.login(conn, credentials)
