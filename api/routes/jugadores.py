from flask import Blueprint, request, jsonify
import logging

from utils.jugadores_storage import jugadores_storage
from utils.api_helpers import verificar_autenticacion_api

jugadores_bp = Blueprint('jugadores', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


@jugadores_bp.before_request
def verificar_auth():
    authenticated, error_response = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not authenticated:
        return error_response


@jugadores_bp.route('/jugadores', methods=['GET'])
def listar_jugadores():
    q = request.args.get('q', '').strip()
    jugadores = jugadores_storage.buscar(q) if q else jugadores_storage.listar()
    return jsonify({'jugadores': jugadores}), 200


@jugadores_bp.route('/jugadores', methods=['POST'])
def crear_jugador():
    data = request.json or {}
    nombre = data.get('nombre', '').strip()
    apellido = data.get('apellido', '').strip()
    if not nombre or not apellido:
        return jsonify({'error': 'nombre y apellido son obligatorios'}), 400
    try:
        jugador = jugadores_storage.crear(
            nombre=nombre,
            apellido=apellido,
            telefono=data.get('telefono'),
            email=data.get('email'),
        )
        return jsonify(jugador), 201
    except Exception:
        logger.exception('Error al crear jugador')
        return jsonify({'error': 'Error al crear el jugador'}), 500


@jugadores_bp.route('/jugadores/<jugador_id>', methods=['PATCH'])
def vincular_usuario(jugador_id):
    data = request.json or {}
    usuario_id = data.get('usuario_id', '').strip()
    if not usuario_id:
        return jsonify({'error': 'usuario_id es obligatorio'}), 400
    try:
        jugador = jugadores_storage.vincular_usuario(jugador_id, usuario_id)
        return jsonify(jugador), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception:
        logger.exception('Error al vincular usuario')
        return jsonify({'error': 'Error al vincular usuario'}), 500
