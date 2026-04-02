"""
Tests unitarios para fixture_service.

Mockea storage para no tocar Supabase ni JSON.
"""

import pytest
from unittest.mock import patch, MagicMock, call

from services.fixture_service import (
    obtener_o_generar_fixtures,
    obtener_fixture_categoria,
    regenerar_todos_fixtures,
    actualizar_ganador,
    guardar_resultado_final,
    obtener_calendario,
    generar_al_activar_torneo,
    _fixture_es_consistente,
    _buscar_partido_en_fixtures,
)
from services.exceptions import ServiceError
from tests.conftest import crear_grupo_dict


# ── Fixtures locales ──────────────────────────────────────────────────────────

def _torneo_con_resultado(num_grupos: int = 3) -> dict:
    return {
        'resultado_algoritmo': {
            'grupos_por_categoria': {
                'Cuarta': [crear_grupo_dict(grupo_id=i) for i in range(1, num_grupos + 1)]
            }
        },
        'fixtures_finales': {},
        'calendario_finales': None,
        'fase': 'inscripcion',
    }


def _fixture_tres_grupos() -> dict:
    """Fixture estructuralmente correcto para 3 grupos."""
    return {
        'cuartos': [
            {'id': 'p1', 'pareja1': {'id': 1}, 'pareja2': {'id': 2}},
            {'id': 'p2', 'pareja1': {'id': 3}, 'pareja2': {'id': 4}},
        ],
        'octavos': [],
        'semifinales': [],
        'final': {'id': 'pf', 'pareja1': {}, 'pareja2': {}},
    }


# ── _fixture_es_consistente ───────────────────────────────────────────────────

class TestFixtureEsConsistente:

    def test_tres_grupos_dos_cuartos(self):
        fixture = {'cuartos': [{}, {}], 'octavos': []}
        assert _fixture_es_consistente(fixture, 3) is True

    def test_tres_grupos_mal_estructurado(self):
        fixture = {'cuartos': [{}, {}, {}], 'octavos': []}
        assert _fixture_es_consistente(fixture, 3) is False

    def test_cuatro_grupos_cuatro_cuartos(self):
        fixture = {'cuartos': [{}, {}, {}, {}], 'octavos': []}
        assert _fixture_es_consistente(fixture, 4) is True

    def test_cinco_grupos_cuatro_cuartos_dos_octavos(self):
        fixture = {'cuartos': [{}, {}, {}, {}], 'octavos': [{}, {}]}
        assert _fixture_es_consistente(fixture, 5) is True

    def test_num_grupos_desconocido_siempre_consistente(self):
        assert _fixture_es_consistente({}, 99) is True


# ── _buscar_partido_en_fixtures ───────────────────────────────────────────────

class TestBuscarPartidoEnFixtures:

    def _fixtures(self):
        return {
            'Cuarta': {
                'cuartos': [{'id': 'q1', 'pareja1': {}, 'pareja2': {}}, {'id': 'q2', 'pareja1': {}, 'pareja2': {}}],
                'octavos': [],
                'semifinales': [{'id': 'sf1', 'pareja1': {}, 'pareja2': {}}],
                'final': {'id': 'fin', 'pareja1': {}, 'pareja2': {}},
            }
        }

    def test_encuentra_en_cuartos(self):
        fixtures = self._fixtures()
        cat, partido, fase = _buscar_partido_en_fixtures(fixtures, 'q1')
        assert cat == 'Cuarta'
        assert partido['id'] == 'q1'
        assert fase == ('cuartos', 0)

    def test_encuentra_final(self):
        fixtures = self._fixtures()
        cat, partido, fase = _buscar_partido_en_fixtures(fixtures, 'fin')
        assert cat == 'Cuarta'
        assert fase == ('final', None)

    def test_no_encontrado_devuelve_nones(self):
        cat, partido, fase = _buscar_partido_en_fixtures({}, 'inexistente')
        assert cat is None
        assert partido is None
        assert fase is None


# ── obtener_o_generar_fixtures ────────────────────────────────────────────────

