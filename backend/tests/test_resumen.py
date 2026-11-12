import io
import json
import unittest
import zipfile
from datetime import timedelta
from unittest import mock

import fake_ml
from sqlalchemy.orm import Session

from lumo import create_app, exportar, notify
from lumo.models import Access, PanelState
from lumo.tokens import save_tokens
from test_avisos import CFG, LUNES, dataset

HOJAS = ["Resumen", "Campañas", "Publicaciones", "Por día"]


def hojas(content: bytes) -> list:
    z = zipfile.ZipFile(io.BytesIO(content))
    assert z.testzip() is None
    wb = z.read("xl/workbook.xml").decode("utf-8")
    return [h for h in HOJAS if 'name="%s"' % h in wb]


class MailSemanal(unittest.TestCase):
    def setUp(self):
        self.subject, self.text, self.html = notify.weekly_mail(dataset(), "https://lumo.test/panel#alertas", "porque sí")

    def test_el_encabezado_lleva_el_logo_y_el_nombre(self):
        self.assertIn("<img src='https://lumo.test/static/logo.png'", self.html)
        self.assertIn(">Lumo</span>", self.html)

    def test_muestra_la_inversion_de_cada_uno_de_los_ultimos_7_dias(self):
        self.assertIn("Cómo evolucionó tu inversión", self.html)
        per = exportar.periodo(dataset(), 7)
        self.assertEqual(len(per["daily"]), 7)
        for d in per["daily"]:
            self.assertIn(notify.money(d["spend"]), self.html)
        self.assertEqual(self.text.count("\n  ") >= 7, True)

    def test_destaca_las_5_publicaciones_que_mas_aportaron(self):
        top = exportar.top_publicaciones(exportar.periodo(dataset(), 7), 5)
        self.assertGreaterEqual(len(top), 1)
        self.assertLessEqual(self.html.count("<li style='margin:7px 0'>"), 5)
        self.assertIn(top[0]["name"][:30], self.html)
        ventas = [o["sales"] for o in top]
        self.assertEqual(ventas, sorted(ventas, reverse=True))
        self.assertIn("estimadas", self.html)

    def test_avisa_que_adjunta_el_excel(self):
        self.assertIn("Excel", self.html)
        self.assertIn("Excel", self.text)

    def test_sin_inversion_no_se_rompe(self):
        data = dataset()
        for c in data["camps"]:
            for d in c["daily"]:
                d.update(spend=0, sales=0, clicks=0, prints=0, units=0)
        _, text, html = notify.weekly_mail(data, "https://lumo.test/panel", "x")
        self.assertIn("No hubo inversión", html)
        self.assertIn("Todavía no hay publicaciones con ventas", html)


class Adjunto(unittest.TestCase):
    def test_el_resumen_semanal_se_manda_con_el_excel(self):
        engine = create_app(CFG).extensions["lumo_engine"]
        sent = []
        with Session(engine) as s:
            notify.run_for(s, CFG, 5, "ana@test.com", {"m1": True}, dataset(), "https://lumo.test/panel", LUNES,
                           lambda cfg, to, subject, text, html, attachments=None: sent.append(attachments))
        self.assertEqual(len(sent), 1)
        (name, content), = sent[0]
        self.assertTrue(name.endswith(".xlsx"))
        self.assertEqual(hojas(content), HOJAS)

    def test_los_avisos_de_publicaciones_no_llevan_adjunto(self):
        engine = create_app(CFG).extensions["lumo_engine"]
        sent = []
        with Session(engine) as s:
            notify.run_for(s, CFG, 5, "ana@test.com", {"m3": True}, dataset(), "https://lumo.test/panel", LUNES + timedelta(days=5),
                           lambda cfg, to, subject, text, html, attachments=None: sent.append(attachments))
        self.assertEqual(sent, [None])

    def test_brevo_recibe_el_archivo_en_base64(self):
        cfg = dict(CFG, BREVO_API_KEY="k", MAIL_FROM="lumo@test.com", SMTP_PASSWORD="")
        with mock.patch("lumo.notify.requests.post") as post:
            post.return_value.status_code = 201
            notify.send_mail(cfg, "a@b.com", "s", "t", "h", attachments=[("x.xlsx", b"hola")])
        self.assertEqual(post.call_args[1]["json"]["attachment"], [{"name": "x.xlsx", "content": "aG9sYQ=="}])


