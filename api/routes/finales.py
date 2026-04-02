"""
API Routes para manejo de finales.
"""

from flask import Blueprint, jsonify, request
import logging

from utils.torneo_storage import storage, ConflictError
from utils.api_helpers import verificar_autenticacion_api
from services import ServiceError
from services import fixture_service

logger = logging.getLogger(__name__)

finales_bp = Blueprint('finales', __name__, url_prefix='/api/finales')


@finales_bp.before_request
def verificar_auth():
    authenticated, error_response = verificar_autenticacion_api()
    if not authenticated:
        return error_response


@finales_bp.route('/fixtures', methods=['GET'])
def obtener_fixtures():
    try:
        torneo = storage.cargar()
        fixtures = fixture_service.obtener_o_generar_fixtures(torneo)
        return jsonify({'success': True, 'fixtures': fixtures})
    except ServiceError as e:
        return jsonify({'success': False, 'message': e.message}), e.status_code
    except ConflictError as e:
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        logger.error('Error al obtener fixtures: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': f'Error al obtener fixtures: {str(e)}'}), 500


@finales_bp.route('/fixtures/<categoria>', methods=['GET'])
def obtener_fixture_categoria(categoria):
    try:
        torneo = storage.cargar()
        fixture = fixture_service.obtener_fixture_categoria(torneo, categoria)
        return jsonify({'success': True, 'fixture': fixture})
    except ServiceError as e:
        return jsonify({'success': False, 'message': e.message}), e.status_code
    except ConflictError as e:
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        logger.error('Error al obtener fixture de %s: %s', categoria, e, exc_info=True)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@finales_bp.route('/fixtures/regenerar', methods=['POST'])
def regenerar_fixtures():
    try:
        torneo = storage.cargar()
        fixtures_nuevos = fixture_service.regenerar_todos_fixtures(torneo)
        return jsonify({'success': True, 'message': 'Fixtures regenerados exitosamente', 'fixtures': fixtures_nuevos})
    except ServiceError as e:
        return jsonify({'success': False, 'message': e.message}), e.status_code
    except ConflictError as e:
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        logger.error('Error al regenerar fixtures: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@finales_bp.route('/partido/<partido_id>/ganador', methods=['POST'])
def actualizar_ganador_partido(partido_id):
    data = request.get_json()
    ganador_id = data.get('ganador_id')
    if not ganador_id:
        return jsonify({'success': False, 'message': 'ganador_id es requerido'}), 400

    try:
        torneo = storage.cargar()
        fixture_dict = fixture_service.actualizar_ganador(torneo, partido_id, ganador_id)
        return jsonify({'success': True, 'message': 'Ganador actualizado exitosamente', 'fixture': fixture_dict})
    except ServiceError as e:
        return jsonify({'success': False, 'message': e.message}), e.status_code
    except ConflictError as e:
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        logger.error('Error al actualizar ganador: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@finales_bp.route('/partido/<partido_id>/resultado', methods=['POST'])
def guardar_resultado_partido(partido_id):
    data = request.get_json()
    sets = data.get('sets', [])

    try:
        torneo = storage.cargar()
        ganador_id = fixture_service.guardar_resultado_final(torneo, partido_id, sets)
        return jsonify({'success': True, 'message': 'Resultado guardado exitosamente', 'ganador_id': ganador_id})
    except ServiceError as e:
        return jsonify({'success': False, 'message': e.message}), e.status_code
    except ConflictError as e:
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        logger.error('Error al guardar resultado: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@finales_bp.route('/calendario', methods=['GET'])
def obtener_calendario():
    try:
        torneo = storage.cargar()
        calendario, resumen = fixture_service.obtener_calendario(torneo)
        return jsonify({'success': True, 'calendario': calendario, 'resumen_horarios': resumen})
    except ServiceError as e:
        return jsonify({'success': False, 'message': e.message}), e.status_code
    except Exception as e:
        logger.error('Error al generar calendario: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
