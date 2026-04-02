"""
Utilidades para manejar JWT tokens en la aplicación.
Reemplaza el sistema de sesiones basado en archivos.
"""

import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify
import logging

logger = logging.getLogger(__name__)


class JWTHandler:
    """Manejador de tokens JWT para autenticación stateless."""
    
    def __init__(self, secret_key, algorithm='HS256', expiration_hours=24):
        """
        Inicializa el manejador de JWT.
        
        Args:
            secret_key: Clave secreta para firmar tokens
            algorithm: Algoritmo de encriptación (default: HS256)
            expiration_hours: Horas de validez del token (default: 24)
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expiration_hours = expiration_hours
    
    def generar_token(self, data=None, expiration_hours=None):
        """
        Genera un nuevo token JWT.

        Args:
            data: Dict con datos adicionales para incluir en el token
            expiration_hours: Override de expiración en horas (usa el default si es None)

        Returns:
            String con el token JWT
        """
        if data is None:
            data = {}

        horas = expiration_hours if expiration_hours is not None else self.expiration_hours
        payload = {
            'exp': datetime.now(tz=timezone.utc) + timedelta(hours=horas),
            'iat': datetime.now(tz=timezone.utc),
            'data': data
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token
    
    def verificar_token(self, token):
        """
        Verifica y decodifica un token JWT.
        
        Args:
            token: String con el token a verificar
            
        Returns:
            Dict con los datos del token si es válido, None si no lo es
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload.get('data', {})
        except jwt.ExpiredSignatureError:
            logger.warning('Token expirado')
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f'Token inválido: {e}')
            return None
    
    def obtener_token_desde_request(self):
        """
        Obtiene el token desde el header Authorization o desde cookies.
        
        Returns:
            String con el token o None si no se encuentra
        """
        # Intentar obtener desde header Authorization
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            return auth_header.split(' ')[1]
        
        # Intentar obtener desde cookies
        token = request.cookies.get('token')
        if token:
            return token
        
        return None
    
    def decorador_requiere_token(self, f):
        """
        Decorador para proteger rutas que requieren autenticación.
        Inyecta 'current_data' en kwargs con los datos del token.
        
        Uso:
            @jwt_handler.decorador_requiere_token
            def mi_ruta(current_data):
                username = current_data.get('username')
                ...
        """
        @wraps(f)
        def decorated(*args, **kwargs):
            token = self.obtener_token_desde_request()
            
            if not token:
                return jsonify({'error': 'Token no proporcionado', 'redirect': '/login'}), 401
            
            data = self.verificar_token(token)
            if data is None:
                return jsonify({'error': 'Token inválido o expirado', 'redirect': '/login'}), 401
            
            # Verificar que esté autenticado
            if not data.get('authenticated'):
                return jsonify({'error': 'No autenticado', 'redirect': '/login'}), 401
            
            # Inyectar datos del token en la función
            kwargs['current_data'] = data
            return f(*args, **kwargs)
        
        return decorated


def crear_respuesta_con_token(jwt_handler, data, mensaje='', status=200):
    """
    Helper para crear respuestas HTTP que incluyen un token JWT.
    
    Args:
        jwt_handler: Instancia de JWTHandler
        data: Dict con datos para incluir en el token
        mensaje: Mensaje de respuesta (opcional)
        status: Código HTTP de respuesta
        
    Returns:
        Tupla (Response, status_code)
    """
    token = jwt_handler.generar_token(data)
    
    response_data = {
        'token': token,
        'data': data
    }
    
    if mensaje:
        response_data['mensaje'] = mensaje
    
    response = jsonify(response_data)
    
    # También establecer como cookie para facilitar acceso desde el navegador
    from flask import current_app
    response.set_cookie('token', token,
                       httponly=True,  # No accesible desde JavaScript
                       samesite='Lax',  # CSRF protection
                       max_age=60*60*2,  # 2 horas
                       secure=not current_app.debug)
    
    return response, status