class ExcelDelPanel(unittest.TestCase):
    def test_los_numeros_del_excel_coinciden_con_el_resumen(self):
        data = dataset()
        per, w = exportar.periodo(data, 7), notify.weekly(data)
        self.assertAlmostEqual(per["tot"]["spend"], w["spend"])
        self.assertAlmostEqual(per["tot"]["sales"], w["sales"])
        self.assertAlmostEqual(per["roas"], w["roas"])

    def test_las_publicaciones_suman_lo_de_cada_campana(self):
        per = exportar.periodo(dataset(), 30)
        for c in per["camps"]:
            if c["items"]:
                self.assertAlmostEqual(sum(o["spend"] for o in c["items"]), c["cur"]["spend"], places=4)

    def test_el_estado_es_el_mismo_criterio_del_panel(self):
        self.assertEqual(exportar.estado(0, 0, 0, 5, None), "sindatos")
        self.assertEqual(exportar.estado(0, 100, 0, 5, None), "revisar")
        self.assertEqual(exportar.estado(6, 100, 600, 5, None), "supera")
        self.assertEqual(exportar.estado(5, 100, 500, 5, None), "objetivo")
        self.assertEqual(exportar.estado(4, 100, 400, 5, 0.1), "mejorando")
        self.assertEqual(exportar.estado(4, 100, 400, 5, None), "oportunidad")
        self.assertEqual(exportar.estado(3, 100, 300, 5, None), "revisar")

    def test_acepta_periodos_raros_sin_romperse(self):
        for days, off in ((1, 0), (7, 0), (90, 0), (500, 0), (30, 999), (0, -5)):
            self.assertEqual(hojas(exportar.excel(dataset(), days, off)), HOJAS)

    def test_sin_campañas_el_excel_igual_se_genera(self):
        data = dataset()
        data["camps"], data["items"] = [], []
        self.assertEqual(hojas(exportar.excel(data, 7)), HOJAS)


class ClicsPorPublicacion(unittest.TestCase):
    def test_los_clics_de_cada_publicacion_son_su_parte_real_de_los_de_su_campana(self):
        import fake_ml
        from datetime import datetime
        from lumo import ads

        def get(path, params=None, version="2"):
            res = fake_ml.api_get(CFG, "AT", path, params, version)
            if path.endswith("/ad_groups/search"):
                rows = [r for r in res["results"] if r["campaign_id"] == 102 and r["status"] == "ACTIVE"]
                rows[0]["metrics"]["clicks"] = 30
                rows[1]["metrics"]["clicks"] = 10
            return res
        data = ads.build_dataset(get, fake_ml.ADVERTISER, datetime(2026, 10, 28, 15, 0).astimezone())
        mismos = [it for it in data["items"] if it["camp"] == 102]
        self.assertGreaterEqual(len(mismos), 2)
        self.assertAlmostEqual(sum(it["kc"] for it in mismos), 1.0)
        self.assertAlmostEqual(sum(it["kp"] for it in mismos), 1.0)
        self.assertEqual([round(x, 3) for x in sorted(it["kc"] for it in mismos)], [0.125, 0.375, 0.5])   # 10, 30 y 40 clics de 80
        self.assertTrue(all(it["kc"] == 0.0 for it in data["items"] if it["camp"] is None))   # sin campaña no hay parte que repartir

    def test_el_panel_ya_no_inventa_variaciones_en_los_clics(self):
        fuente = open("lumo/panel.html", encoding="utf-8").read()
        self.assertNotIn("0.12", fuente)
        self.assertNotIn("0.15", fuente)
        self.assertIn("o.clicks = c.cur.clicks * o.kc", fuente)

    def test_el_excel_trae_clics_ctr_y_cpc_por_publicacion(self):
        per = exportar.periodo(dataset(), 30)
        for o in per["items"]:
            self.assertGreaterEqual(o["clicks"], 0)
            self.assertAlmostEqual(o["cpc"], o["spend"] / o["clicks"] if o["clicks"] else 0)
        c = per["camps"][0]
        if c["items"]:
            self.assertAlmostEqual(sum(o["clicks"] for o in c["items"]), c["cur"]["clicks"], places=4)


class RutaExportar(unittest.TestCase):
    def setUp(self):
        self.app = create_app(CFG)
        self.client = self.app.test_client()
        self.engine = self.app.extensions["lumo_engine"]
        with Session(self.engine) as s:
            acc = save_tokens(s, CFG, 5, {"access_token": "AT", "refresh_token": "RT", "expires_in": 21600, "scope": "read"})
            acc.email = "ana@test.com"
            s.add(Access(user_id=5))
            s.add(PanelState(user_id=5, data=json.dumps({})))
            s.commit()
        patches = [mock.patch("lumo.ml.api_get", side_effect=lambda cfg, tok, path, params=None, version="2": fake_ml.api_get(cfg, tok, path, params, version)),
                   mock.patch("lumo.ml.advertisers", return_value=[fake_ml.ADVERTISER])]
        [p.start() for p in patches]
        self.addCleanup(mock.patch.stopall)

    def login(self):
        with self.client.session_transaction() as sess:
            sess["uid"] = 5

    def test_pide_ingresar(self):
        self.assertEqual(self.client.get("/api/exportar").status_code, 401)

    def test_sin_datos_todavia_avisa(self):
        self.login()
        self.assertEqual(self.client.get("/api/exportar").status_code, 404)

    def test_baja_el_excel_del_periodo_pedido(self):
        self.login()
        self.assertEqual(self.client.get("/api/datos").status_code, 200)
        r = self.client.get("/api/exportar?days=7&off=0")
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml.sheet", r.headers["Content-Type"])
        self.assertIn("attachment", r.headers["Content-Disposition"])
        self.assertIn(".xlsx", r.headers["Content-Disposition"])
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        self.assertEqual(hojas(r.data), HOJAS)

    def test_el_panel_trae_el_boton_de_descarga(self):
        fuente = open("lumo/panel.html", encoding="utf-8").read()
        self.assertIn("/api/exportar?days=", fuente)
        self.assertIn("Descargar Excel", fuente)


if __name__ == "__main__":
    unittest.main()
