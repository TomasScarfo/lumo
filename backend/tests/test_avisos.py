import json
import unittest
from datetime import datetime, timedelta
from unittest import mock

import fake_ml
from sqlalchemy.orm import Session

from lumo import ads, create_app, notify
from lumo.models import Access, Account, PanelState
from lumo.tokens import save_tokens

CFG = {"ML_CLIENT_ID": "123", "ML_CLIENT_SECRET": "secreto-de-prueba", "REDIRECT_URI": "https://lumo.test/callback",
       "ENCRYPTION_KEY": "clave-de-prueba-larga-y-aleatoria", "SECRET_KEY": "otra-clave-de-sesion", "DATABASE_URL": "sqlite://",
       "SMTP_PASSWORD": "pass-de-app", "SMTP_USER": "lumoads.ml@gmail.com", "CRON_TOKEN": "clave-del-cron-larga-y-aleatoria-0123456789"}
LUNES = datetime(2026, 10, 26, 15, 0)   # 12:00 en Argentina
MIERCOLES = datetime(2026, 10, 28, 15, 0)
SABADO = datetime(2026, 10, 31, 15, 0)


def fake_get(path, params=None, version="2"):
    return fake_ml.api_get(CFG, "AT", path, params, version)


def dataset():
    return ads.build_dataset(fake_get, fake_ml.ADVERTISER, datetime(2026, 10, 28, 15, 0).astimezone())


class Contenido(unittest.TestCase):
    def test_semanal_resume_inversion_ventas_y_roas(self):
        w = notify.weekly(dataset())
        self.assertGreater(w["spend"], 0)
        self.assertGreater(w["sales"], 0)
        subject, text, html = notify.weekly_mail(dataset(), "https://lumo.test/panel#alertas", "porque sí")
        self.assertIn("resumen semanal", subject)
        self.assertIn("Invertiste", text)
        self.assertIn("https://lumo.test/panel#alertas", html)

    def test_publicaciones_que_gastan_y_no_venden(self):
        data = dataset()
        self.assertEqual(notify.wasteful(data), [])   # con ventas, ninguna cumple
        for c in data["camps"]:
            if c["id"] == 101:
                for d in c["daily"]:
                    d["sales"] = 0
        ids = [x[0] for x in notify.wasteful(data)]
        self.assertIn("9001", ids)
        self.assertNotIn("9003", ids)   # la campaña 102 sí vendió

    def test_venden_bien_sin_publicidad_usa_el_criterio_de_alertas(self):
        ids = [x[0] for x in notify.organic(dataset())]
        self.assertEqual(ids, ["9006"])   # 9007 convierte menos del 3%


class Envio(unittest.TestCase):
    def setUp(self):
        self.app = create_app(CFG)
        self.engine = self.app.extensions["lumo_engine"]
        self.sent = []
        self.send = lambda cfg, to, subject, text, html: self.sent.append((to, subject))

    def run_for(self, prefs, now):
        with Session(self.engine) as s:
            return notify.run_for(s, CFG, 5, "ana@test.com", prefs, dataset(), "https://lumo.test/panel", now, self.send)

    def test_sin_avisos_activados_no_envia_nada(self):
        self.assertEqual(self.run_for({}, LUNES), [])
        self.assertEqual(self.sent, [])

    def test_resumen_semanal_solo_los_primeros_dias_y_una_vez_por_semana(self):
        self.assertEqual(self.run_for({"m1": True}, LUNES), ["m1"])
        self.assertEqual(self.run_for({"m1": True}, LUNES + timedelta(hours=3)), [])
        self.assertEqual(self.run_for({"m1": True}, MIERCOLES), [])
        self.assertEqual(self.run_for({"m1": True}, SABADO), [])
        self.assertEqual(self.sent, [("ana@test.com", "Tu resumen semanal de Lumo")])
        self.assertEqual(self.run_for({"m1": True}, LUNES + timedelta(days=7)), ["m1"])

    def test_si_el_lunes_fallo_se_reintenta_el_miercoles(self):
        self.assertEqual(self.run_for({"m1": True}, MIERCOLES), ["m1"])

    def test_avisos_de_oportunidad_no_se_repiten_en_14_dias(self):
        self.assertEqual(self.run_for({"m3": True}, SABADO), ["m3"])
        self.assertEqual(self.run_for({"m3": True}, SABADO + timedelta(days=5)), [])
        self.assertEqual(self.run_for({"m3": True}, SABADO + timedelta(days=15)), ["m3"])


