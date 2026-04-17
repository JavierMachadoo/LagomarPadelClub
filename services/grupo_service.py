"""
Capa de servicio para grupos y parejas.

Responsabilidades:
- Ejecutar el algoritmo de agrupación (fusión inscripciones + manual)
- Gestión de grupos: intercambiar, asignar, crear, editar parejas
- Recálculos: score de grupo, estadísticas, calendario
- Serialización/deserialización del resultado del algoritmo
- Enriquecimiento de parejas con info de asignación

No importa nada de Flask. Recibe datos (dicts, primitivos) y devuelve datos.
Los route handlers son responsables de leer la request y persistir con
sincronizar_con_storage_y_token().
"""

import logging

from core import Pareja, AlgoritmoGrupos, ResultadoAlgoritmo, Grupo
from utils import CalendarioBuilder
from config import NUM_CANCHAS_DEFAULT, FRANJAS_A_HORAS_MAP
from config.settings import FRANJAS_HORARIAS
from .exceptions import ServiceError

logger = logging.getLogger(__name__)


# ==================== ALGORITMO ====================

def ejecutar_algoritmo(parejas_blob: list) -> tuple[dict, str]:
    """Fusiona inscripciones confirmadas + parejas manuales y ejecuta el algoritmo.

    Args:
        parejas_blob: parejas ya cargadas en el token (manual/CSV).

    Returns:
        (resultado_serializado, mensaje_resumen)

    Raises:
        ServiceError si no hay parejas o el algoritmo falla.
    """
    parejas_de_inscripciones = _cargar_inscripciones_supabase()

    ids_inscripciones = {p['id'] for p in parejas_de_inscripciones}
    parejas_manuales = [p for p in parejas_blob if p.get('id') not in ids_inscripciones]

    todas_parejas_data = parejas_de_inscripciones + parejas_manuales

    if not todas_parejas_data:
        raise ServiceError('No hay parejas ni inscripciones para generar grupos')

    try:
        parejas_obj = [Pareja.from_dict(p) for p in todas_parejas_data]
        algoritmo = AlgoritmoGrupos(parejas=parejas_obj, num_canchas=NUM_CANCHAS_DEFAULT)
        resultado_obj = algoritmo.ejecutar()
        resultado = serializar_resultado(resultado_obj, NUM_CANCHAS_DEFAULT)
    except Exception as e:
        logger.error('Error al ejecutar algoritmo: %s', e, exc_info=True)
        raise ServiceError(
            'Error al ejecutar el algoritmo. Por favor, verifica los datos e intenta nuevamente.',
            500
        )

    total = len(todas_parejas_data)
    de_inscripciones = len(parejas_de_inscripciones)
    manuales = len(parejas_manuales)
    mensaje = f'✅ {total} parejas procesadas ({de_inscripciones} de inscripciones, {manuales} manuales)'

    return resultado, todas_parejas_data, mensaje


def _cargar_inscripciones_supabase() -> list:
    """Carga inscripciones confirmadas desde Supabase.

    Returns lista vacía si Supabase no está configurado o falla.
    """
    try:
        from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
        from utils.supabase_client import get_supabase_admin
        from utils.torneo_storage import storage

        if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
            return []

        torneo_id = storage.get_torneo_id()
        sb = get_supabase_admin()
        resp = sb.table('inscripciones').select('*').eq('torneo_id', torneo_id).eq('estado', 'confirmado').execute()

        result = []
        for insc in (resp.data or []):
            pareja_id = int(insc['id'].replace('-', '')[:8], 16)
            result.append({
                'id':                  pareja_id,
                'nombre':              f"{insc['integrante1']} / {insc['integrante2']}",
                'jugador1':            insc['integrante1'],
                'jugador2':            insc['integrante2'],
                'telefono':            insc.get('telefono') or '',
                'categoria':           insc['categoria'],
                'franjas_disponibles': insc.get('franjas_disponibles') or [],
                'inscripcion_id':      insc['id'],
            })
        return result
    except Exception as e:
        logger.warning('No se pudieron cargar inscripciones de Supabase: %s', e)
        return []


# ==================== GESTIÓN DE GRUPOS ====================

