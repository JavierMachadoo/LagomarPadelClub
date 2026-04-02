---
name: supabase-torneos
description: >
  Patrones Supabase del proyecto: upsert de JSONB, detección de backend, schema de una sola fila y fallback a JSON local.
  Trigger: Al modificar supabase_schema.sql, queries Supabase en torneo_storage.py, o variables de entorno de Supabase.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root, utils]
  auto_invoke: "Modifying Supabase schema or queries"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Modelo de una sola fila (REQUIRED)

La tabla `torneo_actual` tiene exactamente **una fila** con `id = 1`. Siempre usar `upsert` con `id: 1`, nunca `insert` ni queries sin filtro `eq('id', 1)`.

```python
# ✅ CORRECTO: upsert garantiza que siempre queda una sola fila
self._sb.table('torneo_actual').upsert(
    {'id': 1, 'datos': datos}
).execute()

# ✅ CORRECTO: siempre filtrar por id = 1
resp = self._sb.table('torneo_actual').select('datos').eq('id', 1).execute()

# ❌ NUNCA: insert crea duplicados (la constraint single_row lo bloqueará)
self._sb.table('torneo_actual').insert({'datos': datos}).execute()

# ❌ NUNCA: select sin filtro devuelve todas las filas (aunque solo haya una, es frágil)
resp = self._sb.table('torneo_actual').select('datos').execute()
```

## Detección de backend en runtime

El módulo detecta Supabase en el momento de importación. La variable `_USE_SUPABASE` es el flag global — no releer env vars en runtime.

```python
# ✅ CORRECTO: detección en módulo, no en cada método
_SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
_SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY', '').strip()
_USE_SUPABASE = bool(_SUPABASE_URL and _SUPABASE_KEY)

# En métodos: usar el flag ya calculado
def guardar(self, datos: Dict) -> None:
    if _USE_SUPABASE:
        self._sb.table(self._TABLE).upsert({'id': 1, 'datos': datos}).execute()
    else:
        # JSON local fallback
        with open(self._TORNEO_FILE, 'w', encoding='utf-8') as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)

# ❌ NUNCA: releer env vars en cada llamada
def guardar(self, datos):
    if os.getenv('SUPABASE_URL'):  # recalculado innecesariamente
        ...
```

## Fallback a caché vencido en error de Supabase

Si Supabase falla al leer, devolver el caché aunque esté vencido en vez de lanzar excepción — el torneo no puede quedar inaccesible.

```python
# ✅ CORRECTO: degradación graceful
try:
    resp = self._sb.table(self._TABLE).select('datos').eq('id', 1).execute()
    if resp.data:
        datos = resp.data[0]['datos']
        self._cache = datos
        self._cache_ts = time.monotonic()
        return datos
except Exception as e:
    logger.error('Error al cargar desde Supabase: %s', e)
    if self._cache is not None:
        logger.warning('Usando caché vencido por error de Supabase')
        return self._cache

# ❌ NUNCA: propagar la excepción al handler de Flask
except Exception as e:
    raise  # el usuario ve un 500 con el torneo perfectamente guardado
```

## Schema SQL — reglas para cambios futuros

El schema está en `supabase_schema.sql`. RLS está desactivado intencionalmente hasta v2 (cuando se implemente registro de usuarios).

```sql
-- ✅ CORRECTO: constraint que garantiza una sola fila
CREATE TABLE IF NOT EXISTS torneo_actual (
    id      INTEGER PRIMARY KEY DEFAULT 1,
    datos   JSONB   NOT NULL DEFAULT '{}',
    CONSTRAINT single_row CHECK (id = 1)
);

-- ✅ Si necesitas agregar campos: añadirlos DENTRO del JSONB 'datos', no como columnas nuevas
-- La app lee/escribe siempre el blob completo, no columnas individuales.

-- ❌ NUNCA agregar columnas nuevas a la tabla (rompe el modelo de blob completo)
ALTER TABLE torneo_actual ADD COLUMN nombre TEXT;  -- no hacer esto

-- ❌ No activar RLS hasta implementar auth de Supabase (v2)
-- ALTER TABLE torneo_actual ENABLE ROW LEVEL SECURITY;
```

## Ejemplo Real del Proyecto

Flujo completo de `cargar()` en `utils/torneo_storage.py`:

```python
def cargar(self) -> Dict:
    # 1. Caché en memoria (evita round-trip de ~200ms a Supabase)
    if self._cache is not None:
        if time.monotonic() - self._cache_ts < self._CACHE_TTL:
            return self._cache

    if _USE_SUPABASE:
        try:
            resp = self._sb.table(self._TABLE).select('datos').eq('id', 1).execute()
            if resp.data:
                datos = resp.data[0]['datos']
                self._cache = datos
                self._cache_ts = time.monotonic()
                return datos
        except Exception as e:
            logger.error('Error al cargar desde Supabase: %s', e)
            if self._cache is not None:
                logger.warning('Usando caché vencido por error de Supabase')
                return self._cache
        # Primera ejecución: crear torneo vacío
        default = self._torneo_vacio()
        self.guardar(default)
        return default

    # JSON local fallback
    ...
```

## Referencias

- `utils/torneo_storage.py` — `TorneoStorage`, `guardar()`, `cargar()`, `_USE_SUPABASE`
- `supabase_schema.sql` — DDL completo de la tabla `torneo_actual`
- `requirements.txt` — paquete `supabase` (instalado si se usa Supabase)
- `config/settings.py` — env vars `SUPABASE_URL`, `SUPABASE_ANON_KEY`
