"""Controles de seguridad y privacidad: encabezados, tope de pedidos, origen de los POST, sesiones, auditoría,
rotación de claves, borrado, descarga de datos y plazos de conservación."""
import json
import unittest
from datetime import timedelta
from unittest import mock

from sqlalchemy import select
from sqlalchemy.orm import Session

from lumo import create_app, crypto, privacy, security
from lumo.models import Access, Account, AuditLog, CampaignDay, Invite, Notice, PanelState, Snapshot, utcnow
from lumo.tokens import save_tokens, valid_access_token
from test_access import ADS, CFG, KEY, Base, tok

LARGA = "token-del-cron-largo-y-aleatorio-0123456789"


class Encabezados(Base):
    def test_toda_respuesta_lleva_los_encabezados_de_seguridad(self):
        r = self.client.get("/")
        h = r.headers
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        self.assertIn("object-src 'none'", h["Content-Security-Policy"])
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        self.assertEqual(h["X-Frame-Options"], "DENY")
        # same-origin y no no-referrer: con no-referrer los navegadores mandan "Origin: null" en los formularios
        # y el control de origen rechazaba todos (por ejemplo, crear una invitación en /admin).
        self.assertEqual(h["Referrer-Policy"], "same-origin")
        self.assertIn("max-age=", h["Strict-Transport-Security"])  # REDIRECT_URI es https

    def test_sin_https_no_se_manda_hsts(self):
        r = create_app(dict(CFG, REDIRECT_URI="")).test_client().get("/")
        self.assertNotIn("Strict-Transport-Security", r.headers)

    def test_lo_privado_no_se_guarda_en_cache_y_lo_publico_si_puede(self):
        c = self.app.test_client()
        self.connect(c, 1)
        for path in ("/admin", "/panel", "/api/datos"):
            self.assertEqual(c.get(path).headers["Cache-Control"], "no-store", path)
        self.assertNotIn("no-store", self.client.get("/privacidad").headers.get("Cache-Control", ""))

    def test_la_cookie_de_sesion_es_segura(self):
        r = self.client.get("/connect")
        cookie = r.headers["Set-Cookie"]
        self.assertTrue(cookie.startswith("__Host-lumo="))
        for flag in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/"):
            self.assertIn(flag, cookie)
        self.assertNotIn("Domain", cookie)

    def test_security_txt(self):
        r = self.client.get("/.well-known/security.txt")
        self.assertIn("Contact: mailto:hola@lumo.test", r.get_data(as_text=True))
        self.assertIn("Expires:", r.get_data(as_text=True))


class Arranque(unittest.TestCase):
    def test_en_produccion_sin_secret_key_no_arranca(self):
        with self.assertRaises(RuntimeError):
            create_app(dict(CFG, SECRET_KEY=""))

    def test_en_local_sin_secret_key_si_arranca(self):
        create_app(dict(CFG, SECRET_KEY="", REDIRECT_URI="http://localhost/callback"))

    def test_la_base_de_postgres_pide_conexion_cifrada(self):
        from lumo import make_engine
        with mock.patch("lumo.create_engine") as ce:
            make_engine("postgres://u:p@host/db")
        self.assertEqual(ce.call_args.kwargs["connect_args"], {"sslmode": "require"})
        self.assertTrue(ce.call_args.args[0].startswith("postgresql+psycopg2://"))