def _tiene_resultados(grupo_dict: dict) -> bool:
    """Retorna True si el grupo tiene al menos un resultado registrado (parcial o completo)."""
    return bool(grupo_dict.get('resultados', {}))


def intercambiar_pareja(
    resultado: dict,
    pareja_id: int,
    grupo_origen_id: int,
    grupo_destino_id: int,
    slot_destino: int,
) -> tuple[str, dict]:
    """Intercambia una pareja entre dos grupos.

    Muta `resultado` en lugar.

    Returns:
        (mensaje, estadisticas)

    Raises:
        ServiceError si no se encuentra la pareja o los grupos, o si algún
        grupo involucrado ya tiene resultados registrados.
    """
    # Pre-scan: validar antes de mutar cualquier dato
    _grupo_origen_pre = None
    _grupo_destino_pre = None
    for _cat, _grupos in resultado['grupos_por_categoria'].items():
        for _g in _grupos:
            if _g['id'] == grupo_origen_id:
                _grupo_origen_pre = _g
            if _g['id'] == grupo_destino_id:
                _grupo_destino_pre = _g

    if _grupo_origen_pre and _tiene_resultados(_grupo_origen_pre):
        raise ServiceError(
            'No se puede intercambiar: el grupo de origen ya tiene resultados ingresados.'
        )
    if (_grupo_destino_pre and grupo_destino_id != grupo_origen_id
            and _tiene_resultados(_grupo_destino_pre)):
        raise ServiceError(
            'No se puede intercambiar: el grupo de destino ya tiene resultados ingresados.'
        )

    pareja_movida = None
    grupo_origen_obj = None
    grupo_destino_obj = None

    for categoria, grupos in resultado['grupos_por_categoria'].items():
        for grupo in grupos:
            if grupo['id'] == grupo_origen_id:
                grupo_origen_obj = grupo
                for i, pareja in enumerate(grupo['parejas']):
                    if pareja['id'] == pareja_id:
                        pareja_movida = grupo['parejas'].pop(i)
                        break

            if grupo['id'] == grupo_destino_id:
                grupo_destino_obj = grupo

    if not pareja_movida or not grupo_origen_obj or not grupo_destino_obj:
        raise ServiceError('No se encontró la pareja o el grupo')

    pareja_en_slot = None
    if slot_destino < len(grupo_destino_obj['parejas']):
        pareja_en_slot = grupo_destino_obj['parejas'][slot_destino]

    if pareja_en_slot:
        grupo_destino_obj['parejas'][slot_destino] = pareja_movida
        grupo_origen_obj['parejas'].append(pareja_en_slot)
        mensaje = f"Intercambio exitoso: {pareja_movida['nombre']} ↔ {pareja_en_slot['nombre']}"
    else:
        if slot_destino <= len(grupo_destino_obj['parejas']):
            grupo_destino_obj['parejas'].insert(slot_destino, pareja_movida)
        else:
            grupo_destino_obj['parejas'].append(pareja_movida)
        mensaje = f"Pareja {pareja_movida['nombre']} movida al slot {slot_destino + 1}"

    recalcular_score_grupo(grupo_origen_obj)
    recalcular_score_grupo(grupo_destino_obj)
    regenerar_calendario(resultado)
    estadisticas = recalcular_estadisticas(resultado)

    return mensaje, estadisticas


