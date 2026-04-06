"""
Capa de servicio para fixtures y calendario de finales.

Responsabilidades:
- Obtener / generar / regenerar fixtures de finales
- Actualizar ganador de un partido de finales
- Guardar resultado con sets en un partido de finales
- Obtener / sincronizar el calendario de finales
- Generar fixtures al activar la fase 'torneo' (llamado desde torneo_service)

Los métodos reciben el dict `torneo` (cargado desde storage) y lo mutan;
el caller es responsable de persistir con storage.guardar_con_version().
"""

import logging

from core.fixture_finales_generator import GeneradorFixtureFinales
from core.models import Grupo, FixtureFinales
from utils.calendario_finales_builder import GeneradorCalendarioFinales
from utils.torneo_storage import storage, ConflictError
from .exceptions import ServiceError

logger = logging.getLogger(__name__)


# ==================== FIXTURES ====================

def obtener_o_generar_fixtures(torneo: dict) -> dict:
    """Devuelve los fixtures del torneo, generándolos si no existen o son stale.

    Puede persistir el torneo actualizado.

    Returns:
        dict con todos los fixtures por categoría.

    Raises:
        ServiceError si no hay resultado del algoritmo.
    """
    resultado = torneo.get('resultado_algoritmo')
    if not resultado:
        raise ServiceError('No hay resultado del algoritmo disponible', 404)

    grupos_por_categoria = resultado.get('grupos_por_categoria', {})
    fixtures_guardados = torneo.get('fixtures_finales', {})

    if fixtures_guardados:
        hay_inconsistencia = any(
            cat not in fixtures_guardados
            or not _fixture_es_consistente(fixtures_guardados[cat], len(grupos_data))
            for cat, grupos_data in grupos_por_categoria.items()
        )
        if not hay_inconsistencia:
            return fixtures_guardados
        logger.info('Fixture stale detectado (num_grupos cambió). Regenerando fixtures.')

    fixtures_nuevos = _generar_fixtures_desde_resultado(resultado)

    torneo['fixtures_finales'] = fixtures_nuevos
    torneo['calendario_finales'] = GeneradorCalendarioFinales.asignar_horarios(fixtures_nuevos)
    try:
        storage.guardar_con_version(torneo)
    except ConflictError:
        raise

    return fixtures_nuevos


def obtener_fixture_categoria(torneo: dict, categoria: str) -> dict:
    """Devuelve el fixture de una categoría, generándolo si no existe.

    Returns:
        fixture serializado de la categoría.

    Raises:
        ServiceError si no hay datos para generar el fixture.
    """
    fixtures = torneo.get('fixtures_finales', {})

    if categoria in fixtures:
        return fixtures[categoria]

    resultado = torneo.get('resultado_algoritmo')
    if not resultado:
        raise ServiceError('No hay resultado del algoritmo disponible', 404)

    grupos_data = resultado.get('grupos_por_categoria', {}).get(categoria, [])
    if not grupos_data:
        raise ServiceError(f'No hay grupos para la categoría {categoria}', 404)

    grupos = [Grupo.from_dict(g) for g in grupos_data]
    fixture = GeneradorFixtureFinales.generar_fixture(categoria, grupos)

    if not fixture:
        raise ServiceError(f'No se pudo generar fixture para {categoria}', 500)

    if 'fixtures_finales' not in torneo:
        torneo['fixtures_finales'] = {}
    torneo['fixtures_finales'][categoria] = fixture.to_dict()
    try:
        storage.guardar_con_version(torneo)
    except ConflictError:
        raise

    return fixture.to_dict()


def regenerar_todos_fixtures(torneo: dict) -> dict:
    """Regenera todos los fixtures desde los grupos actuales.

    Persiste el resultado.

    Returns:
        fixtures_nuevos dict.

    Raises:
        ServiceError si no hay resultado del algoritmo.
    """
    resultado = torneo.get('resultado_algoritmo')
    if not resultado:
        raise ServiceError('No hay resultado del algoritmo disponible', 404)

    fixtures_nuevos = _generar_fixtures_desde_resultado(resultado)

    torneo['fixtures_finales'] = fixtures_nuevos
    torneo['calendario_finales'] = GeneradorCalendarioFinales.asignar_horarios(fixtures_nuevos)
    try:
        storage.guardar_con_version(torneo)
    except ConflictError:
        raise

    return fixtures_nuevos


