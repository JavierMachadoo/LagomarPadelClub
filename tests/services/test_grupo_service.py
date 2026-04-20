"""
Tests unitarios para grupo_service.

Cubre funciones puras y aquellas que operan sobre dicts sin acceso a Flask ni storage.
Las funciones que tocan Supabase (ejecutar_algoritmo) se mockean a nivel de función interna.
"""

import pytest
from unittest.mock import patch, MagicMock

from services.grupo_service import (
    recalcular_estadisticas,
    recalcular_score_grupo,
    enriquecer_parejas_con_asignacion,
    intercambiar_pareja,
    asignar_pareja_a_grupo,
    crear_grupo_manual,
    editar_grupo,
    agregar_pareja,
    eliminar_pareja,
    remover_pareja_de_grupo,
    regenerar_calendario,
    eliminar_grupo,
)
from services.exceptions import ServiceError
from tests.conftest import crear_pareja, crear_grupo_dict


# ── Fixtures locales ──────────────────────────────────────────────────────────

def _resultado_con_grupos(num_grupos: int = 2, categoria: str = 'Cuarta') -> dict:
    return {
        'grupos_por_categoria': {
            categoria: [
                crear_grupo_dict(grupo_id=i, categoria=categoria)
                for i in range(1, num_grupos + 1)
            ]
        },
        'parejas_sin_asignar': [],
        'calendario': {},
    }


def _pareja_dict(id: int = 99, categoria: str = 'Cuarta') -> dict:
    return crear_pareja(id=id, categoria=categoria).to_dict()


# ── recalcular_estadisticas ───────────────────────────────────────────────────

class TestRecalcularEstadisticas:

    def test_100_pct_sin_sin_asignar(self):
        resultado = _resultado_con_grupos(2)
        stats = recalcular_estadisticas(resultado)
        assert stats['parejas_asignadas'] == 6
        assert stats['parejas_sin_asignar'] == 0
        assert stats['porcentaje_asignacion'] == 100.0

    def test_porcentaje_parcial(self):
        resultado = _resultado_con_grupos(2)
        resultado['parejas_sin_asignar'] = [_pareja_dict(99), _pareja_dict(100)]
        stats = recalcular_estadisticas(resultado)
        assert stats['total_parejas'] == 8
        assert stats['porcentaje_asignacion'] == pytest.approx(75.0)

    def test_sin_datos_no_divide_por_cero(self):
        resultado = {'grupos_por_categoria': {}, 'parejas_sin_asignar': []}
        stats = recalcular_estadisticas(resultado)
        assert stats['total_parejas'] == 0
        assert stats['porcentaje_asignacion'] == 0

    def test_mutacion_in_place(self):
        resultado = _resultado_con_grupos(1)
        recalcular_estadisticas(resultado)
        assert 'estadisticas' in resultado

    def test_multiples_categorias(self):
        resultado = {
            'grupos_por_categoria': {
                'Cuarta': [crear_grupo_dict(grupo_id=1, categoria='Cuarta')],
                'Quinta': [crear_grupo_dict(grupo_id=2, categoria='Quinta')],
            },
            'parejas_sin_asignar': [],
        }
        stats = recalcular_estadisticas(resultado)
        assert stats['total_grupos'] == 2
        assert stats['parejas_asignadas'] == 6


# ── recalcular_score_grupo ────────────────────────────────────────────────────

class TestRecalcularScoreGrupo:

    def test_grupo_vacio_score_cero(self):
        grupo = {'parejas': [], 'franja_horaria': None}
        recalcular_score_grupo(grupo)
        assert grupo['score'] == 0.0

    def test_todos_disponibles_score_3(self):
        franja = 'Sábado 09:00'
        grupo = crear_grupo_dict(franja=franja)
        recalcular_score_grupo(grupo)
        assert grupo['score'] == pytest.approx(3.0)

    def test_ninguno_disponible_score_0(self):
        grupo = crear_grupo_dict(franja='Sábado 09:00')
        for p in grupo['parejas']:
            p['franjas_disponibles'] = ['Viernes 18:00']
        recalcular_score_grupo(grupo)
        assert grupo['score'] == 0.0

    def test_score_escrito_en_ambas_claves(self):
        grupo = crear_grupo_dict()
        recalcular_score_grupo(grupo)
        assert grupo['score'] == grupo['score_compatibilidad']

    def test_score_parcial_dia_correcto(self):
        grupo = {
            'franja_horaria': 'Sábado 09:00',
            'parejas': [
                {'id': 1, 'franjas_disponibles': ['Sábado 09:00']},   # +1.0
                {'id': 2, 'franjas_disponibles': ['Sábado 12:00']},    # +0.5 (mismo día)
                {'id': 3, 'franjas_disponibles': ['Viernes 18:00']},   # +0.0
            ],
        }
        recalcular_score_grupo(grupo)
        assert grupo['score'] == pytest.approx(1.5)


