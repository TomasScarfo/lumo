import unittest
from unittest import mock

from lumo import create_app
from test_access import CFG


class PaginaDeError(unittest.TestCase):
    def setUp(self):
        self.app = create_app(CFG)
        self.client = self.app.test_client()

    def test_una_direccion_que_no_existe_muestra_la_pagina_404_de_lumo(self):
        r = self.client.get("/esto-no-existe")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 404)
        self.assertIn("No encontramos esta página", html)
        self.assertIn("/static/logo.svg", html)
        self.assertIn("Volver al inicio", html)
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_un_metodo_no_permitido_tambien_usa_la_pagina_de_lumo(self):
        r = self.client.post("/healthz")
        self.assertEqual(r.status_code, 405)
        self.assertIn("Esa acción no está disponible acá", r.get_data(as_text=True))

    def test_la_administracion_no_se_delata_a_quien_no_administra(self):
        r = self.client.get("/admin")
        self.assertIn(r.status_code, (302, 404))
        if r.status_code == 404:
            self.assertIn("No encontramos esta página", r.get_data(as_text=True))

    def test_las_rutas_api_responden_json(self):
        r = self.client.get("/api/no-existe")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["status"], 404)

    def test_un_error_inesperado_muestra_pagina_amable_con_codigo_y_sin_detalles(self):
        with mock.patch("lumo.ads.build_dataset", side_effect=RuntimeError("secreto-interno")):
            @self.app.get("/boom")
            def boom():
                raise RuntimeError("secreto-interno")
            r = self.client.get("/boom")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 500)
        self.assertIn("Algo salió mal de nuestro lado", html)
        self.assertIn("Código del problema", html)
        self.assertNotIn("secreto-interno", html)
        self.assertNotIn("Traceback", html)
        self.assertIn("mailto:", html)

    def test_las_redirecciones_no_se_convierten_en_error(self):
        r = self.client.get("/salir")
        self.assertEqual(r.status_code, 302)


if __name__ == "__main__":
    unittest.main()
