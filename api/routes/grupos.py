from flask import Blueprint, request, jsonify
import logging

from utils.torneo_storage import storage, ConflictError
from utils.api_helpers import (
    obtener_datos_desde_token,
    crear_respuesta_con_token_actualizado,
    sincronizar_con_storage_y_token,
    verificar_autenticacion_api,
)
from config import NUM_CANCHAS_DEFAULT
from services import ServiceError
from services import grupo_service, torneo_service

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
    if storage.get_fase() == 'torneo':
        return jsonify({'error': 'El torneo ya está activo. No se puede ejecutar el algoritmo.'}), 403

    from utils.api_helpers import _verificar_supabase_jwt  # noqa: F401

    datos_actuales = obtener_datos_desde_token()
    try:
        resultado, todas_parejas_data, mensaje = grupo_service.ejecutar_algoritmo(
            datos_actuales.get('parejas', [])
        )
    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code

    datos_actuales['resultado_algoritmo'] = resultado
    datos_actuales['num_canchas'] = NUM_CANCHAS_DEFAULT
    datos_actuales['parejas'] = todas_parejas_data
    sincronizar_con_storage_y_token(datos_actuales)

    return crear_respuesta_con_token_actualizado(
        {'success': True, 'mensaje': mensaje, 'resultado': resultado},
        datos_actuales,
    )


@grupos_bp.route('/resultado_algoritmo', methods=['GET'])
def obtener_resultado_algoritmo():
    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    return jsonify(resultado_data)


# ==================== GESTIÓN DE GRUPOS ====================

@grupos_bp.route('/intercambiar-pareja', methods=['POST'])
def intercambiar_pareja():
    if storage.get_fase() == 'torneo':
        return jsonify({'error': 'El torneo ya está activo. No se pueden modificar los grupos.'}), 403

    data = request.json
    datos_actuales = obtener_datos_desde_token()
    resultado = datos_actuales.get('resultado_algoritmo')
    if not resultado:
        return jsonify({'error': 'No hay resultados cargados'}), 400

    try:
        mensaje, estadisticas = grupo_service.intercambiar_pareja(
            resultado,
            pareja_id=data.get('pareja_id'),
            grupo_origen_id=data.get('grupo_origen'),
            grupo_destino_id=data.get('grupo_destino'),
            slot_destino=data.get('slot_destino'),
            num_canchas=datos_actuales.get('num_canchas', NUM_CANCHAS_DEFAULT),
        )
    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code
    except Exception as e:
        logger.error('Error al intercambiar: %s', e, exc_info=True)
        return jsonify({'error': 'Error al intercambiar parejas. Por favor, intenta nuevamente.'}), 500

    datos_actuales['resultado_algoritmo'] = resultado
    sincronizar_con_storage_y_token(datos_actuales)

    return crear_respuesta_con_token_actualizado(
        {'success': True, 'mensaje': mensaje, 'estadisticas': estadisticas},
        datos_actuales,
    )


@grupos_bp.route('/asignar-pareja-a-grupo', methods=['POST'])
def asignar_pareja_a_grupo():
    if storage.get_fase() == 'torneo':
        return jsonify({'error': 'El torneo ya está activo. No se pueden modificar los grupos.'}), 403

    data = request.json
    pareja_id = data.get('pareja_id')
    grupo_id = data.get('grupo_id')
    categoria = data.get('categoria')

    if not all([pareja_id, grupo_id, categoria]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404

    try:
        estadisticas = grupo_service.asignar_pareja_a_grupo(
            resultado_data,
            pareja_id=pareja_id,
            grupo_id=grupo_id,
            categoria=categoria,
            pareja_a_remover_id=data.get('pareja_a_remover_id'),
            slot_destino=data.get('slot_destino'),
            num_canchas=datos_actuales.get('num_canchas', NUM_CANCHAS_DEFAULT),
        )
    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code

    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)

    return crear_respuesta_con_token_actualizado(
        {'success': True, 'mensaje': '✓ Pareja asignada al grupo correctamente', 'estadisticas': estadisticas},
        datos_actuales,
    )


