"""
Blueprint de inscripciones para jugadores.

Rutas públicas (jugador logueado):
  GET  /inscripcion                            → formulario de inscripción
  POST /api/inscripcion                        → crear inscripción
  GET  /api/inscripcion/mis-datos              → ver mi inscripción
  DELETE /api/inscripcion                      → cancelar inscripción
  GET  /api/jugadores/buscar?telefono=XXX      → buscar compañero por teléfono
  GET  /api/inscripcion/invitaciones-pendientes → invitaciones pendientes (Player B)
  POST /api/inscripcion/<id>/aceptar           → aceptar invitación
  POST /api/inscripcion/<id>/rechazar          → rechazar invitación (cancela inscripción)
  GET  /inscripcion/invitar?token=XXX          → página de invitación por link

Rutas admin:
  GET  /api/admin/inscripciones                      → listar todas
  PATCH /api/admin/inscripciones/<id>/estado         → cambiar estado
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, render_template, make_response, g, redirect, url_for

from core import Pareja, Grupo
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


def _auto_asignar_en_grupos(inscripcion: dict) -> None:
    """
    Si ya hay grupos generados, intenta colocar la pareja recién inscrita en un
    grupo de su misma categoría que tenga hueco (< 3 parejas).
    Si no hay hueco disponible, la agrega a parejas_sin_asignar.
    Si todavía no se generaron grupos, no hace nada.
    """
    from ._helpers import recalcular_score_grupo, recalcular_estadisticas

    torneo = storage.cargar()
    resultado = torneo.get('resultado_algoritmo')
    if not resultado:
        return  # Grupos aún no generados — la pareja queda solo en inscripciones

    categoria = inscripcion['categoria']
    pareja_dict = {
        'id':                 _uuid_to_int_id(inscripcion['id']),
        'nombre':             f"{inscripcion['integrante1']} / {inscripcion['integrante2']}",
        'jugador1':           inscripcion['integrante1'],
        'jugador2':           inscripcion['integrante2'],
        'telefono':           inscripcion.get('telefono') or '',
        'categoria':          categoria,
        'franjas_disponibles': inscripcion.get('franjas_disponibles') or [],
        'inscripcion_id':     inscripcion['id'],
    }

    # Buscar grupo de la misma categoría con espacio libre
    grupos_categoria = resultado.get('grupos_por_categoria', {}).get(categoria, [])
    grupo_destino = next(
        (g for g in grupos_categoria if len(g.get('parejas', [])) < 3),
        None
    )

    if grupo_destino:
        grupo_destino['parejas'].append(pareja_dict)
        recalcular_score_grupo(grupo_destino)

        # Si el grupo llega a 3 parejas, regenerar la lista de partidos
        if len(grupo_destino['parejas']) == 3:
            try:
                grupo_obj = Grupo(id=grupo_destino['id'], categoria=categoria)
                grupo_obj.franja_horaria = grupo_destino.get('franja_horaria')
                for p in grupo_destino['parejas']:
                    grupo_obj.parejas.append(Pareja.from_dict(p))
                grupo_obj.generar_partidos()
                grupo_destino['partidos'] = [
                    {
                        'pareja1':    p1.nombre,
                        'pareja2':    p2.nombre,
                        'pareja1_id': p1.id,
                        'pareja2_id': p2.id,
                    }
                    for p1, p2 in grupo_obj.partidos
                ]
                grupo_destino['resultados'] = {}
                grupo_destino['resultados_completos'] = False
            except Exception as e:
                logger.warning('No se pudieron regenerar partidos del grupo: %s', e)

        logger.info(
            'Pareja "%s" auto-asignada al grupo %s (categoria=%s)',
            pareja_dict['nombre'], grupo_destino['id'], categoria
        )
    else:
        resultado.setdefault('parejas_sin_asignar', []).append(pareja_dict)
        logger.info(
            'Pareja "%s" sin hueco disponible → agregada a parejas_sin_asignar (categoria=%s)',
            pareja_dict['nombre'], categoria
        )

    # Actualizar lista plana de parejas y estadísticas
    torneo.setdefault('parejas', []).append(pareja_dict)
    recalcular_estadisticas(resultado)
    torneo['resultado_algoritmo'] = resultado
    storage.guardar(torneo)


# ── Helpers de invitación ─────────────────────────────────────────────────────

INVITACION_EXPIRACION_HORAS = 48


def _generar_token_invitacion(sb, inscripcion_id: str) -> str:
    """Genera un token seguro, lo persiste en invitacion_tokens y devuelve el token."""
    token = secrets.token_urlsafe(32)
    expira_at = (datetime.now(timezone.utc) + timedelta(hours=INVITACION_EXPIRACION_HORAS)).isoformat()
    sb.table('invitacion_tokens').insert({
        'inscripcion_id': inscripcion_id,
        'token':          token,
        'expira_at':      expira_at,
    }).execute()
    return token


def _expirar_invitaciones_vencidas(sb, torneo_id: str) -> None:
    """Expira invitaciones cuyo token ya venció (verificación lazy)."""
    try:
        sb.rpc('expirar_invitaciones', {'p_torneo_id': torneo_id}).execute()
    except Exception as e:
        logger.warning('Error al expirar invitaciones: %s', e)


def _validar_jugador_no_inscrito(sb, torneo_id: str, jugador_id: str) -> str | None:
    """Verifica que un jugador no esté ya inscrito en el torneo (como jugador1 o jugador2).
    Devuelve mensaje de error o None si está libre."""
    # Como jugador1 (creador de inscripción)
    resp1 = sb.table('inscripciones').select('id').eq('torneo_id', torneo_id).eq('jugador_id', jugador_id).execute()
    if resp1.data:
        return 'Este jugador ya tiene una inscripción en el torneo'
    # Como jugador2 (invitado)
    resp2 = sb.table('inscripciones').select('id').eq('torneo_id', torneo_id).eq('jugador2_id', jugador_id).execute()
    if resp2.data:
        return 'Este jugador ya fue invitado a otra pareja en el torneo'
    return None


def _construir_link_invitacion(token: str) -> str:
    """Construye la URL completa del link de invitación."""
    from flask import request as req
    base = req.host_url.rstrip('/')
    return f"{base}/inscripcion/invitar?token={token}"


# ── API: buscar jugadores por teléfono (GET /api/jugadores/buscar) ───────────

@inscripcion_bp.route('/api/jugadores/buscar', methods=['GET'])
def buscar_jugadores():
    """Busca jugadores registrados por teléfono (últimos dígitos).
    Devuelve nombre + teléfono enmascarado. Excluye al buscador y ya inscritos."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['jugador', 'admin'])
    if not autenticado:
        return error

    telefono_query = request.args.get('telefono', '').strip()
    if len(telefono_query) < 4:
        return jsonify({'error': 'Ingresá al menos 4 dígitos del teléfono'}), 400

    jugador_id = _get_jugador_id()
    torneo_id = storage.get_torneo_id()

    try:
        sb = _get_supabase_admin()

        # Buscar jugadores cuyo teléfono contenga los dígitos buscados
        resp = sb.table('jugadores').select('id, nombre, apellido, telefono').ilike('telefono', f'%{telefono_query}%').execute()

        if not resp.data:
            return jsonify({'jugadores': []})

        # Obtener IDs de jugadores ya inscritos en este torneo
        inscritos_resp = sb.table('inscripciones').select('jugador_id, jugador2_id').eq('torneo_id', torneo_id).execute()
        ids_inscritos = set()
        for ins in (inscritos_resp.data or []):
            if ins.get('jugador_id'):
                ids_inscritos.add(ins['jugador_id'])
            if ins.get('jugador2_id'):
                ids_inscritos.add(ins['jugador2_id'])

        resultados = []
        for j in resp.data:
            # Excluir al buscador y a jugadores ya inscritos
            if j['id'] == jugador_id or j['id'] in ids_inscritos:
                continue
            # Enmascarar teléfono: mostrar solo últimos 3 dígitos
            tel = j.get('telefono') or ''
            tel_parcial = f"***{tel[-3:]}" if len(tel) >= 3 else '***'
            resultados.append({
                'id':              j['id'],
                'nombre':          j['nombre'],
                'apellido':        j['apellido'],
                'telefono_parcial': tel_parcial,
            })

        return jsonify({'jugadores': resultados})

    except Exception as e:
        logger.error('Error al buscar jugadores: %s', e)
        return jsonify({'error': 'Error al buscar jugadores'}), 500


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
    """Crea una inscripción para el jugador logueado.

    Si se envía `jugador2_id`, se invita a ese jugador directamente.
    Si no, se genera un link abierto para compartir (cualquiera puede aceptar).
    En ambos casos la inscripción queda en estado 'pendiente_companero' hasta que
    el compañero acepte.
    """
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
    telefono = data.get('telefono', '').strip()
    categoria = data.get('categoria', '').strip()
    franjas = data.get('franjas', [])
    jugador2_id = data.get('jugador2_id', '').strip() or None

    # Validaciones
    if not integrante1:
        return jsonify({'error': 'El nombre del integrante 1 es obligatorio'}), 400
    if not telefono:
        return jsonify({'error': 'El teléfono de contacto es obligatorio'}), 400
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

        # Validar que jugador2 existe y no está ya inscrito
        integrante2 = ''
        if jugador2_id:
            perfil_resp = sb.table('jugadores').select('id, nombre, apellido').eq('id', jugador2_id).execute()
            if not perfil_resp.data:
                return jsonify({'error': 'El compañero seleccionado no existe'}), 404
            perfil_j2 = perfil_resp.data[0]
            integrante2 = f"{perfil_j2['nombre']} {perfil_j2['apellido']}".strip()

            error_inscrito = _validar_jugador_no_inscrito(sb, torneo_id, jugador2_id)
            if error_inscrito:
                return jsonify({'error': error_inscrito}), 409

        # Crear inscripción en estado pendiente_companero
        resp = sb.table('inscripciones').insert({
            'torneo_id':           torneo_id,
            'jugador_id':          jugador_id,
            'jugador2_id':         jugador2_id,
            'integrante1':         integrante1,
            'integrante2':         integrante2,  # vacío si link abierto
            'telefono':            telefono or None,
            'categoria':           categoria,
            'franjas_disponibles': franjas,
            'estado':              'pendiente_companero',
        }).execute()

        inscripcion = resp.data[0] if resp.data else {}
        logger.info('Inscripción creada (pendiente_companero): jugador=%s, categoria=%s', jugador_id, categoria)

        # Generar token de invitación
        token = _generar_token_invitacion(sb, inscripcion['id'])
        link = _construir_link_invitacion(token)

        return jsonify({
            'ok': True,
            'inscripcion': inscripcion,
            'invitacion_link': link,
            'invitacion_token': token,
        }), 201

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
        _expirar_invitaciones_vencidas(sb, torneo_id)

        # Buscar como jugador1 (creador)
        resp = sb.table('inscripciones').select('*').eq('torneo_id', torneo_id).eq('jugador_id', jugador_id).execute()
        inscripcion = resp.data[0] if resp.data else None

        # Si tiene inscripción pendiente_companero, incluir el link de invitación
        if inscripcion and inscripcion.get('estado') == 'pendiente_companero':
            token_resp = (sb.table('invitacion_tokens')
                          .select('token')
                          .eq('inscripcion_id', inscripcion['id'])
                          .eq('usado', False)
                          .order('created_at', desc=True)
                          .limit(1)
                          .execute())
            if token_resp.data:
                inscripcion['invitacion_link'] = _construir_link_invitacion(token_resp.data[0]['token'])

        return jsonify({'inscripcion': inscripcion})
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


