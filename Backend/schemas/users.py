"""Schemas utilisateurs."""

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Donnees pour creer un utilisateur depuis l'API."""

    email: str = Field(min_length=3)
    password: str = Field(min_length=6)
    full_name: str | None = None
    role: str = "technician"


class UserRead(BaseModel):
    """Representation publique d'un utilisateur."""

    id: str
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
