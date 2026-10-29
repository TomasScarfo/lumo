import unittest
from datetime import timedelta
from unittest import mock

from cryptography.fernet import Fernet
from sqlalchemy import Text
from sqlalchemy.orm import Session

from lumo import create_app, ml
from lumo.crypto import CryptoError, decrypt, encrypt
from lumo.models import Account, utcnow
from lumo.tokens import NeedsReconnect, save_tokens, valid_access_token

KEY = Fernet.generate_key().decode()
CFG = {
    "ML_CLIENT_ID": "123",
    "ML_CLIENT_SECRET": "secreto-de-prueba",
    "REDIRECT_URI": "https://lumo.example/callback",
    "ENCRYPTION_KEY": KEY,
    "SECRET_KEY": "x" * 32,
    "DATABASE_URL": "sqlite://",
}
TOK = {"access_token": "AT-1", "refresh_token": "RT-1", "expires_in": 21600, "scope": "read offline_access", "user_id": 777}


class Crypto(unittest.TestCase):
    def test_roundtrip(self):
        self.assertEqual(decrypt(KEY, encrypt(KEY, "hola")), "hola")

    def test_clave_incorrecta(self):
        with self.assertRaises(CryptoError):
            decrypt(Fernet.generate_key().decode(), encrypt(KEY, "hola"))


class Pkce(unittest.TestCase):
    def test_challenge_s256(self):
        import base64, hashlib
        verifier, challenge = ml.new_pkce()
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(challenge, expected)


class Flujo(unittest.TestCase):
    def setUp(self):
        self.app = create_app(CFG)
        self.client = self.app.test_client()

    def test_connect_redirige_con_state_y_pkce(self):
        r = self.client.get("/connect")
        self.assertEqual(r.status_code, 302)
        loc = r.headers["Location"]
        self.assertTrue(loc.startswith("https://auth.mercadolibre.com.ar/authorization?"))
        for frag in ("response_type=code", "client_id=123", "code_challenge_method=S256", "state="):
            self.assertIn(frag, loc)
        self.assertNotIn("secreto-de-prueba", loc)

    def test_callback_rechaza_state_incorrecto(self):
        self.client.get("/connect")
        r = self.client.get("/callback?code=abc&state=otro")
        self.assertEqual(r.status_code, 400)

    def test_callback_sin_sesion(self):
        r = self.client.get("/callback?code=abc&state=otro")
        self.assertEqual(r.status_code, 400)

    def _conectar(self, advertisers_result):
        loc = self.client.get("/connect").headers["Location"]
        state = loc.split("state=")[1].split("&")[0]
        with mock.patch("lumo.ml.exchange_code", return_value=dict(TOK)) as ex, mock.patch("lumo.ml.advertisers", **advertisers_result):
            r = self.client.get("/callback?code=abc&state=" + state)
        return r, ex

    def test_callback_guarda_tokens_cifrados_y_lista_anunciantes(self):
        ads = [{"advertiser_id": 1, "site_id": "MLA", "advertiser_name": "Casa Nogal", "account_name": "MLA - X"}]
        r, ex = self._conectar({"return_value": ads})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Casa Nogal", r.get_data(as_text=True))
        self.assertTrue(ex.call_args[0][2])  # se envió el code_verifier
        with Session(self.app.extensions["lumo_engine"]) as s:
            acc = s.get(Account, 777)
            self.assertNotIn("AT-1", acc.access_token)
            self.assertNotIn("RT-1", acc.refresh_token)
            self.assertEqual(decrypt(KEY, acc.access_token), "AT-1")
            self.assertEqual(acc.status, "connected")

    def test_publicidad_no_habilitada(self):
        r, _ = self._conectar({"side_effect": ml.MLError(404, "not_found", "No permissions found for user_id")})
        self.assertIn("Publicidad habilitada", r.get_data(as_text=True))

    def test_permiso_restringido(self):
        r, _ = self._conectar({"side_effect": ml.MLError(403, "forbidden")})
        self.assertIn("error 403", r.get_data(as_text=True))

    def test_scope_admite_listas_largas(self):
        # Mercado Libre devuelve más de 255 caracteres; en Postgres un varchar(255) rompía el guardado.
        self.assertIsInstance(Account.__table__.c.scope.type, Text)

    def test_la_pagina_no_muestra_tokens(self):
        r, _ = self._conectar({"return_value": []})
        html = r.get_data(as_text=True)
        self.assertNotIn("AT-1", html)
        self.assertNotIn("RT-1", html)


class Renovacion(unittest.TestCase):
    def setUp(self):
        self.app = create_app(CFG)
        self.engine = self.app.extensions["lumo_engine"]
        with Session(self.engine) as s:
            save_tokens(s, CFG, 777, dict(TOK))
            s.commit()

    def _vencer(self):
        with Session(self.engine) as s:
            s.get(Account, 777).expires_at = utcnow() - timedelta(minutes=1)
            s.commit()

    def test_token_vigente_no_renueva(self):
        with Session(self.engine) as s, mock.patch("lumo.ml.refresh") as rf:
            self.assertEqual(valid_access_token(s, CFG, 777), "AT-1")
            rf.assert_not_called()

    def test_token_vencido_renueva_y_guarda_el_nuevo_refresh(self):
        self._vencer()
        nuevo = {"access_token": "AT-2", "refresh_token": "RT-2", "expires_in": 21600, "scope": "read"}
        with Session(self.engine) as s, mock.patch("lumo.ml.refresh", return_value=nuevo) as rf:
            self.assertEqual(valid_access_token(s, CFG, 777), "AT-2")
            self.assertEqual(rf.call_args[0][1], "RT-1")
        with Session(self.engine) as s:
            self.assertEqual(decrypt(KEY, s.get(Account, 777).refresh_token), "RT-2")

    def test_invalid_grant_marca_requiere_reconectar(self):
        self._vencer()
        with Session(self.engine) as s, mock.patch("lumo.ml.refresh", side_effect=ml.MLError(400, "invalid_grant")):
            with self.assertRaises(NeedsReconnect):
                valid_access_token(s, CFG, 777)
        with Session(self.engine) as s:
            self.assertEqual(s.get(Account, 777).status, "needs_reconnect")

    def test_error_temporal_no_desconecta_la_cuenta(self):
        self._vencer()
        with Session(self.engine) as s, mock.patch("lumo.ml.refresh", side_effect=ml.MLError(429, "too_many_requests")):
            with self.assertRaises(ml.MLError):
                valid_access_token(s, CFG, 777)
        with Session(self.engine) as s:
            self.assertEqual(s.get(Account, 777).status, "connected")


if __name__ == "__main__":
    unittest.main()
