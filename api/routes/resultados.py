from flask import Blueprint, request, jsonify
import logging

from utils.api_helpers import (
    obtener_datos_desde_token,
    sincronizar_con_storage_y_token,
    verificar_autenticacion_api,
)
from utils.torneo_storage import storage, ConflictError
from services import ServiceError
from services import resultado_service

resultados_bp = Blueprint('resultados', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


@resultados_bp.before_request
def verificar_auth():
    authenticated, error_response = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not authenticated:
        return error_response


@resultados_bp.route('/asignar-posicion', methods=['POST'])
def asignar_posicion():
    if storage.get_fase() != 'torneo':
        return jsonify({'error': 'El torneo no está activo. No se pueden asignar posiciones.'}), 403

    data = request.json
    pareja_id = data.get('pareja_id')
    posicion = data.get('posicion')
    categoria = data.get('categoria')

    if pareja_id is None or posicion is None or not categoria:
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    try:
        datos = obtener_datos_desde_token()
        resultado_data = datos.get('resultado_algoritmo')
        if not resultado_data:
            return jsonify({'error': 'No hay resultados cargados'}), 400

        puede_generar, posicion_anterior = resultado_service.asignar_posicion(
            resultado_data, pareja_id, posicion, categoria
        )

        datos['resultado_algoritmo'] = resultado_data
        sincronizar_con_storage_y_token(datos)

        return jsonify({
            'success': True,
            'mensaje': '' if posicion == 0 else f'✓ Posición {posicion}°',
            'puede_generar_finales': puede_generar,
            'posicion': posicion,
            'posicion_anterior': posicion_anterior,
        })

    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code
    except ConflictError as e:
        return jsonify({'error': str(e)}), 409
    except Exception as e:
        logger.error('Error al asignar posición: %s', e, exc_info=True)
        return jsonify({'error': 'Error al asignar posición. Por favor, intenta nuevamente.'}), 500


@resultados_bp.route('/guardar-resultado-partido', methods=['POST'])
def guardar_resultado_partido():
    if storage.get_fase() != 'torneo':
        return jsonify({'error': 'El torneo no está activo. No se pueden ingresar resultados.'}), 403

    data = request.json
    categoria = data.get('categoria')
    grupo_id = data.get('grupo_id')
    pareja1_id = data.get('pareja1_id')
    pareja2_id = data.get('pareja2_id')

    if not all([categoria, grupo_id is not None, pareja1_id is not None, pareja2_id is not None]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    try:
        datos = obtener_datos_desde_token()
        resultado_data = datos.get('resultado_algoritmo')
        if not resultado_data:
            return jsonify({'error': 'No hay resultados cargados'}), 400

        resultado_dict, resultados_completos = resultado_service.guardar_resultado_grupo(
            resultado_data,
            categoria=categoria,
            grupo_id=grupo_id,
            pareja1_id=pareja1_id,
            pareja2_id=pareja2_id,
            games_set1_p1=data.get('games_set1_pareja1'),
            games_set1_p2=data.get('games_set1_pareja2'),
            games_set2_p1=data.get('games_set2_pareja1'),
            games_set2_p2=data.get('games_set2_pareja2'),
            tiebreak_p1=data.get('tiebreak_pareja1'),
            tiebreak_p2=data.get('tiebreak_pareja2'),
        )

        datos['resultado_algoritmo'] = resultado_data
        sincronizar_con_storage_y_token(datos)

        return jsonify({
            'success': True,
            'mensaje': '✓ Resultado guardado',
            'resultado': resultado_dict,
            'resultados_completos': resultados_completos,
        })

    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code
    except ConflictError as e:
        return jsonify({'error': str(e)}), 409
    except Exception as e:
        logger.error('Error al guardar resultado: %s', e, exc_info=True)
        return jsonify({'error': 'Error al guardar el resultado. Por favor, intenta nuevamente.'}), 500


@resultados_bp.route('/obtener-tabla-posiciones/<categoria>/<int:grupo_id>', methods=['GET'])
def obtener_tabla_posiciones(categoria, grupo_id):
    try:
        resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
        if not resultado_data:
            return jsonify({'error': 'No hay resultados cargados'}), 400

        tabla = resultado_service.obtener_tabla_posiciones(resultado_data, categoria, grupo_id)

        grupo_encontrado = next(
            (g for g in resultado_data['grupos_por_categoria'].get(categoria, []) if g['id'] == grupo_id),
            None,
        )
        return jsonify({
            'success': True,
            'tabla': tabla,
            'resultados_completos': grupo_encontrado.get('resultados_completos', False) if grupo_encontrado else False,
        })

    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code
    except Exception as e:
        logger.error('Error al obtener tabla: %s', e, exc_info=True)
        return jsonify({'error': 'Error al obtener la tabla de posiciones. Por favor, intenta nuevamente.'}), 500