class Pedidos(Base):
    def test_un_post_de_otro_origen_se_rechaza(self):
        c = self.app.test_client()
        self.connect(c, 1)
        r = c.post("/api/estado", json={"done": {}}, headers={"Origin": "https://sitio-malo.test"})
        self.assertEqual(r.status_code, 403)
        ok = c.post("/api/estado", json={"done": {}}, headers={"Origin": "http://localhost"})
        self.assertEqual(ok.status_code, 200)

    def test_sec_fetch_site_cross_site_se_rechaza(self):
        r = self.client.post("/api/email", json={}, headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(r.status_code, 403)

    def test_cuerpo_demasiado_grande(self):
        c = self.app.test_client()
        self.connect(c, 1)
        r = c.post("/api/estado", data="x" * 1_100_000, content_type="application/json")
        self.assertEqual(r.status_code, 413)

    def test_tope_de_intentos_de_conexion(self):
        codes = [self.client.get("/connect").status_code for _ in range(25)]
        self.assertEqual(codes[:20], [302] * 20)
        self.assertEqual(codes[20:], [429] * 5)

    def test_tope_responde_json_en_la_api(self):
        c = self.app.test_client()
        self.connect(c, 1)
        r = None
        for _ in range(11):
            r = c.post("/api/email", json={"email": "no"})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.get_json(), {"error": "espera"})
        self.assertIn("Retry-After", r.headers)

    def test_limitador_olvida_con_el_tiempo(self):
        now = [0.0]
        rl = security.RateLimiter(clock=lambda: now[0])
        self.assertTrue(all(rl.allow("k", 3, 10) for _ in range(3)))
        self.assertFalse(rl.allow("k", 3, 10))
        now[0] = 11
        self.assertTrue(rl.allow("k", 3, 10))

    def test_comparacion_segura_acepta_cualquier_texto(self):
        self.assertTrue(security.safe_eq("clave", "clave"))
        self.assertFalse(security.safe_eq("clave", "ñandú"))
        self.assertFalse(security.safe_eq(None, "x"))


class Cron(Base):
    cfg = dict(CFG, CRON_TOKEN=LARGA, SMTP_PASSWORD="x")

    def test_clave_con_caracteres_raros_es_403_y_no_error(self):
        r = self.client.post("/cron/avisos", headers={"X-Cron-Token": "ñandú"})
        self.assertEqual(r.status_code, 403)

    def test_corrida_aplica_los_plazos_de_conservacion(self):
        with Session(self.engine) as s:
            s.add(Notice(user_id=1, kind="m2", ref="a", sent_at=utcnow() - timedelta(days=500)))
            s.commit()
        r = self.client.post("/cron/avisos", headers={"X-Cron-Token": LARGA})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["purga"]["avisos"], 1)
        with Session(self.engine) as s:
            self.assertEqual(s.execute(select(Notice)).scalars().all(), [])
            self.assertEqual([e.event for e in s.execute(select(AuditLog)).scalars()], ["cron_run"])



class Sesiones(Base):
    def test_la_sesion_de_administracion_vence(self):
        c = self.admin_client()
        self.assertEqual(c.get("/admin").status_code, 200)
        with c.session_transaction() as sess:
            sess["at"] -= 13 * 3600
        r = c.get("/admin")
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "/connect"))

    def test_una_sesion_sin_fecha_de_ingreso_no_administra(self):
        c = self.admin_client()
        with c.session_transaction() as sess:
            del sess["at"]
        self.assertEqual(c.get("/admin").status_code, 302)

    def test_el_panel_sigue_andando_con_la_sesion_de_administracion_vencida(self):
        c = self.admin_client()
        with c.session_transaction() as sess:
            sess["at"] -= 13 * 3600
        self.assertEqual(c.get("/panel").status_code, 200)

    def test_csrf_con_caracteres_raros_no_rompe(self):
        c = self.admin_client()
        c.get("/admin")
        r = c.post("/admin/invitar", data={"csrf": "ñandú", "label": "x"})
        self.assertEqual(r.status_code, 400)

    def test_id_enorme_no_rompe_el_alta(self):
        c = self.admin_client()
        r = c.post("/admin/acceso/agregar", data={"csrf": self.csrf(c), "user_id": "9" * 30})
        self.assertEqual(r.status_code, 302)
        with Session(self.engine) as s:
            self.assertEqual(s.execute(select(Access)).scalars().all(), [])


