"""
Aplicación Flask para gestión de torneos de pádel.
Genera grupos optimizados según categorías y disponibilidad horaria.
"""

from flask import Flask, render_template, request, redirect, url_for, flash, make_response
import os
import logging

from config import (
    SECRET_KEY, 
    CATEGORIAS, 
    FRANJAS_HORARIAS, 
    EMOJI_CATEGORIA, 
    COLORES_CATEGORIA,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    TIPOS_TORNEO
)
from config.settings import BASE_DIR, DEBUG
from api import api_bp
from api.routes.finales import finales_bp
from utils.torneo_storage import storage
from utils.jwt_handler import JWTHandler


def crear_app():
    """Factory para crear y configurar la aplicación Flask."""
    # Configure logging - solo consola, sin archivo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )
    
    app = Flask(__name__, 
                template_folder='web/templates',
                static_folder='web/static')
    
    # Configuración básica
    app.secret_key = SECRET_KEY
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    
    # Inicializar JWT handler con expiración de 2 horas (seguridad)
    jwt_handler = JWTHandler(SECRET_KEY, expiration_hours=2)
    app.jwt_handler = jwt_handler  # Hacer accesible en toda la app
    
    # Registrar blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(finales_bp)
    
    # Helper para obtener datos del token o storage
    def obtener_datos_torneo():
        """Obtiene datos del torneo desde storage.
        El token JWT solo valida la sesión, no almacena datos."""
        # Siempre cargar desde storage
        torneo = storage.cargar()
        return {
            'parejas': torneo.get('parejas', []),
            'resultado_algoritmo': torneo.get('resultado_algoritmo'),
            'num_canchas': torneo.get('num_canchas', 2)
        }
    
    # Middleware: Verificar autenticación
    @app.before_request
    def verificar_autenticacion():
        """Verifica que el usuario esté autenticado antes de acceder a rutas protegidas."""
        # Rutas públicas que no requieren autenticación
        rutas_publicas = ['/login', '/static/', '/_health']
        
        # Permitir acceso a rutas públicas
        if any(request.path.startswith(ruta) for ruta in rutas_publicas):
            return
        
        # Verificar token JWT
        token = jwt_handler.obtener_token_desde_request()
        
        if not token:
            return redirect(url_for('login'))
        
        # Verificar que el token sea válido y contenga authenticated=True
        data = jwt_handler.verificar_token(token)
        if not data or not data.get('authenticated'):
            return redirect(url_for('login'))
    
    # Rutas de autenticación
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Página de login."""
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            # Verificar credenciales
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                # Crear token con autenticación exitosa
                import time
                data = {
                    'authenticated': True,
                    'username': username,
                    'timestamp': int(time.time())
                }
                token = jwt_handler.generar_token(data)
                
                response = make_response(redirect(url_for('inicio')))
                response.set_cookie('token', token,
                                  httponly=True,
                                  samesite='Lax',
                                  max_age=60*60*2)  # 2 horas
                
                flash('¡Bienvenido!', 'success')
                return response
            else:
                flash('Usuario o contraseña incorrectos', 'error')
        
        return render_template('login.html')
    
    @app.route('/logout')
    def logout():
        """Cerrar sesión."""
        response = make_response(redirect(url_for('login')))
        response.set_cookie('token', '', expires=0)
        flash('Sesión cerrada', 'info')
        return response
    
    # Rutas principales
    @app.route('/')
    def inicio():
        """Página de inicio - Carga de datos."""
        datos = obtener_datos_torneo()
        parejas = datos.get('parejas', [])
        resultado = datos.get('resultado_algoritmo')
        torneo = storage.cargar()
        
        # Enriquecer parejas con información de asignación
        parejas_enriquecidas = []
        for pareja in parejas:
            pareja_info = pareja.copy()
            pareja_info['grupo_asignado'] = None
            pareja_info['franja_asignada'] = None
            pareja_info['esta_asignada'] = False
            pareja_info['fuera_de_horario'] = False
            
            # Si hay resultado del algoritmo, buscar asignación
            if resultado:
                for categoria, grupos in resultado.get('grupos_por_categoria', {}).items():
                    for grupo in grupos:
                        for p in grupo.get('parejas', []):
                            if p['id'] == pareja['id']:
                                pareja_info['grupo_asignado'] = grupo['id']
                                pareja_info['franja_asignada'] = grupo.get('franja_horaria')
                                pareja_info['esta_asignada'] = True
                                
                                # Verificar si está fuera de horario
                                franja_asignada = grupo.get('franja_horaria')
                                if franja_asignada:
                                    franjas_disponibles = pareja.get('franjas_disponibles', [])
                                    if franja_asignada not in franjas_disponibles:
                                        pareja_info['fuera_de_horario'] = True
                                break
                        if pareja_info['esta_asignada']:
                            break
                    if pareja_info['esta_asignada']:
                        break
            
            parejas_enriquecidas.append(pareja_info)
        
        # Ordenar parejas por categoría
        orden_categorias = ['Cuarta', 'Quinta', 'Sexta', 'Séptima', 'Tercera']
        parejas_ordenadas = sorted(parejas_enriquecidas, 
                                  key=lambda p: orden_categorias.index(p.get('categoria', 'Cuarta')) if p.get('categoria') in orden_categorias else 99)

        tipo_torneo = torneo.get('tipo_torneo', 'fin1')
        categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)

        response = make_response(render_template('inicio.html', 
                             parejas=parejas_ordenadas,
                             resultado=resultado,
                             torneo=torneo,
                             categorias=categorias_torneo,
                             franjas=FRANJAS_HORARIAS,
                             tipo_torneo=tipo_torneo,
                             tipos_torneo=TIPOS_TORNEO))
        
        return response
    
    @app.route('/resultados')
    def resultados():
        """Página de resultados - Visualización de grupos generados."""
        datos = obtener_datos_torneo()
        resultado = datos.get('resultado_algoritmo')
        
        if not resultado:
            flash('Primero debes generar los grupos', 'warning')
            return redirect(url_for('inicio'))
        
        torneo = storage.cargar()
        tipo_torneo = torneo.get('tipo_torneo', 'fin1')
        categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)
        
        response = make_response(render_template('resultados.html', 
                             resultado=resultado,
                             categorias=categorias_torneo,
                             colores=COLORES_CATEGORIA,
                             emojis=EMOJI_CATEGORIA,
                             torneo=torneo,
                             tipo_torneo=tipo_torneo))
        
        return response
    
    @app.route('/finales')
    def finales():
        """Página de visualización de finales y calendario del domingo."""
        datos = obtener_datos_torneo()
        resultado = datos.get('resultado_algoritmo')
        
        if not resultado:
            flash('Primero debes generar los grupos', 'warning')
            return redirect(url_for('inicio'))
        
        torneo = storage.cargar()
        fixtures = torneo.get('fixtures_finales', {})
        tipo_torneo = torneo.get('tipo_torneo', 'fin1')
        categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)
        
        response = make_response(render_template('finales.html',
                             fixtures=fixtures,
                             categorias=categorias_torneo,
                             colores=COLORES_CATEGORIA,
                             emojis=EMOJI_CATEGORIA,
                             resultado=resultado,
                             torneo=torneo,
                             tipo_torneo=tipo_torneo))
        
        return response
    
    return app


def _registrar_extras(app):
    """Registra health check y manejadores de error globales."""

    @app.route('/_health')
    def health_check():
        """Endpoint para keep-alive (UptimeRobot, Freshping, etc).
        No requiere autenticación."""
        from flask import jsonify
        return jsonify({'status': 'ok'})

    @app.errorhandler(404)
    def not_found(e):
        from flask import request, jsonify
        # Si es llamada de API devolver JSON; si es página devolver HTML
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': 'Ruta no encontrada'}), 404
        return render_template('base.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import request, jsonify
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': 'Error interno del servidor'}), 500
        return render_template('base.html'), 500


# Instancia a nivel de módulo para que gunicorn pueda encontrarla
# (necesario para el deploy en Render/Railway)
app = crear_app()
_registrar_extras(app)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=DEBUG, host='0.0.0.0', port=port)
