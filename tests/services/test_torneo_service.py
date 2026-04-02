"""
Tests unitarios para torneo_service.
"""

import pytest
from unittest.mock import patch, MagicMock

from services.torneo_service import cambiar_fase
from services.exceptions import ServiceError


class TestCambiarFase:

    def _mock_torneo(self, fase_actual: str = 'inscripcion') -> dict:
        return {
            'fase': fase_actual,
            'resultado_algoritmo': None,
            'fixtures_finales': {},
            'calendario_finales': None,
        }

    def test_fase_invalida_lanza_error(self):
        with pytest.raises(ServiceError) as exc:
            cambiar_fase('invalida')
        assert exc.value.status_code == 400

    def test_cambia_a_torneo_exitosamente(self):
        torneo = self._mock_torneo('inscripcion')
        with patch('services.torneo_service.storage') as mock_storage, \
             patch('services.torneo_service.generar_al_activar_torneo') as mock_gen:
            mock_storage.cargar.return_value = torneo
            fase = cambiar_fase('torneo')

        assert fase == 'torneo'
        mock_storage.guardar_con_version.assert_called_once()
        mock_gen.assert_called_once()

    def test_cambia_a_espera_sin_generar_fixtures(self):
        torneo = self._mock_torneo('torneo')
        with patch('services.torneo_service.storage') as mock_storage, \
             patch('services.torneo_service.generar_al_activar_torneo') as mock_gen:
            mock_storage.cargar.return_value = torneo
            fase = cambiar_fase('espera')

        assert fase == 'espera'
        mock_gen.assert_not_called()

    def test_cambia_a_inscripcion(self):
        torneo = self._mock_torneo('torneo')
        with patch('services.torneo_service.storage') as mock_storage, \
             patch('services.torneo_service.generar_al_activar_torneo'):
            mock_storage.cargar.return_value = torneo
            fase = cambiar_fase('inscripcion')

        assert fase == 'inscripcion'

    @pytest.mark.parametrize('fase', ['inscripcion', 'torneo', 'espera'])
    def test_todas_las_fases_validas_son_aceptadas(self, fase):
        torneo = self._mock_torneo()
        with patch('services.torneo_service.storage') as mock_storage, \
             patch('services.torneo_service.generar_al_activar_torneo'):
            mock_storage.cargar.return_value = torneo
            result = cambiar_fase(fase)
        assert result == fase
