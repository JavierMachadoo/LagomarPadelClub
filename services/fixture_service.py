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
        fixtures_validos = {k: v for k, v in torneo['fixtures_finales'].items() if v is not None}
        if fixtures_validos:
            torneo['calendario_finales'] = GeneradorCalendarioFinales.sincronizar_parejas(
                torneo['calendario_finales'], fixtures_validos
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


# ==================== CALENDARIO (ADMIN) ====================

def mover_partido_calendario(torneo: dict, partido_id: str, nueva_hora: str, nueva_cancha: int) -> dict:
    """Mueve o intercambia un partido en el calendario del domingo.

    Si el slot destino está vacío → mueve el partido.
    Si el slot destino está ocupado → intercambia los dos partidos (swap).

    Args:
        torneo: dict del torneo cargado
        partido_id: ID del partido a mover
        nueva_hora: hora destino en formato "HH:00"
        nueva_cancha: número de cancha destino (1 o 2)

    Returns:
        calendario_finales actualizado

    Raises:
        ServiceError si no hay calendario o no se encuentra el partido.
    """
    calendario = torneo.get('calendario_finales')
    if not calendario:
        raise ServiceError('No hay calendario disponible', 404)

    if nueva_cancha not in (1, 2):
        raise ServiceError('Número de cancha inválido', 400)

    # Buscar partido origen
    partido_origen = None
    idx_origen = None
    cancha_origen_key = None
    for cancha_key in ['cancha_1', 'cancha_2']:
        for i, p in enumerate(calendario.get(cancha_key, [])):
            if p.get('partido_id') == partido_id:
                partido_origen = p
                idx_origen = i
                cancha_origen_key = cancha_key
                break
        if partido_origen:
            break

    if not partido_origen:
        raise ServiceError(f'Partido {partido_id} no encontrado en el calendario', 404)

    cancha_destino_key = f'cancha_{nueva_cancha}'
    hora_origen = partido_origen['hora_inicio']
    cancha_num_origen = 1 if cancha_origen_key == 'cancha_1' else 2

    # Verificar que no se mueve al mismo slot
    if hora_origen == nueva_hora and cancha_num_origen == nueva_cancha:
        return calendario

    # Buscar si hay partido en el slot destino
    partido_destino = None
    idx_destino = None
    for i, p in enumerate(calendario.get(cancha_destino_key, [])):
        if p.get('hora_inicio') == nueva_hora:
            partido_destino = p
            idx_destino = i
            break

    if partido_destino:
        # Swap: ambos partidos intercambian slots
        hora_fin_origen = f"{int(hora_origen.split(':')[0]) + 1:02d}:00"
        hora_fin_destino = f"{int(nueva_hora.split(':')[0]) + 1:02d}:00"

        partido_destino['hora_inicio'] = hora_origen
        partido_destino['hora_fin'] = hora_fin_origen
        partido_destino['cancha'] = cancha_num_origen
        calendario[cancha_origen_key][idx_origen] = partido_destino

        partido_origen['hora_inicio'] = nueva_hora
        partido_origen['hora_fin'] = hora_fin_destino
        partido_origen['cancha'] = nueva_cancha
        calendario[cancha_destino_key][idx_destino] = partido_origen
    else:
        # Move: mover al slot libre y mantener orden cronológico
        partido_origen['hora_inicio'] = nueva_hora
        partido_origen['hora_fin'] = f"{int(nueva_hora.split(':')[0]) + 1:02d}:00"
        partido_origen['cancha'] = nueva_cancha

        calendario[cancha_origen_key].pop(idx_origen)

        lista_destino = calendario.get(cancha_destino_key, [])
        lista_destino.append(partido_origen)
        lista_destino.sort(key=lambda x: x['hora_inicio'])
        calendario[cancha_destino_key] = lista_destino

    torneo['calendario_finales'] = calendario
    try:
        storage.guardar_con_version(torneo)
    except ConflictError:
        raise

    return calendario


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
    num_semis = len(fixture_dict.get('semifinales', []))
    if num_grupos == 2:
        return num_cuartos == 0 and num_octavos == 0 and num_semis == 2
    elif num_grupos == 3:
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
