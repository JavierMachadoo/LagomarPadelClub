"""
Blueprint de inscripciones para jugadores.

Rutas públicas (jugador logueado):
  GET  /inscripcion              → formulario de inscripción
  POST /api/inscripcion          → crear inscripción
  GET  /api/inscripcion/mis-datos → ver mi inscripción
  DELETE /api/inscripcion        → cancelar inscripción

Rutas admin:
  GET  /api/admin/inscripciones                      → listar todas
  PATCH /api/admin/inscripciones/<id>/estado         → cambiar estado
"""

import logging

from flask import Blueprint, request, jsonify, render_template, make_response, g

from utils.torneo_storage import storage
from utils.api_helpers import verificar_autenticacion_api
from config import FRANJAS_HORARIAS, TIPOS_TORNEO, CATEGORIAS

logger = logging.getLogger(__name__)

inscripcion_bp = Blueprint('inscripcion', __name__)


# ── Helpers Supabase ──────────────────────────────────────────────────────────

def _get_supabase_admin():
    """Cliente con SERVICE_ROLE — bypasea RLS. Solo operaciones server-side."""
    from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    from supabase import create_client
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY no está configurada")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _get_jugador_data() -> dict | None:
    """Devuelve los datos del jugador autenticado desde el JWT custom, sin llamadas de red."""
    from flask import current_app
    token = request.cookies.get('token')
    if not token:
        return None
    data = current_app.jwt_handler.verificar_token(token)
    if data and data.get('role') == 'jugador':
        return data
    return None


def _get_jugador_id() -> str | None:
    """Devuelve el UUID del jugador autenticado desde el JWT custom, sin llamadas de red."""
    data = _get_jugador_data()
    return data.get('user_id') if data else None


def _uuid_to_int_id(uuid_str: str) -> int:
    """Convierte un UUID a int determinístico para usarlo como Pareja.id."""
    return int(uuid_str.replace('-', '')[:8], 16)


# ── Página del formulario (GET /inscripcion) ──────────────────────────────────

@inscripcion_bp.route('/inscripcion')
def pagina_inscripcion():
    """Renderiza el formulario de inscripción para el jugador logueado."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['jugador', 'admin'])
    if not autenticado:
        from flask import redirect, url_for
        return redirect(url_for('login'))

    torneo = storage.cargar()
    fase = torneo.get('fase', 'inscripcion')
    tipo_torneo = torneo.get('tipo_torneo', 'fin1')
    categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)

    # Leer perfil desde el JWT — sin llamadas de red
    jugador_data = _get_jugador_data()
    perfil = None
    if jugador_data:
        perfil = {
            'nombre':   jugador_data.get('nombre', ''),
            'apellido': jugador_data.get('apellido', ''),
            'telefono': jugador_data.get('telefono', ''),
        }

    return make_response(render_template(
        'inscripcion.html',
        torneo=torneo,
        fase=fase,
        perfil=perfil,
        inscripcion_existente=None,  # se carga vía AJAX al montar la página
        categorias=categorias_torneo,
        franjas=FRANJAS_HORARIAS,
    ))


# ── API: crear inscripción (POST /api/inscripcion) ────────────────────────────

@inscripcion_bp.route('/api/inscripcion', methods=['POST'])
def crear_inscripcion():
    """Crea una inscripción para el jugador logueado."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['jugador', 'admin'])
    if not autenticado:
        return error

    torneo = storage.cargar()
    if torneo.get('fase', 'inscripcion') != 'inscripcion':
        return jsonify({'error': 'Las inscripciones están cerradas para este torneo'}), 403

    jugador_id = _get_jugador_id()
    if not jugador_id:
        return jsonify({'error': 'No se pudo identificar al jugador'}), 401

    data = request.get_json(silent=True) or {}
    integrante1 = data.get('integrante1', '').strip()
    integrante2 = data.get('integrante2', '').strip()
    telefono = data.get('telefono', '').strip()
    categoria = data.get('categoria', '').strip()
    franjas = data.get('franjas', [])

    # Validaciones
    if not integrante1:
        return jsonify({'error': 'El nombre del integrante 1 es obligatorio'}), 400
    if not integrante2:
        return jsonify({'error': 'El nombre del integrante 2 es obligatorio'}), 400
    if not categoria:
        return jsonify({'error': 'La categoría es obligatoria'}), 400
    if len(franjas) < 2:
        return jsonify({'error': 'Seleccioná al menos 2 franjas horarias'}), 400

    tipo_torneo = torneo.get('tipo_torneo', 'fin1')
    categorias_validas = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)
    if categoria not in categorias_validas:
        return jsonify({'error': f'Categoría inválida para este torneo: {categoria}'}), 400

    torneo_id = storage.get_torneo_id()

    try:
        sb = _get_supabase_admin()
        resp = sb.table('inscripciones').insert({
            'torneo_id':           torneo_id,
            'jugador_id':          jugador_id,
            'integrante1':         integrante1,
            'integrante2':         integrante2,
            'telefono':            telefono or None,
            'categoria':           categoria,
            'franjas_disponibles': franjas,
            'estado':              'confirmado',
        }).execute()

        inscripcion = resp.data[0] if resp.data else {}
        logger.info('Inscripción creada: jugador=%s, categoria=%s', jugador_id, categoria)
        return jsonify({'ok': True, 'inscripcion': inscripcion}), 201

    except Exception as e:
        error_msg = str(e)
        if 'unique' in error_msg.lower() or 'duplicate' in error_msg.lower():
            return jsonify({'error': 'Ya tenés una inscripción para este torneo'}), 409
        logger.error('Error al crear inscripción: %s', e)
        return jsonify({'error': 'Error al guardar la inscripción'}), 500


