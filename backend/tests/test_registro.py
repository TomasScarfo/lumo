import re
import unittest
from datetime import timedelta
from unittest import mock

from sqlalchemy import select
from sqlalchemy.orm import Session

from lumo import privacy, usuarios
from lumo.models import Account, LoginToken, User, utcnow
from test_access import connect_as
from test_billing import BILLING, Base

EMAIL = "ana@ejemplo.com"


def link_de(mails):
    m = re.search(r"https://lumo\.test/acceso/([\w-]+)", mails[-1][2])
    return m.group(0), m.group(1)


class Registro(Base):
    def pedir(self, client=None, email=EMAIL, **extra):
        return (client or self.client).post("/entrar", data=dict({"email": email}, **extra))

    def entrar(self, client=None, email=EMAIL, **extra):
        """Pide el enlace y lo abre, como la persona desde su mail."""
        c = client or self.client
        self.pedir(c, email, **extra)
        link, token = link_de(self.mails)
        return c.post("/acceso/" + token)

    def usuario(self, email=EMAIL):
        with Session(self.engine) as s:
            return s.execute(select(User).where(User.email == email)).scalar_one_or_none()

    # ---------- el pedido del enlace ----------
    def test_la_pantalla_pide_el_email_y_ofrece_ingresar_con_mercado_libre(self):
        r = self.client.get("/entrar")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('name="email"', html)
        self.assertIn("Ingresá a Lumo", html)  # "Ingresar": ya tiene cuenta, primero Mercado Libre y también el email
        self.assertLess(html.index('href="/connect"'), html.index('name="email"'))
        self.assertIn("Ingresar con Mercado Libre", html)
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        # desde un plan de la portada es un registro: primero el email
        html = self.client.get("/entrar?plan=monthly").get_data(as_text=True)
        self.assertIn("Creá tu cuenta", html)
        self.assertIn("No hace falta contraseña", html)

    def test_pedir_el_enlace_manda_un_mail_con_el_enlace_y_guarda_solo_su_hash(self):
        r = self.pedir()
        self.assertEqual(r.status_code, 200)
        self.assertIn("Revisá tu correo", r.get_data(as_text=True))
        self.assertEqual([(m[0], m[1]) for m in self.mails], [(EMAIL, "Tu enlace para entrar a Lumo")])
        _, token = link_de(self.mails)
        with Session(self.engine) as s:
            filas = s.execute(select(LoginToken)).scalars().all()
        self.assertEqual(len(filas), 1)
        self.assertNotIn(token, (filas[0].token_hash, filas[0].email))
        self.assertEqual(len(filas[0].token_hash), 64)
        self.assertEqual(self.usuario(), None)  # todavía no es usuaria: falta abrir el enlace

    def test_el_email_se_normaliza_y_uno_inventado_se_rechaza(self):
        self.pedir(email="  Ana@Ejemplo.COM ")
        self.assertEqual(self.mails[-1][0], EMAIL)
        for malo in ("", "sin-arroba", "a@b", "a b@c.com", "a@@c.com", "x" * 300 + "@c.com"):
            r = self.pedir(email=malo)
            self.assertEqual(r.status_code, 400, malo)
        self.assertEqual(len(self.mails), 1)

    def test_no_se_manda_mas_de_3_enlaces_al_mismo_email_en_15_minutos_y_no_se_nota(self):
        for _ in range(5):
            r = self.pedir()
            self.assertEqual(r.status_code, 200)
            self.assertIn("Revisá tu correo", r.get_data(as_text=True))
        self.assertEqual(len(self.mails), 3)

    def test_si_el_proveedor_de_correo_falla_se_avisa_sin_detalles(self):
        with mock.patch("lumo.notify.send_mail", side_effect=notify_error()):
            r = self.pedir()
        self.assertEqual(r.status_code, 502)
        html = r.get_data(as_text=True)
        self.assertIn("No pudimos mandar el enlace", html)
        self.assertNotIn("secreto", html)

    def test_sin_envio_de_mails_configurado_ofrece_mercado_libre(self):
        app = self.app
        with mock.patch("lumo.notify.enabled", return_value=False):
            r = app.test_client().post("/entrar", data={"email": EMAIL})
        self.assertEqual(r.status_code, 503)
        self.assertIn("/connect", r.get_data(as_text=True))
        self.assertEqual(self.mails, [])

    # ---------- abrir el enlace ----------
    def test_abrir_el_enlace_solo_confirma_y_no_lo_gasta(self):
        self.pedir()
        _, token = link_de(self.mails)
        r = self.client.get("/acceso/" + token)
        self.assertEqual(r.status_code, 200)
        self.assertIn(EMAIL, r.get_data(as_text=True))
        self.assertEqual(r.headers["Referrer-Policy"], "same-origin")  # no se lo pasa a otros sitios y deja mandar el Origin del botón
        self.assertIn('content="same-origin"', r.get_data(as_text=True))
        self.assertEqual(self.client.get("/acceso/" + token).status_code, 200)  # un programa que lo "visita" no lo gasta
        self.assertEqual(self.usuario(), None)

    def test_el_navegador_manda_su_origen_y_el_pedido_se_acepta(self):
        """El botón de la confirmación y el del email mandan el Origin del navegador: con la política equivocada llegaba "null"."""
        origen = {"Origin": "http://localhost"}  # el cliente de pruebas se llama "localhost"
        self.assertEqual(self.client.post("/entrar", data={"email": EMAIL}, headers=origen).status_code, 200)
        _, token = link_de(self.mails)
        self.assertEqual(self.client.post("/acceso/" + token, headers=origen).status_code, 302)
        self.assertEqual(self.app.test_client().post("/entrar", data={"email": EMAIL}, headers={"Origin": "null"}).status_code, 403)

    def test_confirmar_crea_el_usuario_y_lleva_a_elegir_plan(self):
        r = self.entrar()
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/suscripcion"))
        u = self.usuario()
        self.assertIsNotNone(u)
        self.assertIsNone(u.ml_user_id)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["luid"], u.id)
            self.assertEqual(sess["via"], "email")
            self.assertNotIn("uid", sess)  # todavía no conectó Mercado Libre
        self.assertEqual(self.client.get("/suscripcion").status_code, 200)

    def test_quien_se_registro_ve_su_email_ya_escrito_y_no_le_ofrece_ingresar(self):
        self.entrar()
        html = self.client.get("/suscripcion").get_data(as_text=True)
        self.assertIn('value="%s"' % EMAIL, html)
        self.assertNotIn("¿Ya tenés cuenta? Ingresar", html)
        self.assertIn("¿Ya tenés cuenta? Ingresar", self.app.test_client().get("/suscripcion").get_data(as_text=True))

    def test_el_enlace_sirve_una_sola_vez(self):
        self.pedir()
        _, token = link_de(self.mails)
        self.assertEqual(self.client.post("/acceso/" + token).status_code, 302)
        otro = self.app.test_client()
        r = otro.post("/acceso/" + token)
        self.assertEqual(r.status_code, 410)
        self.assertIn("ya no sirve", r.get_data(as_text=True))
        self.assertEqual(otro.get("/acceso/" + token).status_code, 410)

    def test_un_enlace_vencido_o_inventado_no_entra(self):
        self.pedir()
        _, token = link_de(self.mails)
        with Session(self.engine) as s:
            for fila in s.execute(select(LoginToken)).scalars():
                fila.expires_at = utcnow() - timedelta(minutes=1)
            s.commit()
        self.assertEqual(self.client.post("/acceso/" + token).status_code, 410)
        self.assertEqual(self.client.post("/acceso/" + "a" * 43).status_code, 410)
        self.assertEqual(self.client.post("/acceso/corto").status_code, 410)
        self.assertEqual(self.usuario(), None)

    def test_el_enlace_se_gasta_aunque_lleguen_dos_pedidos_a_la_vez(self):
        self.pedir()
        _, token = link_de(self.mails)
        with Session(self.engine) as a, Session(self.engine) as b:
            self.assertIsNotNone(usuarios.consume_login_token(a, token))
            self.assertIsNone(usuarios.consume_login_token(b, token))

    def test_el_plan_y_la_invitacion_viajan_con_el_enlace_aunque_se_abra_en_otro_navegador(self):
        token_inv = self.invite_token()
        self.client.get("/invitacion/" + token_inv)
        self.pedir(plan="annual")
        _, token = link_de(self.mails)
        otro = self.app.test_client()  # el mail se abre en otro navegador: la sesión original no está
        otro.post("/acceso/" + token)
        with otro.session_transaction() as sess:
            self.assertEqual(sess["plan"], "annual")
            self.assertEqual(sess["invite"], token_inv)

    def invite_token(self):
        from lumo import access
        with Session(self.engine) as s:
            inv = access.create_invite(s, "Casa Nogal", 14)
            s.commit()
            return inv.token

    def test_volver_a_entrar_no_duplica_al_usuario(self):
        self.entrar()
        self.entrar(client=self.app.test_client())
        with Session(self.engine) as s:
            self.assertEqual(len(s.execute(select(User)).scalars().all()), 1)

    # ---------- conectar Mercado Libre desde adentro ----------
    def test_al_conectar_mercado_libre_la_cuenta_queda_asociada_y_los_avisos_van_a_su_email(self):
        self.entrar()
        r = connect_as(self.client, 901)
        self.assertEqual(r.status_code, 302)
        u = self.usuario()
        self.assertEqual(u.ml_user_id, 901)
        with Session(self.engine) as s:
            self.assertEqual(s.get(Account, 901).email, EMAIL)
        with self.client.session_transaction() as sess:
            self.assertEqual((sess["luid"], sess["uid"], sess["via"]), (u.id, 901, "ml"))

    def test_quien_ya_conecto_entra_con_su_email_directo_al_panel(self):
        self.trialing_by_email(902)
        nuevo = self.app.test_client()
        r = self.entrar(client=nuevo)
        self.assertTrue(r.headers["Location"].endswith("/panel"))
        with nuevo.session_transaction() as sess:
            self.assertEqual(sess["uid"], 902)

    def trialing_by_email(self, uid):
        """Se registra con su email, elige plan, paga (prueba gratis) y conecta Mercado Libre."""
        self.entrar()
        self.client.get("/suscripcion")
        with self.client.session_transaction() as sess:
            csrf = sess["csrf"]
        r = self.client.post("/suscripcion", data={"plan": "monthly", "email": "pago@ejemplo.com", "csrf": csrf})
        pid = r.headers["Location"].rsplit("/", 1)[1]
        self.mp.authorize(pid, 14)
        back = self.mp.store[pid]["back_url"].replace("https://lumo.test", "")
        self.client.get(back + "?preapproval_id=" + pid)
        connect_as(self.client, uid)

    def test_una_cuenta_de_mercado_libre_no_se_comparte_entre_dos_usuarios(self):
        self.entrar()
        connect_as(self.client, 903)
        otra = self.app.test_client()
        self.entrar(client=otra, email="beto@ejemplo.com")
        r = connect_as(otra, 903)
        self.assertEqual(r.status_code, 409)
        self.assertIn("ya está asociada a otro usuario", r.get_data(as_text=True))
        self.assertIsNone(self.usuario("beto@ejemplo.com").ml_user_id)

    def test_un_usuario_no_conecta_una_segunda_cuenta_de_mercado_libre_todavia(self):
        self.entrar()
        connect_as(self.client, 904)
        r = connect_as(self.client, 905)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.usuario().ml_user_id, 904)

    def test_quien_ingresa_con_mercado_libre_se_reconoce_como_su_usuario(self):
        self.entrar()
        connect_as(self.client, 906)
        con_ml = self.app.test_client()
        connect_as(con_ml, 906)  # ingresa solo con Mercado Libre, sin pasar por el email
        with con_ml.session_transaction() as sess:
            self.assertEqual(sess["luid"], self.usuario().id)

    def test_la_cuenta_que_ya_estaba_conectada_sigue_entrando_sin_registro(self):
        connect_as(self.client, 907)  # como antes: solo Mercado Libre
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["uid"], 907)
            self.assertNotIn("luid", sess)

    # ---------- la administración ----------
    def test_la_administracion_pide_confirmar_con_mercado_libre_aunque_se_entre_con_el_email(self):
        self.entrar()
        connect_as(self.client, 1)   # 1 es administrador en la configuración de pruebas
        self.assertEqual(self.client.get("/admin").status_code, 200)
        otro = self.app.test_client()
        self.entrar(client=otro)     # mismo usuario, ahora con el enlace del email
        r = otro.get("/admin")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/connect"))

    # ---------- raíz, salida y borrado ----------
    def test_quien_se_registro_y_no_conecto_vuelve_a_su_lugar_desde_la_raiz(self):
        self.entrar()
        r = self.client.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/suscripcion"))

    def test_salir_cierra_la_sesion_completa(self):
        self.entrar()
        self.client.get("/salir")
        with self.client.session_transaction() as sess:
            self.assertEqual(dict(sess), {})

    def test_borrar_la_cuenta_borra_tambien_al_usuario_y_sus_enlaces(self):
        self.trialing_by_email(908)
        self.client.post("/cuenta/eliminar", data={"csrf": self.csrf()})
        self.assertIsNone(self.usuario())
        with Session(self.engine) as s:
            self.assertEqual(s.execute(select(LoginToken)).scalars().all(), [])

    def test_los_enlaces_vencidos_se_limpian(self):
        self.pedir()
        with Session(self.engine) as s:
            for fila in s.execute(select(LoginToken)).scalars():
                fila.expires_at = utcnow() - timedelta(days=2)
            s.commit()
            out = privacy.purge(s)
            s.commit()
            self.assertEqual(out["enlaces"], 1)

    def test_el_pedido_de_enlaces_tiene_tope_por_direccion(self):
        for i in range(8):
            self.assertEqual(self.pedir(email="u%d@ejemplo.com" % i).status_code, 200)
        self.assertEqual(self.pedir(email="otro@ejemplo.com").status_code, 429)


def notify_error():
    from lumo.notify import MailError
    return MailError("Brevo respondió 401 (unauthorized): secreto")


if __name__ == "__main__":
    unittest.main()
