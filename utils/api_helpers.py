"""
Helper functions para trabajar con JWT en las rutas de la API.
"""

from flask import current_app, jsonify, make_response, request
from utils.torneo_storage import storage
import logging

logger = logging.getLogger(__name__)


def verificar_autenticacion_api():
    """
    Verifica que la petición a la API esté autenticada.
    
    Returns:
        Tuple (authenticated: bool, error_response: Response|None)
        Si authenticated es False, error_response contiene la respuesta de error
    """
    jwt_handler = current_app.jwt_handler
    token = jwt_handler.obtener_token_desde_request()
    
    if not token:
        return False, jsonify({'error': 'No autenticado', 'redirect': '/login'}), 401
    
    data = jwt_handler.verificar_token(token)
    if not data or not data.get('authenticated'):
        return False, jsonify({'error': 'Sesión inválida o expirada', 'redirect': '/login'}), 401
    
    return True, None


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
