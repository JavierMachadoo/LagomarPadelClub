"""
Aplicación Flask para gestión de torneos de pádel.
Genera grupos optimizados según categorías y disponibilidad horaria.
"""

from flask import Flask, render_template, request, redirect, url_for, flash, make_response, g, session
import os
import logging
import time

logger = logging.getLogger(__name__)

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
from config.settings import BASE_DIR, DEBUG, SUPABASE_SERVICE_ROLE_KEY
from api import api_bp, grupos_bp, resultados_bp, calendario_bp
from api.routes.finales import finales_bp
from api.routes.auth_jugador import auth_jugador_bp
from api.routes.inscripcion import inscripcion_bp
from api.routes.historial import historial_bp, _cargar_archivado
from utils.torneo_storage import storage
from utils.jwt_handler import JWTHandler
from core.fixture_finales_generator import GeneradorFixtureFinales
from utils.calendario_finales_builder import GeneradorCalendarioFinales
from core.models import Grupo


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
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB — protección DoS en uploads
    
    # Rate limiting — protección contra fuerza bruta
    from utils.rate_limiter import limiter
    limiter.init_app(app)

    # Inicializar JWT handler con expiración de 2 horas (seguridad)
    jwt_handler = JWTHandler(SECRET_KEY, expiration_hours=2)
    app.jwt_handler = jwt_handler  # Hacer accesible en toda la app
    
    # Registrar blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(grupos_bp)
    app.register_blueprint(resultados_bp)
    app.register_blueprint(calendario_bp)
    app.register_blueprint(finales_bp)
    app.register_blueprint(auth_jugador_bp)
    app.register_blueprint(inscripcion_bp)
    app.register_blueprint(historial_bp)
    
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
    
    # Context processor: inyecta es_admin, torneo_tiene_datos y fase_torneo en todos los templates
    @app.context_processor
    def inject_globals():
        torneo = storage.cargar()
        tiene_datos = bool(torneo.get('resultado_algoritmo'))
        fase = torneo.get('fase', 'inscripcion')
        return dict(
            es_admin=getattr(g, 'es_admin', False),
            es_autenticado=getattr(g, 'es_autenticado', False),
            es_jugador=getattr(g, 'es_jugador', False),
            torneo_tiene_datos=tiene_datos,
            fase_torneo=fase,
            proximo_torneo=torneo.get('proximo_torneo'),
        )

    # Middleware: Verificar autenticación
    @app.before_request
    def verificar_autenticacion():
        """Verifica autenticación. Siempre resuelve g.es_admin; solo bloquea rutas privadas."""
        # Siempre intentar determinar si el usuario es admin (para navbar condicional)
        g.es_autenticado = False
        g.es_admin = False
        g.es_jugador = False
        token = jwt_handler.obtener_token_desde_request()
        if token:
            data = jwt_handler.verificar_token(token)
            if data and data.get('authenticated'):
                g.es_autenticado = True
                # Compatibilidad: tokens previos sin campo 'role' eran siempre admin
                role = data.get('role')
                if role is None or role == 'admin':
                    g.es_admin = True
                elif role == 'jugador':
                    g.es_jugador = True
        # Rutas públicas: no requieren autenticación
        rutas_publicas_prefijos = ['/login', '/logout', '/static/', '/_health', '/grupos', '/cuadro', '/calendario', '/api/auth/', '/registro', '/auth/', '/inscripcion', '/api/inscripcion', '/api/jugadores/buscar', '/api/admin/inscripciones', '/torneos']
        if request.path == '/' or any(request.path.startswith(r) for r in rutas_publicas_prefijos):
            return

        # Rutas privadas: redirigir si no es admin
        if not g.es_admin:
            return redirect(url_for('login'))
    
    # Rutas de autenticación
    @app.route('/login', methods=['GET'])
    def login():
        """Página de login — el POST lo maneja /api/auth/login."""
        return render_template('login.html')
    
    @app.route('/logout')
    def logout():
        """Cerrar sesión — limpia cookies de admin y jugador."""
        response = make_response(redirect(url_for('login')))
        response.set_cookie('token', '', expires=0, secure=not app.debug)
        response.set_cookie('sb_token', '', expires=0, secure=not app.debug)
        return response
    
    # Landing pública
    @app.route('/')
    def inicio():
        """Página de inicio pública — información del torneo y acceso."""
        torneo = storage.cargar()
        resultado = torneo.get('resultado_algoritmo')
        tipo_torneo = torneo.get('tipo_torneo', 'fin1')
        categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)
        return make_response(render_template('inicio.html',
                             torneo=torneo,
                             resultado=resultado,
                             categorias=categorias_torneo,
                             emojis=EMOJI_CATEGORIA,
                             tipo_torneo=tipo_torneo))

    # Panel de administración (antes era /)
    @app.route('/admin')
    def admin_panel():
        """Panel de administración - Carga de datos."""
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
        orden_categorias = ['Tercera', 'Cuarta', 'Quinta', 'Sexta', 'Séptima']
        parejas_ordenadas = sorted(parejas_enriquecidas, 
                                  key=lambda p: orden_categorias.index(p.get('categoria', 'Cuarta')) if p.get('categoria') in orden_categorias else 99)

        tipo_torneo = torneo.get('tipo_torneo', 'fin1')
        categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)

        response = make_response(render_template('homePanel.html',
                             parejas=parejas_ordenadas,
                             resultado=resultado,
                             torneo=torneo,
                             categorias=categorias_torneo,
                             franjas=FRANJAS_HORARIAS,
                             tipo_torneo=tipo_torneo,
                             tipos_torneo=TIPOS_TORNEO))
        
        return response
    
    @app.route('/dashboard')
    def dashboard():
        """Dashboard - Visualización de grupos generados."""
        datos = obtener_datos_torneo()
        resultado = datos.get('resultado_algoritmo')

        if not resultado:
            flash('Primero debes generar los grupos', 'warning')
            return redirect(url_for('admin_panel'))

        torneo = storage.cargar()
        tipo_torneo = torneo.get('tipo_torneo', 'fin1')
        categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)
        fixtures = torneo.get('fixtures_finales', {})

        response = make_response(render_template('dashboard.html',
                             resultado=resultado,
                             categorias=categorias_torneo,
                             colores=COLORES_CATEGORIA,
                             emojis=EMOJI_CATEGORIA,
                             torneo=torneo,
                             tipo_torneo=tipo_torneo,
                             fixtures=fixtures))

        return response

    @app.route('/finales')
    def finales():
        """Página de visualización de finales y calendario del domingo."""
        datos = obtener_datos_torneo()
        resultado = datos.get('resultado_algoritmo')
        
        if not resultado:
            flash('Primero debes generar los grupos', 'warning')
            return redirect(url_for('admin_panel'))
        
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
    
    def _build_calendario_index(calendario: dict) -> dict:
        """Devuelve {partido_id: {cancha, hora_inicio}} a partir del calendario persistido."""
        if not calendario:
            return {}
        index = {}
        for lista in [calendario.get('cancha_1', []), calendario.get('cancha_2', [])]:
            for p in lista:
                index[p['partido_id']] = {'cancha': p['cancha'], 'hora_inicio': p['hora_inicio']}
        return index

    def _build_franjas_finales(calendario: dict) -> list:
        """Convierte el calendario persistido en lista de (hora, partido_c1, partido_c2)
        para renderizar el panel de finales en Jinja2 con la misma estética que grupos."""
        if not calendario:
            return []
        por_hora = {}
        for p in calendario.get('cancha_1', []):
            por_hora.setdefault(p['hora_inicio'], [None, None])[0] = p
        for p in calendario.get('cancha_2', []):
            por_hora.setdefault(p['hora_inicio'], [None, None])[1] = p
        return [(h, slots[0], slots[1]) for h, slots in sorted(por_hora.items())]

    # Rutas públicas (sin login)
    @app.route('/grupos')
    def grupos_publico():
        """Vista pública de grupos — sin teléfonos ni franjas de disponibilidad.

        Solo muestra datos cuando fase='torneo'. En fase 'inscripcion' u 'organizando'
        muestra pantalla de "torneo en organización".
        """
        torneo = storage.cargar()
        fase = torneo.get('fase', 'inscripcion')

        # Estado espera: mostrar datos del último torneo archivado
        if fase == 'espera':
            ultimo_id = torneo.get('ultimo_torneo_id')
            if ultimo_id:
                archivado = _cargar_archivado(ultimo_id)
                if archivado:
                    datos_blob = archivado.get('datos_blob') or {}
                    resultado = datos_blob.get('resultado_algoritmo')
                    fixtures = datos_blob.get('fixtures_finales', {})
                    cal_arch = datos_blob.get('calendario_finales', {})
                    tipo_torneo = datos_blob.get('tipo_torneo', 'fin1')
                    categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)
                    return make_response(render_template('grupos_publico.html',
                                         resultado=resultado,
                                         fixtures=fixtures,
                                         calendario_index=_build_calendario_index(cal_arch),
                                         categorias=categorias_torneo,
                                         colores=COLORES_CATEGORIA,
                                         emojis=EMOJI_CATEGORIA,
                                         torneo=torneo,
                                         tipo_torneo=tipo_torneo,
                                         es_ultimo_torneo=True,
                                         nombre_ultimo_torneo=archivado.get('nombre', '')))
            return make_response(render_template('organizando.html', torneo=torneo))

        if fase != 'torneo':
            return make_response(render_template('organizando.html', torneo=torneo))

        datos = obtener_datos_torneo()
        resultado = datos.get('resultado_algoritmo')
        fixtures = torneo.get('fixtures_finales', {})
        tipo_torneo = torneo.get('tipo_torneo', 'fin1')
        categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)

        # Auto-generar fixtures para categorías que tengan grupos pero no tengan fixture
        if resultado:
            grupos_por_cat = resultado.get('grupos_por_categoria', {})
            guardado = False
            for cat in categorias_torneo:
                if cat not in fixtures and cat in grupos_por_cat:
                    grupos_data = grupos_por_cat[cat]
                    grupos = [Grupo.from_dict(g) for g in grupos_data]
                    fixture = GeneradorFixtureFinales.generar_fixture(cat, grupos)
                    if fixture:
                        fixtures[cat] = fixture.to_dict()
                        guardado = True
            if guardado:
                torneo['fixtures_finales'] = fixtures
                torneo['calendario_finales'] = GeneradorCalendarioFinales.asignar_horarios(fixtures)
                storage.guardar(torneo)

        calendario_finales = torneo.get('calendario_finales', {})
        return make_response(render_template('grupos_publico.html',
                             resultado=resultado,
                             fixtures=fixtures,
                             calendario_index=_build_calendario_index(calendario_finales),
                             categorias=categorias_torneo,
                             colores=COLORES_CATEGORIA,
                             emojis=EMOJI_CATEGORIA,
                             torneo=torneo,
                             tipo_torneo=tipo_torneo))

    @app.route('/calendario')
    def calendario_publico():
        """Vista pública del calendario de partidos — sin controles de admin.

        Visible cuando fase='torneo' o fase='espera' (muestra último torneo).
        """
        torneo = storage.cargar()
        fase = torneo.get('fase', 'inscripcion')

        # Estado espera: mostrar calendario del último torneo archivado
        if fase == 'espera':
            ultimo_id = torneo.get('ultimo_torneo_id')
            if ultimo_id:
                archivado = _cargar_archivado(ultimo_id)
                if archivado:
                    datos_blob = archivado.get('datos_blob') or {}
                    resultado = datos_blob.get('resultado_algoritmo')
                    tipo_torneo = datos_blob.get('tipo_torneo', 'fin1')
                    categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)
                    cal_arch = datos_blob.get('calendario_finales', {})
                    return make_response(render_template('calendario_publico.html',
                                         resultado=resultado,
                                         categorias=categorias_torneo,
                                         colores=COLORES_CATEGORIA,
                                         emojis=EMOJI_CATEGORIA,
                                         torneo=torneo,
                                         tipo_torneo=tipo_torneo,
                                         franjas_finales=_build_franjas_finales(cal_arch),
                                         es_ultimo_torneo=True,
                                         nombre_ultimo_torneo=archivado.get('nombre', '')))
            return make_response(render_template('organizando.html', torneo=torneo))

        if fase != 'torneo':
            return make_response(render_template('organizando.html', torneo=torneo))

        resultado = torneo.get('resultado_algoritmo')
        tipo_torneo = torneo.get('tipo_torneo', 'fin1')
        categorias_torneo = TIPOS_TORNEO.get(tipo_torneo, CATEGORIAS)
        calendario_finales = torneo.get('calendario_finales', {})

        return make_response(render_template('calendario_publico.html',
                             resultado=resultado,
                             categorias=categorias_torneo,
                             colores=COLORES_CATEGORIA,
                             emojis=EMOJI_CATEGORIA,
                             torneo=torneo,
                             tipo_torneo=tipo_torneo,
                             franjas_finales=_build_franjas_finales(calendario_finales)))

    @app.route('/cuadro')
    def cuadro_publico():
        """Redirect legacy /cuadro → /grupos (bracket ahora integrado en grupos)."""
        return redirect(url_for('grupos_publico'), code=301)

    @app.route('/registro')
    def registro():
        """Página de registro para jugadores."""
        return make_response(render_template('registro.html'))

    @app.route('/auth/callback')
    def oauth_callback():
        """
        Callback del flujo OAuth (Google).

        Supabase redirige aquí con un `code` después de que el usuario autenticó
        con Google. Intercambiamos ese code + el PKCE verifier guardado en sesión
        por un access_token y seteamos la cookie sb_token.
        """
        from config.settings import SUPABASE_URL, SUPABASE_ANON_KEY
        from supabase import create_client

        code     = request.args.get('code')
        verifier = session.pop('pkce_verifier', None)

        if not code or not verifier:
            flash('Error en la autenticación con Google. Intenta de nuevo.', 'error')
            return redirect(url_for('login'))

        try:
            sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
            auth_response = sb.auth.exchange_code_for_session({
                'auth_code':     code,
                'code_verifier': verifier,
            })

            if not auth_response.session:
                raise ValueError("Sin sesión en la respuesta")

            jwt_token = auth_response.session.access_token
            expires   = auth_response.session.expires_in
            user      = auth_response.user

            # Si el jugador no tiene perfil en la tabla jugadores, lo creamos
            # (puede pasar la primera vez que entra con Google)
            if not SUPABASE_SERVICE_ROLE_KEY:
                logger.error("SUPABASE_SERVICE_ROLE_KEY no está configurada o está vacía")
                raise RuntimeError("Configuración inválida del servicio de autenticación")

            sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

            perfil = sb_admin.table('jugadores').select('id,nombre,apellido').eq('id', user.id).execute()
            if not perfil.data:
                meta = user.user_metadata or {}
                nombre   = meta.get('given_name') or meta.get('name', 'Jugador').split()[0]
                apellido = meta.get('family_name') or (meta.get('name', '').split()[-1] if ' ' in meta.get('name', '') else '')
                sb_admin.table('jugadores').insert({
                    'id':       user.id,
                    'nombre':   nombre,
                    'apellido': apellido,
                }).execute()
                logger.info("Perfil creado para jugador OAuth: %s", user.id)
            else:
                nombre   = perfil.data[0].get('nombre', '')
                apellido = perfil.data[0].get('apellido', '')

            jwt_handler = app.jwt_handler
            token_data = {
                'authenticated': True,
                'role': 'jugador',
                'user_id': str(user.id),
                'nombre': nombre,
                'apellido': apellido,
                'telefono': '',
                'timestamp': int(time.time()),
            }
            token = jwt_handler.generar_token(token_data)
            response = make_response(redirect(url_for('grupos_publico')))
            response.set_cookie('token', token, httponly=True, samesite='Lax', max_age=60 * 60 * 2, secure=not app.debug)
            return response

        except Exception as e:
            logger.error("Error en OAuth callback: %s", e)
            flash('Error al autenticar con Google. Intenta de nuevo.', 'error')
            return redirect(url_for('login'))

    return app


def _registrar_extras(app):
    """Registra health check y manejadores de error globales."""

    @app.route('/_health')
    def health_check():
        """Endpoint para keep-alive (UptimeRobot, Freshping, etc).
        No requiere autenticación.
        Hace una query real a Supabase para evitar que el proyecto free tier se pause."""
        from flask import jsonify
        try:
            storage = app.torneo_storage
            if storage._sb:
                storage._sb.table('torneo_actual').select('id').limit(1).execute()
        except Exception:
            pass  # No romper el health check si Supabase está lento o caído
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
        logger.error('Error 500 en %s %s: %s', request.method, request.path, e, exc_info=True)
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