def asignar_pareja_a_grupo(
    resultado_data: dict,
    pareja_id: int,
    grupo_id: int,
    categoria: str,
    pareja_a_remover_id: int | None,
    slot_destino: int | None,
) -> dict:
    """Asigna una pareja no asignada a un grupo.

    Muta `resultado_data` en lugar.

    Returns:
        estadisticas actualizadas

    Raises:
        ServiceError en caso de error de negocio.
    """
    grupos_dict = resultado_data['grupos_por_categoria']
    parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])

    pareja_a_asignar = None
    for idx, p in enumerate(parejas_sin_asignar):
        if p.get('id') == pareja_id:
            pareja_a_asignar = parejas_sin_asignar.pop(idx)
            break

    if not pareja_a_asignar:
        raise ServiceError('Pareja no encontrada en no asignadas', 404)

    grupo_encontrado = None
    for grupo in grupos_dict.get(categoria, []):
        if grupo['id'] == grupo_id:
            grupo_encontrado = grupo
            break

    if not grupo_encontrado:
        raise ServiceError('Grupo no encontrado', 404)

    if pareja_a_remover_id:
        pareja_removida = None
        for idx, p in enumerate(grupo_encontrado['parejas']):
            if p.get('id') == pareja_a_remover_id:
                pareja_removida = grupo_encontrado['parejas'].pop(idx)
                break
        if pareja_removida:
            pareja_removida['posicion_grupo'] = None
            parejas_sin_asignar.append(pareja_removida)

    if len(grupo_encontrado['parejas']) >= 3 and not pareja_a_remover_id:
        parejas_sin_asignar.append(pareja_a_asignar)
        raise ServiceError(
            'El grupo ya tiene 3 parejas. Debes especificar cuál reemplazar.',
            400
        )

    if slot_destino is not None and slot_destino < len(grupo_encontrado['parejas']):
        grupo_encontrado['parejas'].insert(slot_destino, pareja_a_asignar)
    else:
        grupo_encontrado['parejas'].append(pareja_a_asignar)

    recalcular_score_grupo(grupo_encontrado)

    if len(grupo_encontrado['parejas']) == 3:
        _regenerar_partidos_grupo(grupo_encontrado, categoria)

    regenerar_calendario(resultado_data)
    return recalcular_estadisticas(resultado_data)


def _regenerar_partidos_grupo(grupo_dict: dict, categoria: str) -> None:
    """Regenera los partidos de un grupo cuando queda completo (3 parejas)."""
    try:
        grupo_obj = Grupo(id=grupo_dict['id'], categoria=categoria)
        grupo_obj.franja_horaria = grupo_dict.get('franja_horaria')
        for p in grupo_dict['parejas']:
            grupo_obj.parejas.append(Pareja.from_dict(p))
        grupo_obj.generar_partidos()
        grupo_dict['partidos'] = [
            {
                'pareja1':    p1.nombre,
                'pareja2':    p2.nombre,
                'pareja1_id': p1.id,
                'pareja2_id': p2.id,
            }
            for p1, p2 in grupo_obj.partidos
        ]
        grupo_dict['resultados'] = {}
        grupo_dict['resultados_completos'] = False
    except Exception as e:
        logger.warning('No se pudieron regenerar partidos del grupo: %s', e)


def crear_grupo_manual(
    resultado_data: dict,
    categoria: str,
    franja_horaria: str,
    cancha: int | str,
) -> dict:
    """Crea un nuevo grupo vacío para una categoría.

    Muta `resultado_data` en lugar.

    Returns:
        dict con el nuevo grupo creado.

    Raises:
        ServiceError si ya existe conflicto de cancha/franja.
    """
    grupos_dict = resultado_data['grupos_por_categoria']

    # Verificar conflicto exacto (misma franja + misma cancha)
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            if grupo.get('franja_horaria') == franja_horaria and str(grupo.get('cancha')) == str(cancha):
                raise ServiceError(
                    f'La Cancha {cancha} ya está ocupada en {franja_horaria} por un grupo de {cat}'
                )

    # Verificar solapamiento horario en la misma cancha
    horas_nueva_franja = FRANJAS_A_HORAS_MAP.get(franja_horaria, [])
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            if str(grupo.get('cancha')) == str(cancha):
                franja_existente = grupo.get('franja_horaria')
                horas_existente = FRANJAS_A_HORAS_MAP.get(franja_existente, [])
                horas_conflicto = set(horas_nueva_franja) & set(horas_existente)
                if horas_conflicto:
                    raise ServiceError(
                        f'Conflicto: La Cancha {cancha} tiene un solapamiento horario con '
                        f'{franja_existente} (grupo de {cat}) en las horas: {", ".join(sorted(horas_conflicto))}'
                    )

    if categoria not in grupos_dict:
        grupos_dict[categoria] = []

    max_id = max(
        (grupo['id'] for cat_grupos in grupos_dict.values() for grupo in cat_grupos),
        default=0
    )

    nuevo_grupo = {
        'id':                  max_id + 1,
        'franja_horaria':      franja_horaria,
        'cancha':              cancha,
        'score':               0.0,
        'score_compatibilidad': 0.0,
        'parejas':             [],
        'partidos':            [],
        'resultados':          {},
        'resultados_completos': False,
    }

    grupos_dict[categoria].append(nuevo_grupo)
    regenerar_calendario(resultado_data)
    return nuevo_grupo


