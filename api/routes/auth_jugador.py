"""
Blueprint de autenticación para jugadores.

Flujo separado del admin:
- Admin   → POST /api/auth/login        → cookie 'token'    (JWT custom)
- Jugador → POST /api/auth/register     → cookie 'sb_token' (Supabase JWT)
          → POST /api/auth/login        → cookie 'sb_token' (Supabase JWT)
          → GET  /api/auth/google       → redirect OAuth Google (PKCE)
          → POST /api/auth/logout       → borra ambas cookies

El callback OAuth vive en main.py: GET /auth/callback
"""

import hashlib
import base64
import logging
import re
import secrets
import time
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify, make_response, current_app, redirect, session, url_for

from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, ADMIN_USERNAME, ADMIN_PASSWORD
from utils.rate_limiter import limiter
from utils.input_validation import validar_longitud, MAX_NOMBRE, MAX_TELEFONO, MAX_EMAIL, MAX_PASSWORD

logger = logging.getLogger(__name__)

auth_jugador_bp = Blueprint("auth_jugador", __name__, url_prefix="/api/auth")


def _es_redirect_seguro(url: str) -> bool:
    """
    Valida que la URL sea un path relativo interno seguro.

    Rechaza:
      - URLs vacías
      - Rutas scheme-relative tipo //evil.com (open redirect)
      - URLs con scheme (http://, https://)
      - URLs con netloc (dominio externo)

    Acepta solo paths que empiecen con '/' y no contengan '//' al inicio.
    """
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme == "" and parsed.netloc == "" and url.startswith("/") and not url.startswith("//")


def _get_supabase_admin():
    """Devuelve un cliente Supabase con SERVICE_ROLE_KEY. Solo operaciones server-side."""
    from utils.supabase_client import get_supabase_admin
    return get_supabase_admin()


def _get_supabase_anon():
    """Devuelve un cliente Supabase con ANON_KEY. Para sign_up / sign_in."""
    from utils.supabase_client import get_supabase_anon
    return get_supabase_anon()


