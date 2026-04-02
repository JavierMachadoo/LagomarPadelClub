"""
Capa de servicio para transiciones de estado del torneo.

Responsabilidades:
- Cambiar la fase del torneo (inscripcion → torneo → espera)
- Coordinar la generación de fixtures y calendario al activar la fase 'torneo'

No importa nada de Flask.
"""

import logging

from utils.torneo_storage import storage, ConflictError
from services.fixture_service import generar_al_activar_torneo
from .exceptions import ServiceError

logger = logging.getLogger(__name__)

_FASES_VALIDAS = ('inscripcion', 'torneo', 'espera')


def cambiar_fase(nueva_fase: str) -> str:
    """Cambia la fase del torneo.

    Al activar 'torneo', genera fixtures y calendario si no existen.

    Returns:
        la nueva fase establecida.

    Raises:
        ServiceError si la fase es inválida.
        ConflictError si hay conflicto de versión en storage.
    """
    if nueva_fase not in _FASES_VALIDAS:
        raise ServiceError('Fase inválida')

    torneo = storage.cargar()
    fase_actual = torneo.get('fase', 'inscripcion')

    torneo['fase'] = nueva_fase

    if nueva_fase == 'torneo':
        generar_al_activar_torneo(torneo)

    storage.guardar_con_version(torneo)
    logger.info('Fase del torneo cambiada: %s → %s', fase_actual, nueva_fase)
    return nueva_fase