class Rutas(unittest.TestCase):
    def setUp(self):
        self.app = create_app(CFG)
        self.client = self.app.test_client()
        self.engine = self.app.extensions["lumo_engine"]
        with Session(self.engine) as s:
            acc = save_tokens(s, CFG, 5, {"access_token": "AT", "refresh_token": "RT", "expires_in": 21600, "scope": "read"})
            acc.email = "ana@test.com"
            s.add(Access(user_id=5))
            s.add(PanelState(user_id=5, data=json.dumps({"sw": {"m1": True}})))
            s.commit()
        patches = [mock.patch("lumo.ml.api_get", side_effect=lambda cfg, tok, path, params=None, version="2": fake_ml.api_get(cfg, tok, path, params, version)),
                   mock.patch("lumo.ml.advertisers", return_value=[fake_ml.ADVERTISER]),
                   mock.patch("lumo.notify.send_mail")]
        _, _, self.mail = [p.start() for p in patches]
        self.addCleanup(mock.patch.stopall)

    def cron(self, token="clave-del-cron-larga-y-aleatoria-0123456789"):
        return self.client.post("/cron/avisos", headers={"X-Cron-Token": token} if token is not None else {})

    def test_el_chequeo_diario_exige_la_clave(self):
        self.assertEqual(self.cron(None).status_code, 403)
        self.assertEqual(self.cron("otra").status_code, 403)
        self.mail.assert_not_called()

    def test_sin_clave_configurada_la_ruta_no_existe(self):
        app = create_app(dict(CFG, CRON_TOKEN=""))
        self.assertEqual(app.test_client().post("/cron/avisos", headers={"X-Cron-Token": ""}).status_code, 404)

    def test_sin_contrasena_de_correo_no_envia(self):
        app = create_app(dict(CFG, SMTP_PASSWORD=""))
        r = app.test_client().post("/cron/avisos", headers={"X-Cron-Token": "clave-del-cron-larga-y-aleatoria-0123456789"})
        self.assertEqual(r.status_code, 503)

    def test_el_chequeo_diario_envia_a_quien_activo_el_aviso_y_no_repite(self):
        with Session(self.engine) as s:
            s.get(PanelState, 5).data = json.dumps({"sw": {"m3": True}})
            s.commit()
        r = self.cron().get_json()
        self.assertEqual((r["cuentas"], r["enviados"], r["errores"]), (1, 1, 0))
        self.assertEqual(self.mail.call_args[0][1], "ana@test.com")
        self.assertEqual(self.cron().get_json()["enviados"], 0)

    def test_las_pruebas_van_solo_a_la_propia_cuenta(self):
        with self.client.session_transaction() as sess:
            sess["uid"] = 5
        r = self.client.post("/api/avisos/prueba")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.mail.call_args[0][1], "ana@test.com")
        self.assertEqual(self.client.post("/api/avisos/prueba").status_code, 429)   # no más de uno por minuto

    def test_el_email_se_puede_cargar_a_mano_y_se_valida(self):
        with self.client.session_transaction() as sess:
            sess["uid"] = 5
        self.assertEqual(self.client.post("/api/email", json={"email": "no-es-un-mail"}).status_code, 400)
        self.assertEqual(self.client.post("/api/email", json={"email": "ana@x"}).status_code, 400)
        self.assertEqual(self.client.post("/api/email", json={"email": " nueva@test.com "}).status_code, 200)
        self.assertEqual(self.client.get("/api/datos").get_json()["email"], "nueva@test.com")
        self.client.post("/api/email", json={"email": "otra@test.com"})

    def test_email_pide_sesion(self):
        self.assertEqual(self.client.post("/api/email", json={"email": "a@b.com"}).status_code, 401)

    def test_cuentas_sin_email_lo_leen_al_abrir_el_panel(self):
        with Session(self.engine) as s:
            s.get(Account, 5).email = None
            s.commit()
        with self.client.session_transaction() as sess:
            sess["uid"] = 5
        with mock.patch("lumo.ml.api_get", side_effect=lambda cfg, tok, path, params=None, version="2": {"email": "leido@ml.com"} if path == "/users/me" else fake_ml.api_get(cfg, tok, path, params, version)):
            self.assertEqual(self.client.get("/api/datos").get_json()["email"], "leido@ml.com")

    def test_prueba_pide_sesion(self):
        self.assertEqual(self.client.post("/api/avisos/prueba").status_code, 401)

    def test_datos_informan_el_email_y_si_el_envio_esta_habilitado(self):
        with self.client.session_transaction() as sess:
            sess["uid"] = 5
        d = self.client.get("/api/datos").get_json()
        self.assertEqual(d["email"], "ana@test.com")
        self.assertTrue(d["mailOn"])


if __name__ == "__main__":
    unittest.main()
