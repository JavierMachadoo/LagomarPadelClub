"""Tests para POST /api/admin/toggle-finales."""
import pytest
from unittest.mock import patch
from utils.torneo_storage import ConflictError

_BASE = {
    "parejas": [],
    "resultado_algoritmo": None,
    "fase": "torneo",
    "tipo_torneo": "fin1",
    "fixtures_finales": {},
    "calendario_finales": {},
    "nombre": "Test",
    "version": 1,
    "torneo_id": "test-id",
}

URL = "/api/admin/toggle-finales"


def test_toggle_activa_false(admin_cookie):
    torneo = {**_BASE, "mostrar_finales": True}
    with patch("api.routes.historial.storage") as mock:
        mock.cargar.return_value = torneo
        mock.guardar_con_version.return_value = None
        resp = admin_cookie.post(URL)
    assert resp.status_code == 200
    assert resp.get_json()["mostrar_finales"] is False


def test_toggle_activa_true(admin_cookie):
    torneo = {**_BASE, "mostrar_finales": False}
    with patch("api.routes.historial.storage") as mock:
        mock.cargar.return_value = torneo
        mock.guardar_con_version.return_value = None
        resp = admin_cookie.post(URL)
    assert resp.status_code == 200
    assert resp.get_json()["mostrar_finales"] is True


def test_toggle_default_true(admin_cookie):
    """Sin campo mostrar_finales en el blob, parte de True y retorna False."""
    torneo = {**_BASE}
    with patch("api.routes.historial.storage") as mock:
        mock.cargar.return_value = torneo
        mock.guardar_con_version.return_value = None
        resp = admin_cookie.post(URL)
    assert resp.status_code == 200
    assert resp.get_json()["mostrar_finales"] is False


def test_toggle_sin_auth(client):
    resp = client.post(URL)
    assert resp.status_code == 302  # before_request redirige a login


def test_toggle_conflict(admin_cookie):
    torneo = {**_BASE, "mostrar_finales": True}
    with patch("api.routes.historial.storage") as mock:
        mock.cargar.return_value = torneo
        mock.guardar_con_version.side_effect = ConflictError("concurrent write")
        resp = admin_cookie.post(URL)
    assert resp.status_code == 409
