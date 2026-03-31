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
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, render_template, make_response, g, redirect, url_for

from core import Pareja, Grupo
from utils.torneo_storage import storage
from utils.api_helpers import verificar_autenticacion_api
from config import FRANJAS_HORARIAS, TIPOS_TORNEO, CATEGORIAS
from utils.input_validation import validar_longitud, MAX_NOMBRE, MAX_TELEFONO, MAX_CATEGORIA

logger = logging.getLogger(__name__)

inscripcion_bp = Blueprint('inscripcion', __name__)


# ── Helpers Supabase ──────────────────────────────────────────────────────────

_supabase_admin_client = None


def _get_supabase_admin():
    """Cliente con SERVICE_ROLE — bypasea RLS. Solo operaciones server-side.

    Singleton: create_client() es costoso (inicializa pool HTTP + TLS).
    Con 1 worker Gunicorn el estado del módulo es estable entre requests.
    """
    global _supabase_admin_client
    if _supabase_admin_client is None:
        from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
        from supabase import create_client
        if not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY no está configurada")
        _supabase_admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _supabase_admin_client


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
    
    grupo_completado = False

    if grupo_destino:
        grupo_destino['parejas'].append(pareja_dict)
        recalcular_score_grupo(grupo_destino)

        # Si el grupo llega a 3 parejas, regenerar la lista de partidos
        if len(grupo_destino['parejas']) == 3:
            grupo_completado = True
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
    resultado['estadisticas'] = recalcular_estadisticas(resultado)
    
    # Regenerar calendario si el grupo quedó completo
    if grupo_completado:
        from ._helpers import regenerar_calendario
        try:
            regenerar_calendario(resultado)
            logger.info('Calendario regenerado exitosamente para grupo_id=%s', grupo_destino['id'])
        except Exception as e:
            logger.error('Error al regenerar calendario post-inscripción: %s', e, exc_info=True)
    
    torneo['resultado_algoritmo'] = resultado
    storage.guardar(torneo)
    logger.info('Inscripción completada y torneo guardado con resultado actualizado')


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


_last_expiracion: float = 0.0
_EXPIRACION_INTERVALO: float = 60.0  # correr la RPC como máximo 1 vez por minuto


def _expirar_invitaciones_vencidas(sb, torneo_id: str) -> None:
    """Expira invitaciones cuyo token ya venció (verificación lazy, rate-limited).

    Las invitaciones vencen cada 48h — correr esta RPC en cada request es innecesario.
    Con 1 worker Gunicorn el estado del módulo es estable y no hay riesgo de race condition.
    """
    global _last_expiracion
    ahora = time.monotonic()
    if ahora - _last_expiracion < _EXPIRACION_INTERVALO:
        return
    _last_expiracion = ahora
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


def _cancelar_inscripcion_pendiente_propia(sb, torneo_id: str, jugador_id: str, excluir_id: str) -> None:
    """Si el jugador tiene una inscripción pendiente_companero propia (como Player A),
    la cancela automáticamente antes de que acepte ser Player B de otro.
    No toca inscripciones confirmadas ni la inscripción que está por aceptar."""
    resp = (sb.table('inscripciones')
            .select('id')
            .eq('torneo_id', torneo_id)
            .eq('jugador_id', jugador_id)
            .eq('estado', 'pendiente_companero')
            .neq('id', excluir_id)
            .execute())
    for ins in (resp.data or []):
        sb.table('inscripciones').delete().eq('id', ins['id']).execute()
        logger.info(
            'Inscripción pendiente previa auto-cancelada: id=%s, jugador=%s (aceptó otra invitación)',
            ins['id'], jugador_id
        )


def _construir_link_invitacion(token: str) -> str:
    """Construye la URL completa del link de invitación."""
    from flask import request as req
    base = req.host_url.rstrip('/')
    return f"{base}/inscripcion/invitar?token={token}"


