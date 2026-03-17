---
name: flask-torneos
description: >
  Patrones Flask para este proyecto: JWT middleware, blueprints, rutas protegidas y formato de respuestas API.
  Trigger: Al modificar rutas en main.py, api/routes/parejas.py o api/routes/finales.py.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root, api]
  auto_invoke: "Modifying routes or API endpoints"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## JWT Middleware (REQUIRED)

Toda ruta protegida pasa por `verificar_autenticacion()` definida en `main.py`. El token se lee desde la **cookie HttpOnly** `token`.

```python
# ✅ CORRECTO: la autenticación ocurre antes de cualquier lógica
@app.before_request
def verificar_autenticacion():
    if request.endpoint in rutas_publicas:
        return
    token = request.cookies.get('token')
    if not token:
        return redirect(url_for('login'))
    payload = jwt_handler.verificar_token(token)
    if not payload:
        return redirect(url_for('login'))
    g.usuario = payload

# ❌ NUNCA: verificar JWT dentro del handler de cada ruta
@app.route('/resultados')
def resultados():
    token = request.cookies.get('token')  # ya se hizo arriba
    ...
```

## Respuestas API

Todos los endpoints en `api/routes/` deben retornar JSON con estructura consistente.

```python
# ✅ Éxito
return jsonify({"success": True, "data": resultado}), 200

# ✅ Error del cliente
return jsonify({"success": False, "error": "Mensaje legible"}), 400

# ✅ Error de servidor
return jsonify({"success": False, "error": "Error interno"}), 500

# ❌ NUNCA retornar strings planos o estructuras inconsistentes
return "OK", 200
```

## Blueprints

Los blueprints se registran en `main.py`. El prefijo de URL va en `register_blueprint`, no en cada ruta.

```python
# api/routes/parejas.py
parejas_bp = Blueprint('parejas', __name__)

@parejas_bp.route('/parejas', methods=['GET'])
def listar_parejas():
    ...

# main.py
from api.routes.parejas import parejas_bp
app.register_blueprint(parejas_bp, url_prefix='/api')
# → genera /api/parejas
```

## Acceso al Storage

Siempre usar la instancia global de `TorneoStorage`. No crear instancias nuevas por request.

```python
# ✅ Importar la instancia global
from utils.torneo_storage import storage

@parejas_bp.route('/parejas', methods=['GET'])
def listar_parejas():
    torneo = storage.cargar()
    return jsonify({"success": True, "data": torneo.get('parejas', [])})

# ❌ NUNCA instanciar storage en el handler
def listar_parejas():
    s = TorneoStorage()  # rompe el cache compartido
    ...
```

## Ejemplo Real del Proyecto

En `api/routes/finales.py`, el endpoint para actualizar ganador de un partido:

```python
@finales_bp.route('/finales/partido/<partido_id>/ganador', methods=['POST'])
def actualizar_ganador(partido_id):
    data = request.get_json()
    if not data or 'ganador_id' not in data:
        return jsonify({"success": False, "error": "ganador_id requerido"}), 400

    torneo = storage.cargar()
    fixtures = torneo.get('fixtures_finales', {})
    # ... lógica de actualización ...
    storage.guardar(torneo)
    return jsonify({"success": True})
```

## Referencias

- `main.py` — middleware JWT y registro de blueprints
- `api/routes/parejas.py` — endpoints CRUD y ejecución del algoritmo
- `api/routes/finales.py` — gestión del bracket de finales
- `utils/jwt_handler.py` — creación y verificación de tokens