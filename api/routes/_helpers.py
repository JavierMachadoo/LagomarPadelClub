"""
Helpers compartidos entre los módulos de rutas de la API.

Contiene funciones internas (no rutas) que son usadas por más de un blueprint:
- serializar_resultado / deserializar_resultado
- regenerar_calendario (depende de deserializar_resultado)
- recalcular_estadisticas / recalcular_score_grupo
- regenerar_fixtures_categoria
- verificar_posiciones_completas
"""

import logging

from core import Pareja, AlgoritmoGrupos, ResultadoAlgoritmo, Grupo
from core.fixture_finales_generator import GeneradorFixtureFinales
from utils import CalendarioBuilder
from utils.torneo_storage import storage, ConflictError
from utils.api_helpers import obtener_datos_desde_token, sincronizar_con_storage_y_token
from config import NUM_CANCHAS_DEFAULT

logger = logging.getLogger(__name__)


# ==================== SERIALIZACIÓN ====================

def serializar_resultado(resultado, num_canchas):
    """Convierte el resultado del algoritmo a formato JSON serializable."""
    grupos_dict = {}
    canchas_por_grupo = {}

    for franja, partidos_franja in resultado.calendario.items():
        for partido in partidos_franja:
            grupo_id = partido.get('grupo_id')
            cancha = partido.get('cancha')
            if grupo_id and cancha:
                canchas_por_grupo[grupo_id] = cancha

    for categoria, grupos in resultado.grupos_por_categoria.items():
        grupos_dict[categoria] = []

        for grupo in grupos:
            cancha_num = canchas_por_grupo.get(grupo.id)

            grupos_dict[categoria].append({
                'id': grupo.id,
                'parejas': [p.to_dict() for p in grupo.parejas],
                'partidos': [
                    {
                        'pareja1': p1.nombre,
                        'pareja2': p2.nombre,
                        'pareja1_id': p1.id,
                        'pareja2_id': p2.id
                    }
                    for p1, p2 in grupo.partidos
                ],
                'resultados': {},
                'franja_horaria': grupo.franja_horaria,
                'cancha': cancha_num,
                'score': grupo.score_compatibilidad,
                'resultados_completos': False
            })

    calendario_builder = CalendarioBuilder(num_canchas)
    calendario = calendario_builder.organizar_partidos(resultado, canchas_por_grupo)

    return {
        'grupos_por_categoria': grupos_dict,
        'estadisticas': resultado.estadisticas,
        'parejas_sin_asignar': [p.to_dict() for p in resultado.parejas_sin_asignar],
        'calendario': calendario
    }


def deserializar_resultado(resultado_data):
    """Reconstruye el objeto ResultadoAlgoritmo desde datos de sesión."""
    from core.models import ResultadoPartido

    grupos_por_categoria = {}

    for categoria, grupos_list in resultado_data['grupos_por_categoria'].items():
        grupos_por_categoria[categoria] = []
        for grupo_dict in grupos_list:
            grupo = Grupo(
                id=grupo_dict['id'],
                categoria=categoria
            )
            grupo.franja_horaria = grupo_dict.get('franja_horaria')
            grupo.score_compatibilidad = grupo_dict.get('score', 0.0)

            resultados_raw = grupo_dict.get('resultados', {})
            for key, r_data in resultados_raw.items():
                if isinstance(r_data, dict):
                    grupo.resultados[key] = ResultadoPartido.from_dict(r_data)
                else:
                    grupo.resultados[key] = r_data
            grupo.resultados_completos = grupo_dict.get('resultados_completos', False)

            for pareja_dict in grupo_dict['parejas']:
                pareja = Pareja(
                    id=pareja_dict['id'],
                    nombre=pareja_dict['nombre'],
                    telefono=pareja_dict.get('telefono', 'Sin teléfono'),
                    categoria=pareja_dict['categoria'],
                    franjas_disponibles=pareja_dict.get('franjas_disponibles', [])
                )
                grupo.parejas.append(pareja)

            grupo.generar_partidos()
            grupos_por_categoria[categoria].append(grupo)

    parejas_sin_asignar = []
    for p in resultado_data.get('parejas_sin_asignar', []):
        pareja = Pareja(
            id=p['id'],
            nombre=p['nombre'],
            telefono=p.get('telefono', 'Sin teléfono'),
            categoria=p['categoria'],
            franjas_disponibles=p.get('franjas_disponibles', [])
        )
        parejas_sin_asignar.append(pareja)

    return ResultadoAlgoritmo(
        grupos_por_categoria=grupos_por_categoria,
        parejas_sin_asignar=parejas_sin_asignar,
        calendario=resultado_data.get('calendario', {}),
        estadisticas=resultado_data.get('estadisticas', {})
    )


# ==================== RECÁLCULOS ====================

def recalcular_estadisticas(resultado_data):
    """Recalcula las estadísticas globales del torneo basándose en el estado actual."""
    grupos_dict = resultado_data.get('grupos_por_categoria', {})
    parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])

    parejas_asignadas = 0
    total_grupos = 0
    sum_scores = 0.0
    grupos_con_score = 0

    for categoria, grupos in grupos_dict.items():
        for grupo in grupos:
            total_grupos += 1
            parejas_en_grupo = len(grupo.get('parejas', []))
            parejas_asignadas += parejas_en_grupo

            score = grupo.get('score', 0.0)
            if score > 0:
                sum_scores += score
                grupos_con_score += 1

    total_parejas = parejas_asignadas + len(parejas_sin_asignar)
    porcentaje_asignacion = (parejas_asignadas / total_parejas * 100) if total_parejas > 0 else 0
    score_promedio = (sum_scores / grupos_con_score) if grupos_con_score > 0 else 0.0

    resultado_data['estadisticas'] = {
        'parejas_asignadas': parejas_asignadas,
        'total_parejas': total_parejas,
        'parejas_sin_asignar': len(parejas_sin_asignar),
        'porcentaje_asignacion': porcentaje_asignacion,
        'total_grupos': total_grupos,
        'score_compatibilidad_promedio': score_promedio
    }

    return resultado_data['estadisticas']