def _ejecutar_aceptar_invitacion(sb, token: str, jugador_id: str, torneo_id: str) -> tuple[bool, str | None]:
    """Acepta una invitación por token.
    Devuelve (True, None) si tuvo éxito o (False, mensaje_error) si falló.
    Usado tanto desde la ruta GET /inscripcion/invitar (auto-aceptar) como desde el POST API."""
    token_resp = (sb.table('invitacion_tokens')
                  .select('inscripcion_id, expira_at, usado')
                  .eq('token', token)
                  .execute())
    if not token_resp.data:
        return False, 'Token de invitación inválido'

    token_data = token_resp.data[0]
    if token_data['usado']:
        return False, 'Esta invitación ya fue utilizada'

    expira = datetime.fromisoformat(token_data['expira_at'].replace('Z', '+00:00'))
    if datetime.now(timezone.utc) > expira:
        return False, 'Esta invitación expiró'

    ins_resp = (sb.table('inscripciones')
                .select('*')
                .eq('id', token_data['inscripcion_id'])
                .eq('estado', 'pendiente_companero')
                .execute())
    if not ins_resp.data:
        return False, 'La inscripción ya no está disponible'

    inscripcion = ins_resp.data[0]

    if inscripcion['jugador_id'] == jugador_id:
        return False, 'No podés aceptar tu propia inscripción'

    if inscripcion.get('jugador2_id') and inscripcion['jugador2_id'] != jugador_id:
        return False, 'Esta invitación es para otro jugador'

    error_inscrito = _validar_jugador_no_inscrito(sb, torneo_id, jugador_id)
    if error_inscrito:
        check = (sb.table('inscripciones').select('id')
                 .eq('id', inscripcion['id'])
                 .eq('jugador2_id', jugador_id)
                 .execute())
        if not check.data:
            return False, error_inscrito

    perfil_resp = sb.table('jugadores').select('nombre, apellido').eq('id', jugador_id).execute()
    nombre_j2 = ''
    if perfil_resp.data:
        p = perfil_resp.data[0]
        nombre_j2 = f"{p['nombre']} {p['apellido']}".strip()

    # Si Player B tenía su propia inscripción pendiente, cancelarla (primer servidor gana)
    _cancelar_inscripcion_pendiente_propia(sb, torneo_id, jugador_id, excluir_id=inscripcion['id'])

    sb.table('inscripciones').update({
        'jugador2_id': jugador_id,
        'integrante2': nombre_j2,
        'estado':      'confirmado',
    }).eq('id', inscripcion['id']).execute()

    sb.table('invitacion_tokens').update({'usado': True}).eq('token', token).execute()

    logger.info('Invitación aceptada: inscripcion=%s, jugador2=%s', inscripcion['id'], jugador_id)

    updated = sb.table('inscripciones').select('*').eq('id', inscripcion['id']).execute()
    if updated.data:
        try:
            _auto_asignar_en_grupos(updated.data[0])
        except Exception as e:
            logger.error('Error en auto-asignación post-aceptar: %s', e, exc_info=True)

    return True, None


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

    error_len = validar_longitud({
        'Nombre':    (integrante1, MAX_NOMBRE),
        'Teléfono':  (telefono, MAX_TELEFONO),
        'Categoría': (categoria, MAX_CATEGORIA),
    })
    if error_len:
        return jsonify({'error': error_len}), 400
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
        insert_data = {
            'torneo_id':           torneo_id,
            'jugador_id':          jugador_id,
            'integrante1':         integrante1,
            'telefono':            telefono or None,
            'categoria':           categoria,
            'franjas_disponibles': franjas,
            'estado':              'pendiente_companero',
        }
        # jugador2_id e integrante2 solo se incluyen si ya se conoce el compañero
        if jugador2_id:
            insert_data['jugador2_id'] = jugador2_id
            insert_data['integrante2'] = integrante2 or None
        resp = sb.table('inscripciones').insert(insert_data).execute()

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
        logger.error('Error al crear inscripción: %s', error_msg)
        if 'unique' in error_msg.lower() or 'duplicate' in error_msg.lower():
            return jsonify({'error': 'Ya tenés una inscripción para este torneo'}), 409
        # Exponer el error real de Supabase para facilitar el debugging
        return jsonify({'error': f'Error al guardar la inscripción: {error_msg}'}), 500


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

        # Si no encontró como creador, buscar como jugador2 (invitado que ya aceptó)
        if not inscripcion:
            resp2 = sb.table('inscripciones').select('*').eq('torneo_id', torneo_id).eq('jugador2_id', jugador_id).execute()
            inscripcion = resp2.data[0] if resp2.data else None

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


