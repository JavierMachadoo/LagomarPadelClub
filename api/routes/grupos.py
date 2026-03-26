from flask import Blueprint, request, jsonify
import logging

from core import Pareja, AlgoritmoGrupos
from utils.torneo_storage import storage
from utils.api_helpers import (
    obtener_datos_desde_token,
    crear_respuesta_con_token_actualizado,
    sincronizar_con_storage_y_token,
    verificar_autenticacion_api
)
from config import NUM_CANCHAS_DEFAULT
from ._helpers import (
    serializar_resultado,
    recalcular_estadisticas,
    recalcular_score_grupo,
    regenerar_calendario,
    guardar_estado_torneo,
)

grupos_bp = Blueprint('grupos', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


@grupos_bp.before_request
def verificar_auth():
    authenticated, error_response = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not authenticated:
        return error_response


# ==================== ALGORITMO ====================

@grupos_bp.route('/ejecutar-algoritmo', methods=['POST'])
def ejecutar_algoritmo():
    """Ejecuta el algoritmo de generación de grupos para el torneo.

    Fusiona dos fuentes de parejas:
    1. Inscripciones confirmadas en Supabase (con inscripcion_id para lookup "Mi Grupo")
    2. Parejas cargadas manualmente/CSV en el blob (sin inscripcion_id)

    Si no hay ninguna fuente, devuelve error.
    """
    from utils.api_helpers import _verificar_supabase_jwt  # noqa: F401 (evita importación circular)

    datos_actuales = obtener_datos_desde_token()
    parejas_blob = datos_actuales.get('parejas', [])

    # ── 1. Leer inscripciones confirmadas de Supabase ─────────────────────────
    parejas_de_inscripciones = []
    try:
        from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
        from supabase import create_client

        if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
            torneo_id = storage.get_torneo_id()
            sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            resp = sb.table('inscripciones').select('*').eq('torneo_id', torneo_id).eq('estado', 'confirmado').execute()

            for insc in (resp.data or []):
                pareja_id = int(insc['id'].replace('-', '')[:8], 16)
                parejas_de_inscripciones.append({
                    'id':                 pareja_id,
                    'nombre':             f"{insc['integrante1']} / {insc['integrante2']}",
                    'jugador1':           insc['integrante1'],
                    'jugador2':           insc['integrante2'],
                    'telefono':           insc.get('telefono') or '',
                    'categoria':          insc['categoria'],
                    'franjas_disponibles': insc.get('franjas_disponibles') or [],
                    'inscripcion_id':     insc['id'],
                })
    except Exception as e:
        logger.warning('No se pudieron cargar inscripciones de Supabase: %s', e)

    # ── 2. Parejas manuales/CSV que NO tienen inscripcion_id ya en la lista ───
    ids_inscripciones = {p['id'] for p in parejas_de_inscripciones}
    parejas_manuales = [p for p in parejas_blob if p.get('id') not in ids_inscripciones]

    # ── 3. Fusionar y validar ─────────────────────────────────────────────────
    todas_parejas_data = parejas_de_inscripciones + parejas_manuales

    if not todas_parejas_data:
        return jsonify({'error': 'No hay parejas ni inscripciones para generar grupos'}), 400

    try:
        parejas_obj = [Pareja.from_dict(p) for p in todas_parejas_data]

        algoritmo = AlgoritmoGrupos(parejas=parejas_obj, num_canchas=NUM_CANCHAS_DEFAULT)
        resultado_obj = algoritmo.ejecutar()

        resultado = serializar_resultado(resultado_obj, NUM_CANCHAS_DEFAULT)

        datos_actuales['resultado_algoritmo'] = resultado
        datos_actuales['num_canchas'] = NUM_CANCHAS_DEFAULT
        # Actualizar parejas en blob con las de inscripciones (para edición manual posterior)
        datos_actuales['parejas'] = todas_parejas_data
        sincronizar_con_storage_y_token(datos_actuales)
        guardar_estado_torneo()

        total = len(todas_parejas_data)
        de_inscripciones = len(parejas_de_inscripciones)
        manuales = len(parejas_manuales)
        mensaje = f'✅ {total} parejas procesadas ({de_inscripciones} de inscripciones, {manuales} manuales)'

        return crear_respuesta_con_token_actualizado({
            'success': True,
            'mensaje': mensaje,
            'resultado': resultado
        }, datos_actuales)
    except Exception as e:
        logger.error('Error al ejecutar algoritmo: %s', e, exc_info=True)
        return jsonify({
            'error': 'Error al ejecutar el algoritmo. Por favor, verifica los datos e intenta nuevamente.'
        }), 500


@grupos_bp.route('/resultado_algoritmo', methods=['GET'])
def obtener_resultado_algoritmo():
    """Obtiene el resultado completo del algoritmo con grupos y parejas."""
    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get('resultado_algoritmo')

    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404

    return jsonify(resultado_data)


# ==================== GESTIÓN DE GRUPOS ====================

@grupos_bp.route('/intercambiar-pareja', methods=['POST'])
def intercambiar_pareja():
    """Intercambia parejas entre slots específicos de grupos."""
    data = request.json
    pareja_id = data.get('pareja_id')
    grupo_origen_id = data.get('grupo_origen')
    grupo_destino_id = data.get('grupo_destino')
    slot_destino = data.get('slot_destino')

    datos_actuales = obtener_datos_desde_token()
    resultado = datos_actuales.get('resultado_algoritmo')
    if not resultado:
        return jsonify({'error': 'No hay resultados cargados'}), 400

    try:
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

        if not pareja_movida or not grupo_destino_obj:
            return jsonify({'error': 'No se encontró la pareja o el grupo'}), 400

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

        datos_actuales['resultado_algoritmo'] = resultado
        sincronizar_con_storage_y_token(datos_actuales)
        guardar_estado_torneo()

        return crear_respuesta_con_token_actualizado({
            'success': True,
            'mensaje': mensaje,
            'estadisticas': estadisticas
        }, datos_actuales)
    except Exception as e:
        logger.error(f"Error al intercambiar: {str(e)}", exc_info=True)
        return jsonify({'error': 'Error al intercambiar parejas. Por favor, intenta nuevamente.'}), 500


@grupos_bp.route('/asignar-pareja-a-grupo', methods=['POST'])
def asignar_pareja_a_grupo():
    """Asigna una pareja no asignada a un grupo, opcionalmente en un slot específico."""
    data = request.json
    pareja_id = data.get('pareja_id')
    grupo_id = data.get('grupo_id')
    pareja_a_remover_id = data.get('pareja_a_remover_id')
    categoria = data.get('categoria')
    slot_destino = data.get('slot_destino')

    if not all([pareja_id, grupo_id, categoria]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404

    grupos_dict = resultado_data['grupos_por_categoria']
    parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])

    pareja_a_asignar = None
    for idx, p in enumerate(parejas_sin_asignar):
        if p.get('id') == pareja_id:
            pareja_a_asignar = parejas_sin_asignar.pop(idx)
            break

    if not pareja_a_asignar:
        return jsonify({'error': 'Pareja no encontrada en no asignadas'}), 404

    grupo_encontrado = None
    for grupo in grupos_dict.get(categoria, []):
        if grupo['id'] == grupo_id:
            grupo_encontrado = grupo
            break

    if not grupo_encontrado:
        return jsonify({'error': 'Grupo no encontrado'}), 404

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
        return jsonify({
            'error': 'El grupo ya tiene 3 parejas. Debes especificar cuál reemplazar.',
            'grupo_lleno': True,
            'parejas_grupo': grupo_encontrado['parejas']
        }), 400

    if slot_destino is not None and slot_destino < len(grupo_encontrado['parejas']):
        grupo_encontrado['parejas'].insert(slot_destino, pareja_a_asignar)
    else:
        grupo_encontrado['parejas'].append(pareja_a_asignar)

    recalcular_score_grupo(grupo_encontrado)
    
    # Si el grupo está completo, regenerar los partidos
    if len(grupo_encontrado['parejas']) == 3:
        try:
            from core import Grupo, Pareja
            grupo_obj = Grupo(id=grupo_encontrado['id'], categoria=categoria)
            grupo_obj.franja_horaria = grupo_encontrado.get('franja_horaria')
            for p in grupo_encontrado['parejas']:
                grupo_obj.parejas.append(Pareja.from_dict(p))
            grupo_obj.generar_partidos()
            grupo_encontrado['partidos'] = [
                {
                    'pareja1': p1.nombre,
                    'pareja2': p2.nombre,
                    'pareja1_id': p1.id,
                    'pareja2_id': p2.id,
                }
                for p1, p2 in grupo_obj.partidos
            ]
            grupo_encontrado['resultados'] = {}
            grupo_encontrado['resultados_completos'] = False
        except Exception as e:
            logger.warning('No se pudieron regenerar partidos del grupo: %s', e)
    
    regenerar_calendario(resultado_data)
    estadisticas = recalcular_estadisticas(resultado_data)

    datos_actuales = obtener_datos_desde_token()
    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    guardar_estado_torneo()

    return crear_respuesta_con_token_actualizado({
        'success': True,
        'mensaje': '✓ Pareja asignada al grupo correctamente',
        'estadisticas': estadisticas
    }, datos_actuales)