# ── API: invitaciones pendientes (GET /api/inscripcion/invitaciones-pendientes)

@inscripcion_bp.route('/api/inscripcion/invitaciones-pendientes', methods=['GET'])
def invitaciones_pendientes():
    """Devuelve invitaciones pendientes donde el jugador actual es Player B."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['jugador', 'admin'])
    if not autenticado:
        return error

    jugador_id = _get_jugador_id()
    if not jugador_id:
        return jsonify({'error': 'No se pudo identificar al jugador'}), 401

    torneo_id = storage.get_torneo_id()

    try:
        sb = _get_supabase_admin()
        _expirar_invitaciones_vencidas(sb, torneo_id)

        resp = (sb.table('inscripciones')
                .select('id, integrante1, categoria, franjas_disponibles, jugador_id, created_at')
                .eq('torneo_id', torneo_id)
                .eq('jugador2_id', jugador_id)
                .eq('estado', 'pendiente_companero')
                .execute())

        invitaciones = []
        for ins in (resp.data or []):
            # Obtener nombre del invitador (Player A)
            perfil_resp = sb.table('jugadores').select('nombre, apellido').eq('id', ins['jugador_id']).execute()
            nombre_invitador = ''
            if perfil_resp.data:
                p = perfil_resp.data[0]
                nombre_invitador = f"{p['nombre']} {p['apellido']}".strip()

            # Obtener fecha de expiración del token
            token_resp = (sb.table('invitacion_tokens')
                          .select('expira_at')
                          .eq('inscripcion_id', ins['id'])
                          .eq('usado', False)
                          .order('created_at', desc=True)
                          .limit(1)
                          .execute())
            expira_at = token_resp.data[0]['expira_at'] if token_resp.data else None

            invitaciones.append({
                'inscripcion_id':   ins['id'],
                'nombre_invitador': nombre_invitador,
                'categoria':        ins['categoria'],
                'franjas':          ins['franjas_disponibles'],
                'created_at':       ins['created_at'],
                'expira_at':        expira_at,
            })

        return jsonify({'invitaciones': invitaciones})

    except Exception as e:
        logger.error('Error al obtener invitaciones pendientes: %s', e)
        return jsonify({'error': 'Error al cargar invitaciones'}), 500


# ── API: aceptar invitación (POST /api/inscripcion/<id>/aceptar) ─────────────

@inscripcion_bp.route('/api/inscripcion/<inscripcion_id>/aceptar', methods=['POST'])
def aceptar_invitacion(inscripcion_id):
    """Player B acepta la invitación. La inscripción pasa a 'confirmado'."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['jugador', 'admin'])
    if not autenticado:
        return error

    jugador_id = _get_jugador_id()
    if not jugador_id:
        return jsonify({'error': 'No se pudo identificar al jugador'}), 401

    try:
        sb = _get_supabase_admin()
        torneo_id = storage.get_torneo_id()

        # Verificar que el jugador no esté ya inscrito en otra pareja
        error_inscrito = _validar_jugador_no_inscrito(sb, torneo_id, jugador_id)
        # Permitir si el único match es esta misma inscripción (ya es jugador2)
        if error_inscrito:
            check = sb.table('inscripciones').select('id').eq('id', inscripcion_id).eq('jugador2_id', jugador_id).execute()
            if not check.data:
                return jsonify({'error': error_inscrito}), 409

        # Obtener la inscripción
        resp = sb.table('inscripciones').select('*').eq('id', inscripcion_id).eq('estado', 'pendiente_companero').execute()
        if not resp.data:
            return jsonify({'error': 'Invitación no encontrada o ya procesada'}), 404

        inscripcion = resp.data[0]

        # Verificar que el jugador es el invitado (jugador2_id) o que es link abierto
        if inscripcion.get('jugador2_id') and inscripcion['jugador2_id'] != jugador_id:
            return jsonify({'error': 'Esta invitación no es para vos'}), 403

        # No puede aceptar su propia inscripción
        if inscripcion['jugador_id'] == jugador_id:
            return jsonify({'error': 'No podés aceptar tu propia inscripción'}), 400

        # Obtener nombre del jugador que acepta
        perfil_resp = sb.table('jugadores').select('nombre, apellido').eq('id', jugador_id).execute()
        nombre_j2 = ''
        if perfil_resp.data:
            p = perfil_resp.data[0]
            nombre_j2 = f"{p['nombre']} {p['apellido']}".strip()

        # Actualizar inscripción: vincular jugador2, confirmar, rellenar integrante2
        sb.table('inscripciones').update({
            'jugador2_id':  jugador_id,
            'integrante2':  nombre_j2,
            'estado':       'confirmado',
        }).eq('id', inscripcion_id).execute()

        # Marcar tokens como usados
        sb.table('invitacion_tokens').update({
            'usado': True,
        }).eq('inscripcion_id', inscripcion_id).execute()

        logger.info('Invitación aceptada: inscripcion=%s, jugador2=%s', inscripcion_id, jugador_id)

        # Re-obtener inscripción actualizada para auto-asignar
        updated = sb.table('inscripciones').select('*').eq('id', inscripcion_id).execute()
        if updated.data:
            try:
                _auto_asignar_en_grupos(updated.data[0])
            except Exception as e:
                logger.error('Error en auto-asignación post-aceptar: %s', e, exc_info=True)

        return jsonify({'ok': True, 'mensaje': 'Invitación aceptada. ¡Ya estás inscripto!'})

    except Exception as e:
        logger.error('Error al aceptar invitación: %s', e)
        return jsonify({'error': 'Error al aceptar la invitación'}), 500


