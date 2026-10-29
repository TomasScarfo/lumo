import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import fake_ml
from sqlalchemy.orm import Session

from lumo import ads, create_app, ml
from lumo.models import Account, Snapshot, utcnow
from lumo.tokens import save_tokens

CFG = {"ML_CLIENT_ID": "123", "ML_CLIENT_SECRET": "secreto-de-prueba", "REDIRECT_URI": "https://lumo.test/callback",
       "ENCRYPTION_KEY": "clave-de-prueba-larga-y-aleatoria", "SECRET_KEY": "otra-clave-de-sesion", "DATABASE_URL": "sqlite://"}
NOW = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)  # 12:00 en Argentina


def fake_get(path, params=None, version="2"):
    return fake_ml.api_get(CFG, "AT", path, params, version)


class Dataset(unittest.TestCase):
    def setUp(self):
        self.data = ads.build_dataset(fake_get, fake_ml.ADVERTISER, NOW)

    def test_ventana_termina_ayer_y_antes_de_las_10_dos_dias_atras(self):
        self.assertEqual(ads.window_end(NOW).strftime("%Y-%m-%d"), "2026-10-27")
        temprano = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)  # 09:00 en Argentina
        self.assertEqual(ads.window_end(temprano).strftime("%Y-%m-%d"), "2026-10-26")

    def test_campanas_con_60_dias_y_objetivo_de_cada_una(self):
        camps = {c["id"]: c for c in self.data["camps"]}
        self.assertEqual(len(camps), 4)
        self.assertEqual(len(camps[101]["daily"]), 60)
        self.assertAlmostEqual(camps[101]["target"], 5.0)   # roas_target tal cual
        self.assertAlmostEqual(camps[102]["target"], 4.0)   # sin roas_target: ACOS objetivo 25 -> ROAS objetivo 4
        self.assertFalse(camps[101]["estTarget"])
        self.assertFalse(camps[102]["estTarget"])

    def test_campana_sin_objetivo_usa_uno_estimado_y_avisa(self):
        c = next(c for c in self.data["camps"] if c["id"] == 103)
        self.assertTrue(c["estTarget"])
        self.assertTrue(any("Sin objetivo" in n for n in self.data["notes"]))

    def test_porcentajes_de_mercado_libre_quedan_como_fraccion(self):
        c = self.data["camps"][0]
        self.assertAlmostEqual(c["lostB"], 0.20)
        self.assertAlmostEqual(c["lostR"], 0.415)
        self.assertAlmostEqual(c["share"], 0.385)

    def test_ventas_y_unidades_de_publicidad_suman_directas_e_indirectas(self):
        c = next(c for c in self.data["camps"] if c["id"] == 101)
        dia = next(d for d in c["daily"] if d["units"])
        self.assertGreaterEqual(dia["units"], 1)      # incluye la unidad indirecta
        self.assertGreaterEqual(dia["sales"], 12000.0)  # incluye el monto indirecto

    def test_participacion_de_cada_publicacion_suma_uno_por_campana(self):
        for cid in (101, 102):
            its = [i for i in self.data["items"] if i["camp"] == cid]
            self.assertTrue(its)
            self.assertAlmostEqual(sum(i["sp"] for i in its), 1.0)
            self.assertAlmostEqual(sum(i["sa"] for i in its), 1.0)

    def test_publicaciones_sin_publicidad_o_pausadas_no_pertenecen_a_campana(self):
        by = {i["id"]: i for i in self.data["items"]}
        self.assertIsNone(by["9006"]["camp"])   # sin campaña
        self.assertIsNone(by["9008"]["camp"])   # pausada
        self.assertEqual(by["9006"]["units"], 31)
        self.assertEqual(by["9006"]["prevUnits"], 21)
        self.assertEqual(by["9006"]["orgAmt"], 31 * 38000.0)
        self.assertEqual(by["9006"]["stock"], 7)
        self.assertAlmostEqual(by["9006"]["conv"], 31 / 800)
        self.assertEqual(by["9006"]["cat"], "Comedor")

    def test_grupos_de_familia_no_tienen_stock_ni_visitas(self):
        fam = next(i for i in self.data["items"] if i["id"] == "9009")
        self.assertEqual(fam["camp"], 102)
        self.assertIsNone(fam["stock"])
        self.assertIsNone(fam["conv"])

    def test_marca_por_defecto(self):
        by = {i["id"]: i for i in self.data["items"]}
        self.assertEqual(by["9001"]["brand"], "Nogal")
        self.assertEqual(by["9003"]["brand"], "Sin marca")

    def test_si_fallan_stock_y_visitas_el_panel_sigue_y_avisa(self):
        def parcial(path, params=None, version="2"):
            if path in ("/items", "/visits/items"):
                raise ml.MLError(500, "boom")
            return fake_get(path, params, version)
        data = ads.build_dataset(parcial, fake_ml.ADVERTISER, NOW)
        it = next(i for i in data["items"] if i["id"] == "9006")
        self.assertIsNone(it["stock"])
        self.assertIsNone(it["conv"])
        self.assertEqual(len(data["notes"]), 3)  # objetivo estimado + stock + visitas

    def test_usa_solo_las_rutas_vigentes_con_el_sitio(self):
        llamadas = []

        def get(path, params=None, version="2"):
            llamadas.append(path)
            return fake_get(path, params, version)
        ads.build_dataset(get, fake_ml.ADVERTISER, NOW)
        propias = [p for p in llamadas if p.startswith("/advertising")]
        self.assertTrue(propias)
        self.assertTrue(all(p.startswith("/advertising/MLA/") for p in propias), propias)
        self.assertFalse([p for p in propias if "/product_ads/items" in p or "/ads/search" in p])  # rutas dadas de baja