def editar_grupo(
    resultado_data: dict,
    grupo_id: int,
    categoria: str,
    franja_horaria: str,
    cancha: int | str,
) -> None:
    """Edita la franja horaria y cancha de un grupo.

    Muta `resultado_data` en lugar.

    Raises:
        ServiceError si el grupo no existe o hay conflicto.
    """
    grupos_dict = resultado_data['grupos_por_categoria']

    grupo_encontrado = None
    for grupo in grupos_dict.get(categoria, []):
        if grupo['id'] == grupo_id:
            grupo_encontrado = grupo
            break

    if not grupo_encontrado:
        raise ServiceError('Grupo no encontrado', 404)

    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            if grupo['id'] == grupo_id:
                continue
            if grupo.get('franja_horaria') == franja_horaria and str(grupo.get('cancha')) == str(cancha):
                raise ServiceError(
                    f'La Cancha {cancha} ya está ocupada en {franja_horaria} por otro grupo ({cat})'
                )

    grupo_encontrado['franja_horaria'] = franja_horaria
    grupo_encontrado['cancha'] = cancha

    recalcular_score_grupo(grupo_encontrado)
    regenerar_calendario(resultado_data)


# ==================== GESTIÓN DE PAREJAS ====================

def agregar_pareja(
    datos: dict,
    jugador1: str,
    jugador2: str,
    nombre: str,
    telefono: str,
    categoria: str,
    franjas: list,
    desde_resultados: bool,
) -> tuple[dict, dict | None]:
    """Agrega una nueva pareja al torneo.

    Muta `datos` en lugar (datos['parejas'] y opcionalmente datos['resultado_algoritmo']).

    Returns:
        (nueva_pareja, estadisticas_o_None)
    """
    parejas = datos.get('parejas', [])
    max_id = max([p['id'] for p in parejas], default=0)
    nueva_pareja = {
        'categoria':          categoria,
        'franjas_disponibles': franjas,
        'id':                 max_id + 1,
        'nombre':             nombre,
        'jugador1':           jugador1 or nombre,
        'jugador2':           jugador2,
        'telefono':           telefono or 'Sin telefono',
        'origen':             'manual',
    }
    parejas.append(nueva_pareja)
    datos['parejas'] = parejas

    estadisticas = None
    if desde_resultados:
        resultado_data = datos.get('resultado_algoritmo')
        if resultado_data:
            resultado_data.get('parejas_sin_asignar', []).append(nueva_pareja)
            estadisticas = recalcular_estadisticas(resultado_data)
            datos['resultado_algoritmo'] = resultado_data

    return nueva_pareja, estadisticas


def eliminar_pareja(datos: dict, pareja_id: int) -> None:
    """Elimina una pareja del torneo (del blob de parejas y de cualquier grupo).

    Muta `datos` en lugar.
    """
    datos['parejas'] = [p for p in datos.get('parejas', []) if p['id'] != pareja_id]

    resultado_data = datos.get('resultado_algoritmo')
    if not resultado_data:
        return

    for cat, grupos in resultado_data['grupos_por_categoria'].items():
        for grupo in grupos:
            prev = len(grupo.get('parejas', []))
            grupo['parejas'] = [p for p in grupo['parejas'] if p.get('id') != pareja_id]
            if len(grupo['parejas']) != prev:
                recalcular_score_grupo(grupo)

    resultado_data['parejas_sin_asignar'] = [
        p for p in resultado_data.get('parejas_sin_asignar', []) if p.get('id') != pareja_id
    ]
    regenerar_calendario(resultado_data)
    resultado_data['estadisticas'] = recalcular_estadisticas(resultado_data)
    datos['resultado_algoritmo'] = resultado_data


