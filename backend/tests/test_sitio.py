import json
import re
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
        self.assertEqual((build_site.OUT / "404.html").read_text(encoding="utf-8"), build_site.render_404(),
                         "La página 404 de la portada quedó vieja: correr `cd backend && python build_site.py`")
        self.assertEqual((build_site.OUT / "robots.txt").read_text(encoding="utf-8"), build_site.robots())
        self.assertEqual((build_site.OUT / "sitemap.xml").read_text(encoding="utf-8"), build_site.sitemap())
        for path, html in build_site.paginas_guias().items():
            self.assertEqual((build_site.OUT / path).read_text(encoding="utf-8"), html, path)
        for name in build_site.ASSETS:
            self.assertEqual((build_site.OUT / "static" / name).read_bytes(), (build_site.STATIC / name).read_bytes(), name)

    def test_los_botones_van_a_la_app_y_la_despiertan(self):
        html = build_site.render()
        self.assertNotIn('href="/connect"', html)
        self.assertIn('href="__APP_URL__/entrar?plan=annual" data-app', html)
        self.assertIn('href="__APP_URL__/entrar" data-app', html)
        self.assertIn("fetch(APP + '/healthz'", html)
        self.assertIn('id="waking"', html)

    def test_buscadores(self):
        """Google necesita la dirección canónica, una imagen con dirección completa, el mapa del sitio y los datos estructurados."""
        html = build_site.render()
        self.assertIn('<link rel="canonical" href="https://lumoads.com.ar/">', html)
        self.assertIn('<meta property="og:image" content="https://lumoads.com.ar/static/logo.png">', html)
        self.assertIn('content="index,follow', html)
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        tipos = {n["@type"]: n for n in ld["@graph"]}
        self.assertEqual(set(tipos), {"Organization", "WebSite", "SoftwareApplication", "FAQPage"})
        preguntas = tipos["FAQPage"]["mainEntity"]
        self.assertEqual(len(preguntas), html.count("<details><summary>"))
        self.assertNotIn("<span", json.dumps(preguntas))
        self.assertIn("Sitemap: https://lumoads.com.ar/sitemap.xml", build_site.robots())
        self.assertIn("<loc>https://lumoads.com.ar/</loc>", build_site.sitemap())

    def test_guias(self):
        """Cada guía: su dirección canónica, sus datos estructurados, enlaces a las demás y a los planes, y en el mapa del sitio."""
        from lumo import guias
        client = create_app(CFG).test_client()
        portada, mapa = build_site.render(), build_site.sitemap()
        self.assertIn('href="/guias/"', portada)
        self.assertEqual(client.get("/guias/").status_code, 200)
        self.assertEqual(client.get("/guias/inventada/").status_code, 404)
        for g in guias.GUIAS:
            url = "https://lumoads.com.ar/guias/%s/" % g["slug"]
            html = build_site.render_guia(g["slug"])
            self.assertIn('<link rel="canonical" href="%s">' % url, html)
            self.assertIn("<h1>%s</h1>" % g["titulo"], html)
            self.assertIn('href="/#precio"', html)
            self.assertNotIn("__APP_URL__", html)
            ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
            self.assertEqual({n["@type"] for n in ld["@graph"]}, {"BreadcrumbList", "Article"})
            for otra in guias.GUIAS:
                if otra is not g:
                    self.assertIn('href="/guias/%s/"' % otra["slug"], html)
            self.assertIn("<loc>%s</loc>" % url, mapa)
            self.assertIn('href="/guias/%s/"' % g["slug"], portada)
            self.assertEqual(client.get("/guias/%s/" % g["slug"]).get_data(as_text=True), html)

    def test_las_invitaciones_no_se_indexan(self):
        html = create_app(CFG).test_client().get("/invitacion/inventado").get_data(as_text=True)
        self.assertIn('<meta name="robots" content="noindex">', html)
        self.assertNotIn("application/ld+json", html)

    def test_la_portada_de_la_app_no_trae_la_espera(self):
        html = create_app(CFG).test_client().get("/").get_data(as_text=True)
        self.assertIn('href="/entrar?plan=annual" data-app', html)
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