@auth_jugador_bp.route("/register", methods=["POST"])
@limiter.limit("3/minute")
def register():
    """
    Registra un nuevo jugador.

    Body JSON: { email, password, nombre, apellido, telefono? }

    Flujo:
      1. Crea usuario en Supabase Auth (anon key es suficiente para sign_up)
      2. Inserta perfil en tabla `jugadores` con service_role (bypasea RLS)
    """
    data = request.get_json(silent=True) or {}
    email        = data.get("email", "").strip()
    password     = data.get("password", "")
    nombre       = data.get("nombre", "").strip()
    apellido     = data.get("apellido", "").strip()
    telefono     = data.get("telefono", "").strip()
    invite_token = data.get("invite_token", "").strip() or request.args.get("invite_token", "").strip() or ""

    if not all([email, password, nombre, apellido]):
        return jsonify({"error": "email, password, nombre y apellido son obligatorios"}), 400
    if len(password) < 8:
        return jsonify({"error": "La contraseña debe tener al menos 8 caracteres"}), 400
    if not telefono:
        return jsonify({"error": "El teléfono es obligatorio"}), 400
    if not re.match(r'^\d{9}$', telefono):
        return jsonify({"error": "El teléfono debe tener exactamente 9 dígitos numéricos"}), 400

    error_len = validar_longitud({
        'Nombre':    (nombre, MAX_NOMBRE),
        'Apellido':  (apellido, MAX_NOMBRE),
        'Email':     (email, MAX_EMAIL),
        'Teléfono':  (telefono, MAX_TELEFONO),
        'Contraseña': (password, MAX_PASSWORD),
    })
    if error_len:
        return jsonify({"error": error_len}), 400

    try:
        # 1. Crear usuario en Supabase Auth usando Admin API (SERVICE_ROLE_KEY).
        # sign_up() con anon_key puede devolver un user ID ficticio cuando el email
        # ya existe (Supabase lo hace para no revelar si el email está registrado),
        # lo que causa FK violation al insertar en jugadores. La Admin API es
        # síncrona y lanza excepción explícita si el email ya existe.
        sb_admin = _get_supabase_admin()
        user_id = None
        try:
            auth_response = sb_admin.auth.admin.create_user({
                "email":          email,
                "password":       password,
                "email_confirm":  False,  # False = requiere confirmación de email (no auto-confirmar)
            })
            if not auth_response.user:
                return jsonify({"error": "No se pudo crear el usuario"}), 400
            user_id = str(auth_response.user.id)

            # admin.create_user NO dispara el email de confirmación automáticamente.
            # Hay que pedirlo explícitamente vía resend() con el cliente anon.
            try:
                sb_anon = _get_supabase_anon()
                sb_anon.auth.resend({"type": "signup", "email": email})
            except Exception as resend_err:
                logger.warning("No se pudo enviar email de confirmación a %s: %s", email, resend_err)

        except Exception as create_err:
            err_str = str(create_err)
            if "already registered" not in err_str and "already been registered" not in err_str:
                raise

            # Registro parcial: el usuario existe en auth.users pero sin perfil.
            # Buscamos su ID para completar el perfil en jugadores.
            all_users = sb_admin.auth.admin.list_users()
            existing = next((u for u in all_users if u.email == email), None)
            if not existing:
                return jsonify({"error": "Este email ya está registrado"}), 409

            existing_profile = sb_admin.table("jugadores").select("id").eq("id", str(existing.id)).execute()
            if existing_profile.data:
                # Tiene perfil completo — email genuinamente duplicado
                return jsonify({"error": "Este email ya está registrado"}), 409

            # Sin perfil → completar registro parcial
            user_id = str(existing.id)
            logger.warning("Completando registro parcial para %s (%s)", email, user_id)

        # 2. Insertar perfil en tabla jugadores
        sb_admin.table("jugadores").insert({
            "id":       user_id,
            "nombre":   nombre,
            "apellido": apellido,
            "telefono": telefono or None,
        }).execute()

        logger.info("Jugador registrado: %s (%s)", email, user_id)

        # 3. Si hay invite_token, auto-aceptar la invitación después del registro
        if invite_token:
            try:
                _auto_aceptar_invitacion_post_registro(sb_admin, invite_token, user_id, f"{nombre} {apellido}".strip())
                logger.info("Invitación auto-aceptada post-registro: token=%s, jugador=%s", invite_token, user_id)
            except Exception as e:
                logger.warning("No se pudo auto-aceptar invitación post-registro: %s", e)
                # No bloquear el registro si falla la invitación

        return jsonify({"message": "Registro exitoso. Revisa tu email para confirmar tu cuenta."}), 201

    except Exception as e:
        logger.error("Error en registro de jugador: %s", e)
        # Supabase devuelve mensajes descriptivos, los exponemos con cuidado
        error_msg = str(e)
        if "already registered" in error_msg or "already been registered" in error_msg:
            return jsonify({"error": "Este email ya está registrado"}), 409
        if "SUPABASE_SERVICE_ROLE_KEY no está configurada" in error_msg or "SUPABASE_ANON_KEY no está configurada" in error_msg:
            return jsonify({"error": error_msg}), 500
        return jsonify({"error": "Error al registrar. Intenta de nuevo."}), 500


def _auto_aceptar_invitacion_post_registro(sb, token: str, jugador_id: str, nombre_jugador: str) -> None:
    """Auto-acepta una invitación pendiente después del registro.
    Se llama opcionalmente — no debe bloquear el flujo principal de registro."""
    from datetime import datetime, timezone

    token_resp = (sb.table('invitacion_tokens')
                  .select('inscripcion_id, expira_at, usado')
                  .eq('token', token)
                  .execute())

    if not token_resp.data:
        return

    token_data = token_resp.data[0]
    if token_data['usado']:
        return

    expira = datetime.fromisoformat(token_data['expira_at'].replace('Z', '+00:00'))
    if datetime.now(timezone.utc) > expira:
        return

    # Obtener la inscripción
    ins_resp = (sb.table('inscripciones')
                .select('*')
                .eq('id', token_data['inscripcion_id'])
                .eq('estado', 'pendiente_companero')
                .execute())

    if not ins_resp.data:
        return

    inscripcion = ins_resp.data[0]

    # Verificar que no sea la propia inscripción
    if inscripcion['jugador_id'] == jugador_id:
        return

    # Verificar que si tiene jugador2_id especificado, coincida
    if inscripcion.get('jugador2_id') and inscripcion['jugador2_id'] != jugador_id:
        return

    # Aceptar
    sb.table('inscripciones').update({
        'jugador2_id': jugador_id,
        'integrante2': nombre_jugador,
        'estado':      'confirmado',
    }).eq('id', inscripcion['id']).execute()

    sb.table('invitacion_tokens').update({'usado': True}).eq('token', token).execute()