@grupos_bp.route('/crear-grupo-manual', methods=['POST'])
def crear_grupo_manual():
    """Crea un nuevo grupo manualmente para una categoría."""
    data = request.json
    categoria = data.get('categoria')
    franja_horaria = data.get('franja_horaria')
    cancha = data.get('cancha')

    if not all([categoria, franja_horaria, cancha]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404

    grupos_dict = resultado_data['grupos_por_categoria']

    franjas_a_horas_mapa = {
        'Jueves 18:00': ['Jueves 18:00', 'Jueves 19:00', 'Jueves 20:00'],
        'Jueves 20:00': ['Jueves 20:00', 'Jueves 21:00', 'Jueves 22:00'],
        'Viernes 18:00': ['Viernes 18:00', 'Viernes 19:00', 'Viernes 20:00'],
        'Viernes 21:00': ['Viernes 21:00', 'Viernes 22:00', 'Viernes 23:00'],
        'Sábado 09:00': ['Sábado 09:00', 'Sábado 10:00', 'Sábado 11:00'],
        'Sábado 12:00': ['Sábado 12:00', 'Sábado 13:00', 'Sábado 14:00'],
        'Sábado 16:00': ['Sábado 16:00', 'Sábado 17:00', 'Sábado 18:00'],
        'Sábado 19:00': ['Sábado 19:00', 'Sábado 20:00', 'Sábado 21:00'],
    }

    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            if grupo.get('franja_horaria') == franja_horaria and str(grupo.get('cancha')) == str(cancha):
                return jsonify({
                    'error': f'La Cancha {cancha} ya está ocupada en {franja_horaria} por un grupo de {cat}'
                }), 400

    horas_nueva_franja = franjas_a_horas_mapa.get(franja_horaria, [])
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            if str(grupo.get('cancha')) == str(cancha):
                franja_existente = grupo.get('franja_horaria')
                horas_existente = franjas_a_horas_mapa.get(franja_existente, [])
                horas_conflicto = set(horas_nueva_franja) & set(horas_existente)

                if horas_conflicto:
                    return jsonify({
                        'error': f'Conflicto: La Cancha {cancha} tiene un solapamiento horario con {franja_existente} (grupo de {cat}) en las horas: {", ".join(sorted(horas_conflicto))}'
                    }), 400

    if categoria not in grupos_dict:
        grupos_dict[categoria] = []

    max_id = 0
    for cat_grupos in grupos_dict.values():
        for grupo in cat_grupos:
            if grupo.get('id', 0) > max_id:
                max_id = grupo['id']

    nuevo_grupo = {
        'id': max_id + 1,
        'franja_horaria': franja_horaria,
        'cancha': cancha,
        'score': 0.0,
        'score_compatibilidad': 0.0,
        'parejas': [],
        'partidos': [],
        'resultados': {},
        'resultados_completos': False
    }

    grupos_dict[categoria].append(nuevo_grupo)
    regenerar_calendario(resultado_data)

    datos_actuales = obtener_datos_desde_token()
    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    guardar_estado_torneo()

    return crear_respuesta_con_token_actualizado({
        'success': True,
        'mensaje': '✓ Grupo creado correctamente',
        'grupo': nuevo_grupo
    }, datos_actuales)


@grupos_bp.route('/editar-grupo', methods=['POST'])
def editar_grupo():
    """Edita la franja horaria y cancha de un grupo."""
    data = request.json
    grupo_id = data.get('grupo_id')
    categoria = data.get('categoria')
    franja_horaria = data.get('franja_horaria')
    cancha = data.get('cancha')

    if not all([grupo_id, categoria, franja_horaria, cancha]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404

    grupos_dict = resultado_data['grupos_por_categoria']

    grupo_encontrado = None
    for grupo in grupos_dict.get(categoria, []):
        if grupo['id'] == grupo_id:
            grupo_encontrado = grupo
            break

    if not grupo_encontrado:
        return jsonify({'error': 'Grupo no encontrado'}), 404

    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            if grupo['id'] == grupo_id:
                continue
            if grupo.get('franja_horaria') == franja_horaria and str(grupo.get('cancha')) == str(cancha):
                return jsonify({
                    'error': f'La Cancha {cancha} ya está ocupada en {franja_horaria} por otro grupo ({cat})'
                }), 400

    grupo_encontrado['franja_horaria'] = franja_horaria
    grupo_encontrado['cancha'] = cancha

    recalcular_score_grupo(grupo_encontrado)
    regenerar_calendario(resultado_data)

    datos_actuales = obtener_datos_desde_token()
    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    guardar_estado_torneo()

    return crear_respuesta_con_token_actualizado({
        'success': True,
        'mensaje': '✓ Grupo actualizado correctamente'
    }, datos_actuales)


# ==================== CONSULTAS DE GRUPOS ====================

@grupos_bp.route('/estadisticas', methods=['GET'])
def obtener_estadisticas():
    """Obtiene las estadísticas actualizadas del torneo."""
    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados disponibles'}), 404

    estadisticas = recalcular_estadisticas(resultado_data)

    return jsonify({
        'success': True,
        'estadisticas': estadisticas
    })


@grupos_bp.route('/obtener-categoria/<categoria>', methods=['GET'])
def obtener_categoria(categoria):
    """Devuelve solo los datos de una categoría específica para actualización parcial."""
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404

    if categoria not in resultado_dict.get('grupos_por_categoria', {}):
        return jsonify({'error': f'Categoría {categoria} no encontrada'}), 404

    return jsonify({
        'success': True,
        'categoria': categoria,
        'grupos': resultado_dict['grupos_por_categoria'][categoria],
        'parejas_sin_asignar': [p for p in resultado_dict.get('parejas_sin_asignar', []) if p.get('categoria') == categoria]
    })


@grupos_bp.route('/obtener-grupo/<categoria>/<int:grupo_id>', methods=['GET'])
def obtener_grupo(categoria, grupo_id):
    """Devuelve los datos de un grupo específico."""
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404

    grupos = resultado_dict.get('grupos_por_categoria', {}).get(categoria, [])
    grupo = next((g for g in grupos if g['id'] == grupo_id), None)

    if not grupo:
        return jsonify({'error': 'Grupo no encontrado'}), 404

    return jsonify({
        'success': True,
        'grupo': grupo
    })


@grupos_bp.route('/obtener-datos-categoria/<categoria>', methods=['GET'])
def obtener_datos_categoria(categoria):
    """Devuelve todos los datos actualizados de una categoría para actualización dinámica."""
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404

    grupos = resultado_dict.get('grupos_por_categoria', {}).get(categoria, [])
    parejas_sin_asignar = resultado_dict.get('parejas_sin_asignar', [])
    parejas_no_asignadas = [p for p in parejas_sin_asignar if p.get('categoria') == categoria]

    partidos_por_grupo = resultado_dict.get('partidos_por_grupo', {})
    partidos_categoria = {}
    for grupo in grupos:
        grupo_id = str(grupo.get('id'))
        if grupo_id in partidos_por_grupo:
            partidos_categoria[grupo_id] = partidos_por_grupo[grupo_id]

    return jsonify({
        'success': True,
        'categoria': categoria,
        'grupos': grupos,
        'parejas_no_asignadas': parejas_no_asignadas,
        'partidos': partidos_categoria
    })


# ==================== FASE DEL TORNEO ====================

@grupos_bp.route('/cambiar-fase', methods=['POST'])
def cambiar_fase():
    """Cambia la fase del torneo (inscripcion ↔ torneo ↔ espera).

    Solo el admin puede ejecutarla.
    Esto controla la visibilidad pública de grupos, finales y calendario.
    """
    data = request.get_json(silent=True) or {}
    nueva_fase = data.get('fase')

    fases_validas = ('inscripcion', 'torneo', 'espera')
    if nueva_fase not in fases_validas:
        return jsonify({'error': 'Fase inválida'}), 400

    torneo = storage.cargar()
    fase_actual = torneo.get('fase', 'inscripcion')

    torneo['fase'] = nueva_fase
    storage.guardar(torneo)
    logger.info('Fase del torneo cambiada: %s → %s', fase_actual, nueva_fase)
    return jsonify({'ok': True, 'fase': nueva_fase})
