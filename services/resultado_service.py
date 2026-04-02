"""
Capa de servicio para resultados de partidos de grupo y clasificación.

Responsabilidades:
- Asignar posición final de una pareja en su grupo
- Guardar/actualizar resultado de un partido de grupo (sets, ganador, tiebreak)
- Calcular tabla de posiciones de un grupo
- Llamar a fixture_service cuando todos los resultados de un grupo están completos

No importa nada de Flask.
"""

import logging

from core import Pareja, Grupo
from core.models import ResultadoPartido
from core.clasificacion import CalculadorClasificacion
from utils.torneo_storage import storage, ConflictError
from .exceptions import ServiceError

logger = logging.getLogger(__name__)


def asignar_posicion(
    resultado_data: dict,
    pareja_id: int,
    posicion: int,
    categoria: str,
) -> tuple[bool, int | None]:
    """Asigna o desasigna la posición final de una pareja en su grupo.

    Muta `resultado_data` en lugar.

    Args:
        posicion: 0 para deseleccionar, 1-3 para asignar.

    Returns:
        (puede_generar_finales, posicion_anterior)

    Raises:
        ServiceError si la pareja no se encuentra.
    """
    grupos_categoria = resultado_data['grupos_por_categoria'].get(categoria, [])
    pareja_encontrada = False
    posicion_anterior = None

    for grupo in grupos_categoria:
        for pareja in grupo['parejas']:
            if pareja['id'] == pareja_id:
                posicion_anterior = pareja.get('posicion_grupo')
                pareja['posicion_grupo'] = None if posicion == 0 else posicion
                pareja_encontrada = True
                break
        if pareja_encontrada:
            break

    if not pareja_encontrada:
        raise ServiceError('Pareja no encontrada', 404)

    puede_generar = _verificar_posiciones_completas(grupos_categoria)

    # Regenerar fixture porque las posiciones determinan quién clasifica a finales
    _regenerar_fixture_si_completo(resultado_data, categoria)

    return puede_generar, posicion_anterior


def guardar_resultado_grupo(
    resultado_data: dict,
    categoria: str,
    grupo_id: int,
    pareja1_id: int,
    pareja2_id: int,
    games_set1_p1: int | None,
    games_set1_p2: int | None,
    games_set2_p1: int | None,
    games_set2_p2: int | None,
    tiebreak_p1: int | None,
    tiebreak_p2: int | None,
) -> tuple[dict, bool]:
    """Guarda el resultado de un partido de grupo y recalcula clasificación si completo.

    Muta `resultado_data` en lugar. Si todos los resultados de un grupo están
    completos, también regenera el fixture de finales para esa categoría.

    Returns:
        (resultado_dict, resultados_completos)

    Raises:
        ServiceError si el grupo no existe.
    """
    grupos_categoria = resultado_data['grupos_por_categoria'].get(categoria, [])
    grupo_encontrado = None
    for grupo in grupos_categoria:
        if grupo['id'] == grupo_id:
            grupo_encontrado = grupo
            break

    if not grupo_encontrado:
        raise ServiceError('Grupo no encontrado', 404)

    # Calcular sets ganados
    sets_p1 = 0
    sets_p2 = 0
    if games_set1_p1 is not None and games_set1_p2 is not None:
        if games_set1_p1 > games_set1_p2:
            sets_p1 += 1
        else:
            sets_p2 += 1
    if games_set2_p1 is not None and games_set2_p2 is not None:
        if games_set2_p1 > games_set2_p2:
            sets_p1 += 1
        else:
            sets_p2 += 1

    resultado = ResultadoPartido(
        pareja1_id=pareja1_id,
        pareja2_id=pareja2_id,
        sets_pareja1=sets_p1,
        sets_pareja2=sets_p2,
        games_set1_pareja1=games_set1_p1,
        games_set1_pareja2=games_set1_p2,
        games_set2_pareja1=games_set2_p1,
        games_set2_pareja2=games_set2_p2,
        tiebreak_pareja1=tiebreak_p1,
        tiebreak_pareja2=tiebreak_p2,
    )

    if 'resultados' not in grupo_encontrado:
        grupo_encontrado['resultados'] = {}

    ids_ordenados = sorted([pareja1_id, pareja2_id])
    key = f"{ids_ordenados[0]}-{ids_ordenados[1]}"
    grupo_encontrado['resultados'][key] = resultado.to_dict()

    # Verificar si todos los resultados del grupo están completos
    grupo_encontrado['resultados_completos'] = False
    if len(grupo_encontrado.get('parejas', [])) == 3:
        resultados_completos_count = sum(
            1 for r in grupo_encontrado['resultados'].values()
            if ResultadoPartido.from_dict(r).esta_completo()
        )
        grupo_encontrado['resultados_completos'] = (resultados_completos_count == 3)

    # Si grupo completo: calcular posiciones automáticamente
    if grupo_encontrado.get('resultados_completos', False):
        _calcular_posiciones_grupo(grupo_encontrado, categoria)
        _regenerar_fixture_si_completo(resultado_data, categoria)

    return resultado.to_dict(), grupo_encontrado.get('resultados_completos', False)


