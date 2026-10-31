import unittest
from pathlib import Path

import build_site
from lumo import create_app
from test_access import CFG


class PortadaEstatica(unittest.TestCase):
    def test_esta_al_dia_con_la_portada_de_la_app(self):
        """site/ se genera con build_site.py: si cambia la portada, los estilos o el logo, hay que volver a generarla."""
        self.assertEqual((build_site.OUT / "index.html").read_text(encoding="utf-8"), build_site.render(),
                         "La portada estática quedó vieja: correr `cd backend && python build_site.py`")
        for name in build_site.ASSETS:
            self.assertEqual((build_site.OUT / "static" / name).read_bytes(), (build_site.STATIC / name).read_bytes(), name)

    def test_los_botones_van_a_la_app_y_la_despiertan(self):
        html = build_site.render()
        self.assertNotIn('href="/connect"', html)
        self.assertIn('href="__APP_URL__/connect" data-app', html)
        self.assertIn("fetch(APP + '/healthz'", html)
        self.assertIn('id="waking"', html)

    def test_la_portada_de_la_app_no_trae_la_espera(self):
        html = create_app(CFG).test_client().get("/").get_data(as_text=True)
        self.assertIn('href="/connect" data-app', html)
        self.assertNotIn('id="waking"', html)


class App(unittest.TestCase):
    def test_healthz_se_puede_consultar_desde_la_portada(self):
        r = create_app(CFG).test_client().get("/healthz")
        self.assertEqual(r.get_json(), {"ok": True})
        self.assertEqual(r.headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_sin_sesion_la_app_manda_a_la_portada_estatica(self):
        r = create_app(dict(CFG, SITE_URL="https://lumo-sitio.onrender.com")).test_client().get("/")
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "https://lumo-sitio.onrender.com"))

    def test_las_invitaciones_siguen_en_la_app(self):
        r = create_app(dict(CFG, SITE_URL="https://lumo-sitio.onrender.com")).test_client().get("/invitacion/inventado")
        self.assertEqual(r.status_code, 404)

    def test_render_publica_la_carpeta_site(self):
        render = (Path(build_site.ROOT) / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("staticPublishPath: ./site", render)
        self.assertIn("__APP_URL__", render)


if __name__ == "__main__":
    unittest.main()