def remover_pareja_de_grupo(
    resultado_data: dict,
    pareja_id: int,
) -> dict:
    """Remueve una pareja de su grupo y la pone en sin asignar.

    Muta `resultado_data` en lugar.

    Returns:
        estadisticas actualizadas

    Raises:
        ServiceError si la pareja no se encuentra en ningún grupo.
    """
    grupos_dict = resultado_data['grupos_por_categoria']
    parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])

    pareja_encontrada = None
    grupo_contenedor = None

    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            for idx, pareja in enumerate(grupo.get('parejas', [])):
                if pareja.get('id') == pareja_id:
                    pareja_encontrada = grupo['parejas'].pop(idx)
                    grupo_contenedor = grupo
                    break
            if pareja_encontrada:
                break
        if pareja_encontrada:
            break

    if not pareja_encontrada:
        raise ServiceError('Pareja no encontrada en ningun grupo', 404)

    pareja_encontrada['posicion_grupo'] = None
    parejas_sin_asignar.append(pareja_encontrada)
    recalcular_score_grupo(grupo_contenedor)
    regenerar_calendario(resultado_data)
    return recalcular_estadisticas(resultado_data)


def editar_pareja(
    datos: dict,
    pareja_id: int,
    nombre: str,
    telefono: str,
    categoria: str,
    franjas: list,
) -> str:
    """Edita los datos de una pareja (en grupos, sin asignar y blob base).

    Muta `datos` en lugar.

    Returns:
        mensaje de confirmación.

    Raises:
        ServiceError si la pareja no existe.
    """
    resultado_data = datos.get('resultado_algoritmo')
    if not resultado_data:
        raise ServiceError('No hay resultados del algoritmo', 404)

    grupos_dict = resultado_data['grupos_por_categoria']
    parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])

    pareja_encontrada = None
    grupo_contenedor = None
    categoria_original = None

    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            for pareja in grupo.get('parejas', []):
                if pareja.get('id') == pareja_id:
                    pareja_encontrada = pareja
                    grupo_contenedor = grupo
                    categoria_original = cat
                    break
            if pareja_encontrada:
                break
        if pareja_encontrada:
            break

    if not pareja_encontrada:
        for pareja in parejas_sin_asignar:
            if pareja.get('id') == pareja_id:
                pareja_encontrada = pareja
                categoria_original = pareja.get('categoria')
                break

    if not pareja_encontrada:
        raise ServiceError('Pareja no encontrada', 404)

    cambio_categoria = categoria != categoria_original
    if cambio_categoria and grupo_contenedor:
        grupo_contenedor['parejas'].remove(pareja_encontrada)
        recalcular_score_grupo(grupo_contenedor)
        pareja_encontrada['categoria'] = categoria
        parejas_sin_asignar.append(pareja_encontrada)

    pareja_encontrada.update({
        'nombre':              nombre,
        'telefono':            telefono,
        'categoria':           categoria,
        'franjas_disponibles': franjas,
    })

    parejas_base = datos.get('parejas', [])
    updated = False
    for pb in parejas_base:
        if pb['id'] == pareja_id:
            pb.update({'nombre': nombre, 'telefono': telefono, 'categoria': categoria, 'franjas_disponibles': franjas})
            updated = True
            break
    if not updated:
        parejas_base.append({'id': pareja_id, 'nombre': nombre, 'telefono': telefono, 'categoria': categoria, 'franjas_disponibles': franjas})
    datos['parejas'] = parejas_base

    if grupo_contenedor and not cambio_categoria:
        recalcular_score_grupo(grupo_contenedor)

    regenerar_calendario(resultado_data)
    datos['resultado_algoritmo'] = resultado_data

    mensaje = 'Pareja actualizada'
    if cambio_categoria:
        mensaje += ' (movida a no asignadas por cambio de categoria)'
    return mensaje


def enriquecer_parejas_con_asignacion(parejas: list, resultado: dict | None) -> list:
    """Agrega info de asignación de grupo a cada pareja.

    Unifica la lógica duplicada que había en admin_panel() y obtener_parejas().

    Returns:
        lista de parejas enriquecidas con grupo_asignado, franja_asignada,
        esta_asignada, fuera_de_horario.
    """
    enriched = []
    for pareja in parejas:
        info = pareja.copy()
        info.update({
            'grupo_asignado': None,
            'franja_asignada': None,
            'esta_asignada':   False,
            'fuera_de_horario': False,
        })

        if resultado:
            for cat, grupos in resultado.get('grupos_por_categoria', {}).items():
                for grupo in grupos:
                    for p in grupo.get('parejas', []):
                        if p['id'] == pareja['id']:
                            info['grupo_asignado'] = grupo['id']
                            info['franja_asignada'] = grupo.get('franja_horaria')
                            info['esta_asignada'] = True
                            franja_asignada = grupo.get('franja_horaria')
                            if franja_asignada and franja_asignada not in pareja.get('franjas_disponibles', []):
                                info['fuera_de_horario'] = True
                            break
                    if info['esta_asignada']:
                        break
                if info['esta_asignada']:
                    break

        enriched.append(info)
    return enriched


