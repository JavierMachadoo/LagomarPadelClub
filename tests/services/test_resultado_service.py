"""
Tests unitarios para resultado_service.

Cubre asignación de posiciones, guardado de resultados y tabla de posiciones.
"""

import pytest
from unittest.mock import patch, MagicMock

from services.resultado_service import (
    asignar_posicion,
    guardar_resultado_grupo,
    obtener_tabla_posiciones,
    _verificar_posiciones_completas,
)
from services.exceptions import ServiceError
from tests.conftest import crear_grupo_dict, crear_resultado_dict


# ── Fixtures locales ──────────────────────────────────────────────────────────

def _resultado_con_grupo(categoria: str = 'Cuarta', grupo_id: int = 1) -> dict:
    return {
        'grupos_por_categoria': {
            categoria: [crear_grupo_dict(grupo_id=grupo_id, categoria=categoria)]
        },
        'parejas_sin_asignar': [],
    }


# ── _verificar_posiciones_completas ───────────────────────────────────────────

class TestVerificarPosicionesCompletas:

    def test_todas_asignadas_devuelve_true(self):
        grupos = [
            {'parejas': [
                {'id': 1, 'posicion_grupo': 1},
                {'id': 2, 'posicion_grupo': 2},
                {'id': 3, 'posicion_grupo': 3},
            ]}
        ]
        assert _verificar_posiciones_completas(grupos) is True

    def test_una_sin_asignar_devuelve_false(self):
        grupos = [
            {'parejas': [
                {'id': 1, 'posicion_grupo': 1},
                {'id': 2, 'posicion_grupo': None},
                {'id': 3, 'posicion_grupo': 3},
            ]}
        ]
        assert _verificar_posiciones_completas(grupos) is False

    def test_grupos_vacios_devuelve_true(self):
        assert _verificar_posiciones_completas([]) is True


# ── asignar_posicion ──────────────────────────────────────────────────────────

class TestAsignarPosicion:

    def test_asigna_posicion_correctamente(self):
        resultado_data = _resultado_con_grupo()
        grupo = resultado_data['grupos_por_categoria']['Cuarta'][0]
        pareja_id = grupo['parejas'][0]['id']

        with patch('services.resultado_service._regenerar_fixture_si_completo'):
            puede_generar, anterior = asignar_posicion(resultado_data, pareja_id, 1, 'Cuarta')

        pareja = grupo['parejas'][0]
        assert pareja['posicion_grupo'] == 1

    def test_posicion_cero_desasigna(self):
        resultado_data = _resultado_con_grupo()
        grupo = resultado_data['grupos_por_categoria']['Cuarta'][0]
        pareja_id = grupo['parejas'][0]['id']
        grupo['parejas'][0]['posicion_grupo'] = 2  # asignado previamente

        with patch('services.resultado_service._regenerar_fixture_si_completo'):
            _, anterior = asignar_posicion(resultado_data, pareja_id, 0, 'Cuarta')

        assert grupo['parejas'][0]['posicion_grupo'] is None
        assert anterior == 2

    def test_pareja_inexistente_lanza_error(self):
        resultado_data = _resultado_con_grupo()
        with patch('services.resultado_service._regenerar_fixture_si_completo'):
            with pytest.raises(ServiceError) as exc:
                asignar_posicion(resultado_data, pareja_id=9999, posicion=1, categoria='Cuarta')
        assert exc.value.status_code == 404


# ── guardar_resultado_grupo ───────────────────────────────────────────────────

class TestGuardarResultadoGrupo:

    def _params_partido(self, resultado_data: dict, categoria: str = 'Cuarta') -> dict:
        grupo = resultado_data['grupos_por_categoria'][categoria][0]
        p1_id = grupo['parejas'][0]['id']
        p2_id = grupo['parejas'][1]['id']
        return {
            'resultado_data': resultado_data,
            'categoria': categoria,
            'grupo_id': grupo['id'],
            'pareja1_id': p1_id,
            'pareja2_id': p2_id,
            'games_set1_p1': 6,
            'games_set1_p2': 3,
            'games_set2_p1': 6,
            'games_set2_p2': 2,
            'tiebreak_p1': None,
            'tiebreak_p2': None,
        }

    def test_guarda_resultado_en_grupo(self):
        resultado_data = _resultado_con_grupo()
        params = self._params_partido(resultado_data)

        with patch('services.resultado_service._regenerar_fixture_si_completo'):
            resultado_dict, completos = guardar_resultado_grupo(**params)

        grupo = resultado_data['grupos_por_categoria']['Cuarta'][0]
        assert len(grupo['resultados']) == 1
        assert resultado_dict['sets_pareja1'] == 2
        assert resultado_dict['sets_pareja2'] == 0

    def test_grupo_inexistente_lanza_error(self):
        resultado_data = _resultado_con_grupo()
        with pytest.raises(ServiceError) as exc:
            guardar_resultado_grupo(
                resultado_data, 'Cuarta', grupo_id=9999,
                pareja1_id=1, pareja2_id=2,
                games_set1_p1=6, games_set1_p2=3,
                games_set2_p1=6, games_set2_p2=3,
                tiebreak_p1=None, tiebreak_p2=None,
            )
        assert exc.value.status_code == 404

    def test_clave_resultado_es_ids_ordenados(self):
        resultado_data = _resultado_con_grupo()
        grupo = resultado_data['grupos_por_categoria']['Cuarta'][0]
        p1_id = grupo['parejas'][0]['id']
        p2_id = grupo['parejas'][1]['id']

        with patch('services.resultado_service._regenerar_fixture_si_completo'):
            guardar_resultado_grupo(
                resultado_data, 'Cuarta', grupo['id'],
                pareja1_id=p1_id, pareja2_id=p2_id,
                games_set1_p1=6, games_set1_p2=3,
                games_set2_p1=6, games_set2_p2=2,
                tiebreak_p1=None, tiebreak_p2=None,
            )

        ids_ordenados = sorted([p1_id, p2_id])
        key = f"{ids_ordenados[0]}-{ids_ordenados[1]}"
        assert key in grupo['resultados']


# ── obtener_tabla_posiciones ──────────────────────────────────────────────────

class TestObtenerTablaPosiciones:

    def test_grupo_inexistente_lanza_error(self):
        resultado_data = _resultado_con_grupo()
        with pytest.raises(ServiceError) as exc:
            obtener_tabla_posiciones(resultado_data, 'Cuarta', grupo_id=9999)
        assert exc.value.status_code == 404

    def test_devuelve_tabla_con_grupo_existente(self):
        resultado_data = _resultado_con_grupo()
        grupo = resultado_data['grupos_por_categoria']['Cuarta'][0]
        grupo_id = grupo['id']

        mock_tabla = [{'pareja': 'Test', 'puntos': 3}]
        with patch('services.resultado_service.CalculadorClasificacion.calcular_tabla_posiciones', return_value=mock_tabla):
            tabla = obtener_tabla_posiciones(resultado_data, 'Cuarta', grupo_id)

        assert tabla == mock_tabla