class Rutas(unittest.TestCase):
    def setUp(self):
        self.app = create_app(CFG)
        self.client = self.app.test_client()
        self.engine = self.app.extensions["lumo_engine"]
        with Session(self.engine) as s:
            save_tokens(s, CFG, 5, {"access_token": "AT", "refresh_token": "RT", "expires_in": 21600, "scope": "read"})
            s.commit()
        patches = [mock.patch("lumo.ml.api_get", side_effect=lambda cfg, tok, path, params=None, version="2": fake_ml.api_get(cfg, tok, path, params, version)),
                   mock.patch("lumo.ml.advertisers", return_value=[fake_ml.ADVERTISER])]
        self.api, self.advs = [p.start() for p in patches]
        self.addCleanup(mock.patch.stopall)

    def login(self, uid=5):
        with self.client.session_transaction() as sess:
            sess["uid"] = uid

    def test_panel_pide_ingresar(self):
        r = self.client.get("/panel")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/"))
        self.assertEqual(self.client.get("/api/datos").status_code, 401)
        self.assertEqual(self.client.post("/api/estado", json={}).status_code, 401)

    def test_quien_ya_entro_va_directo_al_panel(self):
        self.login()
        r = self.client.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/panel"))
        html = self.client.get("/panel").get_data(as_text=True)
        self.assertIn("/api/datos", html)
        self.assertNotIn("Casa Nogal", html)  # ya no trae los datos de ejemplo

    def test_sesion_de_una_cuenta_desconectada_no_entra(self):
        self.login()
        with Session(self.engine) as s:
            s.get(Account, 5).status = "needs_reconnect"
            s.commit()
        self.assertEqual(self.client.get("/panel").status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_salir_borra_la_sesion(self):
        self.login()
        self.client.get("/salir")
        self.assertEqual(self.client.get("/panel").status_code, 302)

    def test_datos_se_guardan_y_no_se_vuelven_a_pedir(self):
        self.login()
        r = self.client.get("/api/datos")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["advertiser"]["id"], 3646719)
        self.assertEqual(data["advertisers"][0]["name"], "Casa de prueba")
        self.assertEqual(data["estado"], {})
        n = self.api.call_count
        self.assertGreater(n, 5)
        self.client.get("/api/datos")
        self.assertEqual(self.api.call_count, n)  # segunda visita: sale de la copia guardada
        self.client.get("/api/datos?refresh=1")
        self.assertEqual(self.api.call_count, n)  # "Actualizar" dentro de los 10 minutos tampoco vuelve a pedir

    def test_actualizar_despues_de_10_minutos_vuelve_a_pedir(self):
        self.login()
        self.client.get("/api/datos")
        with Session(self.engine) as s:
            s.get(Snapshot, 5).fetched_at = utcnow() - timedelta(minutes=30)
            s.commit()
        n = self.api.call_count
        self.client.get("/api/datos?refresh=1")
        self.assertGreater(self.api.call_count, n)

    def test_copia_vieja_se_renueva(self):
        self.login()
        self.client.get("/api/datos")
        with Session(self.engine) as s:
            s.get(Snapshot, 5).fetched_at = utcnow() - timedelta(hours=4)
            s.commit()
        n = self.api.call_count
        self.client.get("/api/datos")
        self.assertGreater(self.api.call_count, n)

    def test_cuenta_sin_publicidad(self):
        self.login()
        self.advs.side_effect = ml.MLError(404, "not_found", "No permissions found")
        r = self.client.get("/api/datos")
        self.assertEqual((r.status_code, r.get_json()["error"]), (404, "no_ads"))

    def test_un_404_en_otra_ruta_no_se_confunde_con_falta_de_publicidad(self):
        self.login()

        def falla_campanas(cfg, tok, path, params=None, version="2"):
            if path.endswith("/campaigns/search"):
                exc = ml.MLError(404, "not_found", "ruta")
                exc.path = path
                raise exc
            return fake_ml.api_get(cfg, tok, path, params, version)
        self.api.side_effect = falla_campanas
        r = self.client.get("/api/datos")
        body = r.get_json()
        self.assertEqual((r.status_code, body["error"]), (502, "api"))
        self.assertIn("/campaigns/search", body["detail"])

    def test_sin_anunciantes(self):
        self.login()
        self.advs.return_value = []
        self.assertEqual(self.client.get("/api/datos").get_json()["error"], "no_ads")

    def test_permiso_denegado_y_limite_de_pedidos(self):
        self.login()
        self.advs.side_effect = ml.MLError(403, "forbidden")
        self.assertEqual(self.client.get("/api/datos").get_json()["error"], "forbidden")
        self.advs.side_effect = ml.MLError(429, "too_many_requests")
        r = self.client.get("/api/datos")
        self.assertEqual((r.status_code, r.get_json()["error"]), (503, "busy"))

    def test_cuenta_que_hay_que_reconectar(self):
        self.login()
        with Session(self.engine) as s:
            s.get(Account, 5).status = "needs_reconnect"
            s.commit()
        r = self.client.get("/api/datos")
        self.assertEqual((r.status_code, r.get_json()["error"]), (401, "reconnect"))

    def test_estado_se_guarda_y_vuelve_con_los_datos(self):
        self.login()
        estado = {"done": {"low-MLA5": True}, "actions": [{"id": "low-MLA5", "src": "tuya", "at": "2026-10-28"}], "custom": [{"id": "c1", "title": "Sacar fotos"}], "sw": {"sw1": False}, "otro": "se descarta"}
        self.assertEqual(self.client.post("/api/estado", json=estado).status_code, 200)
        data = self.client.get("/api/datos").get_json()
        self.assertEqual(data["estado"]["done"], {"low-MLA5": True})
        self.assertEqual(data["estado"]["custom"][0]["title"], "Sacar fotos")
        self.assertNotIn("otro", data["estado"])

    def test_estado_rechaza_formato_y_tamano(self):
        self.login()
        self.assertEqual(self.client.post("/api/estado", data="no es json").status_code, 400)
        self.assertEqual(self.client.post("/api/estado", json=[1, 2]).status_code, 400)
        grande = {"custom": [{"title": "x" * 1000}] * 500}
        self.assertEqual(self.client.post("/api/estado", json=grande).status_code, 413)

    def test_el_estado_de_una_cuenta_no_se_mezcla_con_otra(self):
        with Session(self.engine) as s:
            save_tokens(s, CFG, 6, {"access_token": "AT2", "refresh_token": "RT2", "expires_in": 21600, "scope": "read"})
            s.commit()
        self.login(5)
        self.client.post("/api/estado", json={"done": {"a": True}})
        self.login(6)
        self.assertEqual(self.client.get("/api/datos").get_json()["estado"], {})

    def test_respuestas_no_se_guardan_en_cache_del_navegador(self):
        self.login()
        self.assertEqual(self.client.get("/api/datos").headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.get("/panel").headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