def obtener_franjas_disponibles(resultado_data: dict) -> dict:
    """Calcula disponibilidad de franjas y canchas considerando solapamientos.

    Returns:
        dict con disponibilidad por franja y cancha.
    """
    grupos_dict = resultado_data['grupos_por_categoria']

    franjas_ocupadas: dict[str, dict[str, str]] = {}
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            franja = grupo.get('franja_horaria')
            cancha = str(grupo.get('cancha'))
            if franja and cancha:
                franjas_ocupadas.setdefault(franja, {})[cancha] = cat

    disponibilidad: dict = {}
    for franja in FRANJAS_HORARIAS:
        disponibilidad[franja] = {}
        for cn in range(1, NUM_CANCHAS_DEFAULT + 1):
            cs = str(cn)
            ocupada = franja in franjas_ocupadas and cs in franjas_ocupadas[franja]
            solapamiento = None
            horas_f = FRANJAS_A_HORAS_MAP.get(franja, [])
            for otra, cat_cn in franjas_ocupadas.items():
                if otra != franja and cs in cat_cn:
                    horas_o = FRANJAS_A_HORAS_MAP.get(otra, [])
                    horas_c = set(horas_f) & set(horas_o)
                    if horas_c:
                        solapamiento = {
                            'franja':          otra,
                            'categoria':       cat_cn[cs],
                            'horas_conflicto': sorted(horas_c),
                        }
                        break
            disponibilidad[franja][cs] = {
                'disponible':  not ocupada,
                'ocupada_por': franjas_ocupadas.get(franja, {}).get(cs),
                'solapamiento': solapamiento,
            }
    return disponibilidad


# ==================== RECÁLCULOS (helpers de dominio) ====================

def recalcular_estadisticas(resultado_data: dict) -> dict:
    """Recalcula las estadísticas globales del torneo.

    Muta resultado_data['estadisticas'] y lo devuelve.
    """
    grupos_dict = resultado_data.get('grupos_por_categoria', {})
    parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])

    parejas_asignadas = 0
    total_grupos = 0
    sum_scores = 0.0
    grupos_con_score = 0

    for categoria, grupos in grupos_dict.items():
        for grupo in grupos:
            total_grupos += 1
            parejas_asignadas += len(grupo.get('parejas', []))
            score = grupo.get('score', 0.0)
            if score > 0:
                sum_scores += score
                grupos_con_score += 1

    total_parejas = parejas_asignadas + len(parejas_sin_asignar)
    porcentaje_asignacion = (parejas_asignadas / total_parejas * 100) if total_parejas > 0 else 0
    score_promedio = (sum_scores / grupos_con_score) if grupos_con_score > 0 else 0.0

    resultado_data['estadisticas'] = {
        'parejas_asignadas':           parejas_asignadas,
        'total_parejas':               total_parejas,
        'parejas_sin_asignar':         len(parejas_sin_asignar),
        'porcentaje_asignacion':       porcentaje_asignacion,
        'total_grupos':                total_grupos,
        'score_compatibilidad_promedio': score_promedio,
    }
    return resultado_data['estadisticas']


def recalcular_score_grupo(grupo_dict: dict) -> None:
    """Recalcula el score de compatibilidad de un grupo según sus parejas actuales.

    Muta grupo_dict en lugar.
    """
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
            score = 2.0 if (franjas_p1 & franjas_p2) else 0.0
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


