"""Cliente mínimo de la API de Mercado Libre: autorización, tokens y anunciantes."""
import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import requests

TIMEOUT = 15
TIMEOUT_API = 30


class MLError(Exception):
    def __init__(self, status: int, code: str, message: str = ""):
        super().__init__("%s %s %s" % (status, code, message))
        self.status = status
        self.code = code
        self.message = message
        self.path = ""


def new_pkce():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def auth_url(cfg: dict, state: str, challenge: str) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": cfg["ML_CLIENT_ID"],
            "redirect_uri": cfg["REDIRECT_URI"],
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return "%s/authorization?%s" % (cfg["ML_AUTH_BASE"], query)


def _token_request(cfg: dict, data: dict) -> dict:
    payload = dict(data, client_id=cfg["ML_CLIENT_ID"], client_secret=cfg["ML_CLIENT_SECRET"])
    resp = requests.post(
        cfg["ML_API_BASE"] + "/oauth/token",
        data=payload,
        headers={"accept": "application/json", "content-type": "application/x-www-form-urlencoded"},
        timeout=TIMEOUT,
    )
    body = _json(resp)
    if resp.status_code != 200:
        # No se registra el cuerpo completo: no debe filtrarse ningún secreto a los logs.
        raise MLError(resp.status_code, str(body.get("error", "error")), str(body.get("message", "")))
    return body


def exchange_code(cfg: dict, code: str, verifier: str) -> dict:
    return _token_request(
        cfg,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg["REDIRECT_URI"],
            "code_verifier": verifier,
        },
    )


def refresh(cfg: dict, refresh_token: str) -> dict:
    return _token_request(cfg, {"grant_type": "refresh_token", "refresh_token": refresh_token})


def advertisers(cfg: dict, access_token: str) -> list:
    resp = requests.get(
        cfg["ML_API_BASE"] + "/advertising/advertisers",
        params={"product_id": "PADS"},
        headers={"Authorization": "Bearer " + access_token, "Content-Type": "application/json", "Api-Version": "1"},
        timeout=TIMEOUT,
    )
    body = _json(resp)
    if resp.status_code != 200:
        raise MLError(resp.status_code, str(body.get("error", "error")), str(body.get("message", "")))
    return body.get("advertisers", [])


def api_get(cfg: dict, access_token: str, path: str, params: dict = None, version: str = "2"):
    """GET autenticado. Devuelve el JSON (dict o lista). Reintenta dos veces si Mercado Libre pide bajar el ritmo (429)."""
    headers = {"Authorization": "Bearer " + access_token, "Content-Type": "application/json"}
    if version:
        headers["api-version"] = version
    for attempt in range(3):
        resp = requests.get(cfg["ML_API_BASE"] + path, params=params, headers=headers, timeout=TIMEOUT_API)
        if resp.status_code == 429 and attempt < 2:
            time.sleep(1.5 * (attempt + 1))
            continue
        break
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code != 200:
        err = body if isinstance(body, dict) else {}
        exc = MLError(resp.status_code, str(err.get("error", "error")), str(err.get("message", "")))
        exc.path = path
        raise exc
    return body


def _json(resp) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}