class Auditoria(Base):
    def events(self):
        with Session(self.engine) as s:
            return [(e.event, e.actor, e.target) for e in s.execute(select(AuditLog).order_by(AuditLog.id)).scalars()]

    def test_ingresos_y_cambios_de_administracion_quedan_registrados(self):
        c = self.admin_client()
        csrf = self.csrf(c)
        c.post("/admin/invitar", data={"csrf": csrf, "label": "Cliente"})
        c.post("/admin/acceso/agregar", data={"csrf": csrf, "user_id": "77", "note": "x"})
        c.post("/admin/acceso/quitar", data={"csrf": csrf, "user_id": "77"})
        ev = self.events()
        self.assertEqual([e[0] for e in ev], ["login_ok", "invite_create", "access_grant", "access_remove"])
        self.assertEqual(ev[2], ("access_grant", 1, "77"))

    def test_acceso_denegado_queda_registrado(self):
        self.connect(self.client, 50)
        self.assertEqual(self.events(), [("login_denied", None, "50")])

    def test_el_registro_no_guarda_emails_ni_tokens(self):
        c = self.admin_client()
        c.post("/api/email", json={"email": "persona@ejemplo.com"})
        with Session(self.engine) as s:
            dump = json.dumps([(e.event, e.actor, e.target, e.detail) for e in s.execute(select(AuditLog)).scalars()])
        self.assertNotIn("persona@ejemplo.com", dump)
        self.assertNotIn("AT-1", dump)
        self.assertIn("email_set", dump)

    def test_la_administracion_muestra_la_actividad(self):
        c = self.admin_client()
        self.assertIn("login_ok", c.get("/admin").get_data(as_text=True))


class Cifrado(unittest.TestCase):
    def test_rotacion_de_claves(self):
        viejo = crypto.encrypt("clave-vieja-larga-y-aleatoria-0123456789", "secreto")
        nuevo = "clave-nueva-larga-y-aleatoria-0123456789"
        with self.assertRaises(crypto.CryptoError):
            crypto.decrypt(nuevo, viejo)
        self.assertEqual(crypto.decrypt(nuevo, viejo, ("clave-vieja-larga-y-aleatoria-0123456789",)), "secreto")
        rot = crypto.rewrap(nuevo, viejo, ("clave-vieja-larga-y-aleatoria-0123456789",))
        self.assertEqual(crypto.decrypt(nuevo, rot), "secreto")  # ya no hace falta la anterior

    def test_rotate_keys_vuelve_a_cifrar_las_cuentas(self):
        import rotate_keys
        old = "clave-vieja-larga-y-aleatoria-0123456789"
        app = create_app(dict(CFG, ENCRYPTION_KEY=old))
        engine = app.extensions["lumo_engine"]
        with Session(engine) as s:
            save_tokens(s, app.extensions["lumo_cfg"], 5, tok(5))
            s.commit()
        app.extensions["lumo_cfg"].update(ENCRYPTION_KEY=KEY, ENCRYPTION_KEY_PREVIOUS=old)
        self.assertEqual(rotate_keys.rotate(app), (1, 0))
        app.extensions["lumo_cfg"].update(ENCRYPTION_KEY_PREVIOUS="")
        with Session(engine) as s:
            acc = s.get(Account, 5)
            acc.expires_at = utcnow() + timedelta(hours=1)
            self.assertEqual(valid_access_token(s, app.extensions["lumo_cfg"], 5), "AT-5")

    def test_los_tokens_no_se_guardan_en_claro(self):
        app = create_app(CFG)
        with Session(app.extensions["lumo_engine"]) as s:
            acc = save_tokens(s, CFG, 3, tok(3))
            self.assertNotIn("AT-3", acc.access_token)
            self.assertNotIn("RT", acc.refresh_token)


