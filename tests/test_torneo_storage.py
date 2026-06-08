"""Tests for TorneoStorage: cuenta_ranking in _torneo_vacio and set_proximo_torneo."""

from unittest.mock import MagicMock, patch


def _make_storage():
    with patch('utils.torneo_storage._USE_SUPABASE', False):
        from utils.torneo_storage import TorneoStorage
        return TorneoStorage()


class TestTorneoVacio:
    def test_cuenta_ranking_default_true(self):
        s = _make_storage()
        result = s._torneo_vacio()
        assert result.get('cuenta_ranking') is True


class TestSetProximoTorneo:
    def _storage_with_mocks(self, tipo='fin1', cuenta_ranking=True):
        s = _make_storage()
        torneo = {'nombre': '', 'tipo_torneo': tipo, 'version': 0, 'cuenta_ranking': cuenta_ranking}
        s.cargar = MagicMock(return_value=torneo)
        s.guardar_con_version = MagicMock()
        return s

    def test_mixto_sets_cuenta_ranking_false(self):
        s = self._storage_with_mocks()
        s.set_proximo_torneo(fecha='2026-07-01', nombre='Mixto', tipo_torneo='mixto')
        saved = s.guardar_con_version.call_args[0][0]
        assert saved['cuenta_ranking'] is False

    def test_fin1_sets_cuenta_ranking_true(self):
        s = self._storage_with_mocks(tipo='mixto', cuenta_ranking=False)
        s.set_proximo_torneo(fecha='2026-07-01', nombre='Fin1', tipo_torneo='fin1')
        saved = s.guardar_con_version.call_args[0][0]
        assert saved['cuenta_ranking'] is True

    def test_fin2_sets_cuenta_ranking_true(self):
        s = self._storage_with_mocks()
        s.set_proximo_torneo(fecha='2026-07-01', nombre='Fin2', tipo_torneo='fin2')
        saved = s.guardar_con_version.call_args[0][0]
        assert saved['cuenta_ranking'] is True

    def test_proximo_torneo_dict_incluye_cuenta_ranking(self):
        s = self._storage_with_mocks()
        s.set_proximo_torneo(fecha='2026-07-01', nombre='Mixto', tipo_torneo='mixto')
        saved = s.guardar_con_version.call_args[0][0]
        assert saved['proximo_torneo']['cuenta_ranking'] is False
