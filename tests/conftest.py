"""
Fixtures compartidos para tests del proyecto.

- app / client: test client de Flask con TESTING=True
- admin_headers: JWT válido de admin inyectado como cookie
- mock_storage: parcha utils.torneo_storage.storage para no tocar Supabase ni JSON
- Factories: crear_pareja(), crear_grupo(), crear_resultado_dict()
"""

import pytest
from unittest.mock import MagicMock, patch

from main import crear_app
from core.models import Pareja, Grupo, ResultadoPartido


# ── Aplicación Flask ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    flask_app = crear_app()
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key"
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ── Auth ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_token(app):
    """Genera un JWT de admin válido para la SECRET_KEY de test."""
    with app.app_context():
        token = app.jwt_handler.generar_token({
            "authenticated": True,
            "role": "admin",
            "username": "admin",
        })
    return token


@pytest.fixture
def admin_cookie(client, admin_token):
    """Configura la cookie 'token' en el test client."""
    client.set_cookie("token", admin_token)
    return client


# ── Storage mock ──────────────────────────────────────────────────────────────

TORNEO_BASE = {
    "parejas": [],
    "resultado_algoritmo": None,
    "num_canchas": 2,
    "estado": "espera",
    "tipo_torneo": "fin1",
    "fixtures_finales": {},
    "calendario_finales": None,
    "nombre": "Torneo Test",
    "version": 1,
    "torneo_id": "test-torneo-id",
}


@pytest.fixture
def mock_storage():
    """Parcha la instancia global de storage para no tocar Supabase ni JSON."""
    with patch("utils.torneo_storage.storage") as mock:
        torneo = TORNEO_BASE.copy()
        mock.cargar.return_value = torneo
        mock.guardar_con_version.return_value = None
        mock.get_fase.return_value = "espera"
        mock.get_torneo_id.return_value = "test-torneo-id"
        yield mock


# ── Factories ─────────────────────────────────────────────────────────────────

def crear_pareja(
    id: int = 1,
    nombre: str = None,
    categoria: str = "Cuarta",
    franjas: list = None,
    telefono: str = "600000000",
) -> Pareja:
    return Pareja(
        id=id,
        nombre=nombre or f"Pareja {id}",
        telefono=telefono,
        categoria=categoria,
        franjas_disponibles=franjas or ["Sábado 09:00"],
    )


def crear_grupo(
    grupo_id: int = 1,
    categoria: str = "Cuarta",
    franja: str = "Sábado 09:00",
    num_parejas: int = 3,
) -> Grupo:
    parejas = [
        crear_pareja(id=grupo_id * 10 + i, categoria=categoria, franjas=[franja])
        for i in range(1, num_parejas + 1)
    ]
    grupo = Grupo(id=grupo_id, categoria=categoria, franja_horaria=franja)
    for p in parejas:
        grupo.agregar_pareja(p)
    if num_parejas == 3:
        grupo.generar_partidos()
    return grupo


def crear_grupo_dict(
    grupo_id: int = 1,
    categoria: str = "Cuarta",
    franja: str = "Sábado 09:00",
    num_parejas: int = 3,
) -> dict:
    """Versión dict del grupo — como viene de resultado_algoritmo."""
    grupo = crear_grupo(grupo_id, categoria, franja, num_parejas)
    d = grupo.to_dict()
    d["score"] = 3.0
    d["cancha"] = 1
    d["resultados_completos"] = False
    return d


def crear_resultado_dict(
    pareja1_id: int,
    pareja2_id: int,
    games_s1_p1: int = 6,
    games_s1_p2: int = 3,
    games_s2_p1: int = 6,
    games_s2_p2: int = 3,
) -> dict:
    return {
        "pareja1_id": pareja1_id,
        "pareja2_id": pareja2_id,
        "sets_pareja1": 2,
        "sets_pareja2": 0,
        "games_set1_pareja1": games_s1_p1,
        "games_set1_pareja2": games_s1_p2,
        "games_set2_pareja1": games_s2_p1,
        "games_set2_pareja2": games_s2_p2,
        "tiebreak_pareja1": None,
        "tiebreak_pareja2": None,
    }
