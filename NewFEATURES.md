# Plan: Evolución Arquitectónica — Algoritmo-Torneos

## Contexto
El sistema actual es una plataforma web donde jugadores pueden inscribirse, ver sus grupos/calendario, mientras el admin gestiona el torneo. El objetivo siguiente es agregar ranking anual por categoría.

---

## Decisiones de Arquitectura

| Decisión | Recomendación | Razón |
|---|---|---|
| Auth jugadores | **Supabase Auth** (email + contraseña) ✅ | Ya usan Supabase; maneja JWT, refresh, password reset gratis |
| Google OAuth | Posponer o no implementar | Complejidad extra de OAuth sin suficiente beneficio inicial |
| Frontend | **Mantener Jinja2 + Bootstrap 5** ✅ | Templates existentes no justifican React; no separar repos |
| Repo separado para frontend | **No** ✅ | Dos servicios Render + CORS + dos repos = overhead puro para un solo dev |
| Admin auth | **Mantener JWT custom** ✅ | Cero riesgo por ahora |
| Base de datos | **Migración incremental** (tablas nuevas junto al blob) ✅ | No romper lo que funciona |
| Deployment | **Único servicio Render** ✅ | Sin razón para dividir |

---

## Modelo de Estados del Torneo ✅ IMPLEMENTADO

El admin controla el estado desde homePanel. La transición es **bidireccional** entre `inscripcion` y `torneo`:

```
inscripcion ↔ torneo   (admin puede volver atrás)
     ↓
 finalizado             (via botón "Terminar Torneo" → archiva y resetea)
```

| Estado | Jugador puede | Admin puede | Público ve |
|---|---|---|---|
| `inscripcion` | Inscribirse | Organizar grupos en privado, generar/re-generar | "Organizando torneo" |
| `torneo` | Ver grupos, calendario, finales | Ingresar resultados **solo** (grupos bloqueados) | Todo visible |
| `finalizado` | Ver histórico en `/torneos` | — (torneo reseteado) | Histórico |

---

## Navegación por Rol ✅ IMPLEMENTADO

```
Público (sin login):     Grupos | Finales | Calendario
Jugador logueado:        Grupos | Finales | Calendario | Inscribirse / Mi Inscripción
Admin:                   Todo lo anterior + Panel Admin
```

---

## Tablas Supabase actuales ✅ CREADAS

```sql
-- Torneo activo (una sola fila, estado mutable)
torneo_actual (id, datos JSONB)

-- Historial de torneos archivados
torneos (id, nombre, tipo, estado, datos_blob JSONB, created_at)

-- Inscripciones de jugadores
inscripciones (id, torneo_id, jugador_id, integrante1, integrante2,
               telefono, categoria, franjas_disponibles, estado, created_at)
```

---

## Roadmap por Fases

### ✅ Fase 0: State Machine + Fundación
- Tabla `torneos` en Supabase
- `TorneoStorage`: leer/escribir `fase` ('inscripcion'|'torneo')
- homePanel: botones de transición con modal de confirmación
- Middleware `main.py`: inyectar `fase_torneo` en context processor
- Rutas públicas muestran "Organizando torneo" si fase != 'torneo'
- Nav: "Torneo" → "Grupos"; "Finales" en nav público

### ✅ Fase 1: Inscripciones
- Tabla `inscripciones` en Supabase
- Blueprint `api/routes/inscripcion.py` con GET/POST/DELETE `/inscripcion`
- Panel admin: lista de inscripciones con estado
- `/api/ejecutar-algoritmo` lee de `inscripciones` confirmadas
- `inscripcion_id` en cada Pareja para lookup "Mi Grupo"
- Auto-asignación de nuevas inscripciones al dashboard si ya hay grupos generados

### ✅ Fase 2: Vista del Jugador
- Filtros "Mi Grupo" y "Mi Calendario" en vistas públicas
- Lookup por `inscripcion_id` en el resultado del algoritmo
- Placeholder "Organizando torneo" cuando fase != 'torneo'