def regenerar_fixture_categoria(torneo: dict, categoria: str, grupos_data: list) -> None:
    """Regenera el fixture de una categoría específica y lo persiste.

    Usado por resultado_service cuando todos los resultados de un grupo están completos.

    Raises:
        ConflictError si hay conflicto de versión (propagado al caller).
    """
    if not grupos_data:
        logger.warning('No se encontraron grupos para la categoría %s', categoria)
        return

    grupos = []
    for grupo_data in grupos_data:
        try:
            grupos.append(Grupo.from_dict(grupo_data))
        except Exception as e:
            logger.error('Error al reconstruir grupo: %s', e)

    if not grupos:
        logger.warning('No se pudieron reconstruir grupos para %s', categoria)
        return

    fixture = GeneradorFixtureFinales.generar_fixture(categoria, grupos)

    if 'fixtures_finales' not in torneo:
        torneo['fixtures_finales'] = {}

    torneo['fixtures_finales'][categoria] = fixture.to_dict() if fixture else None

    # Sincronizar calendario_finales para que el calendario público refleje las parejas clasificadas
    if torneo.get('calendario_finales') and torneo.get('fixtures_finales'):
        torneo['calendario_finales'] = GeneradorCalendarioFinales.sincronizar_parejas(
            torneo['calendario_finales'], torneo['fixtures_finales']
        )

    storage.guardar_con_version(torneo)
    logger.info('Fixtures regenerados para categoría %s', categoria)


# ==================== RESULTADOS DE FINALES ====================

def actualizar_ganador(torneo: dict, partido_id: str, ganador_id: str) -> dict:
    """Actualiza el ganador de un partido de finales.

    Returns:
        fixture actualizado (to_dict).

    Raises:
        ServiceError si no hay fixtures o no se encuentra el partido.
    """
    fixtures_dict = torneo.get('fixtures_finales', {})
    if not fixtures_dict:
        raise ServiceError('No hay fixtures disponibles', 404)

    resultado = torneo.get('resultado_algoritmo')
    categoria_encontrada, _, _ = _buscar_partido_en_fixtures(fixtures_dict, partido_id)

    if not categoria_encontrada:
        raise ServiceError(f'Partido {partido_id} no encontrado', 404)

    grupos_data = resultado.get('grupos_por_categoria', {}).get(categoria_encontrada, [])
    grupos = [Grupo.from_dict(g) for g in grupos_data]
    fixture = FixtureFinales.from_dict(fixtures_dict[categoria_encontrada], grupos)

    exito = GeneradorFixtureFinales.actualizar_ganador_partido(fixture, partido_id, ganador_id)
    if not exito:
        raise ServiceError('No se pudo actualizar el ganador', 500)

    fixtures_dict[categoria_encontrada] = fixture.to_dict()
    torneo['fixtures_finales'] = fixtures_dict

    if torneo.get('calendario_finales'):
        torneo['calendario_finales'] = GeneradorCalendarioFinales.sincronizar_parejas(
            torneo['calendario_finales'], fixtures_dict
        )

    try:
        storage.guardar_con_version(torneo)
    except ConflictError:
        raise

    return fixture.to_dict()


def guardar_resultado_final(torneo: dict, partido_id: str, sets: list) -> str:
    """Guarda el resultado con sets de un partido de finales y determina el ganador.

    Returns:
        ganador_id

    Raises:
        ServiceError en caso de error de negocio.
    """
    if not sets or len(sets) < 2:
        raise ServiceError('Debes proporcionar al menos 2 sets')

    fixtures_dict = torneo.get('fixtures_finales', {})
    if not fixtures_dict:
        raise ServiceError('No hay fixtures disponibles', 404)

    resultado = torneo.get('resultado_algoritmo')
    categoria_encontrada, partido_encontrado, fase_encontrada = \
        _buscar_partido_en_fixtures(fixtures_dict, partido_id)

    if not categoria_encontrada or not partido_encontrado:
        raise ServiceError(f'Partido {partido_id} no encontrado', 404)

    sets_pareja1 = 0
    sets_pareja2 = 0
    for set_data in sets:
        games_p1 = set_data.get('pareja1', 0)
        games_p2 = set_data.get('pareja2', 0)
        if games_p1 > games_p2:
            sets_pareja1 += 1
        elif games_p2 > games_p1:
            sets_pareja2 += 1

    if sets_pareja1 > sets_pareja2:
        ganador_id = partido_encontrado.get('pareja1', {}).get('id')
    elif sets_pareja2 > sets_pareja1:
        ganador_id = partido_encontrado.get('pareja2', {}).get('id')
    else:
        raise ServiceError('No se puede determinar un ganador con estos resultados')

    partido_encontrado['sets'] = sets
    partido_encontrado['ganador'] = {'id': ganador_id}

    if fase_encontrada[0] == 'final':
        fixtures_dict[categoria_encontrada]['final'] = partido_encontrado
    else:
        fixtures_dict[categoria_encontrada][fase_encontrada[0]][fase_encontrada[1]] = partido_encontrado

    grupos_data = resultado.get('grupos_por_categoria', {}).get(categoria_encontrada, [])
    grupos = [Grupo.from_dict(g) for g in grupos_data]
    fixture = FixtureFinales.from_dict(fixtures_dict[categoria_encontrada], grupos)

    GeneradorFixtureFinales.actualizar_ganador_partido(fixture, partido_id, ganador_id)
    fixtures_dict[categoria_encontrada] = fixture.to_dict()
    torneo['fixtures_finales'] = fixtures_dict

    if torneo.get('calendario_finales'):
        torneo['calendario_finales'] = GeneradorCalendarioFinales.sincronizar_parejas(
            torneo['calendario_finales'], fixtures_dict
        )

    try:
        storage.guardar_con_version(torneo)
    except ConflictError:
        raise

    return ganador_id


