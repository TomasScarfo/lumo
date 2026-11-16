import json
import unittest
from datetime import datetime
from unittest import mock

import fake_ml
from sqlalchemy.orm import Session

from lumo import ads, create_app, notify
from lumo.models import Access, Account, PanelState, Snapshot
from lumo.tokens import save_tokens

CFG = {"ML_CLIENT_ID": "123", "ML_CLIENT_SECRET": "secreto-de-prueba", "REDIRECT_URI": "https://lumo.test/callback",
       "ENCRYPTION_KEY": "clave-de-prueba-larga-y-aleatoria", "SECRET_KEY": "otra-clave-de-sesion", "DATABASE_URL": "sqlite://",
       "SMTP_PASSWORD": "pass-de-app", "SMTP_USER": "lumoads.ml@gmail.com", "CRON_TOKEN": "clave-del-cron-larga-y-aleatoria-0123456789"}
LUNES = datetime(2026, 10, 26, 15, 0)   # 12:00 en Argentina


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

    def test_el_resumen_usa_los_mismos_estados_que_el_panel(self):
        data = dataset()
        for c in data["camps"]:
            if c["id"] == 101:      # ventas en cero esta semana: Revisar
                for d in c["daily"][-7:]:
                    d["sales"] = 0
            if c["id"] == 102:      # ROAS alto y visibilidad en caída
                for d in c["daily"][-7:]:
                    d["sales"] *= 5
                    d["prints"] *= 0.4
        w = notify.weekly(data)
        self.assertIn("Mesas y sillas", [x["name"] for x in w["opp"]])
        self.assertTrue(any(x["kind"] == "baja" for x in w["vis"]))
        subject, text, html = notify.weekly_mail(data, "https://lumo.test/panel#alertas", "porque sí")
        self.assertIn("oportunidad de mejora", text)
        self.assertIn("Visibilidad y ROAS objetivo", text)
        self.assertIn("bajar", text.lower())

    def test_resumen_sin_hallazgos_dice_que_estan_en_objetivo(self):
        data = dataset()
        for c in data["camps"]:
            for d in c["daily"]:
                d["spend"], d["sales"], d["clicks"], d["prints"], d["units"] = 0, 0, 0, 0, 0
        _, text, _ = notify.weekly_mail(data, "https://lumo.test/panel", "porque sí")
        self.assertIn("están en su ROAS objetivo", text)


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

    def test_la_tarea_diaria_no_manda_recomendaciones_aunque_hubiera_avisos_activados(self):
        with Session(self.engine) as s:
            s.get(PanelState, 5).data = json.dumps({"sw": {"m1": True, "m2": True, "m3": True}})   # preferencias viejas
            s.commit()
        r = self.cron()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.mail.assert_not_called()

    def login(self):
        with self.client.session_transaction() as sess:
            sess["uid"] = 5

    def test_la_recomendacion_se_manda_solo_a_la_propia_cuenta_y_solo_al_pedirla(self):
        self.mail.assert_not_called()
        self.login()
        r = self.client.post("/api/recomendacion/mail", json={"title": "Mesas y sillas tiene oportunidad", "text": "Su ROAS es $3,2 <b>x</b>", "action": "Mejorá las publicaciones", "to": "otro@test.com"})
        self.assertEqual(r.status_code, 200)
        args = self.mail.call_args[0]
        self.assertEqual(args[1], "ana@test.com")                       # nunca otra dirección
        self.assertIn("Mesas y sillas tiene oportunidad", args[2])
        self.assertIn("&lt;b&gt;", args[4])                              # el texto del navegador va escapado
        self.assertNotIn("<b>x</b>", args[4])
        self.assertIn("Mejorá las publicaciones", args[3])

    def test_la_recomendacion_se_valida_y_tiene_tope(self):
        self.login()
        self.assertEqual(self.client.post("/api/recomendacion/mail", json={"title": "", "text": "x"}).status_code, 400)
        self.assertEqual(self.client.post("/api/recomendacion/mail", json={"title": "a", "text": "x" * 1600}).status_code, 400)
        self.assertEqual(self.client.post("/api/recomendacion/mail", json={"title": "a\nBcc: x@y.com", "text": "t"}).status_code, 200)
        self.assertNotIn("\n", self.mail.call_args[0][2])               # sin saltos de línea en el asunto
        self.assertEqual(self.client.post("/api/recomendacion/mail", json={"title": "a Bcc: x@y.com", "text": "t"}).status_code, 429)   # la misma, una vez por minuto

    def test_tope_de_mails_por_hora(self):
        self.login()
        codes = [self.client.post("/api/recomendacion/mail", json={"title": "rec %d" % i, "text": "t"}).status_code for i in range(12)]
        self.assertEqual(codes.count(200), 10)
        self.assertEqual(codes[-1], 429)

    def test_la_recomendacion_pide_sesion_email_y_envio_habilitado(self):
        self.assertEqual(self.client.post("/api/recomendacion/mail", json={"title": "a", "text": "t"}).status_code, 401)
        self.login()
        with Session(self.engine) as s:
            s.get(Account, 5).email = None
            s.commit()
        self.assertEqual(self.client.post("/api/recomendacion/mail", json={"title": "a", "text": "t"}).status_code, 400)
        app = create_app(dict(CFG, SMTP_PASSWORD=""))
        self.assertEqual(app.test_client().post("/api/recomendacion/mail", json={"title": "a", "text": "t"}).status_code, 401)

    def test_si_el_proveedor_falla_no_se_marca_como_enviada(self):
        self.login()
        self.mail.side_effect = notify.MailError("Brevo respondió 401")
        self.assertEqual(self.client.post("/api/recomendacion/mail", json={"title": "a", "text": "t"}).status_code, 502)
        self.mail.side_effect = None
        self.assertEqual(self.client.post("/api/recomendacion/mail", json={"title": "a", "text": "t"}).status_code, 200)

    def test_el_resumen_semanal_se_manda_con_su_excel_solo_al_pedirlo(self):
        self.login()
        self.assertEqual(self.client.post("/api/resumen/mail").status_code, 409)        # todavía no hay datos
        with Session(self.engine) as s:
            s.add(Snapshot(user_id=5, advertiser_id=fake_ml.ADVERTISER["advertiser_id"], data=json.dumps(dataset())))
            s.commit()
        r = self.client.post("/api/resumen/mail")
        self.assertEqual(r.status_code, 200)
        args, kwargs = self.mail.call_args
        self.assertEqual(args[1], "ana@test.com")
        self.assertTrue(kwargs["attachments"][0][0].endswith(".xlsx"))
        self.assertEqual(self.client.post("/api/resumen/mail").status_code, 429)

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

    def test_datos_informan_el_email_y_si_el_envio_esta_habilitado(self):
        with self.client.session_transaction() as sess:
            sess["uid"] = 5
        d = self.client.get("/api/datos").get_json()
        self.assertEqual(d["email"], "ana@test.com")
        self.assertTrue(d["mailOn"])


if __name__ == "__main__":
    unittest.main()