# ── API: estado completo de inscripción (GET /api/inscripcion/estado) ─────────

@inscripcion_bp.route('/api/inscripcion/estado', methods=['GET'])
def estado_inscripcion():
    """Devuelve en una sola llamada la inscripción propia y las invitaciones pendientes.
    Reemplaza los dos endpoints separados para evitar doble round-trip y doble RPC."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['jugador', 'admin'])
    if not autenticado:
        return error

    jugador_id = _get_jugador_id()
    if not jugador_id:
        return jsonify({'error': 'No se pudo identificar al jugador'}), 401

    torneo_id = storage.get_torneo_id()
    try:
        sb = _get_supabase_admin()
        _expirar_invitaciones_vencidas(sb, torneo_id)  # Una sola vez por page load

        # ── Inscripción propia (como Player A) ───────────────────────────────
        inscripcion = None
        resp = (sb.table('inscripciones')
                .select('*')
                .eq('torneo_id', torneo_id)
                .eq('jugador_id', jugador_id)
                .execute())
        if resp.data:
            inscripcion = resp.data[0]
            if inscripcion.get('estado') == 'pendiente_companero':
                token_resp = (sb.table('invitacion_tokens')
                              .select('token')
                              .eq('inscripcion_id', inscripcion['id'])
                              .eq('usado', False)
                              .order('created_at', desc=True)
                              .limit(1)
                              .execute())
                if token_resp.data:
                    inscripcion['invitacion_link'] = _construir_link_invitacion(token_resp.data[0]['token'])

        # ── Inscripción confirmada donde soy Player B (ya acepté) ───────────
        if not inscripcion:
            resp_b = (sb.table('inscripciones')
                      .select('*')
                      .eq('torneo_id', torneo_id)
                      .eq('jugador2_id', jugador_id)
                      .neq('estado', 'pendiente_companero')
                      .execute())
            if resp_b.data:
                inscripcion = resp_b.data[0]

        # ── Invitaciones recibidas (como Player B) ───────────────────────────
        inv_resp = (sb.table('inscripciones')
                    .select('id, integrante1, categoria, franjas_disponibles, jugador_id, created_at')
                    .eq('torneo_id', torneo_id)
                    .eq('jugador2_id', jugador_id)
                    .eq('estado', 'pendiente_companero')
                    .execute())

        # Construir invitaciones con 2 queries batch en lugar de 2×N queries individuales
        inv_list = inv_resp.data or []
        invitaciones = []
        if inv_list:
            # Una sola query para todos los perfiles de invitadores
            jugador_ids = list({ins['jugador_id'] for ins in inv_list})
            perfiles_resp = (sb.table('jugadores')
                             .select('id, nombre, apellido')
                             .in_('id', jugador_ids)
                             .execute())
            perfiles_map = {p['id']: p for p in (perfiles_resp.data or [])}

            # Una sola query para todos los tokens de estas inscripciones
            inscripcion_ids = [ins['id'] for ins in inv_list]
            tokens_resp = (sb.table('invitacion_tokens')
                           .select('inscripcion_id, expira_at')
                           .in_('inscripcion_id', inscripcion_ids)
                           .eq('usado', False)
                           .order('created_at', desc=True)
                           .execute())
            # Tomar el token más reciente por inscripción (order desc ya viene del query)
            tokens_map: dict[str, str] = {}
            for t in (tokens_resp.data or []):
                if t['inscripcion_id'] not in tokens_map:
                    tokens_map[t['inscripcion_id']] = t['expira_at']

            for ins in inv_list:
                perfil = perfiles_map.get(ins['jugador_id'])
                nombre_invitador = (
                    f"{perfil['nombre']} {perfil['apellido']}".strip()
                    if perfil else ins['integrante1']
                )
                invitaciones.append({
                    'inscripcion_id':   ins['id'],
                    'nombre_invitador': nombre_invitador,
                    'categoria':        ins['categoria'],
                    'franjas':          ins['franjas_disponibles'],
                    'created_at':       ins['created_at'],
                    'expira_at':        tokens_map.get(ins['id']),
                })

        return jsonify({'inscripcion': inscripcion, 'invitaciones': invitaciones})

    except Exception as e:
        logger.error('Error al obtener estado de inscripción: %s', e)
        return jsonify({'inscripcion': None, 'invitaciones': []})


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

        # Si Player B tenía su propia inscripción pendiente, cancelarla (primer servidor gana)
        _cancelar_inscripcion_pendiente_propia(sb, torneo_id, jugador_id, excluir_id=inscripcion_id)

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
    """Procesa el link de invitación.
    - Jugador logueado → acepta automáticamente y redirige a /inscripcion.
    - No logueado → muestra la página con opciones de login/registro."""
    token = request.args.get('token', '').strip()
    if not token:
        return render_template('invitacion.html', error='Link de invitación inválido')

    jugador_data = _get_jugador_data()

    if jugador_data:
        # Ya autenticado: aceptar directamente sin pasar por el template
        jugador_id = jugador_data.get('user_id')
        if not jugador_id:
            return render_template('invitacion.html', error='No se pudo identificar al jugador')
        try:
            sb = _get_supabase_admin()
            torneo_id = storage.get_torneo_id()
            ok, error_msg = _ejecutar_aceptar_invitacion(sb, token, jugador_id, torneo_id)
            if ok:
                return redirect(url_for('inscripcion.pagina_inscripcion'))
            return render_template('invitacion.html', error=error_msg)
        except Exception as e:
            logger.error('Error al auto-aceptar invitación: %s', e)
            return render_template('invitacion.html', error='Error al procesar la invitación')

    # No autenticado: mostrar detalles + opciones de login/registro
    try:
        sb = _get_supabase_admin()

        token_resp = (sb.table('invitacion_tokens')
                      .select('inscripcion_id, expira_at, usado')
                      .eq('token', token)
                      .execute())
        if not token_resp.data:
            return render_template('invitacion.html', error='Link de invitación inválido o expirado')

        token_data = token_resp.data[0]
        if token_data['usado']:
            return render_template('invitacion.html', error='Esta invitación ya fue utilizada')

        expira = datetime.fromisoformat(token_data['expira_at'].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expira:
            return render_template('invitacion.html', error='Esta invitación expiró')

        ins_resp = (sb.table('inscripciones')
                    .select('*')
                    .eq('id', token_data['inscripcion_id'])
                    .eq('estado', 'pendiente_companero')
                    .execute())
        if not ins_resp.data:
            return render_template('invitacion.html', error='La inscripción ya no está disponible')

        inscripcion = ins_resp.data[0]

        perfil_resp = sb.table('jugadores').select('nombre, apellido').eq('id', inscripcion['jugador_id']).execute()
        nombre_invitador = inscripcion['integrante1']
        if perfil_resp.data:
            p = perfil_resp.data[0]
            nombre_invitador = f"{p['nombre']} {p['apellido']}".strip()

        return render_template('invitacion.html',
                               inscripcion=inscripcion,
                               nombre_invitador=nombre_invitador,
                               token=token,
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
        torneo_id = storage.get_torneo_id()
        ok, error_msg = _ejecutar_aceptar_invitacion(sb, token, jugador_id, torneo_id)
        if ok:
            return jsonify({'ok': True, 'mensaje': 'Invitación aceptada. ¡Ya estás inscripto!'})
        code = 409 if 'ya tiene una inscripción' in (error_msg or '') else 400
        return jsonify({'error': error_msg}), code
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

        # Enriquecer con nombre de jugador2 — una sola query batch para todos
        inscripciones = resp.data or []
        jugador2_ids = list({ins['jugador2_id'] for ins in inscripciones if ins.get('jugador2_id')})
        if jugador2_ids:
            perfiles = sb.table('jugadores').select('id, nombre, apellido').in_('id', jugador2_ids).execute()
            perfiles_map = {p['id']: p for p in (perfiles.data or [])}
            for ins in inscripciones:
                perfil = perfiles_map.get(ins.get('jugador2_id'))
                if perfil:
                    ins['nombre_jugador2'] = f"{perfil['nombre']} {perfil['apellido']}".strip()

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