class Privacidad(Base):
    def setUp(self):
        super().setUp()
        self.c = self.app.test_client()
        self.connect(self.c, 1)
        with Session(self.engine) as s:
            s.add_all([PanelState(user_id=1, data=json.dumps({"done": {"a": 1}})), Snapshot(user_id=1, advertiser_id=9, data="{}"),
                       CampaignDay(user_id=1, campaign_id=5, day="2026-10-01", spend=10), Notice(user_id=1, kind="m1", ref="2026-W40"),
                       CampaignDay(user_id=2, campaign_id=5, day="2026-10-01", spend=99)])
            s.get(Account, 1).email = "yo@ejemplo.com"
            s.commit()

    def test_la_pagina_es_publica_y_muestra_las_acciones_solo_con_sesion(self):
        anon = self.client.get("/privacidad").get_data(as_text=True)
        self.assertIn("Qué guardamos", anon)
        self.assertNotIn("Borrar mi cuenta", anon)
        self.assertIn("Borrar mi cuenta", self.c.get("/privacidad").get_data(as_text=True))

    def test_descarga_de_los_propios_datos_sin_tokens(self):
        r = self.c.get("/api/cuenta/exportar")
        self.assertIn("attachment", r.headers["Content-Disposition"])
        d = r.get_json()
        self.assertEqual(d["cuenta"]["email"], "yo@ejemplo.com")
        self.assertEqual(d["panel"], {"done": {"a": 1}})
        self.assertEqual([x["gasto"] for x in d["historial_de_campanas"]], [10])  # no incluye los de otra cuenta
        self.assertNotIn("AT-1", r.get_data(as_text=True))
        self.assertNotIn("access_token", r.get_data(as_text=True))

    def test_descarga_exige_sesion(self):
        self.assertEqual(self.client.get("/api/cuenta/exportar").status_code, 401)

    def test_borrar_la_cuenta_elimina_todo_lo_de_esa_cuenta_y_nada_mas(self):
        csrf = self.csrf(self.c)
        r = self.c.post("/cuenta/eliminar", data={"csrf": csrf})
        self.assertEqual(r.status_code, 200)
        with Session(self.engine) as s:
            for model in (Access, Account, Snapshot, PanelState, Notice):
                self.assertEqual(s.execute(select(model).where(model.user_id == 1)).scalars().all(), [], model.__name__)
            self.assertEqual([d.user_id for d in s.execute(select(CampaignDay)).scalars()], [2])
            self.assertIn("account_erase", [e.event for e in s.execute(select(AuditLog)).scalars()])
        self.assertEqual(self.c.get("/panel").status_code, 302)  # la sesión ya no sirve

    def test_borrar_exige_csrf(self):
        self.assertEqual(self.c.post("/cuenta/eliminar", data={"csrf": "otro"}).status_code, 400)
        with Session(self.engine) as s:
            self.assertIsNotNone(s.get(Account, 1))

    def test_quitar_acceso_desde_administracion_tambien_borra_historial_y_avisos(self):
        admin = self.admin_client()
        with Session(self.engine) as s:
            s.add(Access(user_id=1))
            s.commit()
        admin.post("/admin/acceso/quitar", data={"csrf": self.csrf(admin), "user_id": "1"})
        with Session(self.engine) as s:
            self.assertEqual(s.execute(select(CampaignDay).where(CampaignDay.user_id == 1)).scalars().all(), [])
            self.assertEqual(s.execute(select(Notice).where(Notice.user_id == 1)).scalars().all(), [])

    def test_la_invitacion_usada_deja_de_apuntar_a_la_cuenta_borrada(self):
        with Session(self.engine) as s:
            s.add(Invite(token="t" * 20, expires_at=utcnow() + timedelta(days=1), used_by=1, used_at=utcnow()))
            s.commit()
            privacy.erase_user(s, 1)
            s.commit()
            self.assertEqual(s.get(Invite, "t" * 20).used_by, 0)

    def test_toda_tabla_con_user_id_entra_en_el_borrado(self):
        """Si se agrega una tabla con datos de una cuenta y no se suma a privacy.PER_USER, el borrado quedaría incompleto."""
        from lumo.models import Base as Models
        con_usuario = {m.class_ for m in Models.registry.mappers if "user_id" in m.columns}
        self.assertEqual(con_usuario, set(privacy.PER_USER))

    def test_plazos_de_conservacion(self):
        now = utcnow()
        with Session(self.engine) as s:
            s.add_all([AuditLog(at=now - timedelta(days=401), event="viejo"), AuditLog(at=now - timedelta(days=10), event="nuevo"),
                       Invite(token="v" * 20, expires_at=now - timedelta(days=100)), Invite(token="n" * 20, expires_at=now + timedelta(days=3)),
                       CampaignDay(user_id=1, campaign_id=6, day=(now - timedelta(days=800)).strftime("%Y-%m-%d"))])
            s.commit()
            out = privacy.purge(s, now)
            self.assertEqual((out["auditoria"], out["invitaciones"], out["historial"]), (1, 1, 1))
            self.assertEqual([e.event for e in s.execute(select(AuditLog)).scalars()], ["login_ok", "nuevo"])
            self.assertIsNotNone(s.get(Invite, "n" * 20))


if __name__ == "__main__":
    unittest.main()