# ==================== CALENDARIO ====================

def obtener_calendario(torneo: dict) -> tuple[dict, dict]:
    """Devuelve el calendario de finales sincronizado.

    Returns:
        (calendario, resumen_horarios)

    Raises:
        ServiceError si no hay fixtures.
    """
    calendario = torneo.get('calendario_finales')
    fixtures = torneo.get('fixtures_finales', {})

    if not calendario:
        if not fixtures:
            raise ServiceError('No hay fixtures disponibles', 404)
        calendario = GeneradorCalendarioFinales.generar_plantilla_calendario(fixtures)

    if fixtures:
        calendario = GeneradorCalendarioFinales.sincronizar_parejas(calendario, fixtures)

    resumen = GeneradorCalendarioFinales.generar_resumen_horarios()
    return calendario, resumen


# ==================== GENERACIÓN AL ACTIVAR TORNEO ====================

def generar_al_activar_torneo(torneo: dict) -> None:
    """Genera fixtures y calendario cuando se activa la fase 'torneo'.

    Muta `torneo` en lugar. No persiste — el caller (torneo_service) lo hace.
    """
    resultado = torneo.get('resultado_algoritmo')
    if not resultado or torneo.get('fixtures_finales'):
        return

    try:
        grupos_por_cat = resultado.get('grupos_por_categoria', {})
        fixtures_nuevos = {}
        for cat, grupos_data in grupos_por_cat.items():
            grupos = [Grupo.from_dict(g) for g in grupos_data]
            fixture = GeneradorFixtureFinales.generar_fixture(cat, grupos)
            if fixture:
                fixtures_nuevos[cat] = fixture.to_dict()
        if fixtures_nuevos:
            torneo['fixtures_finales'] = fixtures_nuevos
            logger.info('Fixtures generados al activar torneo: %s', list(fixtures_nuevos.keys()))
    except Exception as e:
        logger.error('Error generando fixtures al activar torneo: %s', e)

    if torneo.get('fixtures_finales') and not torneo.get('calendario_finales'):
        try:
            torneo['calendario_finales'] = GeneradorCalendarioFinales.generar_plantilla_calendario(
                torneo['fixtures_finales']
            )
            logger.info('Calendario de finales generado al activar torneo')
        except Exception as e:
            logger.error('Error generando calendario al activar torneo: %s', e)


# ==================== HELPERS INTERNOS ====================

def _buscar_partido_en_fixtures(fixtures_dict: dict, partido_id: str):
    """Busca un partido en todos los fixtures por ID.

    Returns:
        (categoria, partido_dict, (fase_key, fase_idx)) si se encuentra.
        (None, None, None) si no se encuentra.
    """
    for categoria, fixture_dict in fixtures_dict.items():
        for fase in ['octavos', 'cuartos', 'semifinales']:
            for idx, partido in enumerate(fixture_dict.get(fase, [])):
                if partido and partido.get('id') == partido_id:
                    return categoria, partido, (fase, idx)
        if fixture_dict.get('final', {}).get('id') == partido_id:
            return categoria, fixture_dict['final'], ('final', None)
    return None, None, None


def _fixture_es_consistente(fixture_dict: dict, num_grupos: int) -> bool:
    """Verifica si el fixture almacenado es estructuralmente consistente."""
    num_cuartos = len(fixture_dict.get('cuartos', []))
    num_octavos = len(fixture_dict.get('octavos', []))
    if num_grupos == 3:
        return num_cuartos == 2 and num_octavos == 0
    elif num_grupos == 4:
        return num_cuartos == 4 and num_octavos == 0
    elif num_grupos == 5:
        return num_cuartos == 4 and num_octavos == 2
    return True


def _generar_fixtures_desde_resultado(resultado: dict) -> dict:
    """Genera todos los fixtures desde un dict resultado_algoritmo."""
    grupos_por_categoria = resultado.get('grupos_por_categoria', {})
    fixtures_nuevos = {}
    for categoria, grupos_data in grupos_por_categoria.items():
        grupos = [Grupo.from_dict(g) for g in grupos_data]
        fixture = GeneradorFixtureFinales.generar_fixture(categoria, grupos)
        if fixture:
            fixtures_nuevos[categoria] = fixture.to_dict()
    return fixtures_nuevos
