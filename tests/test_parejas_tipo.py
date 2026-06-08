"""Tests para el validator de tipo en parejas blueprint."""

from unittest.mock import patch, MagicMock


class TestCambiarTipoTorneo:
    def test_mixto_aceptado(self, admin_cookie):
        with patch('api.routes.parejas.storage') as mock_st:
            mock_st.set_tipo_torneo.return_value = None
            resp = admin_cookie.post('/api/cambiar-tipo-torneo', json={'tipo_torneo': 'mixto'})
        assert resp.status_code == 200

    def test_tipo_invalido_retorna_400(self, admin_cookie):
        resp = admin_cookie.post('/api/cambiar-tipo-torneo', json={'tipo_torneo': 'fin3'})
        assert resp.status_code == 400

    def test_fin1_sigue_siendo_valido(self, admin_cookie):
        with patch('api.routes.parejas.storage') as mock_st:
            mock_st.set_tipo_torneo.return_value = None
            resp = admin_cookie.post('/api/cambiar-tipo-torneo', json={'tipo_torneo': 'fin1'})
        assert resp.status_code == 200

    def test_fin2_sigue_siendo_valido(self, admin_cookie):
        with patch('api.routes.parejas.storage') as mock_st:
            mock_st.set_tipo_torneo.return_value = None
            resp = admin_cookie.post('/api/cambiar-tipo-torneo', json={'tipo_torneo': 'fin2'})
        assert resp.status_code == 200