# ── enriquecer_parejas_con_asignacion ─────────────────────────────────────────

class TestEnriquecerParejas:

    def test_sin_resultado_all_not_assigned(self):
        parejas = [_pareja_dict(1), _pareja_dict(2)]
        resultado = enriquecer_parejas_con_asignacion(parejas, None)
        assert all(not p['esta_asignada'] for p in resultado)
        assert all(p['grupo_asignado'] is None for p in resultado)

    def test_pareja_asignada_en_grupo(self):
        grupo = crear_grupo_dict(grupo_id=5, categoria='Cuarta', franja='Sábado 09:00')
        pareja_id = grupo['parejas'][0]['id']
        resultado_data = {
            'grupos_por_categoria': {'Cuarta': [grupo]},
        }
        parejas = [grupo['parejas'][0]]
        enriched = enriquecer_parejas_con_asignacion(parejas, resultado_data)
        assert enriched[0]['esta_asignada'] is True
        assert enriched[0]['grupo_asignado'] == 5

    def test_fuera_de_horario(self):
        grupo = crear_grupo_dict(grupo_id=1, franja='Sábado 09:00')
        pareja = grupo['parejas'][0]
        pareja['franjas_disponibles'] = ['Viernes 18:00']  # franja distinta a la del grupo
        resultado_data = {'grupos_por_categoria': {'Cuarta': [grupo]}}
        enriched = enriquecer_parejas_con_asignacion([pareja], resultado_data)
        assert enriched[0]['fuera_de_horario'] is True

    def test_preserva_datos_originales(self):
        parejas = [_pareja_dict(1)]
        resultado = enriquecer_parejas_con_asignacion(parejas, None)
        assert resultado[0]['id'] == 1


# ── intercambiar_pareja ───────────────────────────────────────────────────────

class TestIntercambiarPareja:

    def _resultado_dos_grupos(self):
        g1 = crear_grupo_dict(grupo_id=1, categoria='Cuarta', franja='Sábado 09:00')
        g2 = crear_grupo_dict(grupo_id=2, categoria='Cuarta', franja='Viernes 18:00')
        return {
            'grupos_por_categoria': {'Cuarta': [g1, g2]},
            'parejas_sin_asignar': [],
            'calendario': {},
        }

    def test_intercambio_exitoso_mueve_pareja(self):
        resultado = self._resultado_dos_grupos()
        g1 = resultado['grupos_por_categoria']['Cuarta'][0]
        g2 = resultado['grupos_por_categoria']['Cuarta'][1]
        pareja_id = g1['parejas'][0]['id']
        pareja_en_slot = g2['parejas'][0]['id']

        with patch('services.grupo_service.regenerar_calendario'):
            mensaje, stats = intercambiar_pareja(
                resultado, pareja_id, g1['id'], g2['id'], slot_destino=0
            )

        # La pareja se movió de g1 a g2
        ids_g2 = [p['id'] for p in g2['parejas']]
        assert pareja_id in ids_g2
        assert 'Intercambio' in mensaje or 'movida' in mensaje

    def test_pareja_inexistente_lanza_error(self):
        resultado = self._resultado_dos_grupos()
        g1 = resultado['grupos_por_categoria']['Cuarta'][0]
        g2 = resultado['grupos_por_categoria']['Cuarta'][1]
        with pytest.raises(ServiceError) as exc:
            intercambiar_pareja(resultado, pareja_id=9999, grupo_origen_id=g1['id'], grupo_destino_id=g2['id'], slot_destino=0)
        assert exc.value.status_code == 400

    def test_origen_con_resultados_lanza_error(self):
        resultado = self._resultado_dos_grupos()
        g1 = resultado['grupos_por_categoria']['Cuarta'][0]
        g2 = resultado['grupos_por_categoria']['Cuarta'][1]
        g1['resultados'] = {'0_1': {'sets': [{'local': 6, 'visitante': 3}]}}
        pareja_id = g1['parejas'][0]['id']
        with pytest.raises(ServiceError) as exc:
            intercambiar_pareja(resultado, pareja_id, g1['id'], g2['id'], slot_destino=0)
        assert exc.value.status_code == 400

    def test_destino_con_resultados_lanza_error(self):
        resultado = self._resultado_dos_grupos()
        g1 = resultado['grupos_por_categoria']['Cuarta'][0]
        g2 = resultado['grupos_por_categoria']['Cuarta'][1]
        g2['resultados'] = {'0_1': {'sets': [{'local': 6, 'visitante': 3}]}}
        pareja_id = g1['parejas'][0]['id']
        with pytest.raises(ServiceError) as exc:
            intercambiar_pareja(resultado, pareja_id, g1['id'], g2['id'], slot_destino=0)
        assert exc.value.status_code == 400


