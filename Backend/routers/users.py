"""Routes utilisateurs."""

from fastapi import APIRouter, Depends, status
from typing import Any

from Backend.controllers.users import UserController
from Backend.database import get_db
from Backend.schemas.users import UserCreate, UserRead


router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserRead])
def list_users(conn: Any = Depends(get_db)) -> list[dict]:
    """Liste les utilisateurs pour l'administration ou le debug."""
    return UserController.list_users(conn)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: str, conn: Any = Depends(get_db)) -> dict:
    """Recupere un utilisateur precis."""
    return UserController.get_user(conn, user_id)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, conn: Any = Depends(get_db)) -> dict:
    """Cree un utilisateur et hash son mot de passe avant stockage."""
    return UserController.create_user(conn, payload)