def recalcular_score_grupo(grupo_dict):
    """Recalcula el score de compatibilidad de un grupo según sus parejas actuales."""
    parejas = grupo_dict.get('parejas', [])
    franja_asignada = grupo_dict.get('franja_horaria')

    if len(parejas) == 0:
        grupo_dict['score'] = 0.0
        grupo_dict['score_compatibilidad'] = 0.0
        return

    if not franja_asignada:
        parejas_obj = [Pareja.from_dict(p) for p in parejas]

        if len(parejas_obj) < 2:
            score = 0.0
        elif len(parejas_obj) < 3:
            franjas_p1 = set(parejas_obj[0].franjas_disponibles)
            franjas_p2 = set(parejas_obj[1].franjas_disponibles)
            franjas_comunes = franjas_p1 & franjas_p2
            score = 2.0 if franjas_comunes else 0.0
        else:
            algoritmo = AlgoritmoGrupos(parejas_obj)
            score, _ = algoritmo._calcular_compatibilidad(parejas_obj)
    else:
        dia_asignado = franja_asignada.split(' ')[0] if ' ' in franja_asignada else ''
        score = 0.0

        for pareja in parejas:
            franjas_pareja = pareja.get('franjas_disponibles', [])

            if franja_asignada in franjas_pareja:
                score += 1.0
            elif dia_asignado:
                dias_pareja = set(f.split(' ')[0] for f in franjas_pareja if ' ' in f)
                if dia_asignado in dias_pareja:
                    score += 0.5

    grupo_dict['score'] = score
    grupo_dict['score_compatibilidad'] = score


def regenerar_calendario(resultado_data):
    """Regenera el calendario completo y los partidos de cada grupo."""
    try:
        resultado_obj = deserializar_resultado(resultado_data)

        datos_actuales = obtener_datos_desde_token()
        num_canchas = datos_actuales.get('num_canchas', NUM_CANCHAS_DEFAULT)

        canchas_por_grupo = {}
        for categoria, grupos_list in resultado_data['grupos_por_categoria'].items():
            for grupo_dict in grupos_list:
                if grupo_dict.get('cancha'):
                    canchas_por_grupo[grupo_dict['id']] = grupo_dict['cancha']

        calendario_builder = CalendarioBuilder(num_canchas)
        calendario = calendario_builder.organizar_partidos(resultado_obj, canchas_por_grupo)

        resultado_data['calendario'] = calendario

        for categoria, grupos_obj in resultado_obj.grupos_por_categoria.items():
            grupos_list = resultado_data['grupos_por_categoria'].get(categoria, [])
            for grupo_obj in grupos_obj:
                for grupo_dict in grupos_list:
                    if grupo_dict['id'] == grupo_obj.id:
                        grupo_dict['partidos'] = [
                            {
                                'pareja1': p1.nombre,
                                'pareja2': p2.nombre,
                                'pareja1_id': p1.id,
                                'pareja2_id': p2.id
                            }
                            for p1, p2 in grupo_obj.partidos
                        ]
                        grupo_dict['resultados'] = {k: v.to_dict() for k, v in grupo_obj.resultados.items()}
                        grupo_dict['resultados_completos'] = grupo_obj.todos_resultados_completos()
                        break

        return calendario
    except Exception as e:
        logger.error(f"Error al regenerar calendario: {e}", exc_info=True)
        return resultado_data.get('calendario', {})


# ==================== FIXTURES ====================

def regenerar_fixtures_categoria(categoria, resultado_data):
    """Regenera los fixtures de finales para una categoría específica."""
    try:
        grupos_data = resultado_data.get('grupos_por_categoria', {}).get(categoria, [])
        if not grupos_data:
            logger.warning(f"No se encontraron grupos para la categoría {categoria}")
            return

        grupos = []
        for grupo_data in grupos_data:
            try:
                grupo = Grupo.from_dict(grupo_data)
                grupos.append(grupo)
            except Exception as e:
                logger.error(f"Error al reconstruir grupo: {e}")
                continue

        if not grupos:
            logger.warning(f"No se pudieron reconstruir grupos para {categoria}")
            return

        fixture = GeneradorFixtureFinales.generar_fixture(categoria, grupos)

        torneo = storage.cargar()
        if not torneo:
            torneo = {}

        if 'fixtures_finales' not in torneo:
            torneo['fixtures_finales'] = {}

        torneo['fixtures_finales'][categoria] = fixture.to_dict() if fixture else None
        storage.guardar_con_version(torneo)
        logger.info(f"Fixtures regenerados exitosamente para categoría {categoria}")

    except ConflictError:
        raise  # propagar al route handler para que devuelva 409
    except Exception as e:
        logger.error(f"Error al regenerar fixtures para {categoria}: {e}")
        import traceback
        traceback.print_exc()


# ==================== MISC ====================

def verificar_posiciones_completas(grupos: list) -> bool:
    """Verifica si todas las parejas tienen posiciones asignadas."""
    for grupo in grupos:
        for pareja in grupo['parejas']:
            if not pareja.get('posicion_grupo'):
                return False
    return True


