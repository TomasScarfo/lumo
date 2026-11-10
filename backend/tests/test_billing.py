import hashlib
import hmac
import unittest
from datetime import timedelta
from unittest import mock

from sqlalchemy import select
from sqlalchemy.orm import Session

from lumo import billing, create_app, notify
from lumo.models import Account, AuditLog, Notice, Subscription, utcnow
from test_access import CFG, connect_as

# Cotización fija para los tests: US$1 = $1.000.
BILLING = dict(CFG, MP_ACCESS_TOKEN="TEST-mp", MP_API_BASE="https://mp.test", MP_CHECKOUT_ORIGINS="https://mp.test", USD_ARS_RATE="1000",
               SMTP_USER="lumo@lumo.test", SMTP_PASSWORD="pass-de-app", CRON_TOKEN="clave-del-cron-larga-y-aleatoria-0123456789")
CRON = {"X-Cron-Token": BILLING["CRON_TOKEN"]}


class FakeMP:
    """Simula la API de suscripciones de Mercado Pago y guarda los pedidos que recibe."""

    def __init__(self):
        self.calls, self.store, self.payments = [], {}, {}

    def __call__(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append((method, url, json))
        path = url.replace("https://mp.test", "")
        if method == "POST" and path == "/preapproval":
            pid = "pre-%d" % (len(self.store) + 1)
            self.store[pid] = dict(json, id=pid, init_point="https://mp.test/checkout/" + pid)
            return Resp(201, self.store[pid])
        kind, key = path.strip("/").split("/")
        box = self.payments if kind == "authorized_payments" else self.store
        if key not in box:
            return Resp(404, {"message": "not found"})
        if method == "PUT":
            if "auto_recurring" in json:
                box[key]["auto_recurring"].update(json["auto_recurring"])
            box[key].update({k: v for k, v in json.items() if k != "auto_recurring"})
        return Resp(200, box[key])

    def authorize(self, pid, days=30):
        self.store[pid].update(status="authorized", next_payment_date=(utcnow() + timedelta(days=days)).isoformat() + "-03:00")

    def charge(self, pid, result, state="processed"):
        """Agrega un cobro de la suscripción y devuelve su id, como el que llega en el aviso de Mercado Pago."""
        key = "pay-%d" % (len(self.payments) + 1)
        self.payments[key] = {"id": key, "preapproval_id": pid, "status": state, "payment": {"status": result}}
        return key


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
        self.mails = []
        for target, value in (("lumo.billing.requests.request", self.mp),
                              ("lumo.notify.send_mail", lambda cfg, to, subject, text, html: self.mails.append((to, subject, text)))):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def end_trial(self, uid):
        """Como si ya hubieran pasado los días de prueba."""
        self.edit(uid, trial_ends_at=utcnow() - timedelta(minutes=1))

    def used_trial(self, uid):
        """Una cuenta que ya gastó su prueba gratis y hoy no tiene suscripción."""
        with Session(self.engine) as s:
            s.add(Subscription(user_id=uid, status="cancelled", plan="monthly", trial_started_at=utcnow() - timedelta(days=40), trial_ends_at=utcnow() - timedelta(days=26)))
            s.commit()

    def csrf(self):
        self.client.get("/suscripcion")
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def subscribe(self, plan="monthly", email="vende@dor.test"):
        return self.client.post("/suscripcion", data={"plan": plan, "email": email, "csrf": self.csrf()})

    def paying(self, uid, plan="monthly", days=30):
        """Deja la cuenta con un plan autorizado y la prueba gratis ya terminada."""
        pid = self.trialing(uid, plan, days)
        self.end_trial(uid)
        return pid

    def trialing(self, uid, plan="monthly", days=14):
        """La cuenta eligió un plan y Mercado Pago confirmó su medio de pago: está en la prueba gratis."""
        connect_as(self.client, uid)
        self.subscribe(plan)
        pid = self.sub(uid).mp_preapproval_id
        self.mp.authorize(pid, days)
        self.client.get("/suscripcion/listo?preapproval_id=" + pid)
        return pid

    def sub(self, uid):
        with Session(self.engine) as s:
            return s.get(Subscription, uid)

    def edit(self, uid, **fields):
        with Session(self.engine) as s:
            sub = s.get(Subscription, uid)
            for k, v in fields.items():
                setattr(sub, k, v)
            s.commit()

    def notify_mp(self, kind, data_id, **kw):
        return self.app.test_client().post("/webhooks/mercadopago?data.id=%s&type=%s" % (data_id, kind), json={"type": kind, "data": {"id": data_id}}, **kw)

    def events(self):
        with Session(self.engine) as s:
            return [e.event for e in s.execute(select(AuditLog).order_by(AuditLog.id)).scalars()]


class Precios(unittest.TestCase):
    def test_etiquetas_y_ahorro_del_plan_anual(self):
        cfg = {"PLAN_PRICE_USD": "5.99", "PLAN_PRICE_ANNUAL_USD": "59,99"}
        self.assertEqual(billing.offer(cfg), {"monthly": "US$5,99", "annual": "US$59,99", "saving_pct": 17, "saving_usd": "US$11,89"})
        self.assertEqual(billing.saving({"PLAN_PRICE_USD": "6", "PLAN_PRICE_ANNUAL_USD": "60"}), (12.0, 17))
        self.assertEqual(billing.usd_label(6), "US$6")
        self.assertIsNone(billing.saving({"PLAN_PRICE_USD": "6", "PLAN_PRICE_ANNUAL_USD": "72"}))  # sin descuento no se anuncia ahorro
        self.assertEqual(billing.available_plans({"PLAN_PRICE_USD": "6"}), ("monthly",))

    def test_dias_de_prueba_y_de_gracia(self):
        self.assertEqual((billing.trial_days({}), billing.grace_days({})), (14, 7))
        self.assertEqual((billing.trial_days({"TRIAL_DAYS": "7"}), billing.grace_days({"GRACE_DAYS": "3"})), (7, 3))

    def test_el_cobro_necesita_token(self):
        self.assertFalse(billing.enabled({"PLAN_PRICE_USD": "6"}))
        self.assertTrue(billing.enabled({"PLAN_PRICE_USD": "6", "MP_ACCESS_TOKEN": "x"}))

    def test_los_precios_por_defecto_son_los_de_venta(self):
        from lumo import load_config
        cfg = load_config()
        self.assertEqual((cfg["PLAN_PRICE_USD"], cfg["PLAN_PRICE_ANNUAL_USD"], cfg["TRIAL_DAYS"], cfg["GRACE_DAYS"]), ("5.99", "59.99", "14", "7"))


class Cotizacion(unittest.TestCase):
    def setUp(self):
        billing._rate_cache.clear()
        self.cfg = {"PLAN_PRICE_USD": "5.99", "PLAN_PRICE_ANNUAL_USD": "59.99", "USD_RATE_URL": "https://dolar.test/oficial"}

    def test_convierte_con_la_cotizacion_de_venta(self):
        with mock.patch("lumo.billing.requests.get", return_value=Resp(200, {"compra": 1400, "venta": 1450.5})) as get:
            self.assertEqual(billing.ars_amount(self.cfg, "monthly"), 8688.5)   # 5,99 × 1.450,50, redondeado a centavos
            self.assertEqual(billing.ars_amount(self.cfg, "annual"), 87015.5)
            self.assertEqual(get.call_count, 1)  # la segunda vez usa la cotización guardada

    def test_si_el_servicio_falla_usa_la_ultima_cotizacion(self):
        with mock.patch("lumo.billing.requests.get", return_value=Resp(200, {"venta": 1000})):
            billing.rate(self.cfg)
        billing._rate_cache[self.cfg["USD_RATE_URL"]] = (1000, 0)  # vencida
        with mock.patch("lumo.billing.requests.get", return_value=Resp(500, {})):
            self.assertEqual(billing.rate(self.cfg), 1000)

    def test_sin_cotizacion_no_se_inventa_un_precio(self):
        with mock.patch("lumo.billing.requests.get", return_value=Resp(500, {})):
            self.assertRaises(billing.RateError, billing.rate, self.cfg)

    def test_cotizacion_fija_a_mano(self):
        self.assertEqual(billing.rate(dict(self.cfg, USD_ARS_RATE="1500")), 1500)


class Prueba(Base):
    def test_portada_muestra_los_dos_planes_y_el_ahorro(self):
        html = self.client.get("/").get_data(as_text=True)
        for texto in ("US$5,99", "US$59,99", "Ahorrás 17%", "no se cobra nada hasta el día 15", "al tipo de cambio oficial del día",
                      'href="/terminos"', 'href="/arrepentimiento"', "Botón de arrepentimiento"):
            self.assertIn(texto, html)
        self.assertNotIn("10 meses", html)
        self.assertNotIn("sin tarjeta", html.lower())

    def test_una_cuenta_nueva_no_entra_hasta_cargar_su_medio_de_pago(self):
        r = connect_as(self.client, 800)
        self.assertTrue(r.headers["Location"].endswith("/suscripcion"))
        self.assertIsNone(self.sub(800))
        self.assertTrue(self.client.get("/panel").headers["Location"].endswith("/suscripcion"))
        r = self.client.get("/api/datos")
        self.assertEqual((r.status_code, r.get_json()["error"]), (402, "plan"))
        html = self.client.get("/suscripcion").get_data(as_text=True)
        for texto in ("Empezá tu prueba gratis de 14 días", "No se cobra nada durante 14 días", "el día 15", "Empezar mi prueba gratis",
                      "US$5,99", "US$59,99", "Ahorrás 17%", "Hoy son $5.990.", "Hoy son $59.990.", "tenés 7 días", 'href="/terminos"'):
            self.assertIn(texto, html)

    def test_la_prueba_empieza_cuando_mercado_pago_confirma_el_medio_de_pago(self):
        connect_as(self.client, 801)
        self.subscribe("monthly")
        recurring = self.mp.calls[-1][2]["auto_recurring"]
        primer_cobro = (utcnow() + timedelta(days=14)).strftime("%Y-%m-%d")
        self.assertTrue(recurring["start_date"].startswith(primer_cobro))  # no se cobra por 14 días
        # eligió el plan pero todavía no cargó el medio de pago: no hay prueba ni acceso
        self.assertIsNone(self.sub(801).trial_started_at)
        self.assertEqual(self.client.get("/panel").status_code, 302)
        self.mp.authorize("pre-1", days=14)
        r = self.client.get("/suscripcion/listo?preapproval_id=pre-1")
        self.assertTrue(r.headers["Location"].endswith("/panel"))
        sub = self.sub(801)
        self.assertIsNotNone(sub.trial_started_at)
        self.assertEqual(sub.trial_ends_at.strftime("%Y-%m-%d"), primer_cobro)
        self.assertEqual(self.client.get("/panel").status_code, 200)
        html = self.client.get("/suscripcion").get_data(as_text=True)
        self.assertIn("Estás en tu prueba gratis: te quedan 14 días", html)
        self.assertIn("Todavía no se te cobró nada", html)
        self.assertIn("trial_start", self.events())

    def test_abandonar_el_pago_no_gasta_la_prueba(self):
        connect_as(self.client, 802)
        self.subscribe("monthly")
        self.subscribe("annual")  # vuelve y elige otro plan
        self.assertIn("start_date", self.mp.calls[-1][2]["auto_recurring"])
        self.assertIn("Empezá tu prueba gratis", self.client.get("/suscripcion").get_data(as_text=True))

    def test_la_prueba_es_una_sola_por_cuenta(self):
        self.trialing(803)
        self.client.post("/suscripcion/cancelar", data={"csrf": self.csrf()})
        self.edit(803, paid_until=utcnow() - timedelta(minutes=1), trial_ends_at=utcnow() - timedelta(minutes=1))
        html = self.client.get("/suscripcion").get_data(as_text=True)
        self.assertIn("Tu suscripción terminó", html)
        self.assertNotIn("prueba gratis", html)
        self.subscribe("monthly")
        self.assertNotIn("start_date", self.mp.calls[-1][2]["auto_recurring"])  # esta vez cobra enseguida

    def test_cancelar_durante_la_prueba_no_cobra_y_deja_terminarla(self):
        pid = self.trialing(804)
        self.client.post("/suscripcion/cancelar", data={"csrf": self.csrf()})
        self.assertEqual(self.mp.store[pid]["status"], "cancelled")
        self.assertEqual(self.client.get("/panel").status_code, 200)
        self.assertIn("Cancelaste tu suscripción", self.client.get("/suscripcion").get_data(as_text=True))

    def test_sin_sesion_no_hay_pagina_de_suscripcion(self):
        self.assertEqual(self.client.get("/suscripcion").headers["Location"], "/")
        self.assertEqual(self.client.post("/suscripcion").headers["Location"], "/")

    def test_quien_tiene_acceso_sin_cargo_no_paga(self):
        connect_as(self.client, 1)  # administrador
        self.assertIn("acceso sin cargo", self.client.get("/suscripcion").get_data(as_text=True))
        self.assertTrue(self.subscribe().headers["Location"].endswith("/panel"))
        self.assertEqual(self.mp.calls, [])


class Pago(Base):
    def test_mensual_cobra_en_pesos(self):
        connect_as(self.client, 810)
        r = self.subscribe("monthly")
        self.assertEqual(r.headers["Location"], "https://mp.test/checkout/pre-1")
        method, url, body = self.mp.calls[-1]
        self.assertEqual((method, url), ("POST", "https://mp.test/preapproval"))
        self.assertEqual(body["external_reference"], "810")
        self.assertEqual(body["payer_email"], "vende@dor.test")
        self.assertEqual(body["back_url"], "https://lumo.test/suscripcion/listo")
        self.assertEqual(body["auto_recurring"], dict(body["auto_recurring"], frequency=1, frequency_type="months", transaction_amount=5990.0, currency_id="ARS"))
        sub = self.sub(810)
        self.assertEqual((sub.status, sub.mp_preapproval_id, sub.plan, sub.amount_ars), ("pending", "pre-1", "monthly", 5990.0))

    def test_anual_cobra_una_vez_por_ano(self):
        connect_as(self.client, 811)
        self.subscribe("annual")
        recurring = self.mp.calls[-1][2]["auto_recurring"]
        self.assertEqual((recurring["frequency"], recurring["frequency_type"], recurring["transaction_amount"]), (12, "months", 59990.0))
        self.assertEqual(self.sub(811).plan, "annual")

    def test_terminada_la_prueba_el_plan_queda_activo(self):
        self.paying(812, "annual", days=365)
        self.assertEqual(self.client.get("/panel").status_code, 200)
        self.assertEqual(self.sub(812).status, "authorized")
        self.assertIn("Tu plan anual está activo", self.client.get("/suscripcion").get_data(as_text=True))
        self.assertIn("sub_authorized", self.events())

    def test_pago_sin_confirmar_queda_pendiente(self):
        connect_as(self.client, 813)
        self.subscribe()
        r = self.client.get("/suscripcion/listo?preapproval_id=pre-1")
        self.assertTrue(r.headers["Location"].endswith("/suscripcion?estado=pendiente"))
        self.assertIn("esperando la confirmación", self.client.get(r.headers["Location"]).get_data(as_text=True))

    def test_no_se_puede_usar_la_suscripcion_de_otra_cuenta(self):
        otro = self.app.test_client()
        connect_as(otro, 814)
        with otro.session_transaction() as sess:
            sess["csrf"] = "c"
        otro.post("/suscripcion", data={"plan": "monthly", "email": "a@b.co", "csrf": "c"})
        self.mp.authorize("pre-1")
        connect_as(self.client, 815)
        self.client.get("/suscripcion/listo?preapproval_id=pre-1")
        self.assertIsNone(self.sub(815))
        self.assertEqual(self.client.get("/panel").status_code, 302)

    def test_validaciones(self):
        connect_as(self.client, 816)
        self.assertEqual(self.subscribe(email="no-es-un-email").status_code, 400)
        self.assertEqual(self.subscribe(plan="vitalicio").status_code, 400)
        self.assertEqual(self.client.post("/suscripcion", data={"plan": "monthly", "email": "a@b.co"}).status_code, 400)  # sin csrf
        self.assertEqual(self.mp.calls, [])

    def test_error_de_mercado_pago(self):
        connect_as(self.client, 817)
        csrf = self.csrf()
        with mock.patch("lumo.billing.requests.request", return_value=Resp(500, {"message": "x"})):
            r = self.client.post("/suscripcion", data={"plan": "monthly", "email": "a@b.co", "csrf": csrf})
        self.assertEqual(r.status_code, 502)
        self.assertIn("no pudo iniciar el pago", r.get_data(as_text=True))

    def test_la_pagina_de_pago_solo_deja_salir_hacia_mercado_pago(self):
        """Los navegadores bloquean la redirección de un formulario si su destino no está en form-action."""
        connect_as(self.client, 822)
        self.assertIn("form-action 'self' https://mp.test;", self.client.get("/suscripcion").headers["Content-Security-Policy"])
        self.assertIn("form-action 'self';", self.client.get("/privacidad").headers["Content-Security-Policy"])
        from lumo import load_config
        self.assertIn("https://www.mercadopago.com.ar", load_config()["MP_CHECKOUT_ORIGINS"])

    def test_un_enlace_de_pago_de_otro_dominio_no_se_sigue(self):
        connect_as(self.client, 823)
        self.app.extensions["lumo_cfg"]["MP_CHECKOUT_ORIGINS"] = "https://www.mercadopago.com.ar"
        r = self.subscribe()
        self.assertEqual(r.status_code, 502)
        self.assertIsNone(self.sub(823))  # no quedó a medio suscribir

    def test_sin_cotizacion_no_se_puede_pagar(self):
        billing._rate_cache.clear()
        self.app.extensions["lumo_cfg"]["USD_ARS_RATE"] = ""
        connect_as(self.client, 819)
        with mock.patch("lumo.billing.requests.get", return_value=Resp(500, {})):  # también al abrir la página: si no, guarda la cotización real
            csrf = self.csrf()
            r = self.client.post("/suscripcion", data={"plan": "monthly", "email": "a@b.co", "csrf": csrf})
        self.assertEqual(r.status_code, 503)
        self.assertIn("No pudimos calcular el precio en pesos", r.get_data(as_text=True))
        self.assertEqual(self.mp.calls, [])

    def test_cancelar_mantiene_el_acceso_hasta_la_fecha_paga(self):
        self.paying(818, days=20)
        self.client.post("/suscripcion/cancelar", data={"csrf": self.csrf()})
        self.assertEqual(self.mp.store["pre-1"]["status"], "cancelled")
        self.assertEqual(self.sub(818).status, "cancelled")
        self.assertEqual(self.client.get("/panel").status_code, 200)
        self.assertIn("Cancelaste tu suscripción", self.client.get("/suscripcion").get_data(as_text=True))
        self.edit(818, paid_until=utcnow() - timedelta(minutes=1))
        self.assertEqual(self.client.get("/panel").status_code, 302)
        self.assertIn("Tu suscripción terminó", self.client.get("/suscripcion").get_data(as_text=True))


class CambioDePlan(Base):
    def test_el_plan_nuevo_empieza_al_terminar_lo_pago_y_reemplaza_al_anterior(self):
        self.paying(860, "monthly", days=20)
        r = self.subscribe("annual")
        self.assertEqual(r.headers["Location"], "https://mp.test/checkout/pre-2")
        nuevo = self.mp.store["pre-2"]["auto_recurring"]
        self.assertEqual((nuevo["frequency"], nuevo["transaction_amount"]), (12, 59990.0))
        self.assertTrue(nuevo["start_date"].startswith(self.sub(860).paid_until.strftime("%Y-%m-%d")))
        # mientras no pague el nuevo, sigue con el mensual
        sub = self.sub(860)
        self.assertEqual((sub.plan, sub.mp_preapproval_id, sub.next_plan, sub.status), ("monthly", "pre-1", "annual", "authorized"))
        self.assertEqual(self.mp.store["pre-1"]["status"], "authorized")
        self.mp.authorize("pre-2", days=385)
        r = self.client.get("/suscripcion/listo?preapproval_id=pre-2")
        self.assertTrue(r.headers["Location"].endswith("/suscripcion?estado=cambio"))
        sub = self.sub(860)
        self.assertEqual((sub.plan, sub.mp_preapproval_id, sub.next_plan, sub.amount_ars), ("annual", "pre-2", None, 59990.0))
        self.assertEqual(self.mp.store["pre-1"]["status"], "cancelled")  # no se cobra dos veces
        self.assertIn("Tu plan ahora es el anual", self.client.get(r.headers["Location"]).get_data(as_text=True))

    def test_abandonar_el_cambio_no_deja_sin_plan(self):
        self.paying(861, "monthly")
        self.subscribe("annual")
        self.mp.store["pre-2"]["status"] = "cancelled"
        self.notify_mp("subscription_preapproval", "pre-2")
        sub = self.sub(861)
        self.assertEqual((sub.plan, sub.status, sub.next_plan), ("monthly", "authorized", None))
        self.assertEqual(self.client.get("/panel").status_code, 200)

    def test_pedir_el_mismo_plan_no_crea_otra_suscripcion(self):
        self.paying(862, "monthly")
        n = len(self.mp.store)
        self.assertTrue(self.subscribe("monthly").headers["Location"].endswith("/suscripcion"))
        self.assertEqual(len(self.mp.store), n)


class CobroRechazado(Base):
    def test_siete_dias_de_gracia_y_despues_se_suspende_sin_borrar(self):
        pid = self.paying(870)
        self.assertEqual(self.notify_mp("subscription_authorized_payment", self.mp.charge(pid, "rejected", "recycling")).status_code, 200)
        sub = self.sub(870)
        self.assertIsNotNone(sub.past_due_since)
        # sigue entrando, con el aviso
        self.assertEqual(self.client.get("/panel").status_code, 200)
        html = self.client.get("/suscripcion").get_data(as_text=True)
        self.assertIn("No pudimos cobrar tu suscripción", html)
        self.assertIn((sub.past_due_since + timedelta(days=7)).strftime("%d/%m/%Y"), html)
        self.assertEqual([(to, subject) for to, subject, _ in self.mails], [("vende@dor.test", "No pudimos cobrar tu suscripción de Lumo")])
        self.assertIn("sub_pago_rechazado", self.events())
        # un segundo rechazo no reinicia el plazo ni repite el email
        self.notify_mp("subscription_authorized_payment", self.mp.charge(pid, "rejected", "recycling"))
        self.assertEqual(self.sub(870).past_due_since, sub.past_due_since)
        self.assertEqual(len(self.mails), 1)
        # pasados los 7 días, se suspende
        self.edit(870, past_due_since=utcnow() - timedelta(days=7, minutes=1))
        self.assertTrue(self.client.get("/panel").headers["Location"].endswith("/suscripcion"))
        self.assertEqual(self.client.get("/api/datos").status_code, 402)
        self.assertIn("Tu acceso está en pausa", self.client.get("/suscripcion").get_data(as_text=True))
        with Session(self.engine) as s:
            self.assertIsNotNone(s.get(Account, 870))  # no se borra nada

    def test_si_el_cobro_despues_entra_se_normaliza(self):
        pid = self.paying(871)
        self.notify_mp("subscription_authorized_payment", self.mp.charge(pid, "rejected", "recycling"))
        self.notify_mp("subscription_authorized_payment", self.mp.charge(pid, "approved"))
        self.assertIsNone(self.sub(871).past_due_since)
        self.assertIn("está activo", self.client.get("/suscripcion").get_data(as_text=True))
        self.assertIn("sub_pago_ok", self.events())

    def test_volver_a_suscribirse_despues_de_la_suspension(self):
        pid = self.paying(872)
        self.notify_mp("subscription_authorized_payment", self.mp.charge(pid, "rejected"))
        self.edit(872, past_due_since=utcnow() - timedelta(days=8))
        self.mp.store[pid]["status"] = "cancelled"  # Mercado Pago la dio de baja
        self.notify_mp("subscription_preapproval", pid)
        self.assertEqual(self.client.get("/panel").status_code, 302)
        self.subscribe("monthly")
        nuevo = self.sub(872).mp_preapproval_id
        self.assertNotEqual(nuevo, pid)
        self.assertNotIn("start_date", self.mp.store[nuevo]["auto_recurring"])  # cobra enseguida
        self.mp.authorize(nuevo)
        self.client.get("/suscripcion/listo?preapproval_id=" + nuevo)
        self.assertIsNone(self.sub(872).past_due_since)
        self.assertEqual(self.client.get("/panel").status_code, 200)

    def test_un_cobro_de_una_suscripcion_desconocida_se_ignora(self):
        self.paying(873)
        self.mp.payments["pay-x"] = {"id": "pay-x", "preapproval_id": "otra", "status": "recycling", "payment": {"status": "rejected"}}
        self.assertEqual(self.notify_mp("subscription_authorized_payment", "pay-x").status_code, 200)
        self.assertIsNone(self.sub(873).past_due_since)


class ChequeoDiario(Base):
    def cron(self):
        with mock.patch("lumo.ml.advertisers", return_value=[]):
            return self.app.test_client().post("/cron/avisos", headers=CRON).get_json()["cobros"]

    def test_actualiza_el_monto_en_pesos_con_la_cotizacion(self):
        pid = self.paying(880)
        self.assertEqual(self.cron()["montos"], 0)  # misma cotización: no toca nada
        self.app.extensions["lumo_cfg"]["USD_ARS_RATE"] = "1100"
        self.assertEqual(self.cron()["montos"], 1)
        self.assertEqual(self.mp.store[pid]["auto_recurring"]["transaction_amount"], 6589.0)
        self.assertEqual(self.sub(880).amount_ars, 6589.0)
        self.app.extensions["lumo_cfg"]["USD_ARS_RATE"] = "1105"  # menos de 1 %: no vale un cambio
        self.assertEqual(self.cron()["montos"], 0)

    def test_se_entera_de_lo_que_no_llego_por_aviso(self):
        pid = self.paying(881)
        self.mp.store[pid]["status"] = "cancelled"
        self.cron()
        self.assertEqual(self.sub(881).status, "cancelled")

    def test_avisa_una_vez_antes_del_primer_cobro(self):
        self.trialing(882, "annual")
        self.assertEqual(self.cron()["avisos"], 0)  # faltan 14 días
        self.edit(882, trial_ends_at=utcnow() + timedelta(days=2, hours=1))
        self.assertEqual(self.cron()["avisos"], 1)
        self.assertEqual(self.cron()["avisos"], 0)
        to, subject, text = self.mails[0]
        self.assertEqual((to, subject), ("vende@dor.test", "Tu prueba gratis de Lumo termina en 3 días"))
        for texto in ("primer cobro de tu plan anual (US$59,99)", "cancelá antes de esa fecha", "https://lumo.test/suscripcion"):
            self.assertIn(texto, text)

    def test_avisa_la_suspension(self):
        pid = self.paying(883)
        self.notify_mp("subscription_authorized_payment", self.mp.charge(pid, "rejected"))
        self.edit(883, past_due_since=utcnow() - timedelta(days=8))
        self.cron()
        self.assertEqual([m[1] for m in self.mails], ["No pudimos cobrar tu suscripción de Lumo", "Tu acceso a Lumo quedó en pausa"])
        with Session(self.engine) as s:
            self.assertEqual(sorted(n.kind for n in s.execute(select(Notice).where(Notice.user_id == 883)).scalars()), ["baja", "pago"])


class Webhook(Base):
    def test_aviso_de_mercado_pago_activa_la_suscripcion(self):
        connect_as(self.client, 820)
        self.subscribe()
        self.mp.authorize("pre-1")
        self.assertEqual(self.notify_mp("subscription_preapproval", "pre-1").status_code, 200)
        self.assertEqual(self.sub(820).status, "authorized")
        self.assertEqual(self.client.get("/panel").status_code, 200)

    def test_otros_avisos_se_ignoran(self):
        connect_as(self.client, 821)
        self.subscribe()
        self.mp.authorize("pre-1")
        self.assertEqual(self.notify_mp("payment", "pre-1").status_code, 200)
        self.assertEqual(self.sub(821).status, "pending")
        self.assertIsNone(self.sub(821).trial_started_at)

    def test_si_mercado_pago_no_responde_pide_reintento(self):
        self.assertEqual(self.notify_mp("preapproval", "inventado").status_code, 502)


class Firma(Base):
    cfg = dict(BILLING, MP_WEBHOOK_SECRET="secreto-webhook")

    def test_firma_valida_e_invalida(self):
        connect_as(self.client, 830)
        self.subscribe()
        self.mp.authorize("pre-1")
        post = lambda sig: self.notify_mp("subscription_preapproval", "pre-1", headers={"x-signature": sig, "x-request-id": "req-1"})
        self.assertEqual(post("ts=1,v1=falsa").status_code, 401)
        self.assertEqual(self.sub(830).status, "pending")
        v1 = hmac.new(b"secreto-webhook", b"id:pre-1;request-id:req-1;ts:1;", hashlib.sha256).hexdigest()
        self.assertEqual(post("ts=1,v1=" + v1).status_code, 200)
        self.assertEqual(self.sub(830).status, "authorized")


class SinCobro(Base):
    cfg = CFG

    def test_sin_mercado_pago_configurado_no_se_cobra(self):
        connect_as(self.client, 840)
        html = self.client.get("/suscripcion").get_data(as_text=True)
        self.assertIn("todavía no está habilitado", html)
        self.assertIn('href="https://wa.me/5491100000000', html)
        self.assertEqual(self.subscribe().status_code, 503)


class Administracion(Base):
    def admin(self):
        c = self.app.test_client()
        connect_as(c, 1)
        c.get("/admin")
        with c.session_transaction() as sess:
            return c, sess["csrf"]

    def test_lista_planes_e_ingreso_mensual(self):
        self.paying(850, "monthly")
        otro = Base.paying
        self.client = self.app.test_client()
        otro(self, 851, "annual", days=365)
        self.client = self.app.test_client()
        Base.trialing(self, 852)  # en prueba
        html = self.admin()[0].get("/admin").get_data(as_text=True)
        for texto in ("Pagando", "vende@dor.test", "Mensual", "Anual", "En prueba", "US$10,99"):  # 5,99 + 59,99 / 12
            self.assertIn(texto, html)

    def test_quitar_acceso_cancela_en_mercado_pago_y_no_da_otra_prueba(self):
        pid = self.paying(853)
        admin, csrf = self.admin()
        admin.post("/admin/acceso/quitar", data={"user_id": "853", "csrf": csrf})
        self.assertEqual(self.mp.store[pid]["status"], "cancelled")
        sub = self.sub(853)
        self.assertEqual((sub.status, sub.payer_email), ("cancelled", None))
        otro = self.app.test_client()
        self.assertTrue(connect_as(otro, 853).headers["Location"].endswith("/suscripcion"))
        self.assertNotIn("prueba gratis", otro.get("/suscripcion").get_data(as_text=True))

    def test_borrar_la_propia_cuenta_corta_el_cobro(self):
        pid = self.paying(854)
        self.client.post("/cuenta/eliminar", data={"csrf": self.csrf()})
        self.assertEqual(self.mp.store[pid]["status"], "cancelled")
        sub = self.sub(854)
        self.assertEqual((sub.status, sub.payer_email, sub.paid_until), ("cancelled", None, None))
        with Session(self.engine) as s:
            self.assertIsNone(s.get(Account, 854))


class Legales(Base):
    def test_terminos_con_precios_prueba_y_plazos(self):
        r = self.client.get("/terminos")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        for texto in ("US$5,99 por mes", "US$59,99 por año", "14 días de prueba gratis", "tipo de cambio oficial", "se renueva sola",
                      "10 días corridos", "7 días", 'href="/arrepentimiento"', 'href="/privacidad"'):
            self.assertIn(texto, html)

    def test_arrepentimiento_sin_sesion_explica_y_ofrece_contacto(self):
        html = self.client.get("/arrepentimiento").get_data(as_text=True)
        for texto in ("10 días corridos", "Ingresar con Mercado Libre", "mailto:hola@lumo.test", "dentro de las 24 horas"):
            self.assertIn(texto, html)
        self.assertEqual(self.client.post("/arrepentimiento").headers["Location"], "/arrepentimiento")

    def test_arrepentirse_cancela_corta_el_acceso_y_da_un_codigo(self):
        pid = self.trialing(890)
        self.assertEqual(self.client.post("/arrepentimiento", data={}).status_code, 400)  # sin csrf
        self.mails.clear()
        r = self.client.post("/arrepentimiento", data={"csrf": self.csrf()})
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        with Session(self.engine) as s:
            code = s.execute(select(AuditLog).where(AuditLog.event == "arrepentimiento")).scalars().one().detail
        self.assertRegex(code, r"^ARR-890-[0-9A-F]{6}$")
        self.assertIn(code, html)
        self.assertIn("Ya cancelamos tu suscripción", html)
        self.assertEqual(self.mp.store[pid]["status"], "cancelled")
        self.assertEqual(self.client.get("/panel").status_code, 302)  # la contratación quedó sin efecto
        # aviso a quien administra (para devolver un cobro si lo hubo) y constancia a la persona
        self.assertEqual([to for to, _, _ in self.mails], ["hola@lumo.test", "vende@dor.test"])
        self.assertTrue(all(code in text for _, _, text in self.mails))
        # no vuelve a tener prueba gratis
        self.subscribe()
        self.assertNotIn("start_date", self.mp.calls[-1][2]["auto_recurring"])

    def test_arrepentirse_sin_suscripcion_igual_da_constancia(self):
        connect_as(self.client, 891)
        html = self.client.post("/arrepentimiento", data={"csrf": self.csrf()}).get_data(as_text=True)
        self.assertIn("ARR-891-", html)
        self.assertIn("No encontramos una suscripción activa", html)
        self.assertEqual(self.mp.calls, [])


class Mensajes(unittest.TestCase):
    def test_textos_de_los_avisos(self):
        subject, text, html = notify.billing_mail("pago", "https://lumo.test/suscripcion", until=utcnow())
        self.assertIn("No pudimos cobrar", subject)
        self.assertIn("Ver mi suscripción", html)
        self.assertIn("mañana", notify.billing_mail("prueba", "x", days=1, until=utcnow(), price="US$5,99", plan="mensual")[0])
        self.assertIn("No borramos nada", notify.billing_mail("baja", "x")[1])


if __name__ == "__main__":
    unittest.main()
