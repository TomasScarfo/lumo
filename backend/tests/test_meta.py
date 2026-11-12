import hashlib
import unittest
from unittest import mock

from sqlalchemy.orm import Session

import build_site
from lumo import create_app, meta, privacy
from lumo.models import AdClick
from test_access import CFG, tok
from test_billing import BILLING, Base

META = dict(BILLING, META_PIXEL_ID="1234567890", META_CAPI_TOKEN="token-capi")
FBC = "fb.1.1762900000000.IwAR-anuncio_1"
FBP = "fb.1.1762900000000.987654321"


def sha(v):
    return hashlib.sha256(v.encode()).hexdigest()


class ConMeta(Base):
    cfg = META

    def setUp(self):
        super().setUp()
        self.sent = []
        patcher = mock.patch("lumo.meta._dispatch", lambda cfg, event: self.sent.append(event))
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self, uid, query=""):
        loc = self.client.get("/connect" + query).headers["Location"]
        state = loc.split("state=")[1].split("&")[0]
        with mock.patch("lumo.ml.exchange_code", return_value=tok(uid)), mock.patch("lumo.ml.advertisers", return_value=[]), \
                mock.patch("lumo.ml.api_get", return_value={"email": "vende@dor.test"}):
            return self.client.get("/callback?code=abc&state=" + state, headers={"User-Agent": "Navegador/1.0"})

    def names(self):
        return [e["event_name"] for e in self.sent]

    def test_registro_prueba_y_primer_cobro_llegan_una_vez_con_el_clic_del_anuncio(self):
        self.connect(901, "?plan=monthly&fbc=%s&fbp=%s" % (FBC, FBP))
        self.assertEqual(self.names(), ["Lead"])
        lead = self.sent[0]
        self.assertEqual(lead["action_source"], "website")
        self.assertEqual(lead["user_data"]["fbc"], FBC)
        self.assertEqual(lead["user_data"]["fbp"], FBP)
        self.assertEqual(lead["user_data"]["external_id"], [sha("901")])
        self.assertEqual(lead["user_data"]["client_user_agent"], "Navegador/1.0")
        self.assertNotIn("vende@dor.test", str(lead))  # el email viaja solo cifrado
        # volver a entrar no repite el registro
        self.connect(901)
        self.assertEqual(self.names(), ["Lead"])
        # la prueba gratis empieza cuando Mercado Pago confirma el medio de pago
        self.subscribe("monthly")
        pid = self.sub(901).mp_preapproval_id
        self.mp.authorize(pid, 14)
        self.client.get("/suscripcion/listo?preapproval_id=" + pid)
        self.assertEqual(self.names(), ["Lead", "StartTrial"])
        trial = self.sent[1]
        self.assertEqual(trial["custom_data"], {"currency": "USD", "value": 5.99})
        self.assertEqual(trial["user_data"]["fbc"], FBC)
        self.assertEqual(trial["user_data"]["em"], [sha("vende@dor.test")])
        # el primer cobro aprobado llega por el aviso de Mercado Pago, sin la persona: no hay IP
        self.end_trial(901)
        self.notify_mp("subscription_authorized_payment", self.mp.charge(pid, "approved"))
        self.notify_mp("subscription_authorized_payment", self.mp.charge(pid, "approved"))  # la renovación no cuenta como nueva
        self.assertEqual(self.names(), ["Lead", "StartTrial", "Subscribe"])
        self.assertNotIn("client_ip_address", self.sent[2]["user_data"])
        with Session(self.engine) as s:
            self.assertEqual(s.get(AdClick, 901).sent, "Lead,StartTrial,Subscribe")

    def test_sin_anuncio_igual_mide_y_descarta_identificadores_raros(self):
        self.connect(902, "?fbc=<script>&fbp=cualquiera")
        ud = self.sent[0]["user_data"]
        self.assertNotIn("fbc", ud)
        self.assertNotIn("fbp", ud)

    def test_fbclid_de_la_direccion(self):
        self.connect(903, "?fbclid=IwAR-xyz")
        self.assertTrue(self.sent[0]["user_data"]["fbc"].endswith(".IwAR-xyz"))

    def test_administradores_no_cuentan(self):
        self.connect(1)
        self.assertEqual(self.sent, [])

    def test_portada_carga_el_pixel_y_lo_permite_la_politica(self):
        r = create_app(META).test_client().get("/")
        html = r.get_data(as_text=True)
        self.assertIn("var PIXEL = '1234567890'", html)
        self.assertIn("https://connect.facebook.net", r.headers["Content-Security-Policy"])

    def test_borrar_la_cuenta_borra_el_clic(self):
        self.connect(904, "?fbc=" + FBC)
        with Session(self.engine) as s:
            self.assertEqual(privacy.export_user(s, 904)["anuncios_de_meta"]["clic_en_anuncio"], FBC)
            privacy.erase_user(s, 904)
            s.commit()
            self.assertIsNone(s.get(AdClick, 904))


class SinMeta(Base):
    def test_sin_configurar_no_hay_pixel_ni_eventos(self):
        with mock.patch("lumo.meta._dispatch") as dispatch:
            r = create_app(CFG).test_client().get("/")
            self.assertNotIn("fbq(", r.get_data(as_text=True))
            self.assertNotIn("facebook", r.headers["Content-Security-Policy"])
            self.trialing(905)
            dispatch.assert_not_called()

    def test_el_panel_nunca_trae_scripts_de_meta(self):
        app = create_app(META)
        self.assertNotIn("facebook", app.test_client().get("/privacidad").headers["Content-Security-Policy"])

    def test_la_portada_estatica_lo_deja_para_render(self):
        html = build_site.render()
        self.assertIn("var PIXEL = '__META_PIXEL_ID__'", html)
        self.assertIn("if (!/^\\d+$/.test(PIXEL)) return;", html)


class Evento(unittest.TestCase):
    def test_sin_navegador_es_del_sistema(self):
        e = meta.build_event(META, "Subscribe", 7, email=" Vende@Dor.test ", value=5.99)
        self.assertEqual(e["action_source"], "system_generated")
        self.assertEqual(e["user_data"]["em"], [sha("vende@dor.test")])
        self.assertEqual(e["user_data"]["country"], [sha("ar")])
        self.assertEqual(e["event_id"], "subscribe-7")

    def test_envio_con_codigo_de_prueba(self):
        cfg = dict(META, META_TEST_EVENT_CODE="TEST123")
        with mock.patch("lumo.meta.requests.post") as post:
            post.return_value.status_code = 200
            self.assertTrue(meta.send(cfg, {"event_name": "Lead"}))
        url = post.call_args[0][0]
        self.assertEqual(url, "https://graph.facebook.com/v23.0/1234567890/events")
        self.assertEqual(post.call_args[1]["json"]["test_event_code"], "TEST123")
        self.assertEqual(post.call_args[1]["params"], {"access_token": "token-capi"})


if __name__ == "__main__":
    unittest.main()
