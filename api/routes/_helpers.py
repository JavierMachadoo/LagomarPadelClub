"""
Re-exportaciones de compatibilidad.

Las funciones de este módulo se movieron a la capa de servicios en la etapa 4 del refactor.
Este archivo existe para no romper imports existentes (tests, etc).

TODO etapa 6: eliminar este archivo y actualizar todos los imports directamente a services/.
"""

from services.grupo_service import (
    serializar_resultado,
    recalcular_estadisticas,
    recalcular_score_grupo,
    regenerar_calendario,
)
from services.grupo_service import _deserializar_resultado as deserializar_resultado
from services.fixture_service import regenerar_fixture_categoria as regenerar_fixtures_categoria
from services.resultado_service import _verificar_posiciones_completas as verificar_posiciones_completas

__all__ = [
    'serializar_resultado',
    'deserializar_resultado',
    'recalcular_estadisticas',
    'recalcular_score_grupo',
    'regenerar_calendario',
    'regenerar_fixtures_categoria',
    'verificar_posiciones_completas',
]
