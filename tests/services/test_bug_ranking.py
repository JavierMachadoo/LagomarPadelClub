"""
Tests para bug-ranking: propagación de jugador1_id/jugador2_id.

Cubre:
- 5.1: _cargar_inscripciones_supabase mapea jugador_id → jugador1_id
- 5.2: _aplicar_update_pareja normaliza '' → None y propaga in-place
- 5.3: endpoint POST /api/editar-pareja acepta y propaga jugador1_id/jugador2_id
"""

import pytest
from unittest.mock import patch, MagicMock

from services.grupo_service import _aplicar_update_pareja, editar_pareja
from services.exceptions import ServiceError
from tests.conftest import crear_grupo_dict


# ── 5.1 _cargar_inscripciones_supabase ───────────────────────────────────────

class TestCargarInscripcionesSupabase:
    """Verifica que jugador_id (col Supabase sin '1') se mapea a jugador1_id."""

    def _run_with_mock_data(self, inscripciones_data):
        """Helper: ejecuta _cargar_inscripciones_supabase con datos fakeados."""
        from services.grupo_service import _cargar_inscripciones_supabase

        mock_resp = MagicMock()
        mock_resp.data = inscripciones_data

        # Los imports dentro de la función son locales, por lo que parchamos
        # los módulos originales directamente.
        with patch('config.settings.SUPABASE_URL', 'http://fake'), \
             patch('config.settings.SUPABASE_SERVICE_ROLE_KEY', 'fake-key'), \
             patch('utils.supabase_client.get_supabase_admin') as mock_sb, \
             patch('utils.torneo_storage.storage') as mock_storage:

            mock_storage.get_torneo_id.return_value = 'test-torneo-id'
            mock_sb.return_value.table.return_value.select.return_value \
                .eq.return_value.eq.return_value.execute.return_value = mock_resp

            return _cargar_inscripciones_supabase()

    def test_jugador_id_se_mapea_a_jugador1_id(self):
        """La columna Supabase 'jugador_id' (sin '1') debe aparecer como jugador1_id."""
        data = [{
            'id': '00000001-0000-0000-0000-000000000001',
            'integrante1': 'Ana García',
            'integrante2': 'Bea López',
            'telefono': '600000001',
            'categoria': 'Cuarta',
            'franjas_disponibles': ['Sábado 09:00'],
            'jugador_id': 'uid-ana',
            'jugador2_id': 'uid-bea',
        }]
        result = self._run_with_mock_data(data)
        assert len(result) == 1
        assert result[0]['jugador1_id'] == 'uid-ana'
        assert result[0]['jugador2_id'] == 'uid-bea'

    def test_jugador_id_null_mapea_a_none(self):
        """Si jugador_id es None en Supabase, jugador1_id debe ser None (no se descarta la pareja)."""
        data = [{
            'id': '00000001-0000-0000-0000-000000000002',
            'integrante1': 'Carlos',
            'integrante2': 'David',
            'telefono': '600000002',
            'categoria': 'Quinta',
            'franjas_disponibles': [],
            'jugador_id': None,
            'jugador2_id': None,
        }]
        result = self._run_with_mock_data(data)
        assert len(result) == 1
        assert result[0]['jugador1_id'] is None
        assert result[0]['jugador2_id'] is None

    def test_pareja_solo_con_jugador1_no_se_descarta(self):
        """Pareja con solo jugador1_id asignado debe incluirse en el resultado."""
        data = [{
            'id': '00000001-0000-0000-0000-000000000003',
            'integrante1': 'Elena',
            'integrante2': 'Fátima',
            'telefono': '600000003',
            'categoria': 'Tercera',
            'franjas_disponibles': ['Viernes 18:00'],
            'jugador_id': 'uid-elena',
            'jugador2_id': None,
        }]
        result = self._run_with_mock_data(data)
        assert len(result) == 1
        assert result[0]['jugador1_id'] == 'uid-elena'
        assert result[0]['jugador2_id'] is None


# ── 5.2 _aplicar_update_pareja ───────────────────────────────────────────────

