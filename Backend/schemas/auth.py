"""Schemas d'authentification."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Payload envoye par Flutter lors de la connexion."""

    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    """Utilisateur public retourne au front sans le mot de passe."""

    id: str
    email: str
    full_name: str | None = None
    role: str | None = None


class LoginResponse(BaseModel):
    """Reponse de login compatible avec le front actuel."""

    status: str
    message: str
    user: UserResponse
