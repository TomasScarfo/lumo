import os
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

from sqlalchemy.orm import Session

from lumo import access, create_app
from lumo.models import Access, Account, Invite, PanelState, Snapshot, utcnow
from lumo.tokens import save_tokens

KEY = "clave-de-prueba-larga-y-aleatoria"
CFG = {"ML_CLIENT_ID": "123", "ML_CLIENT_SECRET": "secreto-de-prueba", "REDIRECT_URI": "https://lumo.test/callback",
       "ENCRYPTION_KEY": KEY, "SECRET_KEY": "otra-clave-de-sesion", "DATABASE_URL": "sqlite://", "ADMIN_USER_IDS": "1, 2;x",
       "CONTACT_EMAIL": "hola@lumo.test", "CONTACT_WHATSAPP": "+54 9 11 0000-0000", "CONTACT_LINKEDIN": "https://www.linkedin.com/in/prueba/"}
ADS = [{"advertiser_id": 9, "site_id": "MLA", "advertiser_name": "Negocio"}]


def tok(uid, refresh="RT"):
    return {"access_token": "AT-%s" % uid, "refresh_token": refresh, "expires_in": 21600, "scope": "read", "user_id": uid}


class Base(unittest.TestCase):
    cfg = CFG

    def setUp(self):
        self.app = create_app(self.cfg)
        self.engine = self.app.extensions["lumo_engine"]
        self.client = self.app.test_client()

    def connect(self, client, uid, advertisers=ADS):
        """Recorre /connect y /callback como si Mercado Libre devolviera una cuenta con ese id."""
        loc = client.get("/connect").headers["Location"]
        state = loc.split("state=")[1].split("&")[0]
        with mock.patch("lumo.ml.exchange_code", return_value=tok(uid)), mock.patch("lumo.ml.advertisers", return_value=advertisers):
            return client.get("/callback?code=abc&state=" + state)

    def invite(self, label="Cliente", days=14):
        with Session(self.engine) as s:
            inv = access.create_invite(s, label, days)
            s.commit()
            return inv.token

    def admin_client(self):
        c = self.app.test_client()
        self.connect(c, 1)
        return c

    def csrf(self, client):
        client.get("/admin")
        with client.session_transaction() as sess:
            return sess["csrf"]


class Ayudantes(unittest.TestCase):
    def test_ids_de_administradores(self):
        self.assertEqual(access.admin_ids(CFG), {1, 2})
        self.assertEqual(access.admin_ids({}), set())
        self.assertTrue(access.is_admin(CFG, "1"))
        self.assertFalse(access.is_admin(CFG, None))


