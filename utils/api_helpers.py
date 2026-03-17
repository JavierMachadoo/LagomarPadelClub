"""
Helper functions para trabajar con JWT en las rutas de la API.
"""

from flask import current_app, jsonify, make_response, request
from utils.torneo_storage import storage
import logging

logger = logging.getLogger(__name__)


def _verificar_supabase_jwt(sb_token: str):
    """
    Verifica un JWT de Supabase Auth llamando a get_user().
    Devuelve el objeto user si es válido, None en caso contrario.

    Nota: usamos el cliente con ANON_KEY para verificar — get_user() acepta
    el access_token del jugador directamente sin necesitar service_role.
    """
    try:
        from config.settings import SUPABASE_URL, SUPABASE_ANON_KEY
        from supabase import create_client
        sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        response = sb.auth.get_user(sb_token)
        return response.user if response and response.user else None
    except Exception as e:
        logger.debug("Supabase JWT inválido: %s", e)
        return None


def verificar_autenticacion_api(roles_permitidos=None):
    """
    Verifica que la petición a la API esté autenticada.

    Acepta dos tipos de sesión:
      - Cookie 'token'    → JWT custom del admin
      - Cookie 'sb_token' → JWT de Supabase (jugador registrado)

    Args:
        roles_permitidos: lista de roles aceptados, p.ej. ['admin'] o ['admin', 'jugador'].
                          Si es None, por defecto se restringe a ['admin'].

    Returns:
        Tuple (authenticated: bool, error_response: Response | tuple[Response, int] | None)
        donde `error_response` puede ser una Response directa o una tupla (Response, status_code).
    """
    # Si no se especifican roles, por seguridad asumir solo-admin
    if roles_permitidos is None:
        roles_permitidos = ['admin']

    # ── 1. Intentar con el JWT custom del admin ──────────────────────────────
    jwt_handler = current_app.jwt_handler
    admin_token = jwt_handler.obtener_token_desde_request()

    if admin_token:
        data = jwt_handler.verificar_token(admin_token)
        if data and data.get('authenticated'):
            role = data.get('role', 'admin')
            if role in roles_permitidos:
                return True, None

    # ── 2. Intentar con el JWT de Supabase (jugador) ─────────────────────────
    sb_token = request.cookies.get('sb_token')

    if sb_token:
        user = _verificar_supabase_jwt(sb_token)
        if user:
            if 'jugador' in roles_permitidos:
                return True, None
            # Token válido pero rol no permitido (p.ej. ruta solo-admin)
            return False, (jsonify({'error': 'Acceso restringido a administradores'}), 403)

    # ── 3. Sin sesión válida ──────────────────────────────────────────────────
    return False, (jsonify({'error': 'No autenticado', 'redirect': '/login'}), 401)


def obtener_datos_desde_token():
    """
    Obtiene los datos del torneo desde storage.
    El token JWT solo valida la sesión, no almacena datos.
    
    Returns:
        Dict con los datos del torneo (parejas, resultado_algoritmo, num_canchas)
    """
    # Siempre cargar desde storage - el token solo valida sesión
    torneo = storage.cargar()
    return {
        'parejas': torneo.get('parejas', []),
        'resultado_algoritmo': torneo.get('resultado_algoritmo'),
        'num_canchas': torneo.get('num_canchas', 2)
    }


def actualizar_datos_en_token(datos_actualizados):
    """
    Actualiza datos específicos en el token JWT.
    
    Args:
        datos_actualizados: Dict con los datos a actualizar (puede ser parcial)
        
    Returns:
        Nuevo token JWT con los datos actualizados
    """
    # Obtener datos actuales
    datos_actuales = obtener_datos_desde_token()
    
    # Fusionar con los nuevos
    datos_actuales.update(datos_actualizados)
    
    # Generar nuevo token
    jwt_handler = current_app.jwt_handler
    return jwt_handler.generar_token(datos_actuales)


def crear_respuesta_con_token_actualizado(data_respuesta, datos_token=None, status=200):
    """
    Crea una respuesta JSON que incluye un token JWT actualizado.
    El token solo contiene datos mínimos de sesión, no datos del torneo.
    
    Args:
        data_respuesta: Dict con los datos a devolver en el JSON
        datos_token: Dict con datos para actualizar en el token (opcional, ignorado)
        status: Código HTTP de respuesta
        
    Returns:
        Response object con el token actualizado en cookies
    """
    jwt_handler = current_app.jwt_handler
    
    # Token mínimo - mantiene autenticación
    import time
    token_data = {
        'authenticated': True,
        'session_id': 'torneo_session',
        'timestamp': int(time.time())
    }
    
    # Generar nuevo token
    nuevo_token = jwt_handler.generar_token(token_data)
    
    # Incluir el token en el cuerpo de la respuesta para JavaScript
    if isinstance(data_respuesta, dict):
        data_respuesta_con_token = data_respuesta.copy()
        data_respuesta_con_token['token'] = nuevo_token
    else:
        data_respuesta_con_token = data_respuesta
    
    # Crear respuesta
    response = make_response(jsonify(data_respuesta_con_token), status)
    
    # Establecer token en cookie (httponly para seguridad)
    response.set_cookie('token', nuevo_token,
                       httponly=True,
                       samesite='Lax',
                       max_age=60*60*2)  # 2 horas
    
    return response


def sincronizar_con_storage_y_token(datos):
    """
    Guarda datos en storage Y actualiza el token.
    Helper para mantener consistencia entre storage y JWT.

    Realiza un MERGE con el torneo existente para no perder campos
    como tipo_torneo, nombre, fecha_creacion, etc. que no forman
    parte del dict parcial recibido.

    Args:
        datos: Dict con datos a guardar (puede ser parcial, ej: solo parejas + resultado)
    """
    # Cargar torneo completo y fusionar — así se preservan tipo_torneo y metadata
    torneo_actual = storage.cargar()
    torneo_actual.update(datos)
    storage.guardar(torneo_actual)

    # Los datos del token se actualizarán en la respuesta
    logger.info("Datos sincronizados con storage")
