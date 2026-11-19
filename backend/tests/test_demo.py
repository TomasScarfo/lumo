import unittest
from unittest import mock

import build_site
from lumo import create_app
from test_billing import BILLING


class PedidoDeDemo(unittest.TestCase):
    def setUp(self):
        self.app = create_app(dict(BILLING, CONTACT_EMAIL="lumoads.ml@gmail.com"))
        self.client = self.app.test_client()
        self.sent = []
        patcher = mock.patch("lumo.notify.send_mail", lambda cfg, to, subject, text, html, attachments=None, reply_to=None:
                             self.sent.append((to, subject, text, reply_to)))
        patcher.start()
        self.addCleanup(patcher.stop)

    def pedir(self, **data):
        self.client.get("/demo")
        with self.client.session_transaction() as sess:
            data.setdefault("csrf", sess["csrf"])
        return self.client.post("/demo", data=data)

    def test_la_portada_ofrece_pedir_una_demo(self):
        self.assertIn('href="__APP_URL__/demo" data-app', build_site.render())
        html = self.client.get("/demo").get_data(as_text=True)
        for texto in ("Pedí una demo", 'name="email"', "¿Qué querés lograr?", "Inversión mensual aproximada", "¿Usás Product Ads hoy?"):
            self.assertIn(texto, html)

    def test_las_respuestas_llegan_por_mail_y_se_responde_a_la_persona(self):
        r = self.pedir(nombre="Ana", email="ana@tienda.test", telefono="11 5555-5555", tienda="ANA_HOGAR", perfil="Vendedor",
                       rubro="Muebles", ads="Sí, hace poco", inversion="$100.000 a $500.000", campanas="2 a 5",
                       publicaciones="20 a 100", objetivos=["Vender más", "Gastar menos por venta", "inventado"],
                       dolor="No sé si subir el presupuesto", horario="Tarde (15 a 19)", origen="Google")
        self.assertIn("Te escribimos pronto", r.get_data(as_text=True))
        [(to, subject, text, reply_to)] = self.sent
        self.assertEqual(to, "lumoads.ml+demos@gmail.com")  # para filtrarlos a una etiqueta en Gmail
        self.assertEqual(reply_to, "ana@tienda.test")
        self.assertIn("Pedido de demo de Ana", subject)
        for dato in ("Tienda en Mercado Libre: ANA_HOGAR", "Inversión mensual: $100.000 a $500.000", "Objetivos: Vender más, Gastar menos por venta",
                     "WhatsApp / teléfono: 11 5555-5555", "Horario para la demo: Tarde (15 a 19)"):
            self.assertIn(dato, text)
        self.assertNotIn("inventado", text)

    def test_sin_email_valido_no_se_manda(self):
        r = self.pedir(email="no-es-un-mail", nombre="Ana")
        self.assertEqual(r.status_code, 400)
        self.assertIn('value="Ana"', r.get_data(as_text=True))  # no pierde lo que escribió
        self.assertEqual(self.sent, [])

    def test_los_robots_no_mandan_nada(self):
        r = self.pedir(email="bot@spam.test", web="http://spam.test")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.sent, [])

    def test_sin_csrf_se_rechaza(self):
        self.assertEqual(self.client.post("/demo", data={"email": "ana@tienda.test"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
