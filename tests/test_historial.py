"""Tests para historial blueprint: validator tipo mixto + write gate cuenta_ranking."""

from unittest.mock import MagicMock, patch


_TORNEO_MIXTO = {
    'nombre': 'Torneo Mixto 2026',
    'tipo_torneo': 'mixto',
    'cuenta_ranking': False,
    'resultado_algoritmo': None,
    'fixtures_finales': {},
    'calendario_finales': {},
    'estado': 'finales',
    'version': 1,
    'torneo_id': 'test-torneo-id',
}

_TORNEO_FIN1 = {
    'nombre': 'Torneo Fin1 2026',
    'tipo_torneo': 'fin1',
    'cuenta_ranking': True,
    'resultado_algoritmo': None,
    'fixtures_finales': {},
    'calendario_finales': {},
    'estado': 'finales',
    'version': 1,
    'torneo_id': 'test-torneo-id',
}


class TestConfigurarProximoTorneo:
    def test_mixto_aceptado(self, admin_cookie):
        with patch('api.routes.historial.storage') as mock_st:
            mock_st.get_fase.return_value = 'espera'
            mock_st.set_proximo_torneo.return_value = None
            mock_st.get_proximo_torneo.return_value = {'tipo_torneo': 'mixto'}
            resp = admin_cookie.post('/api/admin/proximo-torneo', json={
                'nombre': 'Torneo Mixto', 'fecha': '2026-07-01', 'tipo_torneo': 'mixto',
            })
        assert resp.status_code == 200

    def test_tipo_invalido_retorna_400(self, admin_cookie):
        with patch('api.routes.historial.storage') as mock_st:
            mock_st.get_fase.return_value = 'espera'
            resp = admin_cookie.post('/api/admin/proximo-torneo', json={
                'nombre': 'Torneo X', 'fecha': '2026-07-01', 'tipo_torneo': 'fin3',
            })
        assert resp.status_code == 400


class TestTerminarTorneoWriteGate:
    def _mock_sb(self):
        sb = MagicMock()
        sb.table.return_value.upsert.return_value.execute.return_value = MagicMock()
        return sb

    def test_no_calcula_puntos_cuando_cuenta_ranking_false(self, admin_cookie):
        with patch('api.routes.historial.storage') as mock_st, \
             patch('api.routes.historial._use_supabase', return_value=True), \
             patch('api.routes.historial._sb_admin', return_value=self._mock_sb()), \
             patch('api.routes.historial._calcular_y_guardar_puntos') as mock_calc, \
             patch('api.routes.historial._poblar_tablas_relacionales'):
            mock_st.cargar.return_value = _TORNEO_MIXTO.copy()
            mock_st.get_torneo_id.return_value = 'test-torneo-id'
            mock_st.transicion_a_espera.return_value = None

            resp = admin_cookie.post('/api/admin/terminar-torneo')
            assert resp.status_code == 200
            mock_calc.assert_not_called()

    def test_calcula_puntos_cuando_cuenta_ranking_true(self, admin_cookie):
        with patch('api.routes.historial.storage') as mock_st, \
             patch('api.routes.historial._use_supabase', return_value=True), \
             patch('api.routes.historial._sb_admin', return_value=self._mock_sb()), \
             patch('api.routes.historial._calcular_y_guardar_puntos') as mock_calc, \
             patch('api.routes.historial._poblar_tablas_relacionales'):
            mock_st.cargar.return_value = _TORNEO_FIN1.copy()
            mock_st.get_torneo_id.return_value = 'test-torneo-id'
            mock_st.transicion_a_espera.return_value = None

            resp = admin_cookie.post('/api/admin/terminar-torneo')
            assert resp.status_code == 200
            mock_calc.assert_called_once()
