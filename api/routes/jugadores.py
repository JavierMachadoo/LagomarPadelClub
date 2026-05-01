from difflib import SequenceMatcher

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


@jugadores_bp.route('/jugadores/sugerencias-vinculacion', methods=['GET'])
def sugerencias_vinculacion():
    if not jugadores_storage._use_supabase:
        return jsonify({'sugerencias': []}), 200

    try:
        from utils.supabase_client import get_supabase_admin
        sb = get_supabase_admin()
        auth_ids = {str(u.id) for u in sb.auth.admin.list_users()}

        todos = jugadores_storage.listar(activos_only=True)

        # Admin-creados: UUID propio no existe en auth.users, sin usuario_id
        admin_creados = [j for j in todos if j.get('id') not in auth_ids and not j.get('usuario_id')]
        # Registrados: su UUID existe en auth.users, sin usuario_id asignado aún
        registrados = [j for j in todos if j.get('id') in auth_ids and not j.get('usuario_id')]

        def nombre_full(j):
            return f"{j.get('nombre', '')} {j.get('apellido', '')}".strip().lower()

        UMBRAL = 0.75
        sugerencias = []
        for cat in admin_creados:
            for reg in registrados:
                score = SequenceMatcher(None, nombre_full(cat), nombre_full(reg)).ratio()
                if score >= UMBRAL:
                    sugerencias.append({
                        'catalogo':   cat,
                        'registrado': reg,
                        'score':      round(score * 100),
                    })

        sugerencias.sort(key=lambda x: x['score'], reverse=True)
        return jsonify({'sugerencias': sugerencias}), 200

    except Exception:
        logger.exception('Error al calcular sugerencias de vinculación')
        return jsonify({'error': 'Error al calcular sugerencias'}), 500


@jugadores_bp.route('/jugadores/fusionar', methods=['POST'])
def fusionar_jugadores():
    data = request.json or {}
    catalogo_id   = data.get('catalogo_id', '').strip()
    registrado_id = data.get('registrado_id', '').strip()
    if not catalogo_id or not registrado_id:
        return jsonify({'error': 'catalogo_id y registrado_id son obligatorios'}), 400
    try:
        jugador = jugadores_storage.fusionar(catalogo_id, registrado_id)
        return jsonify(jugador), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception('Error al fusionar jugadores')
        return jsonify({'error': 'Error al fusionar jugadores'}), 500


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
