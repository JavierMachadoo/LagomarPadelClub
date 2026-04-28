"""
Tests para el sistema de identidad de jugadores:
- Jugador dataclass (to_dict / from_dict)
- JugadoresStorage (CRUD con mock Supabase y fallback JSON)
- Endpoints /api/jugadores
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from core.models import Jugador
from utils.jugadores_storage import JugadoresStorage


# ── Factories ─────────────────────────────────────────────────────────────────

def crear_jugador(
    id: str = "uuid-001",
    nombre: str = "Roberto",
    apellido: str = "Silva",
    telefono: str = None,
    email: str = None,
    usuario_id: str = None,
    activo: bool = True,
) -> Jugador:
    return Jugador(
        id=id,
        nombre=nombre,
        apellido=apellido,
        telefono=telefono,
        email=email,
        usuario_id=usuario_id,
        activo=activo,
    )


# ── Jugador.to_dict / from_dict ───────────────────────────────────────────────

class TestJugadorSerializacion:
    def test_to_dict_campos_obligatorios(self):
        j = crear_jugador()
        d = j.to_dict()
        assert d["id"] == "uuid-001"
        assert d["nombre"] == "Roberto"
        assert d["apellido"] == "Silva"
        assert d["activo"] is True

    def test_to_dict_campos_opcionales_none(self):
        j = crear_jugador()
        d = j.to_dict()
        assert d["telefono"] is None
        assert d["email"] is None
        assert d["usuario_id"] is None

    def test_to_dict_con_todos_los_campos(self):
        j = crear_jugador(
            telefono="600123456",
            email="roberto@club.com",
            usuario_id="auth-uuid-abc",
        )
        d = j.to_dict()
        assert d["telefono"] == "600123456"
        assert d["email"] == "roberto@club.com"
        assert d["usuario_id"] == "auth-uuid-abc"

    def test_from_dict_roundtrip_completo(self):
        j = crear_jugador(telefono="600123456", email="r@c.com", usuario_id="u-1")
        j2 = Jugador.from_dict(j.to_dict())
        assert j2.id == j.id
        assert j2.nombre == j.nombre
        assert j2.apellido == j.apellido
        assert j2.telefono == j.telefono
        assert j2.email == j.email
        assert j2.usuario_id == j.usuario_id
        assert j2.activo == j.activo

    def test_from_dict_campos_opcionales_ausentes(self):
        """from_dict no debe fallar si los campos opcionales no están en el dict."""
        data = {"id": "uuid-x", "nombre": "Ana", "apellido": "García"}
        j = Jugador.from_dict(data)
        assert j.telefono is None
        assert j.email is None
        assert j.usuario_id is None
        assert j.activo is True

    def test_from_dict_jugador_inactivo(self):
        j = crear_jugador(activo=False)
        j2 = Jugador.from_dict(j.to_dict())
        assert j2.activo is False


# ── JugadoresStorage (Supabase mockeado) ──────────────────────────────────────

def _make_storage_supabase():
    """Instancia JugadoresStorage con Supabase client mockeado."""
    s = JugadoresStorage.__new__(JugadoresStorage)
    s._sb = MagicMock()
    s._use_supabase = True
    s._jugadores_file = None
    return s


class TestJugadoresStorageSupabase:
    def test_crear_retorna_jugador_con_id(self):
        storage = _make_storage_supabase()
        storage._sb.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "new-uuid", "nombre": "Ana", "apellido": "López",
             "telefono": None, "email": None, "usuario_id": None,
             "activo": True, "created_at": "2026-04-28T00:00:00", "telefono_verificado": False}
        ]
        result = storage.crear(nombre="Ana", apellido="López")
        assert result["id"] == "new-uuid"
        assert result["nombre"] == "Ana"
        assert result["apellido"] == "López"

    def test_crear_nombre_apellido_se_envian_a_supabase(self):
        storage = _make_storage_supabase()
        storage._sb.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "x", "nombre": "Luis", "apellido": "Martínez",
             "telefono": "600", "email": None, "usuario_id": None,
             "activo": True, "created_at": None, "telefono_verificado": False}
        ]
        storage.crear(nombre="Luis", apellido="Martínez", telefono="600")
        call_args = storage._sb.table.return_value.insert.call_args[0][0]
        assert call_args["nombre"] == "Luis"
        assert call_args["apellido"] == "Martínez"
        assert call_args["telefono"] == "600"

    def test_listar_retorna_solo_activos(self):
        storage = _make_storage_supabase()
        storage._sb.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
            {"id": "a", "nombre": "A", "apellido": "B", "telefono": None,
             "email": None, "usuario_id": None, "activo": True,
             "created_at": None, "telefono_verificado": False},
        ]
        result = storage.listar()
        assert len(result) == 1
        assert result[0]["nombre"] == "A"

    def test_buscar_filtra_por_nombre(self):
        storage = _make_storage_supabase()
        jugador = {"id": "b", "nombre": "Roberto", "apellido": "Silva", "telefono": None,
                   "email": None, "usuario_id": None, "activo": True,
                   "created_at": None, "telefono_verificado": False}
        storage._sb.table.return_value.select.return_value.eq.return_value.or_.return_value.order.return_value.execute.return_value.data = [jugador]
        result = storage.buscar("roberto")
        assert len(result) == 1
        assert result[0]["nombre"] == "Roberto"

    def test_buscar_nombre_completo_supabase(self):
        """Buscar 'Roberto Silva' debe llamar or_ dos veces (una por palabra)."""
        storage = _make_storage_supabase()
        jugador = {"id": "b", "nombre": "Roberto", "apellido": "Silva", "telefono": None,
                   "email": None, "usuario_id": None, "activo": True,
                   "created_at": None, "telefono_verificado": False}
        # Con dos palabras, la cadena es: eq().or_().or_().order()
        storage._sb.table.return_value.select.return_value.eq.return_value \
            .or_.return_value.or_.return_value \
            .order.return_value.execute.return_value.data = [jugador]
        result = storage.buscar("Roberto Silva")
        assert len(result) == 1
        assert result[0]["apellido"] == "Silva"


# ── JugadoresStorage (fallback JSON) ─────────────────────────────────────────

class TestJugadoresStorageFallback:
    def test_crear_persiste_en_json(self, tmp_path):
        archivo = tmp_path / "jugadores.json"
        s = JugadoresStorage.__new__(JugadoresStorage)
        s._use_supabase = False
        s._jugadores_file = archivo

        result = s.crear(nombre="Pedro", apellido="Gómez")
        assert result["nombre"] == "Pedro"
        assert result["apellido"] == "Gómez"
        assert "id" in result

        data = json.loads(archivo.read_text())
        assert len(data) == 1
        assert data[0]["nombre"] == "Pedro"

    def test_listar_desde_json(self, tmp_path):
        archivo = tmp_path / "jugadores.json"
        archivo.write_text(json.dumps([
            {"id": "x1", "nombre": "Ana", "apellido": "García", "activo": True,
             "telefono": None, "email": None, "usuario_id": None,
             "created_at": None, "telefono_verificado": False},
            {"id": "x2", "nombre": "Luis", "apellido": "Pérez", "activo": False,
             "telefono": None, "email": None, "usuario_id": None,
             "created_at": None, "telefono_verificado": False},
        ]), encoding="utf-8")
        s = JugadoresStorage.__new__(JugadoresStorage)
        s._use_supabase = False
        s._jugadores_file = archivo

        result = s.listar()
        assert len(result) == 1
        assert result[0]["nombre"] == "Ana"

    def test_buscar_nombre_completo_json(self, tmp_path):
        """Buscar 'Ana García' debe encontrar al jugador aunque nombre y apellido estén separados."""
        archivo = tmp_path / "jugadores.json"
        archivo.write_text(json.dumps([
            {"id": "x1", "nombre": "Ana", "apellido": "García", "activo": True,
             "telefono": None, "email": None, "usuario_id": None,
             "created_at": None, "telefono_verificado": False},
        ]), encoding="utf-8")
        s = JugadoresStorage.__new__(JugadoresStorage)
        s._use_supabase = False
        s._jugadores_file = archivo

        result = s.buscar("Ana García")
        assert len(result) == 1
        assert result[0]["apellido"] == "García"

    def test_json_archivo_no_existe_retorna_lista_vacia(self, tmp_path):
        archivo = tmp_path / "no_existe.json"
        s = JugadoresStorage.__new__(JugadoresStorage)
        s._use_supabase = False
        s._jugadores_file = archivo

        result = s.listar()
        assert result == []


# ── Endpoints /api/jugadores ──────────────────────────────────────────────────

JUGADOR_DICT = {
    "id": "uuid-test", "nombre": "Roberto", "apellido": "Silva",
    "telefono": None, "email": None, "usuario_id": None,
    "activo": True, "created_at": None, "telefono_verificado": False,
}


@pytest.fixture
def mock_jugadores_storage():
    with patch("api.routes.jugadores.jugadores_storage") as mock:
        yield mock


class TestPostJugadores:
    def test_crear_jugador_valido_retorna_201(self, admin_cookie, mock_jugadores_storage):
        mock_jugadores_storage.crear.return_value = JUGADOR_DICT
        resp = admin_cookie.post("/api/jugadores", json={"nombre": "Roberto", "apellido": "Silva"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["id"] == "uuid-test"
        assert data["nombre"] == "Roberto"

    def test_crear_jugador_nombre_vacio_retorna_400(self, admin_cookie, mock_jugadores_storage):
        resp = admin_cookie.post("/api/jugadores", json={"nombre": "", "apellido": "Silva"})
        assert resp.status_code == 400

    def test_crear_jugador_apellido_ausente_retorna_400(self, admin_cookie, mock_jugadores_storage):
        resp = admin_cookie.post("/api/jugadores", json={"nombre": "Roberto"})
        assert resp.status_code == 400


class TestGetJugadores:
    def test_listar_retorna_jugadores(self, admin_cookie, mock_jugadores_storage):
        mock_jugadores_storage.listar.return_value = [JUGADOR_DICT]
        resp = admin_cookie.get("/api/jugadores")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["jugadores"]) == 1
        assert data["jugadores"][0]["nombre"] == "Roberto"

    def test_buscar_con_query_llama_buscar(self, admin_cookie, mock_jugadores_storage):
        mock_jugadores_storage.buscar.return_value = [JUGADOR_DICT]
        resp = admin_cookie.get("/api/jugadores?q=rob")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["jugadores"]) == 1
        mock_jugadores_storage.buscar.assert_called_once_with("rob")

    def test_listar_sin_query_llama_listar(self, admin_cookie, mock_jugadores_storage):
        mock_jugadores_storage.listar.return_value = []
        resp = admin_cookie.get("/api/jugadores")
        assert resp.status_code == 200
        mock_jugadores_storage.listar.assert_called_once()


# ── POST /api/agregar-pareja con jugador_ids ──────────────────────────────────

class TestAgregarParejaConJugadorIds:
    def test_agregar_pareja_acepta_jugador_ids_opcionales(self, admin_cookie, mock_storage):
        mock_storage.cargar.return_value = {
            "parejas": [], "resultado_algoritmo": None, "num_canchas": 2,
            "estado": "espera", "tipo_torneo": "fin1", "fixtures_finales": {},
            "calendario_finales": None, "nombre": "Test", "version": 1,
            "torneo_id": "t-1",
        }
        resp = admin_cookie.post("/api/agregar-pareja", json={
            "nombre": "Silva / García",
            "telefono": "600",
            "categoria": "Cuarta",
            "franjas": ["Sábado 09:00"],
            "jugador1_id": "uuid-j1",
            "jugador2_id": "uuid-j2",
        })
        assert resp.status_code == 200

    def test_agregar_pareja_sin_jugador_ids_sigue_funcionando(self, admin_cookie, mock_storage):
        mock_storage.cargar.return_value = {
            "parejas": [], "resultado_algoritmo": None, "num_canchas": 2,
            "estado": "espera", "tipo_torneo": "fin1", "fixtures_finales": {},
            "calendario_finales": None, "nombre": "Test", "version": 1,
            "torneo_id": "t-1",
        }
        resp = admin_cookie.post("/api/agregar-pareja", json={
            "jugador1": "Roberto",
            "jugador2": "Carlos",
            "telefono": "600",
            "categoria": "Cuarta",
            "franjas": ["Sábado 09:00"],
        })
        assert resp.status_code == 200

    def test_agregar_pareja_persiste_jugador_ids(self, admin_cookie, mock_storage):
        mock_storage.cargar.return_value = {
            "parejas": [], "resultado_algoritmo": None, "num_canchas": 2,
            "estado": "espera", "tipo_torneo": "fin1", "fixtures_finales": {},
            "calendario_finales": None, "nombre": "Test", "version": 1,
            "torneo_id": "t-1",
        }
        resp = admin_cookie.post("/api/agregar-pareja", json={
            "nombre": "Silva / García",
            "telefono": "600",
            "categoria": "Cuarta",
            "franjas": ["Sábado 09:00"],
            "jugador1_id": "uuid-j1",
            "jugador2_id": "uuid-j2",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["pareja"]["jugador1_id"] == "uuid-j1"
        assert data["pareja"]["jugador2_id"] == "uuid-j2"
