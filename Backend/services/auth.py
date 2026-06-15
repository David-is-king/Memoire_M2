"""Logique metier de l'authentification."""

from fastapi import HTTPException, status
from typing import Any

from Backend.core.security import verify_password
from Backend.repositories.users import UserRepository
from Backend.schemas.auth import LoginRequest


class AuthService:
    """Service responsable de verifier les identifiants utilisateur."""

    @staticmethod
    def login(conn: Any, credentials: LoginRequest) -> dict:
        """Valide email/mot de passe puis retourne une reponse compatible Flutter."""
        user = UserRepository.get_by_email(conn, str(credentials.email))

        # Meme message pour email inconnu et mot de passe faux : meilleur pour la securite.
        if not user or not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou mot de passe incorrect",
            )

        if not verify_password(credentials.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou mot de passe incorrect",
            )

        return {
            "status": "success",
            "message": "Connexion reussie",
            "user": {
                "id": str(user["id"]),
                "email": user["email"],
                "full_name": user["full_name"],
                "role": user["role"],
            },
        }
