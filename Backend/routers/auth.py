"""Routes d'authentification."""

from fastapi import APIRouter, Depends, status
from typing import Any

from Backend.controllers.auth import AuthController
from Backend.database import get_db
from Backend.schemas.auth import LoginRequest, LoginResponse


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
def login(credentials: LoginRequest, conn: Any = Depends(get_db)) -> dict:
    """Connexion utilisateur appelee par ApiService.login cote Flutter."""
    return AuthController.login_user(conn, credentials)
