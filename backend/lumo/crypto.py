"""Cifrado de tokens en reposo. La clave vive en una variable de entorno, nunca en el código ni en la base.

ENCRYPTION_KEY puede ser cualquier texto largo y aleatorio: se convierte con SHA-256 en una clave de 32 bytes.

Rotación de claves: se pone la clave nueva en ENCRYPTION_KEY y la anterior en ENCRYPTION_KEY_PREVIOUS (varias, separadas
por coma). Todo se cifra con la nueva y se sigue pudiendo leer lo cifrado con las anteriores. Después se corre
`python rotate_keys.py` para volver a cifrar lo guardado y recién entonces se borra la clave anterior.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class CryptoError(Exception):
    pass


def previous_keys(cfg: dict) -> tuple:
    return tuple(k.strip() for k in (cfg.get("ENCRYPTION_KEY_PREVIOUS") or "").split(",") if k.strip())


def _fernet(secret: str, previous: tuple = ()) -> MultiFernet:
    if not secret:
        raise CryptoError("Falta ENCRYPTION_KEY")
    return MultiFernet([Fernet(base64.urlsafe_b64encode(hashlib.sha256(k.encode()).digest())) for k in (secret, *previous)])


def encrypt(secret: str, plain: str, previous: tuple = ()) -> str:
    return _fernet(secret, previous).encrypt(plain.encode()).decode()


def decrypt(secret: str, token: str, previous: tuple = ()) -> str:
    try:
        return _fernet(secret, previous).decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("No se pudo descifrar: la clave cambió o el dato está dañado") from exc


def rewrap(secret: str, token: str, previous: tuple = ()) -> str:
    """Vuelve a cifrar un dato con la clave principal."""
    try:
        return _fernet(secret, previous).rotate(token.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("No se pudo descifrar: la clave cambió o el dato está dañado") from exc
