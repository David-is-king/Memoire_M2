"""Connexion PostgreSQL partagee par les repositories.

Le backend utilise psycopg en mode synchrone pour rester simple a comprendre.
Chaque endpoint ouvre une connexion courte, execute ses requetes puis la ferme.
"""

from collections.abc import Generator
from typing import Any

from Backend.core.config import settings


def get_db_connection() -> Any:
    """Cree une connexion PostgreSQL qui retourne les lignes en dictionnaires."""
    # Import local : permet d'importer l'application meme si psycopg[binary]
    # n'est pas encore installe. L'erreur apparaitra seulement a la connexion DB.
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(settings.database_url, row_factory=dict_row)


def get_db() -> Generator[Any, None, None]:
    """Dependency FastAPI pour injecter une connexion dans les routers."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()
