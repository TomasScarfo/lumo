import unittest
from unittest import mock

from lumo import notify
from test_access import CFG

BREVO = dict(CFG, BREVO_API_KEY="xkeysib-secreta", MAIL_FROM="lumoads.ml@gmail.com", SMTP_PASSWORD="", SMTP_USER="")


def resp(status, body=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = body if body is not None else {}
    return r


class EnvioPorBrevo(unittest.TestCase):
    def test_con_la_clave_de_brevo_el_envio_queda_habilitado_sin_smtp(self):
        self.assertTrue(notify.enabled(BREVO))
        self.assertFalse(notify.enabled(dict(BREVO, BREVO_API_KEY="")))

    def test_sin_remitente_no_se_habilita(self):
        self.assertFalse(notify.enabled(dict(BREVO, MAIL_FROM="", SMTP_USER="")))

    def test_el_remitente_por_defecto_es_el_de_smtp(self):
        self.assertTrue(notify.enabled(dict(BREVO, MAIL_FROM="", SMTP_USER="lumoads.ml@gmail.com")))

    def test_manda_el_mail_a_la_api_de_brevo_por_https(self):
        with mock.patch("lumo.notify.requests.post", return_value=resp(201, {"messageId": "x"})) as post, \
                mock.patch("lumo.notify.smtplib.SMTP") as smtp:
            notify.send_mail(BREVO, "cliente@ejemplo.com", "Asunto", "texto", "<p>html</p>")
        smtp.assert_not_called()
        args, kw = post.call_args
        self.assertEqual(args[0], "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(kw["headers"]["api-key"], "xkeysib-secreta")
        self.assertEqual(kw["json"]["sender"], {"name": "Lumo", "email": "lumoads.ml@gmail.com"})
        self.assertEqual(kw["json"]["to"], [{"email": "cliente@ejemplo.com"}])
        self.assertEqual((kw["json"]["subject"], kw["json"]["textContent"], kw["json"]["htmlContent"]), ("Asunto", "texto", "<p>html</p>"))

    def test_si_brevo_rechaza_el_envio_se_avisa_con_el_motivo_y_sin_la_clave(self):
        with mock.patch("lumo.notify.requests.post", return_value=resp(400, {"code": "invalid_parameter", "message": "sender no validado"})):
            with self.assertRaises(notify.MailError) as cm:
                notify.send_mail(BREVO, "a@b.com", "s", "t", "h")
        self.assertIn("400", str(cm.exception))
        self.assertIn("sender no validado", str(cm.exception))
        self.assertNotIn("xkeysib", str(cm.exception))

    def test_sin_clave_de_brevo_sigue_usando_smtp(self):
        with mock.patch("lumo.notify.smtplib.SMTP") as smtp, mock.patch("lumo.notify.requests.post") as post:
            notify.send_mail(dict(CFG, SMTP_HOST="smtp.x", SMTP_PORT="587", SMTP_USER="u@x.com", SMTP_PASSWORD="p"), "a@b.com", "s", "t", "h")
        post.assert_not_called()
        smtp.assert_called_once()

    def test_el_registro_incluye_el_motivo_del_proveedor_pero_no_el_de_otros_errores(self):
        self.assertIn("sender no validado", notify.why(notify.MailError("Brevo respondió 400: sender no validado")))
        self.assertEqual(notify.why(ValueError("dato privado")), "ValueError")


if __name__ == "__main__":
    unittest.main()