def _login_admin_fallback(usuario, password, cookie_max_age=None, token_exp_hours=2):
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
    token = jwt_handler.generar_token(token_data, expiration_hours=token_exp_hours)
    response = make_response(jsonify({"message": "Login exitoso", "redirect": "/"}), 200)
    response.set_cookie('token', token, httponly=True, samesite='Lax', max_age=cookie_max_age, secure=not current_app.debug)
    logger.info("Admin autenticado via fallback .env")
    return response


@auth_jugador_bp.route("/login", methods=["POST"])
@limiter.limit("5/minute")
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
    email       = data.get("email", "").strip()
    password    = data.get("password", "")
    remember_me = bool(data.get("remember_me", False))
    # next_url: destino de redirección post-login (ej: /inscripcion/invitar?token=XXX)
    next_url = data.get("next", "").strip() or request.args.get("next", "").strip() or ""

    cookie_max_age  = 60 * 60 * 24 * 30 if remember_me else None  # 30d ó session cookie
    token_exp_hours = 24 * 30            if remember_me else 2    # 30d ó 2h

    if not email or not password:
        return jsonify({"error": "Usuario/email y contraseña son obligatorios"}), 400

    # ── 1. Intentar Supabase Auth ─────────────────────────────────────────────
    try:
        # sign_in_with_password solo necesita ANON_KEY — usar SERVICE_ROLE aquí
        # violaría el principio de mínimo privilegio (service_role bypasea RLS).
        sb_anon = _get_supabase_anon()
        auth_response = sb_anon.auth.sign_in_with_password({"email": email, "password": password})

        if auth_response.session:
            # Renombrado a sb_session para no pisar el objeto `session` de Flask
            # importado en la línea 19 — shadow silencioso que causa bugs difíciles de rastrear.
            sb_session = auth_response.session
            user       = auth_response.user
            jwt_token  = sb_session.access_token
            expires    = sb_session.expires_in

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
                token = jwt_handler.generar_token(token_data, expiration_hours=token_exp_hours)
                response = make_response(jsonify({"message": "Login exitoso", "redirect": "/admin"}), 200)
                response.set_cookie('token', token, httponly=True, samesite='Lax', max_age=cookie_max_age, secure=not current_app.debug)
                logger.info("Admin autenticado via Supabase: %s", user.id)
                return response

            # Jugador regular → usar SERVICE_ROLE solo para leer el perfil server-side
            sb_admin = _get_supabase_admin()
            perfil = sb_admin.table("jugadores").select("nombre,apellido,telefono").eq("id", user.id).single().execute()
            nombre = ""
            apellido = ""
            telefono = ""
            if perfil.data:
                nombre = perfil.data.get('nombre', '')
                apellido = perfil.data.get('apellido', '')
                telefono = perfil.data.get('telefono') or ''

            jwt_handler = current_app.jwt_handler
            token_data = {
                'authenticated': True,
                'role': 'jugador',
                'user_id': str(user.id),
                'nombre': nombre,
                'apellido': apellido,
                'telefono': telefono,
                'timestamp': int(time.time()),
            }
            token = jwt_handler.generar_token(token_data, expiration_hours=token_exp_hours)
            redirect_to = next_url if _es_redirect_seguro(next_url) else '/dashboard'
            response = make_response(jsonify({
                "message":  "Login exitoso",
                "nombre":   f"{nombre} {apellido}".strip(),
                "redirect": redirect_to,
            }), 200)
            response.set_cookie('token', token, httponly=True, samesite='Lax', max_age=cookie_max_age, secure=not current_app.debug)
            logger.info("Jugador autenticado: %s", user.id)
            return response

    except Exception as e:
        err_str = str(e).lower()
        if 'email not confirmed' in err_str or 'not confirmed' in err_str:
            return jsonify({"error": "Necesitás confirmar tu email antes de ingresar. Revisá tu casilla."}), 401
        logger.debug("Supabase login falló (%s), intentando fallback admin", e)

    # ── 2. Fallback: credenciales admin del .env ──────────────────────────────
    fallback = _login_admin_fallback(email, password, cookie_max_age=cookie_max_age, token_exp_hours=token_exp_hours)
    if fallback:
        return fallback

    return jsonify({"error": "Credenciales incorrectas"}), 401


