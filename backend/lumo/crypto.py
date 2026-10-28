"""Cifrado de tokens en reposo. La clave vive en una variable de entorno, nunca en el código ni en la base.

ENCRYPTION_KEY puede ser cualquier texto largo y aleatorio: se convierte con SHA-256 en una clave de 32 bytes.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class CryptoError(Exception):
    pass


def _fernet(secret: str) -> Fernet:
    if not secret:
        raise CryptoError("Falta ENCRYPTION_KEY")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def encrypt(secret: str, plain: str) -> str:
    return _fernet(secret).encrypt(plain.encode()).decode()


def decrypt(secret: str, token: str) -> str:
    try:
        return _fernet(secret).decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("No se pudo descifrar: la clave cambió o el dato está dañado") from exc