# ── API: rechazar invitación (POST /api/inscripcion/<id>/rechazar) ────────────

@inscripcion_bp.route('/api/inscripcion/<inscripcion_id>/rechazar', methods=['POST'])
def rechazar_invitacion(inscripcion_id):
    """Player B rechaza la invitación. La inscripción se cancela (elimina)."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['jugador', 'admin'])
    if not autenticado:
        return error

    jugador_id = _get_jugador_id()
    if not jugador_id:
        return jsonify({'error': 'No se pudo identificar al jugador'}), 401

    try:
        sb = _get_supabase_admin()

        # Obtener la inscripción
        resp = sb.table('inscripciones').select('*').eq('id', inscripcion_id).eq('estado', 'pendiente_companero').execute()
        if not resp.data:
            return jsonify({'error': 'Invitación no encontrada o ya procesada'}), 404

        inscripcion = resp.data[0]

        # Verificar que el jugador es el invitado o que es link abierto con su jugador2_id
        if inscripcion.get('jugador2_id') and inscripcion['jugador2_id'] != jugador_id:
            return jsonify({'error': 'Esta invitación no es para vos'}), 403

        # Eliminar la inscripción (se cancela por rechazo)
        sb.table('inscripciones').delete().eq('id', inscripcion_id).execute()

        logger.info('Invitación rechazada: inscripcion=%s, jugador2=%s', inscripcion_id, jugador_id)

        return jsonify({'ok': True, 'mensaje': 'Invitación rechazada. La inscripción fue cancelada.'})

    except Exception as e:
        logger.error('Error al rechazar invitación: %s', e)
        return jsonify({'error': 'Error al rechazar la invitación'}), 500


# ── Página de invitación por link (GET /inscripcion/invitar) ─────────────────

@inscripcion_bp.route('/inscripcion/invitar', methods=['GET'])
def pagina_invitacion_link():
    """Página que muestra la invitación y permite aceptar/rechazar.
    Si el usuario no está logueado, redirige a login con redirect back."""
    token = request.args.get('token', '').strip()
    if not token:
        return render_template('invitacion.html', error='Link de invitación inválido')

    try:
        sb = _get_supabase_admin()

        # Buscar token
        token_resp = (sb.table('invitacion_tokens')
                      .select('inscripcion_id, expira_at, usado')
                      .eq('token', token)
                      .execute())

        if not token_resp.data:
            return render_template('invitacion.html', error='Link de invitación inválido o expirado')

        token_data = token_resp.data[0]

        if token_data['usado']:
            return render_template('invitacion.html', error='Esta invitación ya fue utilizada')

        # Verificar expiración
        expira = datetime.fromisoformat(token_data['expira_at'].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expira:
            return render_template('invitacion.html', error='Esta invitación expiró')

        # Obtener datos de la inscripción
        ins_resp = (sb.table('inscripciones')
                    .select('*')
                    .eq('id', token_data['inscripcion_id'])
                    .eq('estado', 'pendiente_companero')
                    .execute())

        if not ins_resp.data:
            return render_template('invitacion.html', error='La inscripción ya no está disponible')

        inscripcion = ins_resp.data[0]

        # Obtener nombre del invitador
        perfil_resp = sb.table('jugadores').select('nombre, apellido').eq('id', inscripcion['jugador_id']).execute()
        nombre_invitador = inscripcion['integrante1']
        if perfil_resp.data:
            p = perfil_resp.data[0]
            nombre_invitador = f"{p['nombre']} {p['apellido']}".strip()

        # Verificar si el usuario está logueado
        jugador_data = _get_jugador_data()

        return render_template('invitacion.html',
                               inscripcion=inscripcion,
                               nombre_invitador=nombre_invitador,
                               token=token,
                               es_logueado=jugador_data is not None,
                               error=None)

    except Exception as e:
        logger.error('Error al cargar invitación por link: %s', e)
        return render_template('invitacion.html', error='Error al cargar la invitación')


# ── API: aceptar invitación por token (POST /api/inscripcion/aceptar-por-token)

@inscripcion_bp.route('/api/inscripcion/aceptar-por-token', methods=['POST'])
def aceptar_por_token():
    """Acepta una invitación usando el token del link compartible."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['jugador', 'admin'])
    if not autenticado:
        return error

    jugador_id = _get_jugador_id()
    if not jugador_id:
        return jsonify({'error': 'No se pudo identificar al jugador'}), 401

    data = request.get_json(silent=True) or {}
    token = data.get('token', '').strip()
    if not token:
        return jsonify({'error': 'Token de invitación requerido'}), 400

    try:
        sb = _get_supabase_admin()

        # Buscar y validar token
        token_resp = (sb.table('invitacion_tokens')
                      .select('inscripcion_id, expira_at, usado')
                      .eq('token', token)
                      .execute())

        if not token_resp.data:
            return jsonify({'error': 'Token de invitación inválido'}), 404

        token_data = token_resp.data[0]

        if token_data['usado']:
            return jsonify({'error': 'Esta invitación ya fue utilizada'}), 410

        expira = datetime.fromisoformat(token_data['expira_at'].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expira:
            return jsonify({'error': 'Esta invitación expiró'}), 410

        # Obtener la inscripción
        ins_resp = (sb.table('inscripciones')
                    .select('*')
                    .eq('id', token_data['inscripcion_id'])
                    .eq('estado', 'pendiente_companero')
                    .execute())

        if not ins_resp.data:
            return jsonify({'error': 'La inscripción ya no está disponible'}), 404

        inscripcion = ins_resp.data[0]

        # No puede aceptar su propia inscripción
        if inscripcion['jugador_id'] == jugador_id:
            return jsonify({'error': 'No podés aceptar tu propia inscripción'}), 400

        # Si la inscripción tiene jugador2_id, verificar que coincida
        if inscripcion.get('jugador2_id') and inscripcion['jugador2_id'] != jugador_id:
            return jsonify({'error': 'Esta invitación es para otro jugador'}), 403

        # Verificar que el jugador no esté ya inscrito en otra pareja
        torneo_id = storage.get_torneo_id()
        error_inscrito = _validar_jugador_no_inscrito(sb, torneo_id, jugador_id)
        if error_inscrito:
            # Permitir si el único match es esta misma inscripción
            check = sb.table('inscripciones').select('id').eq('id', inscripcion['id']).eq('jugador2_id', jugador_id).execute()
            if not check.data:
                return jsonify({'error': error_inscrito}), 409

        # Obtener nombre del jugador que acepta
        perfil_resp = sb.table('jugadores').select('nombre, apellido').eq('id', jugador_id).execute()
        nombre_j2 = ''
        if perfil_resp.data:
            p = perfil_resp.data[0]
            nombre_j2 = f"{p['nombre']} {p['apellido']}".strip()

        # Actualizar inscripción
        sb.table('inscripciones').update({
            'jugador2_id':  jugador_id,
            'integrante2':  nombre_j2,
            'estado':       'confirmado',
        }).eq('id', inscripcion['id']).execute()

        # Marcar token como usado
        sb.table('invitacion_tokens').update({'usado': True}).eq('token', token).execute()

        logger.info('Invitación aceptada por token: inscripcion=%s, jugador2=%s', inscripcion['id'], jugador_id)

        # Auto-asignar en grupos
        updated = sb.table('inscripciones').select('*').eq('id', inscripcion['id']).execute()
        if updated.data:
            try:
                _auto_asignar_en_grupos(updated.data[0])
            except Exception as e:
                logger.error('Error en auto-asignación post-aceptar-token: %s', e, exc_info=True)

        return jsonify({'ok': True, 'mensaje': 'Invitación aceptada. ¡Ya estás inscripto!'})

    except Exception as e:
        logger.error('Error al aceptar invitación por token: %s', e)
        return jsonify({'error': 'Error al aceptar la invitación'}), 500


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
        _expirar_invitaciones_vencidas(sb, torneo_id)
        resp = sb.table('inscripciones').select('*').eq('torneo_id', torneo_id).order('created_at').execute()

        # Enriquecer con nombre de jugador2 si existe
        inscripciones = resp.data or []
        for ins in inscripciones:
            if ins.get('jugador2_id'):
                perfil = sb.table('jugadores').select('nombre, apellido').eq('id', ins['jugador2_id']).execute()
                if perfil.data:
                    p = perfil.data[0]
                    ins['nombre_jugador2'] = f"{p['nombre']} {p['apellido']}".strip()

        return jsonify({'inscripciones': inscripciones, 'total': len(inscripciones)})
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
    if nuevo_estado not in ('confirmado', 'rechazado', 'pendiente', 'pendiente_companero', 'cancelada'):
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
