import hashlib
import hmac
import unittest
from datetime import timedelta
from unittest import mock

from sqlalchemy.orm import Session

from lumo import billing, create_app
from lumo.models import Subscription, utcnow
from test_access import CFG, connect_as

BILLING = dict(CFG, MP_ACCESS_TOKEN="TEST-mp", PLAN_PRICE="15000", MP_API_BASE="https://mp.test")


class FakeMP:
    """Simula la API de suscripciones de Mercado Pago y guarda los pedidos que recibe."""

    def __init__(self):
        self.calls, self.store = [], {}

    def __call__(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append((method, url, json))
        path = url.replace("https://mp.test", "")
        if method == "POST" and path == "/preapproval":
            pid = "pre-%d" % (len(self.store) + 1)
            self.store[pid] = dict(json, id=pid, init_point="https://mp.test/checkout/" + pid)
            return Resp(201, self.store[pid])
        pid = path.rsplit("/", 1)[1]
        if pid not in self.store:
            return Resp(404, {"message": "not found"})
        if method == "PUT":
            self.store[pid].update(json)
        return Resp(200, self.store[pid])

    def authorize(self, pid, days=30):
        self.store[pid].update(status="authorized", next_payment_date=(utcnow() + timedelta(days=days)).isoformat() + "-03:00")


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class Base(unittest.TestCase):
    cfg = BILLING

    def setUp(self):
        self.app = create_app(self.cfg)
        self.engine = self.app.extensions["lumo_engine"]
        self.client = self.app.test_client()
        self.mp = FakeMP()
        patcher = mock.patch("lumo.billing.requests.request", self.mp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def expire_trial(self, uid):
        with Session(self.engine) as s:
            s.get(Subscription, uid).trial_ends_at = utcnow() - timedelta(minutes=1)
            s.commit()

    def csrf(self):
        self.client.get("/suscripcion")
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def subscribe(self, email="vende@dor.test"):
        return self.client.post("/suscripcion", data={"email": email, "csrf": self.csrf()})

    def sub(self, uid):
        with Session(self.engine) as s:
            return s.get(Subscription, uid)


class Ayudantes(unittest.TestCase):
    def test_precio_y_dias(self):
        self.assertEqual(billing.price_label({"PLAN_PRICE": "15000"}), "$15.000 ARS")
        self.assertEqual(billing.price_label({"PLAN_PRICE": "9,5", "PLAN_CURRENCY": "USD"}), "$9,50 USD")
        self.assertIsNone(billing.price_label({"PLAN_PRICE": "gratis"}))
        self.assertEqual(billing.trial_days({}), 14)
        self.assertEqual(billing.trial_days({"TRIAL_DAYS": "7"}), 7)
        self.assertFalse(billing.enabled({"PLAN_PRICE": "100"}))
        self.assertTrue(billing.enabled({"PLAN_PRICE": "100", "MP_ACCESS_TOKEN": "x"}))


class Prueba(Base):
    def test_portada_muestra_precio(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("$15.000 ARS", html)
        self.assertIn("14 días gratis, sin tarjeta", html)

    def test_el_panel_avisa_los_dias_que_quedan(self):
        connect_as(self.client, 800)
        with mock.patch("lumo.ml.advertisers", return_value=[]):
            self.client.get("/api/datos")
        self.assertIn("Te quedan 14 días de prueba gratis", self.client.get("/suscripcion").get_data(as_text=True))

    def test_prueba_vencida_lleva_a_suscribirse(self):
        connect_as(self.client, 801)
        self.expire_trial(801)
        self.assertTrue(self.client.get("/panel").headers["Location"].endswith("/suscripcion"))
        self.assertTrue(self.client.get("/").headers["Location"].endswith("/suscripcion"))
        r = self.client.get("/api/datos")
        self.assertEqual((r.status_code, r.get_json()["error"]), (402, "plan"))
        self.assertIn("Tu prueba gratis terminó", self.client.get("/suscripcion").get_data(as_text=True))
        # volver a conectarse no regala otra prueba
        r = connect_as(self.app.test_client(), 801)
        self.assertTrue(r.headers["Location"].endswith("/suscripcion"))

    def test_sin_sesion_no_hay_pagina_de_suscripcion(self):
        self.assertEqual(self.client.get("/suscripcion").headers["Location"], "/")
        self.assertEqual(self.client.post("/suscripcion").headers["Location"], "/")


class Pago(Base):
    def test_suscribirse_durante_la_prueba_cobra_al_terminarla(self):
        connect_as(self.client, 810)
        r = self.subscribe()
        self.assertEqual(r.headers["Location"], "https://mp.test/checkout/pre-1")
        method, url, body = self.mp.calls[-1]
        self.assertEqual((method, url), ("POST", "https://mp.test/preapproval"))
        self.assertEqual(body["external_reference"], "810")
        self.assertEqual(body["payer_email"], "vende@dor.test")
        self.assertEqual(body["back_url"], "https://lumo.test/suscripcion/listo")
        self.assertEqual(body["auto_recurring"]["transaction_amount"], 15000.0)
        self.assertEqual(body["auto_recurring"]["currency_id"], "ARS")
        self.assertIn("start_date", body["auto_recurring"])
        sub = self.sub(810)
        self.assertEqual((sub.status, sub.mp_preapproval_id), ("pending", "pre-1"))

    def test_con_la_prueba_vencida_cobra_enseguida(self):
        connect_as(self.client, 811)
        self.expire_trial(811)
        self.subscribe()
        self.assertNotIn("start_date", self.mp.calls[-1][2]["auto_recurring"])

    def test_vuelta_de_mercado_pago_activa_el_acceso(self):
        connect_as(self.client, 812)
        self.expire_trial(812)
        self.subscribe()
        self.mp.authorize("pre-1")
        r = self.client.get("/suscripcion/listo?preapproval_id=pre-1")
        self.assertTrue(r.headers["Location"].endswith("/panel"))
        self.assertEqual(self.client.get("/panel").status_code, 200)
        self.assertEqual(self.sub(812).status, "authorized")
        self.assertIn("Tu suscripción está activa", self.client.get("/suscripcion").get_data(as_text=True))

    def test_pago_sin_confirmar_queda_pendiente(self):
        connect_as(self.client, 813)
        self.expire_trial(813)
        self.subscribe()
        r = self.client.get("/suscripcion/listo?preapproval_id=pre-1")
        self.assertTrue(r.headers["Location"].endswith("/suscripcion?estado=pendiente"))
        self.assertIn("esperando la confirmación", self.client.get(r.headers["Location"]).get_data(as_text=True))

    def test_no_se_puede_usar_la_suscripcion_de_otra_cuenta(self):
        otro = self.app.test_client()
        connect_as(otro, 814)
        with otro.session_transaction() as sess:
            sess["csrf"] = "c"
        otro.post("/suscripcion", data={"email": "a@b.co", "csrf": "c"})
        self.mp.authorize("pre-1")
        connect_as(self.client, 815)
        self.expire_trial(815)
        self.client.get("/suscripcion/listo?preapproval_id=pre-1")
        self.assertEqual(self.sub(815).status, "trial")
        self.assertEqual(self.client.get("/panel").status_code, 302)

    def test_validaciones(self):
        connect_as(self.client, 816)
        self.assertEqual(self.subscribe("no-es-un-email").status_code, 400)
        self.assertEqual(self.client.post("/suscripcion", data={"email": "a@b.co"}).status_code, 400)  # sin csrf
        self.assertEqual(self.mp.calls, [])

    def test_error_de_mercado_pago(self):
        connect_as(self.client, 817)
        with mock.patch("lumo.billing.requests.request", return_value=Resp(500, {"message": "x"})):
            r = self.subscribe()
        self.assertEqual(r.status_code, 502)
        self.assertIn("no pudo iniciar el pago", r.get_data(as_text=True))

    def test_cancelar_mantiene_el_acceso_hasta_la_fecha_paga(self):
        connect_as(self.client, 818)
        self.expire_trial(818)
        self.subscribe()
        self.mp.authorize("pre-1", days=20)
        self.client.get("/suscripcion/listo?preapproval_id=pre-1")
        self.client.post("/suscripcion/cancelar", data={"csrf": self.csrf()})
        self.assertEqual(self.mp.store["pre-1"]["status"], "cancelled")
        self.assertEqual(self.sub(818).status, "cancelled")
        self.assertEqual(self.client.get("/panel").status_code, 200)
        self.assertIn("Cancelaste tu suscripción", self.client.get("/suscripcion").get_data(as_text=True))
        with Session(self.engine) as s:
            s.get(Subscription, 818).paid_until = utcnow() - timedelta(minutes=1)
            s.commit()
        self.assertEqual(self.client.get("/panel").status_code, 302)


class Webhook(Base):
    def prepare(self, uid):
        connect_as(self.client, uid)
        self.expire_trial(uid)
        self.subscribe()
        self.mp.authorize("pre-1")

    def test_aviso_de_mercado_pago_activa_la_suscripcion(self):
        self.prepare(820)
        r = self.app.test_client().post("/webhooks/mercadopago?data.id=pre-1&type=subscription_preapproval",
                                        json={"type": "subscription_preapproval", "data": {"id": "pre-1"}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.sub(820).status, "authorized")
        self.assertEqual(self.client.get("/panel").status_code, 200)

    def test_otros_avisos_se_ignoran(self):
        self.prepare(821)
        self.app.test_client().post("/webhooks/mercadopago", json={"type": "payment", "data": {"id": "pre-1"}})
        self.app.test_client().post("/webhooks/mercadopago", json={"type": "preapproval", "data": {"id": "inventado"}})
        self.assertEqual(self.sub(821).status, "pending")


class Firma(Base):
    cfg = dict(BILLING, MP_WEBHOOK_SECRET="secreto-webhook")

    def post(self, sig):
        return self.app.test_client().post("/webhooks/mercadopago?data.id=pre-1&type=subscription_preapproval",
                                           json={"type": "subscription_preapproval", "data": {"id": "pre-1"}},
                                           headers={"x-signature": sig, "x-request-id": "req-1"})

    def test_firma_valida_e_invalida(self):
        connect_as(self.client, 830)
        self.expire_trial(830)
        self.subscribe()
        self.mp.authorize("pre-1")
        self.assertEqual(self.post("ts=1,v1=falsa").status_code, 401)
        self.assertEqual(self.sub(830).status, "pending")
        v1 = hmac.new(b"secreto-webhook", b"id:pre-1;request-id:req-1;ts:1;", hashlib.sha256).hexdigest()
        self.assertEqual(self.post("ts=1,v1=" + v1).status_code, 200)
        self.assertEqual(self.sub(830).status, "authorized")


class SinCobro(Base):
    cfg = CFG

    def test_sin_mercado_pago_configurado_no_se_cobra(self):
        connect_as(self.client, 840)
        self.expire_trial(840)
        html = self.client.get("/suscripcion").get_data(as_text=True)
        self.assertIn("todavía no está habilitado", html)
        self.assertEqual(self.subscribe().status_code, 503)


class Administracion(Base):
    def test_lista_pruebas_y_quitar_cancela_en_mercado_pago(self):
        connect_as(self.client, 850)
        self.expire_trial(850)
        self.subscribe()
        self.mp.authorize("pre-1")
        self.client.get("/suscripcion/listo?preapproval_id=pre-1")
        admin = self.app.test_client()
        connect_as(admin, 1)
        html = admin.get("/admin").get_data(as_text=True)
        self.assertIn("Pagando", html)
        self.assertIn("vende@dor.test", html)
        with admin.session_transaction() as sess:
            csrf = sess["csrf"]
        admin.post("/admin/acceso/quitar", data={"user_id": "850", "csrf": csrf})
        self.assertEqual(self.mp.store["pre-1"]["status"], "cancelled")
        self.assertEqual(self.sub(850).status, "cancelled")
        self.assertTrue(connect_as(self.app.test_client(), 850).headers["Location"].endswith("/suscripcion"))


if __name__ == "__main__":
    unittest.main()
