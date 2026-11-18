"""Lo que muestra la administración coincide con quién entra de verdad al panel.

Se arman cuentas en cada situación posible y, para cada una, se compara lo que pasa al abrir el panel y pedir los datos
con lo que dice la página de administración."""
import re
from datetime import timedelta
from unittest import mock

from sqlalchemy.orm import Session

from lumo import access, create_app
from lumo.models import Access, Account, Subscription, utcnow
from test_access import connect_as
from test_billing import BILLING, Base

CFG = dict(BILLING, ADMIN_USER_IDS="1")
CON_ACCESO = "Pagando|En prueba|Canceló|Cobro rechazado|Acceso sin cargo|Siempre con acceso|Conectada|Debe reconectar|Sin conectar"


class AdminDiceLaVerdad(Base):
    cfg = CFG

    def setUp(self):
        super().setUp()
        self.expect = {}  # cuenta -> ¿debería entrar?

    def fila(self, html, uid):
        rows = [r for r in re.findall(r"<tr>.*?</tr>", html, re.S) if "<code>%d</code>" % uid in r]
        return " ".join(rows)

    def entra(self, uid):
        """Una sesión nueva de esa cuenta: ¿llega al panel y a sus datos?"""
        with Session(self.engine) as s:
            acc = s.get(Account, uid)
        if acc is None:
            return False
        c = self.app.test_client()
        with c.session_transaction() as sess:
            sess["uid"], sess["at"] = uid, 10**10
        panel = c.get("/panel")
        with mock.patch("lumo.ml.advertisers", return_value=[]), mock.patch("lumo.ml.api_get", return_value={}):
            datos = c.get("/api/datos").status_code
        estado = c.post("/api/estado", json={}).status_code
        exportar = c.get("/api/exportar").status_code
        bloqueado = (panel.status_code == 302, datos in (401, 402), estado in (401, 402, 403), exportar in (401, 402, 403))
        self.assertEqual(len(set(bloqueado)), 1, "cuenta %s: el panel y la API no coinciden %s" % (uid, bloqueado))
        return not bloqueado[0]

    def test_cada_cuenta_aparece_en_el_admin_como_realmente_entra(self):
        now = utcnow()
        # sin cargo: a mano y por invitación
        connect_as(self.client, 500)
        with Session(self.engine) as s:
            access.grant(s, 500, "Amigo")
            inv = access.create_invite(s, "Invitada")
            s.commit()
            token = inv.token
        c = self.app.test_client()
        c.get("/invitacion/" + token)
        connect_as(c, 501)
        # prueba, pagando, cancelada con días pagos, cobro rechazado (en gracia y vencido), prueba terminada sin pagar
        self.trialing(502)
        self.paying(503)
        self.paying(504); self.edit(504, status="cancelled", paid_until=now + timedelta(days=10))
        self.paying(505); self.edit(505, past_due_since=now - timedelta(days=2))
        self.paying(506); self.edit(506, past_due_since=now - timedelta(days=30))
        self.paying(507); self.edit(507, status="cancelled", paid_until=now - timedelta(days=1))
        # empezó a suscribirse y no cargó el medio de pago; se conectó y nunca eligió plan
        connect_as(self.client, 508); self.subscribe("monthly")
        connect_as(self.client, 509)
        # tenía acceso sin cargo y se lo quitaron
        connect_as(self.client, 510)
        with Session(self.engine) as s:
            access.grant(s, 510, "Ex")
            s.commit()
        admin = self.app.test_client()
        connect_as(admin, 1)
        with admin.session_transaction() as sess:
            csrf = sess.get("csrf")
        if not csrf:
            admin.get("/admin")
            with admin.session_transaction() as sess:
                csrf = sess["csrf"]
        admin.post("/admin/acceso/quitar", data={"user_id": "510", "csrf": csrf})

        esperado = {1: True, 500: True, 501: True, 502: True, 503: True, 504: True, 505: True,
                    506: False, 507: False, 508: False, 509: False, 510: False}
        html = admin.get("/admin").get_data(as_text=True)
        for uid, debe in esperado.items():
            self.assertEqual(self.entra(uid), debe, "cuenta %s" % uid)
            fila = self.fila(html, uid)
            con_acceso = bool(re.search(CON_ACCESO, fila))
            self.assertEqual(con_acceso, debe, "cuenta %s en el admin: %r" % (uid, re.sub(r"\s+", " ", fila)[:300]))

    def test_quien_no_cargo_el_medio_de_pago_no_figura_como_prueba_vencida(self):
        connect_as(self.client, 508)
        self.subscribe("monthly")
        admin = self.app.test_client()
        connect_as(admin, 1)
        fila = self.fila(admin.get("/admin").get_data(as_text=True), 508)
        self.assertIn("No cargó el medio de pago", fila)
        self.assertNotIn("Prueba vencida", fila)
