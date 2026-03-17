"""
Blueprint de autenticación para jugadores.

Flujo separado del admin:
- Admin  → POST /login (form) → cookie 'token'     (JWT custom)
- Jugador → POST /api/auth/register → cookie 'sb_token' (Supabase JWT)
           → POST /api/auth/login   → cookie 'sb_token' (Supabase JWT)
           → POST /api/auth/logout  → borra 'sb_token'
"""

import logging
import time
from flask import Blueprint, request, jsonify, make_response, current_app

from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ADMIN_USERNAME, ADMIN_PASSWORD

logger = logging.getLogger(__name__)

auth_jugador_bp = Blueprint("auth_jugador", __name__, url_prefix="/api/auth")


def _get_supabase_admin():
    """
    Devuelve un cliente Supabase con SERVICE_ROLE_KEY.
    Se usa solo server-side para operaciones de admin (insertar jugadores, etc.)
    """
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


@auth_jugador_bp.route("/register", methods=["POST"])
def register():
    """
    Registra un nuevo jugador.

    Body JSON: { email, password, nombre, apellido, telefono? }

    Flujo:
      1. Crea usuario en Supabase Auth (anon key es suficiente para sign_up)
      2. Inserta perfil en tabla `jugadores` con service_role (bypasea RLS)
    """
    data = request.get_json(silent=True) or {}
    email    = data.get("email", "").strip()
    password = data.get("password", "")
    nombre   = data.get("nombre", "").strip()
    apellido = data.get("apellido", "").strip()
    telefono = data.get("telefono", "").strip()

    if not all([email, password, nombre, apellido]):
        return jsonify({"error": "email, password, nombre y apellido son obligatorios"}), 400

    try:
        sb = _get_supabase_admin()

        # 1. Crear usuario en Supabase Auth
        auth_response = sb.auth.sign_up({"email": email, "password": password})

        if not auth_response.user:
            return jsonify({"error": "No se pudo crear el usuario"}), 400

        user_id = auth_response.user.id

        # 2. Insertar perfil en tabla jugadores
        sb.table("jugadores").insert({
            "id":       user_id,
            "nombre":   nombre,
            "apellido": apellido,
            "telefono": telefono or None,
        }).execute()

        logger.info("Jugador registrado: %s (%s)", email, user_id)
        return jsonify({"message": "Registro exitoso. Revisa tu email para confirmar tu cuenta."}), 201

    except Exception as e:
        logger.error("Error en registro de jugador: %s", e)
        # Supabase devuelve mensajes descriptivos, los exponemos con cuidado
        error_msg = str(e)
        if "already registered" in error_msg or "already been registered" in error_msg:
            return jsonify({"error": "Este email ya está registrado"}), 409
        return jsonify({"error": "Error al registrar. Intenta de nuevo."}), 500


def _login_admin_fallback(usuario, password):
    """
    Fallback: verifica las credenciales hardcodeadas del admin en .env.
    Se usa cuando Supabase no tiene al admin como usuario, o como contingencia.
    Devuelve una Response con cookie 'token' (JWT custom), o None si falla.
    """
    if usuario != ADMIN_USERNAME or password != ADMIN_PASSWORD:
        return None

    jwt_handler = current_app.jwt_handler
    token_data = {
        'authenticated': True,
        'role': 'admin',
        'session_id': 'admin_session',
        'timestamp': int(time.time()),
    }
    token = jwt_handler.generar_token(token_data)
    response = make_response(jsonify({"message": "Login exitoso", "redirect": "/inicio"}), 200)
    response.set_cookie('token', token, httponly=True, samesite='Lax', max_age=60 * 60 * 2)
    logger.info("Admin autenticado via fallback .env")
    return response


@auth_jugador_bp.route("/login", methods=["POST"])
def login():
    """
    Endpoint de login unificado: un solo form para admin y jugadores.

    Body JSON: { email, password }

    Lógica de resolución de rol:
      1. Intenta Supabase Auth con el email/usuario recibido
         a. Si el usuario tiene role='admin' en app_metadata → cookie 'token' (JWT custom admin)
         b. Si es jugador regular → cookie 'sb_token' (Supabase JWT)
      2. Si Supabase falla → fallback a ADMIN_USERNAME/ADMIN_PASSWORD del .env
         (permite al admin seguir entrando aunque no esté en Supabase Auth)
    """
    data = request.get_json(silent=True) or {}
    email    = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Usuario/email y contraseña son obligatorios"}), 400

    # ── 1. Intentar Supabase Auth ─────────────────────────────────────────────
    try:
        sb = _get_supabase_admin()
        auth_response = sb.auth.sign_in_with_password({"email": email, "password": password})

        if auth_response.session:
            session   = auth_response.session
            user      = auth_response.user
            jwt_token = session.access_token
            expires   = session.expires_in

            # Verificar si el usuario tiene rol admin en Supabase
            app_meta  = user.app_metadata or {}
            user_meta = user.user_metadata or {}
            es_admin  = app_meta.get("role") == "admin" or user_meta.get("role") == "admin"

            if es_admin:
                # Admin autenticado vía Supabase → generar JWT custom para el middleware Flask
                jwt_handler = current_app.jwt_handler
                token_data = {
                    'authenticated': True,
                    'role': 'admin',
                    'session_id': str(user.id),
                    'timestamp': int(time.time()),
                }
                token = jwt_handler.generar_token(token_data)
                response = make_response(jsonify({"message": "Login exitoso", "redirect": "/inicio"}), 200)
                response.set_cookie('token', token, httponly=True, samesite='Lax', max_age=60 * 60 * 2)
                logger.info("Admin autenticado via Supabase: %s", user.id)
                return response

            # Jugador regular → usar Supabase JWT directamente
            perfil = sb.table("jugadores").select("nombre,apellido").eq("id", user.id).single().execute()
            nombre_completo = ""
            if perfil.data:
                nombre_completo = f"{perfil.data['nombre']} {perfil.data['apellido']}"

            response = make_response(jsonify({
                "message":  "Login exitoso",
                "nombre":   nombre_completo,
                "redirect": "/grupos",
            }), 200)
            response.set_cookie("sb_token", jwt_token, httponly=True, samesite="Lax", max_age=expires)
            logger.info("Jugador autenticado: %s", user.id)
            return response

    except Exception as e:
        logger.debug("Supabase login falló (%s), intentando fallback admin", e)

    # ── 2. Fallback: credenciales admin del .env ──────────────────────────────
    fallback = _login_admin_fallback(email, password)
    if fallback:
        return fallback

    return jsonify({"error": "Credenciales incorrectas"}), 401


@auth_jugador_bp.route("/logout", methods=["POST"])
def logout():
    """
    Cierra la sesión del jugador borrando la cookie sb_token.
    """
    response = make_response(jsonify({"message": "Sesión cerrada"}), 200)
    response.delete_cookie("sb_token")
    return response