### ✅ Fase 4: Historial de Torneos
- Blueprint `api/routes/historial.py`
- Botón "Terminar Torneo" en homePanel: archiva datos y resetea torneo completo
- `GET /torneos` → lista de torneos archivados
- `GET /torneos/<id>` → detalle con tabs por categoría (Grupos y Posiciones + Cuadros)

---

## Deuda Técnica: Refactor blob → tablas relacionales

**Cuándo:** Antes de implementar Fase 3. Es un prerequisito.

**Por qué existe:** El estado del torneo activo (`torneo_actual.datos`) y el historial (`torneos.datos_blob`) se guardan como JSONB blob. Fue una decisión pragmática válida para las fases 0–4 donde solo se necesita leer/escribir el estado completo. No es posible hacer consultas cross-torneo sobre un blob.

**Por qué Fase 3 lo rompe:** El ranking necesita consultas como "dame todos los partidos ganados por la pareja X en el año" — imposible sin deserializar cada blob individualmente.

**Qué crear:**

```sql
-- Grupos como entidad relacional
CREATE TABLE grupos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    torneo_id   UUID REFERENCES torneos(id) ON DELETE CASCADE,
    categoria   TEXT NOT NULL,
    franja      TEXT,
    cancha      INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Participación de parejas en grupos (con posición final)
CREATE TABLE parejas_grupo (
    grupo_id    UUID REFERENCES grupos(id) ON DELETE CASCADE,
    nombre      TEXT NOT NULL,
    posicion    INTEGER,  -- 1°, 2°, 3°
    PRIMARY KEY (grupo_id, nombre)
);

-- Partidos de fase de grupos
CREATE TABLE partidos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grupo_id    UUID REFERENCES grupos(id) ON DELETE CASCADE,
    pareja1     TEXT NOT NULL,
    pareja2     TEXT NOT NULL,
    resultado   JSONB  -- sets, games, ganador
);

-- Partidos de finales
CREATE TABLE partidos_finales (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    torneo_id   UUID REFERENCES torneos(id) ON DELETE CASCADE,
    categoria   TEXT NOT NULL,
    fase        TEXT NOT NULL,  -- 'Octavos de Final', 'Cuartos de Final', etc.
    pareja1     TEXT,
    pareja2     TEXT,
    ganador     TEXT
);
```

**Estrategia de migración:** El blob se mantiene como cache de lectura rápida para el dashboard. Las tablas relacionales serán la fuente de verdad para ranking y consultas históricas. Al archivar un torneo, poblar ambos.

---

### Fase 3: Ranking Anual por Categoría
**Prerequisito:** Completar refactor blob → tablas relacionales primero.

**Objetivo:** Ranking anual acumulado — cada categoría tiene su propio leaderboard

- El ranking es **ANUAL**: los puntos se acumulan torneo a torneo a lo largo del año
- Cada categoría tiene su tabla de posiciones independiente
- Crear tabla `puntos_historicos`
- Nuevo blueprint: `api/routes/ranking.py`
  - `GET /ranking` → leaderboard público con tabs por categoría; filtro por año
  - `GET /ranking/<categoria>` → tabla de una categoría específica
  - `POST /api/admin/puntos/asignar` → admin asigna puntos al finalizar torneo
- Templates: `ranking.html` (tabs por categoría), `mis_puntos.html` (historial del jugador)
- Fórmula inicial: 1°=10pts, 2°=7pts, 3°=5pts, participación=2pts
- Agregar "Ranking" al nav de jugador y público

---

## Archivos que NO tocar
- `core/algoritmo.py`, `core/clasificacion.py`, `core/fixture_*.py`
- `utils/csv_processor.py`, `utils/calendario_builder.py`, `utils/exportador.py`
- `gunicorn.conf.py`, `render.yaml`
- `api/routes/parejas.py`, `api/routes/finales.py`, `api/routes/resultados.py`, `api/routes/calendario.py`