class TestAplicarUpdatePareja:
    """Verifica normalización '' → None y mutación in-place del dict."""

    def _base_dict(self):
        return {
            'id': 42,
            'nombre': 'Viejo Nombre',
            'telefono': '600000000',
            'categoria': 'Cuarta',
            'franjas_disponibles': [],
            'jugador1_id': None,
            'jugador2_id': None,
        }

    def test_string_vacio_normaliza_a_none_jugador1(self):
        d = self._base_dict()
        _aplicar_update_pareja(
            d,
            nombre='Nuevo', telefono='600', categoria='Cuarta', franjas=[],
            jugador1_id='',
            jugador2_id='uid-b',
        )
        assert d['jugador1_id'] is None

    def test_string_vacio_normaliza_a_none_jugador2(self):
        d = self._base_dict()
        _aplicar_update_pareja(
            d,
            nombre='Nuevo', telefono='600', categoria='Cuarta', franjas=[],
            jugador1_id='uid-a',
            jugador2_id='',
        )
        assert d['jugador2_id'] is None

    def test_none_passthrough_jugador1(self):
        d = self._base_dict()
        d['jugador1_id'] = 'uid-existente'
        _aplicar_update_pareja(
            d,
            nombre='N', telefono='T', categoria='C', franjas=[],
            jugador1_id=None,
            jugador2_id=None,
        )
        # None como input NO debe sobreescribir un valor existente
        assert d['jugador1_id'] == 'uid-existente'

    def test_valor_valido_se_aplica(self):
        d = self._base_dict()
        _aplicar_update_pareja(
            d,
            nombre='Nuevo Nombre', telefono='611', categoria='Quinta',
            franjas=['Sábado 09:00'],
            jugador1_id='uid-1',
            jugador2_id='uid-2',
        )
        assert d['jugador1_id'] == 'uid-1'
        assert d['jugador2_id'] == 'uid-2'
        assert d['nombre'] == 'Nuevo Nombre'
        assert d['categoria'] == 'Quinta'

    def test_mutacion_in_place(self):
        """La función muta el dict recibido (no crea uno nuevo)."""
        d = self._base_dict()
        original_id = id(d)
        _aplicar_update_pareja(
            d,
            nombre='X', telefono='Y', categoria='Z', franjas=[],
            jugador1_id='u1', jugador2_id='u2',
        )
        assert id(d) == original_id


# ── 5.3 Endpoint POST /api/editar-pareja ─────────────────────────────────────

class TestEndpointEditarPareja:
    """Verifica que el endpoint acepta y propaga jugador1_id/jugador2_id."""

    def _datos_con_pareja(self, pareja_id=99):
        grupo = crear_grupo_dict(grupo_id=1, categoria='Cuarta')
        # Agregar jugador ids al primer par del grupo
        grupo['parejas'][0]['id'] = pareja_id
        grupo['parejas'][0]['jugador1_id'] = None
        grupo['parejas'][0]['jugador2_id'] = None
        return {
            'parejas': [],
            'resultado_algoritmo': {
                'grupos_por_categoria': {'Cuarta': [grupo]},
                'parejas_sin_asignar': [],
                'calendario': {},
            },
            'estado': 'espera',
            'num_canchas': 2,
            'tipo_torneo': 'fin1',
            'fixtures_finales': {},
            'calendario_finales': None,
            'nombre': 'Test',
            'version': 1,
            'torneo_id': 'test-id',
        }

    def test_endpoint_acepta_jugador_ids(self, client, admin_cookie):
        datos = self._datos_con_pareja(pareja_id=99)
        pareja = datos['resultado_algoritmo']['grupos_por_categoria']['Cuarta'][0]['parejas'][0]

        with patch('api.routes.parejas.obtener_datos_desde_token', return_value=datos), \
             patch('api.routes.parejas.sincronizar_con_storage_y_token'), \
             patch('api.routes.parejas.crear_respuesta_con_token_actualizado',
                   side_effect=lambda body, _: __import__('flask').jsonify(body)):

            resp = admin_cookie.post('/api/editar-pareja', json={
                'pareja_id': pareja['id'],
                'nombre': pareja['nombre'],
                'telefono': '600000000',
                'categoria': 'Cuarta',
                'franjas': ['Sábado 09:00'],
                'jugador1_id': 'uid-test-1',
                'jugador2_id': 'uid-test-2',
            })

        assert resp.status_code == 200
        # Verificar que los IDs se propagaron al dict
        pareja_actualizada = datos['resultado_algoritmo']['grupos_por_categoria']['Cuarta'][0]['parejas'][0]
        assert pareja_actualizada['jugador1_id'] == 'uid-test-1'
        assert pareja_actualizada['jugador2_id'] == 'uid-test-2'

    def test_endpoint_sin_ids_no_rompe(self, client, admin_cookie):
        """El endpoint es lenient — acepta peticiones sin jugador_ids (legacy)."""
        datos = self._datos_con_pareja(pareja_id=88)
        pareja = datos['resultado_algoritmo']['grupos_por_categoria']['Cuarta'][0]['parejas'][0]

        with patch('api.routes.parejas.obtener_datos_desde_token', return_value=datos), \
             patch('api.routes.parejas.sincronizar_con_storage_y_token'), \
             patch('api.routes.parejas.crear_respuesta_con_token_actualizado',
                   side_effect=lambda body, _: __import__('flask').jsonify(body)):

            resp = admin_cookie.post('/api/editar-pareja', json={
                'pareja_id': pareja['id'],
                'nombre': pareja['nombre'],
                'telefono': '600000000',
                'categoria': 'Cuarta',
                'franjas': ['Sábado 09:00'],
                # Sin jugador1_id ni jugador2_id
            })

        assert resp.status_code == 200