# ── agregar_pareja ────────────────────────────────────────────────────────────

class TestAgregarPareja:

    def test_crea_pareja_con_id_incremental(self):
        datos = {'parejas': [_pareja_dict(1), _pareja_dict(2)], 'resultado_algoritmo': None}
        nueva, _ = agregar_pareja(datos, 'Juan', 'Pedro', 'Juan / Pedro', '600', 'Cuarta', ['Viernes 18:00'], False)
        assert nueva['id'] == 3
        assert len(datos['parejas']) == 3

    def test_agrega_a_sin_asignar_cuando_desde_resultados(self):
        resultado_data = _resultado_con_grupos(1)
        datos = {'parejas': [], 'resultado_algoritmo': resultado_data}
        nueva, stats = agregar_pareja(datos, '', '', 'Test', '600', 'Cuarta', ['Viernes 18:00'], True)
        sin_asignar = resultado_data['parejas_sin_asignar']
        assert any(p['id'] == nueva['id'] for p in sin_asignar)
        assert stats is not None

    def test_sin_desde_resultados_no_modifica_resultado(self):
        resultado_data = _resultado_con_grupos(1)
        datos = {'parejas': [], 'resultado_algoritmo': resultado_data}
        nueva, stats = agregar_pareja(datos, '', '', 'Test', '', 'Cuarta', ['Viernes 18:00'], False)
        assert stats is None
        assert resultado_data['parejas_sin_asignar'] == []


# ── eliminar_pareja ───────────────────────────────────────────────────────────

class TestEliminarPareja:

    def test_elimina_del_blob(self):
        datos = {'parejas': [_pareja_dict(1), _pareja_dict(2)], 'resultado_algoritmo': None}
        eliminar_pareja(datos, pareja_id=1)
        assert len(datos['parejas']) == 1
        assert datos['parejas'][0]['id'] == 2

    def test_elimina_del_grupo(self):
        grupo = crear_grupo_dict(grupo_id=1)
        pareja_id = grupo['parejas'][0]['id']
        resultado_data = {
            'grupos_por_categoria': {'Cuarta': [grupo]},
            'parejas_sin_asignar': [],
            'calendario': {},
        }
        datos = {'parejas': [_pareja_dict(pareja_id)], 'resultado_algoritmo': resultado_data}
        with patch('services.grupo_service.regenerar_calendario'):
            eliminar_pareja(datos, pareja_id)
        ids_en_grupo = [p['id'] for p in grupo['parejas']]
        assert pareja_id not in ids_en_grupo


# ── remover_pareja_de_grupo ───────────────────────────────────────────────────

class TestRemoverParejaDeGrupo:

    def test_mueve_a_sin_asignar(self):
        grupo = crear_grupo_dict(grupo_id=1)
        pareja_id = grupo['parejas'][0]['id']
        resultado_data = {
            'grupos_por_categoria': {'Cuarta': [grupo]},
            'parejas_sin_asignar': [],
            'calendario': {},
        }
        with patch('services.grupo_service.regenerar_calendario'):
            stats = remover_pareja_de_grupo(resultado_data, pareja_id)
        assert any(p['id'] == pareja_id for p in resultado_data['parejas_sin_asignar'])
        assert pareja_id not in [p['id'] for p in grupo['parejas']]
        assert stats is not None

    def test_pareja_inexistente_lanza_error(self):
        resultado_data = {
            'grupos_por_categoria': {'Cuarta': [crear_grupo_dict()]},
            'parejas_sin_asignar': [],
        }
        with pytest.raises(ServiceError) as exc:
            remover_pareja_de_grupo(resultado_data, pareja_id=9999)
        assert exc.value.status_code == 404


# ── crear_grupo_manual ────────────────────────────────────────────────────────

class TestCrearGrupoManual:

    def _resultado_vacio(self) -> dict:
        return {'grupos_por_categoria': {}, 'parejas_sin_asignar': [], 'calendario': {}}

    def test_crea_grupo_con_id_incremental(self):
        resultado = self._resultado_vacio()
        with patch('services.grupo_service.regenerar_calendario'):
            nuevo = crear_grupo_manual(resultado, 'Cuarta', 'Viernes 18:00', 1)
        assert nuevo['id'] == 1
        assert nuevo['franja_horaria'] == 'Viernes 18:00'
        assert nuevo['cancha'] == 1

    def test_conflicto_misma_franja_y_cancha_lanza_error(self):
        resultado = self._resultado_vacio()
        with patch('services.grupo_service.regenerar_calendario'):
            crear_grupo_manual(resultado, 'Cuarta', 'Viernes 18:00', 1)
        with pytest.raises(ServiceError):
            crear_grupo_manual(resultado, 'Quinta', 'Viernes 18:00', 1)

    def test_crea_categoria_si_no_existe(self):
        resultado = self._resultado_vacio()
        with patch('services.grupo_service.regenerar_calendario'):
            crear_grupo_manual(resultado, 'NuevaCategoria', 'Viernes 18:00', 2)
        assert 'NuevaCategoria' in resultado['grupos_por_categoria']