class Portada(Base):
    def test_es_publica_y_ofrece_ingresar(self):
        r = self.client.get("/")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Ingresar con Mercado Libre", html)
        self.assertIn("Ejemplo con datos ficticios", html)
        self.assertIn("no está afiliada", html)

    def test_seccion_de_contacto_con_los_tres_canales(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="contacto"', html)
        self.assertIn("mailto:hola@lumo.test", html)
        self.assertIn("https://wa.me/5491100000000?text=", html)
        self.assertIn("+54 9 11 0000 0000", html)
        self.assertIn("https://www.linkedin.com/in/prueba/", html)

    def test_sin_datos_de_contacto_no_hay_seccion(self):
        app = create_app(dict(CFG, CONTACT_EMAIL="", CONTACT_WHATSAPP="", CONTACT_LINKEDIN=""))
        html = app.test_client().get("/").get_data(as_text=True)
        for texto in ("mailto:", "wa.me", 'id="contacto"', "linkedin.com"):
            self.assertNotIn(texto, html)

    def test_solo_acepta_linkedin_https(self):
        app = create_app(dict(CFG, CONTACT_LINKEDIN="javascript:alert(1)"))
        self.assertNotIn("javascript:", app.test_client().get("/").get_data(as_text=True))

    def test_contacto_por_defecto(self):
        from lumo import load_config
        quitar = {k: v for k, v in os.environ.items() if not k.startswith("CONTACT_")}
        with mock.patch.dict(os.environ, quitar, clear=True):
            cfg = load_config()
        self.assertEqual(cfg["CONTACT_EMAIL"], "tomas.scarfo@gmail.com")
        self.assertEqual(cfg["CONTACT_WHATSAPP"], "5491145597516")
        self.assertEqual(cfg["CONTACT_LINKEDIN"], "https://www.linkedin.com/in/tomas-scarfo/")

    def test_pagina_sin_acceso_ofrece_whatsapp_y_email(self):
        html = Ingreso.denied_html(self)
        self.assertIn("wa.me/5491100000000", html)
        self.assertIn("mailto:hola@lumo.test", html)

    def test_estaticos(self):
        for path in ("/static/site.css", "/static/logo.svg", "/static/logo.png"):
            self.assertEqual(self.client.get(path).status_code, 200, path)


class Invitaciones(Base):
    def test_enlace_valido_muestra_la_invitacion(self):
        token = self.invite("Casa Nogal")
        r = self.client.get("/invitacion/" + token)
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Te invitaron a Lumo, Casa Nogal", html)
        self.assertIn("noindex", html)

    def test_enlace_invalido(self):
        r = self.client.get("/invitacion/inventado")
        self.assertEqual(r.status_code, 404)
        self.assertIn("no es válida", r.get_data(as_text=True))

    def test_vencida_o_cancelada_no_sirven(self):
        vieja = self.invite(days=-1)
        cancelada = self.invite()
        with Session(self.engine) as s:
            s.get(Invite, cancelada).revoked = True
            s.commit()
        self.assertEqual(self.client.get("/invitacion/" + vieja).status_code, 404)
        self.assertEqual(self.client.get("/invitacion/" + cancelada).status_code, 404)


class Ingreso(Base):
    def denied_html(self):
        return Base.connect(self, self.client, 999).get_data(as_text=True)

    def test_la_pantalla_principal_ordena_metricas_graficos_y_campanas(self):
        fuente = open(os.path.join(os.path.dirname(__file__), "..", "lumo", "panel.html"), encoding="utf-8").read()
        self.assertIn("function principalHTML() { return heroHTML() + kpiHTML() + chartsHTML() + campsHTML(); }", fuente)

    def test_sin_invitacion_no_entra_ni_se_guardan_sus_datos(self):
        r = self.connect(self.client, 999)
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 403)
        self.assertIn("Todavía no tenés acceso", html)
        self.assertIn("999", html)
        with Session(self.engine) as s:
            self.assertIsNone(s.get(Account, 999))
            self.assertIsNone(s.get(Access, 999))
        with self.client.session_transaction() as sess:
            self.assertNotIn("uid", sess)
        self.assertEqual(self.client.get("/panel").status_code, 302)
        self.assertEqual(self.client.get("/api/datos").status_code, 401)

    def test_con_invitacion_entra_y_queda_con_acceso(self):
        token = self.invite("Casa Nogal")
        self.client.get("/invitacion/" + token)
        r = self.connect(self.client, 500)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/panel"))
        with Session(self.engine) as s:
            self.assertEqual(s.get(Access, 500).note, "Casa Nogal")
            self.assertEqual(s.get(Invite, token).used_by, 500)
            self.assertIsNotNone(s.get(Account, 500))
        # la próxima vez entra sin invitación
        otro = self.app.test_client()
        self.assertEqual(self.connect(otro, 500).status_code, 302)

    def test_la_invitacion_se_usa_una_sola_vez(self):
        token = self.invite()
        a, b = self.app.test_client(), self.app.test_client()
        a.get("/invitacion/" + token)
        b.get("/invitacion/" + token)
        self.assertEqual(self.connect(a, 501).status_code, 302)
        self.assertEqual(self.connect(b, 502).status_code, 403)
        with Session(self.engine) as s:
            self.assertIsNone(s.get(Access, 502))

    def test_invitacion_cancelada_despues_de_abrirla_no_sirve(self):
        token = self.invite()
        self.client.get("/invitacion/" + token)
        with Session(self.engine) as s:
            s.get(Invite, token).revoked = True
            s.commit()
        self.assertEqual(self.connect(self.client, 503).status_code, 403)

    def test_administrador_entra_sin_invitacion(self):
        r = self.connect(self.client, 1)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/panel"))

    def test_administrador_sin_publicidad_va_a_administracion(self):
        r = self.connect(self.client, 1, advertisers=[])
        self.assertTrue(r.headers["Location"].endswith("/admin"))
        self.assertTrue(self.client.get("/").headers["Location"].endswith("/admin"))

    def test_quitar_el_acceso_corta_la_sesion(self):
        token = self.invite()
        self.client.get("/invitacion/" + token)
        self.connect(self.client, 504)
        self.assertEqual(self.client.get("/panel").status_code, 200)
        with Session(self.engine) as s:
            s.delete(s.get(Access, 504))
            s.commit()
        self.assertEqual(self.client.get("/panel").status_code, 302)
        self.assertEqual(self.client.get("/api/datos").status_code, 401)


