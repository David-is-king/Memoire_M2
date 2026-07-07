"""Configuration centralisee du backend.

Les valeurs peuvent etre surchargees avec des variables d'environnement.
Exemple PowerShell :
$env:DATABASE_URL="postgresql://postgres:Admin@localhost:5432/smartpredict"
"""

import os
from dataclasses import dataclass, field


def _split_origins(raw: str | None) -> list[str]:
    """Transforme une liste d'origines separees par des virgules en liste Python."""
    if not raw:
        return [
            "http://localhost",
            "http://localhost:3000",
            "http://localhost:5000",
            "http://localhost:5173",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8080",
        ]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@dataclass(frozen=True)
class Settings:
    """Parametres applicatifs lus depuis l'environnement."""

    app_name: str = os.getenv("APP_NAME", "SmartPredict Backend API")
    api_prefix: str = os.getenv("API_PREFIX", "/api/v1")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    # Format :
    # postgresql://UTILISATEUR:MOT_DE_PASSE@HOST:PORT/NOM_DE_LA_BASE
    #
    # Ici, le backend se connecte par defaut a une base locale PostgreSQL :
    # - utilisateur : postgres
    # - mot de passe : Admin
    # - serveur     : localhost
    # - port        : 5432
    # - base        : smartpredict
    #
    # Dans pgAdmin, le nom "smartpredict" doit exister dans Servers > PostgreSQL > Databases.
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:Admin@localhost:5432/smartpredict",
    )
    cors_origins: list[str] = field(default_factory=lambda: _split_origins(os.getenv("CORS_ORIGINS")))
    # Autorise Flutter Web quand il se lance sur un port aleatoire, par exemple
    # http://localhost:59937 ou http://127.0.0.1:65492.
    cors_origin_regex: str = os.getenv(
        "CORS_ORIGIN_REGEX",
        r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    )


# Instance unique importee par le reste du backend.
settings = Settings()
