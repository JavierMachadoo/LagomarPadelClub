# Plan: Evolución Arquitectónica — Algoritmo-Torneos

## Contexto
El sistema actual es una herramienta de administración de torneos de pádel exclusiva para un admin. El objetivo es convertirla en una plataforma web donde jugadores puedan inscribirse, ver sus grupos/calendario/ranking, mientras el admin conserva el panel de gestión actual.

---

## Decisiones de Arquitectura

| Decisión | Recomendación | Razón |
|---|---|---|
| Auth jugadores | **Supabase Auth** (email + contraseña) | Ya usan Supabase; maneja JWT, refresh, password reset gratis |
| Google OAuth | Posponer a Fase 3 o no implementar | Complejidad extra de OAuth sin suficiente beneficio inicial |
| Frontend | **Mantener Jinja2 + Bootstrap 5** | 5 templates no justifican React; no separar repos |
| Repo separado para frontend | **No** | Dos servicios Render + CORS + dos repos = overhead puro para un solo dev |
| Admin auth | **Mantener JWT custom** a corto plazo | Cero riesgo; se retira en Fase 5 |
| Base de datos | **Migración incremental** (tablas nuevas junto al blob) | No romper lo que funciona |
| Deployment | **Único servicio Render** | Sin razón para dividir |

---

## Modelo de Estados del Torneo

El admin controla el estado desde homePanel. La transición es **unidireccional** (con modal de confirmación):

```
inscripcion → torneo → finalizado
```

| Estado | Jugador puede | Admin puede | Público ve |
|---|---|---|---|
| `inscripcion` | Inscribirse | Organizar grupos en privado, generar/re-generar | "Organizando torneo" |
| `torneo` | Ver grupos, calendario, finales, ranking | Ingresar resultados **solo** (grupos bloqueados) | Todo visible |
| `finalizado` | Ver histórico | Archivar y limpiar | Histórico |

---

## Navegación por Rol

```
Público (sin login):     Grupos | Finales | Calendario
Jugador logueado:        Grupos | Finales | Calendario | Ranking | Inscribirse / Mi Inscripción
Admin:                   Todo lo anterior + Panel Admin
```

---

## Nuevas Tablas Supabase

```sql
-- Historial de torneos (reemplaza torneo_actual como fuente de IDs)
CREATE TABLE torneos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre      TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('fin1', 'fin2')),
    estado      TEXT DEFAULT 'inscripcion' CHECK (estado IN ('inscripcion','torneo','finalizado')),
    datos_blob  JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Inscripciones a torneos
CREATE TABLE inscripciones (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    torneo_id           UUID REFERENCES torneos(id) ON DELETE CASCADE,
    jugador_id          UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    integrante1         TEXT NOT NULL,
    integrante2         TEXT NOT NULL,
    telefono            TEXT,
    categoria           TEXT NOT NULL,
    franjas_disponibles TEXT[] NOT NULL DEFAULT '{}',
    estado              TEXT DEFAULT 'confirmado' CHECK (estado IN ('pendiente','confirmado','rechazado')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(torneo_id, jugador_id)
);

-- Puntos anuales por torneo y categoría
CREATE TABLE puntos_historicos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jugador_id  UUID REFERENCES jugadores(id) ON DELETE CASCADE,
    torneo_id   UUID REFERENCES torneos(id) ON DELETE CASCADE,
    categoria   TEXT NOT NULL,
    posicion    INTEGER,
    puntos      INTEGER NOT NULL DEFAULT 0,
    anio        INTEGER NOT NULL DEFAULT EXTRACT(YEAR FROM NOW()),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(jugador_id, torneo_id, categoria)
);
```

---

## Formulario de Inscripción

Campos (un solo jugador registra a la pareja):
- Nombre y apellido — Integrante 1 (pre-rellenado con el jugador logueado)
- Nombre y apellido — Integrante 2
- Celular de contacto
- Categoría (dinámica según `tipo_torneo`: fin1→Cuarta/Sexta, fin2→Tercera/Quinta/Séptima)
- Preferencia horaria — seleccionar al menos 2 (Viernes 18:00, Viernes 21:00, Sábado 09:00, Sábado 12:00, Sábado 16:00, Sábado 19:00)

---

## Roadmap por Fases

### Fase 0: State Machine + Fundación (2-3 días) ← SIGUIENTE
**Objetivo:** Estado del torneo controlado por admin; visibilidad condicional por estado

