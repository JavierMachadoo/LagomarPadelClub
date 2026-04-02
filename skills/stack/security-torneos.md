---
name: security-torneos
description: >
  Patrones de seguridad del proyecto: JWT HttpOnly cookies, validación de input en CSV upload, XSS prevention con tojson, y manejo de credenciales.
  Trigger: Al modificar autenticación, validación de archivos subidos, o renderizado de datos de usuario en templates.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root, api, web]
  auto_invoke: "Modifying authentication, file upload validation, or rendering user data in templates"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## JWT en HttpOnly Cookie (REQUIRED)

El token JWT se almacena en una **cookie HttpOnly**, no en localStorage. Esto previene robo de token via XSS.

```python
# ✅ CORRECTO: cookie HttpOnly, SameSite=Lax
response.set_cookie(
    'token',
    token,
    httponly=True,
    samesite='Lax',
    secure=not app.debug,  # HTTPS en producción, HTTP en dev
    max_age=7200  # 2 horas
)

# ❌ NUNCA: enviar el token en el body para que JS lo guarde en localStorage
return jsonify({'token': token})  # JS puede leerlo, susceptible a XSS
```

## Validación de archivo CSV en upload

El endpoint de upload debe validar extensión y tamaño antes de procesar.

```python
# ✅ CORRECTO: validar antes de leer el contenido
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"success": False, "error": "No se seleccionó archivo"}), 400
    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Formato no permitido"}), 400
    # Usar werkzeug para sanitizar el nombre de archivo
    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    ...

# ❌ NUNCA: usar el filename del usuario directamente en una ruta de archivo
filepath = f"uploads/{request.files['file'].filename}"  # path traversal: "../../etc/passwd"
```

## XSS: siempre tojson para datos en templates

Datos del servidor en templates Jinja2 deben usar el filtro `tojson`. Sin él, caracteres como `</script>` en nombres de parejas pueden romper el HTML o inyectar scripts.

```html
<!-- ✅ CORRECTO: tojson escapa </script>, comillas y caracteres especiales -->
<script>
  const grupos = {{ grupos_por_categoria | tojson }};
  const nombreTorneo = {{ torneo.nombre | tojson }};
</script>

<!-- ❌ NUNCA: interpolación directa de dicts/strings Python en JS -->
<script>
  const grupos = {{ grupos_por_categoria }};  <!-- rompe si contiene ' o </script> -->
  const nombre = "{{ torneo.nombre }}";       <!-- XSS si el nombre viene de input del usuario -->
</script>
```

## Credenciales: solo en variables de entorno

Las credenciales (`SECRET_KEY`, `ADMIN_PASSWORD`) deben venir únicamente de env vars. Nunca hardcodear, nunca commitear `.env`.

```python
# ✅ CORRECTO: leer de env, sin default inseguro en producción
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY no configurada — requerida en producción")

# En desarrollo local se puede aceptar un fallback solo para DEBUG=True
if app.debug:
    SECRET_KEY = SECRET_KEY or 'dev-only-secret'

# ❌ NUNCA: hardcodear secretos
SECRET_KEY = 'mi-clave-secreta-123'

# ❌ NUNCA: commitear .env con credenciales reales (ya está en .gitignore)
```

## Middleware: rutas públicas explícitas

El middleware `verificar_autenticacion()` define rutas públicas como allowlist explícita. Si añades una ruta nueva que deba ser pública, agrégala a `rutas_publicas`.

```python
# ✅ CORRECTO: allowlist explícita — cualquier ruta NO listada requiere auth
rutas_publicas = {
    'login', 'static',
    'grupos_publico', 'finales_publico',  # vistas públicas del torneo
    'api_grupos_publico', 'api_finales_publico'
}

@app.before_request
def verificar_autenticacion():
    if request.endpoint in rutas_publicas:
        return
    # resto de la verificación...

# ❌ NUNCA: proteger rutas individualmente, es fácil olvidar una
@app.route('/admin/reset')
def reset():
    token = request.cookies.get('token')  # puede olvidarse en cualquier ruta nueva
    if not token: ...
```

## Ejemplo Real del Proyecto

En `main.py`, el flujo de login que emite la cookie segura:

```python
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            token = jwt_handler.generar_token({'usuario': username, 'rol': 'admin'})
            response = redirect(url_for('home'))
            response.set_cookie('token', token, httponly=True, samesite='Lax',
                                secure=not app.debug, max_age=7200)
            return response
    return render_template('login.html')
```

## Referencias

- `main.py` — `verificar_autenticacion()`, `rutas_publicas`, endpoint de login
- `utils/jwt_handler.py` — `generar_token()`, `verificar_token()`
- `utils/csv_processor.py` — procesamiento del archivo subido
- `web/static/js/jwt-helper.js` — manejo del token en el frontend (cookie, no localStorage)
- `.gitignore` — `.env` ya está ignorado; nunca removerlo de ahí