@grupos_bp.route('/crear-grupo-manual', methods=['POST'])
def crear_grupo_manual():
    if storage.get_fase() == 'torneo':
        return jsonify({'error': 'El torneo ya está activo. No se pueden crear grupos.'}), 403

    data = request.json
    categoria = data.get('categoria')
    franja_horaria = data.get('franja_horaria')
    cancha = data.get('cancha')

    if not all([categoria, franja_horaria, cancha]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404

    try:
        nuevo_grupo = grupo_service.crear_grupo_manual(
            resultado_data, categoria, franja_horaria, cancha,
            datos_actuales.get('num_canchas', NUM_CANCHAS_DEFAULT),
        )
    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code

    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)

    return crear_respuesta_con_token_actualizado(
        {'success': True, 'mensaje': '✓ Grupo creado correctamente', 'grupo': nuevo_grupo},
        datos_actuales,
    )


@grupos_bp.route('/editar-grupo', methods=['POST'])
def editar_grupo():
    if storage.get_fase() == 'torneo':
        return jsonify({'error': 'El torneo ya está activo. No se pueden editar grupos.'}), 403

    data = request.json
    grupo_id = data.get('grupo_id')
    categoria = data.get('categoria')
    franja_horaria = data.get('franja_horaria')
    cancha = data.get('cancha')

    if not all([grupo_id, categoria, franja_horaria, cancha]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404

    try:
        grupo_service.editar_grupo(
            resultado_data, grupo_id, categoria, franja_horaria, cancha,
            datos_actuales.get('num_canchas', NUM_CANCHAS_DEFAULT),
        )
    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code

    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)

    return crear_respuesta_con_token_actualizado(
        {'success': True, 'mensaje': '✓ Grupo actualizado correctamente'},
        datos_actuales,
    )


# ==================== CONSULTAS DE GRUPOS ====================

@grupos_bp.route('/estadisticas', methods=['GET'])
def obtener_estadisticas():
    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    return jsonify({'success': True, 'estadisticas': grupo_service.recalcular_estadisticas(resultado_data)})


@grupos_bp.route('/obtener-categoria/<categoria>', methods=['GET'])
def obtener_categoria(categoria):
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    if categoria not in resultado_dict.get('grupos_por_categoria', {}):
        return jsonify({'error': f'Categoría {categoria} no encontrada'}), 404
    return jsonify({
        'success': True,
        'categoria': categoria,
        'grupos': resultado_dict['grupos_por_categoria'][categoria],
        'parejas_sin_asignar': [
            p for p in resultado_dict.get('parejas_sin_asignar', [])
            if p.get('categoria') == categoria
        ],
    })


@grupos_bp.route('/obtener-grupo/<categoria>/<int:grupo_id>', methods=['GET'])
def obtener_grupo(categoria, grupo_id):
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    grupos = resultado_dict.get('grupos_por_categoria', {}).get(categoria, [])
    grupo = next((g for g in grupos if g['id'] == grupo_id), None)
    if not grupo:
        return jsonify({'error': 'Grupo no encontrado'}), 404
    return jsonify({'success': True, 'grupo': grupo})


@grupos_bp.route('/obtener-datos-categoria/<categoria>', methods=['GET'])
def obtener_datos_categoria(categoria):
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    grupos = resultado_dict.get('grupos_por_categoria', {}).get(categoria, [])
    parejas_no_asignadas = [
        p for p in resultado_dict.get('parejas_sin_asignar', [])
        if p.get('categoria') == categoria
    ]
    partidos_por_grupo = resultado_dict.get('partidos_por_grupo', {})
    partidos_categoria = {
        str(g.get('id')): partidos_por_grupo[str(g.get('id'))]
        for g in grupos
        if str(g.get('id')) in partidos_por_grupo
    }
    return jsonify({
        'success': True,
        'categoria': categoria,
        'grupos': grupos,
        'parejas_no_asignadas': parejas_no_asignadas,
        'partidos': partidos_categoria,
    })


# ==================== FASE DEL TORNEO ====================

@grupos_bp.route('/cambiar-fase', methods=['POST'])
def cambiar_fase():
    data = request.get_json(silent=True) or {}
    nueva_fase = data.get('fase')

    try:
        fase = torneo_service.cambiar_fase(nueva_fase)
    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code
    except ConflictError as e:
        return jsonify({'error': str(e)}), 409

    return jsonify({'ok': True, 'fase': fase})