# ── editar_grupo ──────────────────────────────────────────────────────────────

class TestEditarGrupo:

    def test_actualiza_franja_y_cancha(self):
        grupo = crear_grupo_dict(grupo_id=1, franja='Viernes 18:00')
        grupo['cancha'] = 1
        resultado_data = {
            'grupos_por_categoria': {'Cuarta': [grupo]},
            'parejas_sin_asignar': [],
            'calendario': {},
        }
        with patch('services.grupo_service.regenerar_calendario'):
            editar_grupo(resultado_data, grupo_id=1, categoria='Cuarta', franja_horaria='Sábado 09:00', cancha=2)
        assert grupo['franja_horaria'] == 'Sábado 09:00'
        assert grupo['cancha'] == 2

    def test_grupo_inexistente_lanza_error(self):
        resultado_data = {
            'grupos_por_categoria': {'Cuarta': []},
            'parejas_sin_asignar': [],
        }
        with pytest.raises(ServiceError) as exc:
            editar_grupo(resultado_data, grupo_id=99, categoria='Cuarta', franja_horaria='Viernes 18:00', cancha=1)
        assert exc.value.status_code == 404


# ── eliminar_grupo ────────────────────────────────────────────────────────────

class TestEliminarGrupo:

    def _resultado_vacio(self, grupo_id: int = 1, categoria: str = 'Cuarta') -> dict:
        grupo = crear_grupo_dict(grupo_id=grupo_id, categoria=categoria, num_parejas=0)
        grupo['resultados'] = []
        return {
            'grupos_por_categoria': {categoria: [grupo]},
            'parejas_sin_asignar': [],
            'calendario': {},
            'partidos_por_grupo': {},
        }

    def test_happy_path_elimina_grupo_vacio(self):
        resultado_data = self._resultado_vacio(grupo_id=1)
        with patch('services.grupo_service.regenerar_calendario'):
            eliminar_grupo(resultado_data, grupo_id=1, categoria='Cuarta')
        assert resultado_data['grupos_por_categoria']['Cuarta'] == []

    def test_grupo_inexistente_lanza_404(self):
        resultado_data = self._resultado_vacio(grupo_id=1)
        with pytest.raises(ServiceError) as exc:
            eliminar_grupo(resultado_data, grupo_id=99, categoria='Cuarta')
        assert exc.value.status_code == 404

    def test_grupo_con_parejas_lanza_400(self):
        resultado_data = {
            'grupos_por_categoria': {
                'Cuarta': [crear_grupo_dict(grupo_id=1, categoria='Cuarta', num_parejas=3)]
            },
            'parejas_sin_asignar': [],
            'calendario': {},
            'partidos_por_grupo': {},
        }
        with pytest.raises(ServiceError) as exc:
            eliminar_grupo(resultado_data, grupo_id=1, categoria='Cuarta')
        assert exc.value.status_code == 400

    def test_grupo_con_resultados_lanza_400(self):
        grupo = crear_grupo_dict(grupo_id=1, categoria='Cuarta', num_parejas=0)
        grupo['resultados'] = [{'partido_id': 'x', 'sets': [[6, 3]]}]
        resultado_data = {
            'grupos_por_categoria': {'Cuarta': [grupo]},
            'parejas_sin_asignar': [],
            'calendario': {},
            'partidos_por_grupo': {},
        }
        with pytest.raises(ServiceError) as exc:
            eliminar_grupo(resultado_data, grupo_id=1, categoria='Cuarta')
        assert exc.value.status_code == 400

    def test_limpia_partidos_por_grupo(self):
        resultado_data = self._resultado_vacio(grupo_id=5)
        resultado_data['partidos_por_grupo'] = {'5': [{'id': 'p1'}], '9': [{'id': 'p2'}]}
        with patch('services.grupo_service.regenerar_calendario'):
            eliminar_grupo(resultado_data, grupo_id=5, categoria='Cuarta')
        assert '5' not in resultado_data['partidos_por_grupo']
        assert '9' in resultado_data['partidos_por_grupo']