# ── API: mis datos (GET /api/inscripcion/mis-datos) ───────────────────────────

@inscripcion_bp.route('/api/inscripcion/mis-datos', methods=['GET'])
def mis_datos():
    """Devuelve la inscripción del jugador logueado para el torneo activo."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['jugador', 'admin'])
    if not autenticado:
        return error

    jugador_id = _get_jugador_id()
    if not jugador_id:
        return jsonify({'error': 'No se pudo identificar al jugador'}), 401

    torneo_id = storage.get_torneo_id()
    try:
        sb = _get_supabase_admin()
        resp = sb.table('inscripciones').select('*').eq('torneo_id', torneo_id).eq('jugador_id', jugador_id).execute()
        return jsonify({'inscripcion': resp.data[0] if resp.data else None})
    except Exception as e:
        logger.error('Error al obtener inscripción: %s', e)
        return jsonify({'inscripcion': None})


# ── API: cancelar inscripción (DELETE /api/inscripcion) ───────────────────────

@inscripcion_bp.route('/api/inscripcion', methods=['DELETE'])
def cancelar_inscripcion():
    """Cancela (elimina) la inscripción del jugador logueado.
    Solo disponible mientras la fase sea 'inscripcion'.
    """
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['jugador', 'admin'])
    if not autenticado:
        return error

    torneo = storage.cargar()
    if torneo.get('fase', 'inscripcion') != 'inscripcion':
        return jsonify({'error': 'No se puede cancelar la inscripción fuera del período de inscripción'}), 403

    jugador_id = _get_jugador_id()
    if not jugador_id:
        return jsonify({'error': 'No se pudo identificar al jugador'}), 401

    torneo_id = storage.get_torneo_id()
    try:
        sb = _get_supabase_admin()
        sb.table('inscripciones').delete().eq('torneo_id', torneo_id).eq('jugador_id', jugador_id).execute()
        logger.info('Inscripción cancelada: jugador=%s', jugador_id)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error('Error al cancelar inscripción: %s', e)
        return jsonify({'error': 'Error al cancelar la inscripción'}), 500


# ── API Admin: listar inscripciones (GET /api/admin/inscripciones) ────────────

@inscripcion_bp.route('/api/admin/inscripciones', methods=['GET'])
def listar_inscripciones():
    """Lista todas las inscripciones del torneo activo. Solo admin."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not autenticado:
        return error

    torneo_id = storage.get_torneo_id()
    try:
        sb = _get_supabase_admin()
        resp = sb.table('inscripciones').select('*').eq('torneo_id', torneo_id).order('created_at').execute()
        return jsonify({'inscripciones': resp.data or [], 'total': len(resp.data or [])})
    except Exception as e:
        logger.error('Error al listar inscripciones: %s', e)
        return jsonify({'error': 'Error al cargar inscripciones'}), 500


# ── API Admin: cambiar estado (PATCH /api/admin/inscripciones/<id>/estado) ────

@inscripcion_bp.route('/api/admin/inscripciones/<inscripcion_id>/estado', methods=['PATCH'])
def cambiar_estado_inscripcion(inscripcion_id):
    """Cambia el estado de una inscripción (confirmado / rechazado). Solo admin."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not autenticado:
        return error

    data = request.get_json(silent=True) or {}
    nuevo_estado = data.get('estado')
    if nuevo_estado not in ('confirmado', 'rechazado', 'pendiente'):
        return jsonify({'error': 'Estado inválido'}), 400

    try:
        sb = _get_supabase_admin()
        resp = sb.table('inscripciones').update({'estado': nuevo_estado}).eq('id', inscripcion_id).execute()
        if not resp.data:
            return jsonify({'error': 'Inscripción no encontrada'}), 404
        return jsonify({'ok': True, 'inscripcion': resp.data[0]})
    except Exception as e:
        logger.error('Error al cambiar estado de inscripción: %s', e)
        return jsonify({'error': 'Error al actualizar'}), 500