class Administracion(Base):
    def test_solo_los_administradores_la_ven(self):
        self.assertEqual(self.client.get("/admin").status_code, 404)
        token = self.invite()
        miembro = self.app.test_client()
        miembro.get("/invitacion/" + token)
        self.connect(miembro, 600)
        self.assertEqual(miembro.get("/admin").status_code, 404)
        self.assertEqual(miembro.post("/admin/invitar", data={"label": "x"}).status_code, 404)
        self.assertEqual(self.admin_client().get("/admin").status_code, 200)

    def test_crear_invitacion_y_ver_el_enlace(self):
        c = self.admin_client()
        csrf = self.csrf(c)
        self.assertEqual(c.post("/admin/invitar", data={"label": "Cliente Uno", "csrf": csrf}).status_code, 302)
        html = c.get("/admin").get_data(as_text=True)
        self.assertIn("Cliente Uno", html)
        self.assertIn("/invitacion/", html)
        with Session(self.engine) as s:
            self.assertEqual(s.query(Invite).count(), 1)

    def test_sin_token_csrf_se_rechaza(self):
        c = self.admin_client()
        self.csrf(c)
        self.assertEqual(c.post("/admin/invitar", data={"label": "x"}).status_code, 400)
        self.assertEqual(c.post("/admin/invitar", data={"label": "x", "csrf": "otro"}).status_code, 400)
        with Session(self.engine) as s:
            self.assertEqual(s.query(Invite).count(), 0)

    def test_cancelar_invitacion(self):
        token = self.invite("Para cancelar")
        c = self.admin_client()
        c.post("/admin/invitacion/revocar", data={"token": token, "csrf": self.csrf(c)})
        self.assertEqual(self.client.get("/invitacion/" + token).status_code, 404)

    def test_habilitar_por_id_y_quitar_borra_todo(self):
        c = self.admin_client()
        csrf = self.csrf(c)
        c.post("/admin/acceso/agregar", data={"user_id": "700", "note": "Por ID", "csrf": csrf})
        self.assertIn("Por ID", c.get("/admin").get_data(as_text=True))
        # esa persona entra sin invitación
        self.assertEqual(self.connect(self.app.test_client(), 700).status_code, 302)
        with Session(self.engine) as s:
            s.add_all([Snapshot(user_id=700, advertiser_id=9, data="{}"), PanelState(user_id=700, data="{}")])
            s.commit()
        c.post("/admin/acceso/quitar", data={"user_id": "700", "csrf": csrf})
        with Session(self.engine) as s:
            for model in (Access, Account, Snapshot, PanelState):
                self.assertIsNone(s.get(model, 700), model.__name__)
        self.assertEqual(self.connect(self.app.test_client(), 700).status_code, 403)

    def test_id_no_numerico_se_ignora(self):
        c = self.admin_client()
        c.post("/admin/acceso/agregar", data={"user_id": "abc", "csrf": self.csrf(c)})
        with Session(self.engine) as s:
            self.assertEqual(s.query(Access).count(), 0)


class Existentes(unittest.TestCase):
    def test_las_cuentas_anteriores_siguen_entrando(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            cfg = dict(CFG, DATABASE_URL="sqlite:///" + path)
            app1 = create_app(cfg)
            with Session(app1.extensions["lumo_engine"]) as s:
                save_tokens(s, cfg, 42, tok(42))
                s.query(Access).delete()
                s.commit()
                s.execute(__import__("sqlalchemy").text("DROP TABLE access"))  # como estaba la base antes del control de acceso
                s.commit()
            app2 = create_app(cfg)
            with Session(app2.extensions["lumo_engine"]) as s:
                self.assertIsNotNone(s.get(Access, 42))
            app3 = create_app(cfg)  # un reinicio posterior no vuelve a habilitar a nadie
            with Session(app3.extensions["lumo_engine"]) as s:
                s.delete(s.get(Access, 42))
                s.commit()
            app4 = create_app(cfg)
            with Session(app4.extensions["lumo_engine"]) as s:
                self.assertIsNone(s.get(Access, 42))
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