def regenerar_calendario(resultado_data: dict) -> dict:
    """Regenera el calendario completo y los partidos de cada grupo.

    Muta resultado_data['calendario'] en lugar.
    """
    try:
        resultado_obj = _deserializar_resultado(resultado_data)

        canchas_por_grupo: dict[int, int] = {}
        for categoria, grupos_list in resultado_data['grupos_por_categoria'].items():
            for grupo_dict in grupos_list:
                if grupo_dict.get('cancha'):
                    canchas_por_grupo[grupo_dict['id']] = grupo_dict['cancha']

        calendario_builder = CalendarioBuilder(NUM_CANCHAS_DEFAULT)
        calendario = calendario_builder.organizar_partidos(resultado_obj, canchas_por_grupo)
        resultado_data['calendario'] = calendario

        for categoria, grupos_obj in resultado_obj.grupos_por_categoria.items():
            grupos_list = resultado_data['grupos_por_categoria'].get(categoria, [])
            for grupo_obj in grupos_obj:
                for grupo_dict in grupos_list:
                    if grupo_dict['id'] == grupo_obj.id:
                        grupo_dict['partidos'] = [
                            {
                                'pareja1':    p1.nombre,
                                'pareja2':    p2.nombre,
                                'pareja1_id': p1.id,
                                'pareja2_id': p2.id,
                            }
                            for p1, p2 in grupo_obj.partidos
                        ]
                        grupo_dict['resultados'] = {k: v.to_dict() for k, v in grupo_obj.resultados.items()}
                        grupo_dict['resultados_completos'] = grupo_obj.todos_resultados_completos()
                        break

        return calendario
    except Exception as e:
        logger.error('Error al regenerar calendario: %s', e, exc_info=True)
        return resultado_data.get('calendario', {})


# ==================== SERIALIZACIÓN ====================

def serializar_resultado(resultado, num_canchas: int) -> dict:
    """Convierte el resultado del algoritmo a formato JSON serializable."""
    grupos_dict = {}
    canchas_por_grupo: dict[int, int] = {}

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
                'id':                  grupo.id,
                'parejas':             [p.to_dict() for p in grupo.parejas],
                'partidos':            [
                    {
                        'pareja1':    p1.nombre,
                        'pareja2':    p2.nombre,
                        'pareja1_id': p1.id,
                        'pareja2_id': p2.id,
                    }
                    for p1, p2 in grupo.partidos
                ],
                'resultados':          {},
                'franja_horaria':      grupo.franja_horaria,
                'cancha':              cancha_num,
                'score':               grupo.score_compatibilidad,
                'resultados_completos': False,
            })

    calendario_builder = CalendarioBuilder(num_canchas)
    calendario = calendario_builder.organizar_partidos(resultado, canchas_por_grupo)

    return {
        'grupos_por_categoria': grupos_dict,
        'estadisticas':         resultado.estadisticas,
        'parejas_sin_asignar':  [p.to_dict() for p in resultado.parejas_sin_asignar],
        'calendario':           calendario,
    }


def _deserializar_resultado(resultado_data: dict) -> ResultadoAlgoritmo:
    """Reconstruye el objeto ResultadoAlgoritmo desde el dict almacenado."""
    from core.models import ResultadoPartido

    grupos_por_categoria = {}

    for categoria, grupos_list in resultado_data['grupos_por_categoria'].items():
        grupos_por_categoria[categoria] = []
        for grupo_dict in grupos_list:
            grupo = Grupo(id=grupo_dict['id'], categoria=categoria)
            grupo.franja_horaria = grupo_dict.get('franja_horaria')
            grupo.score_compatibilidad = grupo_dict.get('score', 0.0)

            for key, r_data in grupo_dict.get('resultados', {}).items():
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
                    franjas_disponibles=pareja_dict.get('franjas_disponibles', []),
                )
                grupo.parejas.append(pareja)

            grupo.generar_partidos()
            grupos_por_categoria[categoria].append(grupo)

    parejas_sin_asignar = [
        Pareja(
            id=p['id'],
            nombre=p['nombre'],
            telefono=p.get('telefono', 'Sin teléfono'),
            categoria=p['categoria'],
            franjas_disponibles=p.get('franjas_disponibles', []),
        )
        for p in resultado_data.get('parejas_sin_asignar', [])
    ]

    return ResultadoAlgoritmo(
        grupos_por_categoria=grupos_por_categoria,
        parejas_sin_asignar=parejas_sin_asignar,
        calendario=resultado_data.get('calendario', {}),
        estadisticas=resultado_data.get('estadisticas', {}),
    )
