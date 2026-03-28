# Roadmap — Algoritmo-Torneos

## Deuda técnica pendiente

### `fetchWithToken` en `jwt-helper.js` — dos problemas a resolver

**Problema 1 — `Content-Type: application/json` siempre forzado (bajo impacto)**
El wrapper manda este header en todos los requests, incluyendo GETs. Actualmente no rompe nada porque siempre se usa con JSON, pero es incorrecto semánticamente. Fix: solo agregar el header si el request tiene body (`options.body !== undefined`).

**Problema 2 — `response.json()` sin try/catch en el handler 401 (puede romper en producción)**
Si Railway o un proxy devuelve un 401 con body vacío o HTML (timeout, error de red), `await response.json()` lanza una excepción y el usuario no es redirigido al login. Fix: envolver el `response.json()` del bloque 401 en try/catch propio.

```js
// Fix sugerido
if (response.status === 401) {
    try {
        const data = await response.json();
        if (data.redirect) {
            window.location.href = data.redirect;
            return response;
        }
    } catch (_) { /* body vacío o no-JSON — ignorar, no redirigir */ }
}
```

### `calendario_finales_builder.py` — filtro de partidos 'Vacío' incompleto

Líneas 108 y 113 filtran con `slot1_info != 'Vacío'` pero no chequean `slot2_info`. Un partido con `slot1` asignado pero `slot2` vacío (pareja no asignada aún) pasa el filtro y entra al calendario como si fuera válido. La semántica correcta según el propio comentario del código es filtrar por presencia real de `pareja1`/`pareja2`, no por `slot_info` que es metadata de display.

```python
# Fix sugerido — líneas 108 y 113
if p and p.get('id') and p.get('pareja1') and p.get('pareja2')]
```

Requiere probar con fixture real de octavos antes de aplicar — el cambio afecta qué partidos entran al calendario de finales.

---

### `historial.py` — `torneo_id` puede ser None y `calendario_finales` no se archiva

**Problema 1 — `torneo_id` None en torneos pre-migración**
`torneo.get('torneo_id')` devuelve `None` si el torneo fue creado antes de que existiera ese campo. El upsert con `id=None` falla silenciosamente. Fix: usar `storage.get_torneo_id()` que fue creado específicamente para cubrir este caso.

**Problema 2 — `calendario_finales` no se persiste en el blob archivado**
Al archivar, `datos_blob` no incluye `calendario_finales`. Sin embargo, `main.py` en fase `espera` intenta leerlo de `datos_blob` para renderizar el fixture del último torneo. Resultado: el calendario de finales nunca aparece en la vista pública durante `espera`. Fix: agregar `'calendario_finales': torneo.get('calendario_finales', {})` al blob antes del upsert.

```python
# Fix sugerido en historial.py ~línea 202
torneo_id = storage.get_torneo_id()
datos_blob = {
    'resultado_algoritmo': torneo.get('resultado_algoritmo'),
    'fixtures_finales':    torneo.get('fixtures_finales', {}),
    'calendario_finales':  torneo.get('calendario_finales', {}),  # ← agregar
    'tipo_torneo':         tipo,
}
```

---

## Estado actual del sistema

Plataforma funcional con flujo completo: inscripciones → grupos → resultados → finales → archivado → espera.
Próximo objetivo: migración de infraestructura a Brasil y schema SQL completo y versionado.

**Implementado:**
- State machine del torneo (`espera` ↔ `inscripcion` ↔ `torneo` → `finalizado` → `espera`)
- Estado `espera` entre torneos con info de próximo torneo y datos del último archivado
- Inscripciones de jugadores con auto-asignación
- Sistema de invitación de compañero por UUID (Player A invita a Player B por teléfono o link compartible)
- Vistas públicas con filtros "Mi Grupo" y "Mi Calendario"
- Historial de torneos archivados (`/torneos`, `/torneos/<id>`)
- Navegación por rol (público / jugador / admin)
- Tablas relacionales para ranking cross-torneo (`grupos`, `parejas_grupo`, `partidos`, `partidos_finales`)
- Dev/Prod Supabase separados (`LagomarPadelDB-Dev` / `LagomarPadelDB`)
- Keep-alive: UptimeRobot → `/_health` (query real) para Render+prod; `pg_cron` para dev

---

## Decisiones de Arquitectura

| Decisión | Opción elegida | Razón |
|---|---|---|
| Auth jugadores | Supabase Auth (email + contraseña) | Ya usan Supabase; maneja JWT, refresh, password reset gratis |
| Google OAuth | Implementado | Habilitado en prod y dev vía Supabase Auth |
| Frontend | Mantener Jinja2 + Bootstrap 5 | Los templates existentes no justifican migrar a React |
| Repo frontend separado | No | Dos servicios Render + CORS + dos repos = overhead puro para un solo dev |
| Admin auth | Mantener JWT custom | Cero riesgo por ahora |
| Torneo activo | Blob JSONB (`torneo_actual.datos`) | ~15 parejas/categoría, volumen trivial; no necesita queries SQL durante el torneo |
| Tablas relacionales | Solo para datos cross-torneo (inscripciones, jugadores, archivo) | KPIs, retención de usuarios, ranking futuro — lo que sí necesita SQL |
| Deployment | Único servicio Render | Sin razón para dividir |
| Región | Migración pendiente a São Paulo (Brasil) | Usuarios en Uruguay; ~20-30ms vs ~150ms desde US East |

---

## Filosofía de la base de datos

El sistema usa dos estrategias de almacenamiento complementarias:

| Capa | Almacenamiento | Razón |
|---|---|---|
| **Torneo activo** | Blob JSONB en `torneo_actual` | Es el estado mutable de un solo torneo. Max ~15 parejas/categoría → no necesita queries SQL. El backend lo lee/escribe completo. |
| **Datos cross-torneo** | Tablas relacionales (`inscripciones`, `jugadores`, `torneos`, `grupos`, etc.) | Esto sí necesita SQL: "¿cuántos usuarios se anotaron en los últimos 10 torneos?", KPIs de retención, ranking. |
| **Archivo de torneo** | `torneos.datos_blob` + tablas relacionales | El blob es cache de lectura para el dashboard histórico. Las tablas son la fuente de verdad queryable. |

---

## Tablas Supabase (schema objetivo)

```sql
-- === TORNEO ACTIVO (blob) ===
torneo_actual     (id, datos JSONB)                          -- 1 fila, estado mutable

-- === DATOS CROSS-TORNEO (relacional) ===
jugadores         (id UUID → auth.users, nombre, apellido, telefono, created_at)
inscripciones     (id, torneo_id → torneos, jugador_id → auth.users,
                   integrante1, integrante2, telefono, categoria,
                   franjas_disponibles JSONB, estado, jugador2_id → jugadores,
                   created_at)
invitacion_tokens (id, inscripcion_id → inscripciones, token UNIQUE,
                   expira_at, usado, created_at)

-- === ARCHIVO DE TORNEO (relacional) ===
torneos           (id, nombre, tipo, estado, datos_blob JSONB, created_at)
grupos            (id, torneo_id → torneos, categoria, franja, cancha, created_at)
parejas_grupo     (grupo_id → grupos, nombre, posicion)      -- PK compuesta
partidos          (id, grupo_id → grupos, pareja1, pareja2, resultado JSONB)
partidos_finales  (id, torneo_id → torneos, categoria, fase, pareja1, pareja2, ganador)

-- === CONTROL DE MIGRACIONES ===
_migrations       (id SERIAL, name TEXT UNIQUE, applied_at)
```

**CHECKs importantes:**
- `torneos.estado`: `inscripcion`, `torneo`, `finalizado`, `espera`
- `inscripciones.estado`: `pendiente`, `confirmado`, `rechazado`, `pendiente_companero`, `cancelada`
- `inscripciones.franjas_disponibles`: tipo `JSONB` (no `text[]`) — consistente entre entornos

---

## Próximos pasos (en orden)

### Paso 1 — Migración a Brasil + Schema versionado ← ACTUAL

**Problema:** Prod está en US East (~150ms para usuarios en Uruguay). Además el schema de Prod está desactualizado respecto a Dev (le faltan columnas, tablas y constraints). No hay un mecanismo formal para migrar cambios de schema entre entornos.

**Solución:**

1. **Reescribir `supabase_schema.sql` como `migrations/000_schema_inicial.sql`**
   - Schema completo y autosuficiente (ejecutable en un Supabase vacío)
   - Incluye: todas las tablas, CHECKs, RLS + policies, índices, función de expiración
   - Basado en el schema de Dev (el más actualizado)
   - Unifica `franjas_disponibles` a `JSONB`

2. **Crear proyectos Supabase en São Paulo**
   - `LagomarPadelDB-Prod-BR` y `LagomarPadelDB-Dev-BR`
   - Ejecutar `000_schema_inicial.sql` en ambos

3. **Migrar datos de Prod actual a Prod-BR**
   - Los torneos archivados, jugadores registrados, etc.

4. **Actualizar Render**
   - Apuntar env vars a los nuevos proyectos de Supabase
   - Evaluar migrar Render a São Paulo también

5. **Establecer flujo de migraciones**
   - Tabla `_migrations` para tracking
   - Cada cambio futuro es un archivo `migrations/NNN_descripcion.sql`
   - Workflow: probar en Dev-BR → escribir migración → aplicar en Prod-BR

**Estructura de migraciones:**
```
migrations/
  000_schema_inicial.sql      ← crea TODO desde cero
  001_xxx.sql                 ← cambios futuros
```

**Archivos a modificar/crear:**
- `migrations/000_schema_inicial.sql` (nuevo — reemplaza `supabase_schema.sql`)
- `supabase_schema.sql` (eliminar — reemplazado por migrations/)
- Variables de entorno en Render y `.env` local

---

### Paso 2 — Ranking Anual por Categoría

**Prerequisito:** Migración a Brasil completada (Paso 1). Tablas relacionales disponibles.

**Decisión pendiente:** `parejas_grupo` y `partidos` hoy referencian parejas por nombre (texto). Para el ranking esto puede ser un problema si la misma pareja se inscribe con nombres distintos entre torneos. Evaluar si conviene vincular por `inscripciones.id` o por par de `jugador_id`s antes de implementar.

- Ranking **anual** acumulado, una tabla de posiciones por categoría
- Crear tabla `puntos_historicos` (puntos por **jugador individual**, no por pareja — las parejas cambian pero los jugadores no)
- Blueprint `api/routes/ranking.py`
  - `GET /ranking` → leaderboard público con tabs por categoría + filtro por año
  - `GET /ranking/<categoria>` → tabla de una categoría específica
  - `POST /api/admin/puntos/asignar` → admin asigna puntos al finalizar torneo
- Templates: `ranking.html`, `mis_puntos.html` (historial del jugador)
- Fórmula inicial: 1°=10pts, 2°=7pts, 3°=5pts, participación=2pts
- Agregar "Ranking" al nav de jugador y público
- Migración: `migrations/001_ranking.sql`

---

## Archivos que NO tocar

- `core/algoritmo.py`, `core/clasificacion.py`, `core/fixture_*.py`
- `utils/csv_processor.py`, `utils/calendario_builder.py`, `utils/exportador.py`
- `gunicorn.conf.py`, `render.yaml`
- `api/routes/parejas.py`, `api/routes/finales.py`, `api/routes/resultados.py`, `api/routes/calendario.py`
