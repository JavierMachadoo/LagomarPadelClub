---
name: torneo-storage
description: >
  Patrones para la capa de persistencia: modelo single-tournament, cache TTL, Supabase JSONB y fallback JSON local.
  Trigger: Al modificar utils/torneo_storage.py o cualquier código que llame a storage.cargar() / storage.guardar().
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root, utils]
  auto_invoke: "Modifying storage layer or tournament persistence"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Modelo Single-Tournament (REQUIRED)

Existe exactamente **un torneo activo** (`torneo_actual`). No hay historial de torneos en el storage actual.

```python
# ✅ La estructura del torneo es un dict con claves fijas
torneo = {
    "parejas": [],               # lista de dicts con datos de parejas
    "resultado_algoritmo": {},   # grupos_por_categoria, calendario, estadísticas
    "num_canchas": 3,            # int
    "estado": "activo",          # "activo" | "finalizado"
    "tipo_torneo": "fin1",       # "fin1" | "fin2"
    "fixtures_finales": {},      # dict keyed by categoria
    "nombre": "Torneo Ejemplo"   # str
}

# ❌ NUNCA agregar claves de alto nivel sin actualizar también el schema de Supabase
torneo["nueva_clave"] = []  # faltará en supabase_schema.sql
```

## Cache TTL — Regla de los 5 segundos

El cache en memoria expira a los 5 segundos. Es seguro **solo con 1 worker de Gunicorn**.

```python
# ✅ El cache se invalida automáticamente tras guardar
def guardar(self, torneo):
    self._cache = torneo
    self._cache_time = time.time()
    self._persistir(torneo)

# ✅ Al cargar, respetar el TTL
def cargar(self):
    if self._cache and (time.time() - self._cache_time) < 5:
        return self._cache
    self._cache = self._cargar_desde_fuente()
    self._cache_time = time.time()
    return self._cache

# ❌ NUNCA aumentar workers de Gunicorn sin eliminar el cache compartido
# gunicorn.conf.py: workers = 1  ← NO cambiar
```

## Supabase vs JSON Local

El storage detecta automáticamente el backend. El código que llama al storage **no debe saber** cuál se usa.

```python
# ✅ Transparente para el caller
from utils.torneo_storage import storage

torneo = storage.cargar()   # funciona igual con Supabase o JSON
storage.guardar(torneo)

# ❌ NUNCA acceder directamente al archivo JSON o al cliente Supabase desde rutas
import json
with open('data/torneos/torneo_actual.json') as f:  # bypassea el cache
    data = json.load(f)
```

## Operaciones Atómicas

Siempre cargar → modificar → guardar en el mismo request. No separar en dos requests.

```python
# ✅ Atómico dentro del mismo handler
torneo = storage.cargar()
torneo['estado'] = 'finalizado'
storage.guardar(torneo)

# ❌ Peligroso: otro request puede modificar entre el cargar y el guardar
# (con 1 worker esto no pasa, pero es mala práctica igual)
```

## Ejemplo Real del Proyecto

En `api/routes/finales.py`, actualización de resultado de partido:

```python
@finales_bp.route('/finales/partido/<partido_id>/resultado', methods=['POST'])
def guardar_resultado_partido(partido_id):
    torneo = storage.cargar()                          # 1. cargar
    fixtures = torneo.get('fixtures_finales', {})

    for categoria, fixture in fixtures.items():
        for fase in fixture.get('fases', []):
            for partido in fase.get('partidos', []):
                if partido['id'] == partido_id:
                    partido['resultado'] = request.get_json()  # 2. modificar
                    storage.guardar(torneo)                    # 3. guardar
                    return jsonify({"success": True})

    return jsonify({"success": False, "error": "Partido no encontrado"}), 404
```

## Referencias

- `utils/torneo_storage.py` — `TorneoStorage`, `cargar()`, `guardar()`, `limpiar()`
- `gunicorn.conf.py` — `workers = 1` (crítico, no cambiar)
- `supabase_schema.sql` — estructura de la tabla `torneo_actual`
- `config/settings.py` — `SUPABASE_URL`, `SUPABASE_ANON_KEY`