@auth_jugador_bp.route("/exchange-token", methods=["POST"])
def exchange_token():
    """
    Recibe un access_token de Supabase desde el cliente (leído del hash de la URL
    tras la confirmación de email en flujo implicit) y crea la cookie JWT del servidor.
    """
    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token", "").strip()

    if not access_token:
        return jsonify({"error": "Token requerido"}), 400

    try:
        sb_admin = _get_supabase_admin()
        user_response = sb_admin.auth.get_user(access_token)

        if not user_response.user:
            return jsonify({"error": "Token inválido"}), 401

        user = user_response.user
        perfil = sb_admin.table("jugadores").select("nombre,apellido,telefono").eq("id", str(user.id)).single().execute()
        nombre   = ""
        apellido = ""
        telefono = ""
        if perfil.data:
            nombre   = perfil.data.get("nombre", "")
            apellido = perfil.data.get("apellido", "")
            telefono = perfil.data.get("telefono") or ""

        jwt_handler = current_app.jwt_handler
        token_data = {
            "authenticated": True,
            "role":          "jugador",
            "user_id":       str(user.id),
            "nombre":        nombre,
            "apellido":      apellido,
            "telefono":      telefono,
            "timestamp":     int(time.time()),
        }
        token = jwt_handler.generar_token(token_data, expiration_hours=2)
        response = make_response(jsonify({"redirect": "/dashboard"}), 200)
        response.set_cookie("token", token, httponly=True, samesite="Lax", max_age=60 * 60 * 2, secure=not current_app.debug)
        logger.info("Sesión creada via exchange-token para jugador: %s", user.id)
        return response

    except Exception as e:
        logger.error("Error en exchange-token: %s", e)
        return jsonify({"error": "El enlace expiró o es inválido. Intentá registrarte de nuevo."}), 401


@auth_jugador_bp.route("/logout", methods=["POST"])
def logout():
    """
    Cierra la sesión borrando las cookies de autenticación sb_token y token.
    """
    response = make_response(jsonify({"message": "Sesión cerrada"}), 200)
    response.delete_cookie("sb_token")
    response.delete_cookie("token")
    return response


# ── OAuth Google ──────────────────────────────────────────────────────────────

def _pkce_verifier_y_challenge():
    """
    Genera un par (verifier, challenge) para el flujo PKCE.

    PKCE (Proof Key for Code Exchange) evita que un tercero que intercepte
    el `code` de la redirección pueda canjearlo por un token, porque necesita
    el `verifier` original que solo guardamos nosotros en la sesión Flask.

    - verifier  : string aleatorio que guardamos en session (cookie firmada)
    - challenge : SHA-256 del verifier, codificado en base64url (se envía a Supabase)
    """
    verifier  = secrets.token_urlsafe(64)
    digest    = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
    return verifier, challenge


@auth_jugador_bp.route("/google", methods=["GET"])
def google_oauth():
    """
    Inicia el flujo OAuth con Google vía Supabase.

    1. Genera un par PKCE y guarda el verifier en la sesión Flask
    2. Redirige al endpoint de autorización de Supabase con el challenge
    """
    verifier, challenge = _pkce_verifier_y_challenge()
    session['pkce_verifier'] = verifier

    # Preservar next_url para recuperarlo en el callback post-OAuth
    next_url = request.args.get('next', '').strip()
    if next_url and next_url.startswith('/') and 'token=' in next_url:
        session['oauth_next'] = next_url

    # La URL de callback debe coincidir con la configurada en Supabase Dashboard
    # → Authentication → URL Configuration → Redirect URLs
    callback_url = url_for('oauth_callback', _external=True)

    oauth_url = (
        f"{SUPABASE_URL}/auth/v1/authorize"
        f"?provider=google"
        f"&redirect_to={callback_url}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=s256"
    )
    return redirect(oauth_url)