- Crear tabla `torneos` en Supabase
- Migrar `torneo_actual` → fila en `torneos` (el blob existente pasa a `datos_blob`)
- Extender `TorneoStorage`: leer/escribir `estado` ('inscripcion'|'torneo'|'finalizado')
- homePanel: botones de transición de estado con modal de confirmación
- Middleware `main.py`: inyectar `estado_torneo` en context processor
- Rutas `/grupos`, `/finales`, `/calendario` muestran "Organizando torneo" si estado != 'torneo'
- Nav: renombrar "Torneo" → "Grupos"; agregar "Finales" al nav público

### Fase 1: Inscripciones (3-4 días)
**Objetivo:** Jugador logueado se inscribe; admin genera grupos desde inscripciones

- Crear tabla `inscripciones` en Supabase
- Nuevo blueprint: `api/routes/inscripcion.py`
  - `GET /inscripcion` → formulario (solo disponible si estado='inscripcion')
  - `POST /api/inscripcion` → INSERT en inscripciones
  - `GET /api/inscripcion/mis-datos` → datos guardados del jugador
  - `DELETE /api/inscripcion` → cancelar inscripción (solo si estado='inscripcion')
- Templates: `inscripcion.html`, `mi_inscripcion.html`
- Panel admin: lista de inscripciones con estado (pendiente/confirmado/rechazado)
- Adaptar `/api/ejecutar-algoritmo`: leer de `inscripciones` confirmadas → algoritmo existente sin cambios
- Guardar `inscripcion_id` en el dict de cada Pareja generada (para lookup "Mi Grupo")
- Admin puede re-generar libremente mientras estado='inscripcion'
- En estado='torneo': botón "Generar Grupos" desaparece; grupos bloqueados

### Fase 2: Vista del Jugador (2-3 días)
**Objetivo:** Jugador ve su grupo y calendario personal cuando el torneo está activo

- `GET /mi-grupo` → lookup por `inscripcion_id` en el resultado del algoritmo
- `GET /mi-calendario` → filtrar calendario por la franja del grupo del jugador
- Templates: `mi_grupo.html`, `mi_calendario.html`
- Durante estado != 'torneo': mostrar "El torneo está en organización, pronto verás tu grupo"

### Fase 3: Ranking Anual por Categoría (3-4 días)
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

### Fase 4: Historial de Torneos (2-3 días)
**Objetivo:** Archivar torneos anteriores antes de limpiar

- `TorneoStorage.archivar()` → migra datos a `torneos` histórico
- `limpiar()` llama `archivar()` antes de borrar
- Rutas públicas: `/torneos` (lista) y `/torneos/<id>` (resultados archivados)

---

## Archivos Críticos

| Archivo | Cambio | Fase |
|---|---|---|
| `utils/torneo_storage.py` | Soporte tabla `torneos`, leer/escribir `estado` | 0 |
| `main.py:84-119` | Middleware: visibilidad condicional por estado, inyectar `estado_torneo` | 0 |
| `web/templates/base.html` | Nav renombrado + condicional por rol y estado | 0 |
| `web/templates/homePanel.html` | Controles de transición de estado con confirmación | 0 |
| `api/routes/grupos.py` | Adaptar "Generar Grupos" para leer desde `inscripciones` | 1 |
| `api/routes/inscripcion.py` | NUEVO blueprint | 1 |
| `core/models.py` | Agregar `inscripcion_id` a Pareja (con skill dataclasses-torneos) | 1 |

## Archivos que NO tocar
- `core/algoritmo.py`, `core/clasificacion.py`, `core/fixture_*.py`, `core/models.py` (salvo `inscripcion_id`)
- `utils/csv_processor.py`, `utils/calendario_builder.py`, `utils/exportador.py`
- `gunicorn.conf.py`, `render.yaml`
- `api/routes/parejas.py`, `api/routes/finales.py`, `api/routes/resultados.py`, `api/routes/calendario.py`

---

## Verificación por Fase
- **Fase 0:** Admin cambia estado desde homePanel. Abrir incógnito en `/grupos` → ver "Organizando". Cambiar a 'torneo' → ver grupos reales. Nav muestra "Grupos" y "Finales".
- **Fase 1:** Jugador se inscribe → aparece en panel admin. Admin genera grupos desde inscripciones → mismo output que con CSV. `inscripcion_id` presente en cada Pareja.
- **Fase 2:** Jugador logueado ve `/mi-grupo` con sus datos. Durante inscripcion → placeholder. Durante torneo → grupo real.
- **Fase 3:** Admin asigna puntos al finalizar → `/ranking` muestra tabla anual por categoría con tabs.
- **Fase 4:** Admin archiva torneo → aparece en `/torneos` como historial.
