---
name: debug-torneos
description: >
  Cómo debuggear el algoritmo de grupos, el estado del torneo en Supabase/JSON, y los endpoints Flask sin el frontend.
  Trigger: Al investigar por qué el algoritmo produce grupos incorrectos, al inspeccionar el estado del torneo, o al testear endpoints manualmente.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root]
  auto_invoke: "Debugging algorithm output or tournament state"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Inspeccionar estado del torneo en desarrollo (REQUIRED)

En local, el estado completo del torneo está en `data/torneos/torneo_actual.json`. Es el equivalente al JSONB de Supabase.

```bash
# Ver estado completo del torneo
cat data/torneos/torneo_actual.json | python -m json.tool

# Ver solo las parejas cargadas
cat data/torneos/torneo_actual.json | python -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get('parejas',[]), indent=2, ensure_ascii=False))"

# Contar grupos por categoría
cat data/torneos/torneo_actual.json | python -c "
import json, sys
d = json.load(sys.stdin)
r = d.get('resultado_algoritmo') or {}
grupos = r.get('grupos_por_categoria', {})
for cat, gs in grupos.items():
    print(f'{cat}: {len(gs)} grupos')
"
```

## Testear endpoints con curl (sin abrir el navegador)

Obtener el JWT primero, luego usarlo en requests siguientes.

```bash
# 1. Login y guardar cookie
curl -s -c /tmp/cookies.txt -X POST http://localhost:5000/login \
  -d "username=admin&password=tu_password" -L

# 2. GET endpoint protegido con cookie
curl -s -b /tmp/cookies.txt http://localhost:5000/api/parejas | python -m json.tool

# 3. POST con JSON
curl -s -b /tmp/cookies.txt -X POST http://localhost:5000/api/parejas \
  -H "Content-Type: application/json" \
  -d '{"nombre":"Test","telefono":"600000000","categoria":"Tercera","franjas_disponibles":["Viernes 18:00"]}' \
  | python -m json.tool

# 4. Ejecutar algoritmo manualmente
curl -s -b /tmp/cookies.txt -X POST http://localhost:5000/api/ejecutar-algoritmo \
  | python -m json.tool
```

## Reproducir el algoritmo con datos específicos

Para aislar un bug del algoritmo sin levantar Flask:

```python
# debug_algoritmo.py (ejecutar: python debug_algoritmo.py)
from core.models import Pareja
from core.algoritmo import AlgoritmoGrupos

parejas = [
    Pareja(id=1, nombre="Pareja A", telefono="", categoria="Tercera",
           franjas_disponibles=["Viernes 18:00", "Sábado 09:00"]),
    Pareja(id=2, nombre="Pareja B", telefono="", categoria="Tercera",
           franjas_disponibles=["Viernes 18:00"]),
    Pareja(id=3, nombre="Pareja C", telefono="", categoria="Tercera",
           franjas_disponibles=["Sábado 09:00", "Sábado 12:00"]),
]

algo = AlgoritmoGrupos(parejas, num_canchas=2)
resultado = algo.ejecutar()

for cat, grupos in resultado.grupos_por_categoria.items():
    print(f"\n{cat}: {len(grupos)} grupos")
    for g in grupos:
        print(f"  Grupo {g.id}: {[p.nombre for p in g.parejas]} | franja: {g.franja_horaria} | score: {g.score_compatibilidad:.2f}")

if resultado.parejas_sin_asignar:
    print(f"\nSin asignar: {[p.nombre for p in resultado.parejas_sin_asignar]}")
```

## Logging del algoritmo

El logging está configurado en `main.py`. Para ver los logs del algoritmo durante una ejecución:

```bash
# Levantar con logs en DEBUG para ver backtracking
DEBUG=True python main.py 2>&1 | grep -E "(algoritmo|grupo|score|backtrack)"

# O con gunicorn
gunicorn main:app --config gunicorn.conf.py --log-level debug
```

## Verificar qué backend de storage está activo

```python
# Pegar en consola Python o en un endpoint temporal de debug
from utils.torneo_storage import _USE_SUPABASE, storage
print("Backend:", "Supabase" if _USE_SUPABASE else "JSON local")
print("Cache actual:", "sí" if storage._cache else "vacío")

torneo = storage.cargar()
print("Estado:", torneo.get('estado'))
print("Parejas:", len(torneo.get('parejas', [])))
print("Tipo torneo:", torneo.get('tipo_torneo'))
```

## Resetear torneo en desarrollo

```bash
# Opción 1: via API
curl -s -b /tmp/cookies.txt -X POST http://localhost:5000/api/limpiar-torneo | python -m json.tool

# Opción 2: borrar el JSON local directamente
echo '{}' > data/torneos/torneo_actual.json

# Opción 3: regenerar datos de prueba
python generar_datos_prueba.py
```

## Ejemplo Real del Proyecto

Para inspeccionar el resultado del algoritmo desde el CSV de prueba:

```bash
# 1. Generar datos de prueba
python generar_datos_prueba.py

# 2. El CSV queda en data/uploads/datos_prueba.csv
# 3. Levantar la app y subir el CSV desde /  (inicio)
# 4. Ver el resultado del algoritmo:
cat data/torneos/torneo_actual.json | python -c "
import json, sys
d = json.load(sys.stdin)
r = d.get('resultado_algoritmo') or {}
stats = r.get('estadisticas', {})
print('Estadísticas:', json.dumps(stats, indent=2, ensure_ascii=False))
"
```

## Referencias

- `core/algoritmo.py` — `AlgoritmoGrupos.ejecutar()`, `_formar_grupos_categoria()`, `_buscar_distribucion_optima()`
- `generar_datos_prueba.py` — genera `data/uploads/datos_prueba.csv` con parejas de todas las categorías
- `data/torneos/torneo_actual.json` — estado local del torneo (equivalente al JSONB de Supabase)
- `utils/torneo_storage.py` — `_USE_SUPABASE`, `storage.cargar()`, `storage.limpiar()`