class TestObtenerOGenerarFixtures:

    def test_sin_resultado_lanza_error(self):
        torneo = {'resultado_algoritmo': None, 'fixtures_finales': {}}
        with pytest.raises(ServiceError) as exc:
            obtener_o_generar_fixtures(torneo)
        assert exc.value.status_code == 404

    def test_fixtures_guardados_consistentes_se_devuelven_sin_regenerar(self):
        torneo = _torneo_con_resultado(3)
        torneo['fixtures_finales'] = {'Cuarta': _fixture_tres_grupos()}

        with patch('services.fixture_service.storage') as mock_storage:
            fixtures = obtener_o_generar_fixtures(torneo)

        # No debe llamar a guardar_con_version si ya son consistentes
        mock_storage.guardar_con_version.assert_not_called()
        assert 'Cuarta' in fixtures

    def test_genera_y_persiste_si_no_hay_fixtures(self):
        torneo = _torneo_con_resultado(3)
        mock_fixture = MagicMock()
        mock_fixture.to_dict.return_value = _fixture_tres_grupos()

        with patch('services.fixture_service.GeneradorFixtureFinales.generar_fixture', return_value=mock_fixture), \
             patch('services.fixture_service.GeneradorCalendarioFinales.asignar_horarios', return_value={}), \
             patch('services.fixture_service.storage') as mock_storage:
            fixtures = obtener_o_generar_fixtures(torneo)

        mock_storage.guardar_con_version.assert_called_once()
        assert 'Cuarta' in fixtures


# ── obtener_calendario ────────────────────────────────────────────────────────

class TestObtenerCalendario:

    def test_sin_fixtures_lanza_error(self):
        torneo = {'fixtures_finales': {}, 'calendario_finales': None}
        with pytest.raises(ServiceError) as exc:
            obtener_calendario(torneo)
        assert exc.value.status_code == 404

    def test_devuelve_calendario_y_resumen(self):
        torneo = {
            'fixtures_finales': {'Cuarta': _fixture_tres_grupos()},
            'calendario_finales': {'cancha_1': [], 'cancha_2': []},
        }
        cal_mock = {'cancha_1': [], 'cancha_2': []}
        resumen_mock = {'horarios': []}

        with patch('services.fixture_service.GeneradorCalendarioFinales.sincronizar_parejas', return_value=cal_mock), \
             patch('services.fixture_service.GeneradorCalendarioFinales.generar_resumen_horarios', return_value=resumen_mock):
            calendario, resumen = obtener_calendario(torneo)

        assert calendario == cal_mock
        assert resumen == resumen_mock


# ── generar_al_activar_torneo ─────────────────────────────────────────────────

class TestGenerarAlActivarTorneo:

    def test_no_genera_si_ya_existen_fixtures(self):
        torneo = _torneo_con_resultado(3)
        torneo['fixtures_finales'] = {'Cuarta': _fixture_tres_grupos()}

        with patch('services.fixture_service.GeneradorFixtureFinales.generar_fixture') as mock_gen:
            generar_al_activar_torneo(torneo)

        mock_gen.assert_not_called()

    def test_genera_fixtures_y_calendario_si_no_existen(self):
        torneo = _torneo_con_resultado(3)
        mock_fixture = MagicMock()
        mock_fixture.to_dict.return_value = _fixture_tres_grupos()

        with patch('services.fixture_service.GeneradorFixtureFinales.generar_fixture', return_value=mock_fixture), \
             patch('services.fixture_service.GeneradorCalendarioFinales.generar_plantilla_calendario', return_value={}) as mock_cal:
            generar_al_activar_torneo(torneo)

        assert torneo.get('fixtures_finales')
        mock_cal.assert_called_once()

    def test_no_falla_si_resultado_es_none(self):
        torneo = {'resultado_algoritmo': None, 'fixtures_finales': {}, 'calendario_finales': None}
        generar_al_activar_torneo(torneo)  # No debe lanzar excepción


# ── guardar_resultado_final ───────────────────────────────────────────────────

class TestGuardarResultadoFinal:

    def test_menos_de_dos_sets_lanza_error(self):
        torneo = {'fixtures_finales': {'Cuarta': {}}, 'resultado_algoritmo': {}}
        with pytest.raises(ServiceError) as exc:
            guardar_resultado_final(torneo, 'p1', [{'pareja1': 6, 'pareja2': 3}])
        assert exc.value.status_code == 400

    def test_empate_lanza_error(self):
        torneo = {
            'fixtures_finales': {
                'Cuarta': {
                    'cuartos': [{'id': 'p1', 'pareja1': {'id': 1}, 'pareja2': {'id': 2}}],
                    'octavos': [], 'semifinales': [], 'final': {},
                }
            },
            'resultado_algoritmo': {'grupos_por_categoria': {'Cuarta': []}},
        }
        sets_empate = [{'pareja1': 6, 'pareja2': 3}, {'pareja1': 3, 'pareja2': 6}]
        with pytest.raises(ServiceError):
            guardar_resultado_final(torneo, 'p1', sets_empate)
