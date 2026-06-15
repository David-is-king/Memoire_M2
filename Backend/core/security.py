"""Fonctions de securite reutilisables.

On utilise directement le paquet `bcrypt` pour eviter les soucis de compatibilite
entre certaines versions recentes de bcrypt et passlib.
"""

import bcrypt


def hash_password(password: str) -> str:
    """Transforme un mot de passe clair en hash bcrypt."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare un mot de passe clair avec le hash stocke en base."""
    password_bytes = plain_password.encode("utf-8")
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hash_bytes)
