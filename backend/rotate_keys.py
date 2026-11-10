"""Vuelve a cifrar los tokens guardados con la clave actual (ENCRYPTION_KEY).

Pasos para rotar la clave de cifrado (ver docs/seguridad/politicas.md):
  1. Poner la clave nueva en ENCRYPTION_KEY y la anterior en ENCRYPTION_KEY_PREVIOUS. Desplegar.
  2. Correr, con las mismas variables de entorno que la app:  cd backend && python rotate_keys.py
  3. Cuando diga que no queda nada con la clave anterior, borrar ENCRYPTION_KEY_PREVIOUS.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from lumo import audit, create_app
from lumo.crypto import CryptoError, previous_keys, rewrap
from lumo.models import Account


def rotate(app) -> tuple:
    cfg, engine = app.extensions["lumo_cfg"], app.extensions["lumo_engine"]
    key, prev = cfg["ENCRYPTION_KEY"], previous_keys(cfg)
    done = failed = 0
    with Session(engine) as s:
        for acc in s.execute(select(Account)).scalars():
            try:
                acc.access_token = rewrap(key, acc.access_token, prev)
                if acc.refresh_token:
                    acc.refresh_token = rewrap(key, acc.refresh_token, prev)
                done += 1
            except CryptoError:
                failed += 1  # ninguna de las claves sirve: esa cuenta tendrá que volver a conectarse
        audit.record(s, "key_rotation", detail="cuentas=%d fallidas=%d" % (done, failed))
        s.commit()
    return done, failed


if __name__ == "__main__":
    ok, bad = rotate(create_app())
    print("Cuentas con la clave nueva: %d. Que no se pudieron leer: %d." % (ok, bad))
