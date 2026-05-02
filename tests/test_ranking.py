"""Tests para el blueprint de ranking de jugadores."""

import pytest
from unittest.mock import MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_calcular():
    with patch("api.routes.ranking._calcular_ranking") as mock:
        yield mock


RANKING_FIXTURE = {
    "Cuarta": [
        {"posicion": 1, "jugador_id": "j1", "nombre": "Ana", "apellido": "García",
         "puntos": 200, "torneos": 2, "mejor_resultado": "campeon"},
        {"posicion": 2, "jugador_id": "j2", "nombre": "Luis", "apellido": "Pérez",
         "puntos": 100, "torneos": 1, "mejor_resultado": "serie"},
    ],
    "Tercera": [
        {"posicion": 1, "jugador_id": "j3", "nombre": "Roberto", "apellido": "Silva",
         "puntos": 150, "torneos": 1, "mejor_resultado": "semifinal"},
    ],
}


def _make_sb(torneos_data, puntos_data, jugadores_data):
    """Mock de Supabase que diferencia por nombre de tabla."""
    sb = MagicMock()

    def table_side_effect(table_name):
        m = MagicMock()
        if table_name == "torneos":
            m.select.return_value.eq.return_value.execute.return_value.data = torneos_data
        elif table_name == "puntos_jugador":
            m.select.return_value.in_.return_value.execute.return_value.data = puntos_data
        elif table_name == "jugadores":
            m.select.return_value.in_.return_value.execute.return_value.data = jugadores_data
        return m

    sb.table.side_effect = table_side_effect
    return sb


# ── GET /api/ranking ──────────────────────────────────────────────────────────

class TestApiRanking:
    def test_retorna_200_con_clave_ranking(self, admin_cookie, mock_calcular):
        mock_calcular.return_value = RANKING_FIXTURE
        resp = admin_cookie.get("/api/ranking")
        assert resp.status_code == 200
        assert "ranking" in resp.get_json()

    def test_retorna_categorias(self, admin_cookie, mock_calcular):
        mock_calcular.return_value = RANKING_FIXTURE
        data = admin_cookie.get("/api/ranking").get_json()
        assert "Cuarta" in data["ranking"]
        assert "Tercera" in data["ranking"]

    def test_jugadores_ordenados_por_puntos(self, admin_cookie, mock_calcular):
        mock_calcular.return_value = RANKING_FIXTURE
        cuarta = admin_cookie.get("/api/ranking").get_json()["ranking"]["Cuarta"]
        assert cuarta[0]["puntos"] >= cuarta[1]["puntos"]
        assert cuarta[0]["posicion"] == 1

    def test_ranking_vacio_cuando_no_hay_datos(self, admin_cookie, mock_calcular):
        mock_calcular.return_value = {}
        data = admin_cookie.get("/api/ranking").get_json()
        assert data["ranking"] == {}

    def test_error_interno_retorna_500(self, admin_cookie, mock_calcular):
        mock_calcular.side_effect = Exception("db error")
        resp = admin_cookie.get("/api/ranking")
        assert resp.status_code == 500


# ── GET /ranking (vista pública) ──────────────────────────────────────────────

class TestRankingPublico:
    def test_renderiza_con_datos(self, admin_cookie, mock_calcular):
        mock_calcular.return_value = RANKING_FIXTURE
        resp = admin_cookie.get("/ranking")
        assert resp.status_code == 200

    def test_renderiza_con_ranking_vacio(self, admin_cookie, mock_calcular):
        mock_calcular.return_value = {}
        resp = admin_cookie.get("/ranking")
        assert resp.status_code == 200


# ── _calcular_ranking (lógica de agregación) ─────────────────────────────────

class TestCalcularRankingLogica:
    def test_retorna_vacio_sin_supabase(self):
        from api.routes.ranking import _calcular_ranking
        with patch("api.routes.ranking._use_supabase", return_value=False):
            assert _calcular_ranking() == {}

    def test_retorna_vacio_sin_torneos_finalizados(self):
        from api.routes.ranking import _calcular_ranking
        sb = _make_sb(torneos_data=[], puntos_data=[], jugadores_data=[])
        with patch("api.routes.ranking._use_supabase", return_value=True), \
             patch("api.routes.ranking._sb", return_value=sb):
            assert _calcular_ranking() == {}

    def test_suma_puntos_del_mismo_jugador_en_distintos_torneos(self):
        from api.routes.ranking import _calcular_ranking
        sb = _make_sb(
            torneos_data=[{"id": "t1"}, {"id": "t2"}],
            puntos_data=[
                {"jugador_id": "j1", "torneo_id": "t1", "categoria": "Cuarta",
                 "puntos": 100, "concepto": "serie"},
                {"jugador_id": "j1", "torneo_id": "t2", "categoria": "Cuarta",
                 "puntos": 60, "concepto": "serie"},
            ],
            jugadores_data=[{"id": "j1", "nombre": "Ana", "apellido": "García"}],
        )
        with patch("api.routes.ranking._use_supabase", return_value=True), \
             patch("api.routes.ranking._sb", return_value=sb):
            result = _calcular_ranking()
        assert result["Cuarta"][0]["puntos"] == 160

    def test_mejor_resultado_toma_concepto_mas_alto(self):
        from api.routes.ranking import _calcular_ranking
        sb = _make_sb(
            torneos_data=[{"id": "t1"}, {"id": "t2"}],
            puntos_data=[
                {"jugador_id": "j1", "torneo_id": "t1", "categoria": "Cuarta",
                 "puntos": 50, "concepto": "serie"},
                {"jugador_id": "j1", "torneo_id": "t2", "categoria": "Cuarta",
                 "puntos": 100, "concepto": "campeon"},
            ],
            jugadores_data=[{"id": "j1", "nombre": "Ana", "apellido": "García"}],
        )
        with patch("api.routes.ranking._use_supabase", return_value=True), \
             patch("api.routes.ranking._sb", return_value=sb):
            result = _calcular_ranking()
        assert result["Cuarta"][0]["mejor_resultado"] == "campeon"

    def test_ordena_por_puntos_descendente(self):
        from api.routes.ranking import _calcular_ranking
        sb = _make_sb(
            torneos_data=[{"id": "t1"}],
            puntos_data=[
                {"jugador_id": "j1", "torneo_id": "t1", "categoria": "Cuarta",
                 "puntos": 50, "concepto": "serie"},
                {"jugador_id": "j2", "torneo_id": "t1", "categoria": "Cuarta",
                 "puntos": 200, "concepto": "campeon"},
            ],
            jugadores_data=[
                {"id": "j1", "nombre": "Luis", "apellido": "Pérez"},
                {"id": "j2", "nombre": "Ana", "apellido": "García"},
            ],
        )
        with patch("api.routes.ranking._use_supabase", return_value=True), \
             patch("api.routes.ranking._sb", return_value=sb):
            result = _calcular_ranking()
        cuarta = result["Cuarta"]
        assert cuarta[0]["jugador_id"] == "j2"
        assert cuarta[0]["posicion"] == 1
        assert cuarta[1]["posicion"] == 2