def obtener_tabla_posiciones(resultado_data: dict, categoria: str, grupo_id: int) -> dict:
    """Calcula la tabla de posiciones de un grupo.

    Returns:
        tabla de posiciones.

    Raises:
        ServiceError si el grupo no existe.
    """
    grupos_categoria = resultado_data['grupos_por_categoria'].get(categoria, [])
    grupo_encontrado = None
    for grupo in grupos_categoria:
        if grupo['id'] == grupo_id:
            grupo_encontrado = grupo
            break

    if not grupo_encontrado:
        raise ServiceError('Grupo no encontrado', 404)

    grupo_obj = _reconstruir_grupo_obj(grupo_encontrado, categoria)
    tabla = CalculadorClasificacion.calcular_tabla_posiciones(grupo_obj)
    return tabla


# ==================== HELPERS INTERNOS ====================

def _verificar_posiciones_completas(grupos: list) -> bool:
    """Verifica si todas las parejas de todos los grupos tienen posición asignada."""
    return all(
        pareja.get('posicion_grupo')
        for grupo in grupos
        for pareja in grupo['parejas']
    )


def _calcular_posiciones_grupo(grupo_dict: dict, categoria: str) -> None:
    """Calcula y asigna posiciones automáticamente usando CalculadorClasificacion."""
    grupo_obj = _reconstruir_grupo_obj(grupo_dict, categoria)
    posiciones = CalculadorClasificacion.asignar_posiciones(grupo_obj)
    for pareja_dict in grupo_dict['parejas']:
        pid = pareja_dict['id']
        if pid in posiciones:
            pareja_dict['posicion_grupo'] = posiciones[pid].value


def _reconstruir_grupo_obj(grupo_dict: dict, categoria: str) -> Grupo:
    """Reconstruye un objeto Grupo desde su representación dict."""
    grupo_obj = Grupo(
        id=grupo_dict['id'],
        categoria=categoria,
        franja_horaria=grupo_dict.get('franja_horaria'),
    )
    for pareja_dict in grupo_dict['parejas']:
        pareja = Pareja(
            id=pareja_dict['id'],
            nombre=pareja_dict['nombre'],
            telefono=pareja_dict.get('telefono', 'Sin teléfono'),
            categoria=pareja_dict['categoria'],
            franjas_disponibles=pareja_dict.get('franjas_disponibles', []),
            grupo_asignado=grupo_dict['id'],
        )
        grupo_obj.parejas.append(pareja)
    for k, rd in grupo_dict.get('resultados', {}).items():
        grupo_obj.resultados[k] = ResultadoPartido.from_dict(rd)
    return grupo_obj


def _regenerar_fixture_si_completo(resultado_data: dict, categoria: str) -> None:
    """Regenera el fixture de finales de una categoría y lo persiste.

    Llamado cuando todos los resultados de un grupo de esa categoría están completos.
    Los errores se loguean pero no se propagan — el resultado del partido ya se guardó.
    """
    try:
        from services.fixture_service import regenerar_fixture_categoria
        grupos_data = resultado_data.get('grupos_por_categoria', {}).get(categoria, [])
        torneo = storage.cargar()
        regenerar_fixture_categoria(torneo, categoria, grupos_data)
        logger.info('Fixtures regenerados automáticamente para %s', categoria)
    except ConflictError:
        raise  # el route handler devuelve 409
    except Exception as e:
        logger.error('Error al regenerar fixtures para %s: %s', categoria, e)
