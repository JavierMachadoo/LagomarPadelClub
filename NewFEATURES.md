# Plan: Evolución Arquitectónica — Algoritmo-Torneos

## Contexto
El sistema actual es una herramienta de administración de torneos de pádel exclusiva para un admin. El usuario quiere convertirla en una plataforma web donde jugadores puedan inscribirse, ver resultados públicos y acumular puntos, mientras el admin conserva el panel de gestión actual.

---

## Recomendación: **Camino 2** (Solo torneos, sin landing del club)

**Por qué no el Camino 1:**
La página de información del club (home, fotos, copy) no tiene complejidad técnica pero consume tiempo de diseño/contenido. Se puede agregar en 2 horas después de tener lo importante. Construir lo difícil primero, lo fácil al final.

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

## Nuevas Tablas Supabase

```sql
-- Perfiles de jugadores (vinculado a Supabase Auth)
CREATE TABLE jugadores (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    nombre      TEXT NOT NULL,
    apellido    TEXT NOT NULL,
    telefono    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Inscripciones a torneos
CREATE TABLE inscripciones (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    torneo_id           UUID REFERENCES torneos(id) ON DELETE CASCADE,
    jugador_id          UUID REFERENCES jugadores(id) ON DELETE CASCADE,
    categoria           TEXT NOT NULL,
    franjas_disponibles TEXT[] NOT NULL DEFAULT '{}',
    compañero_nombre    TEXT,
    compañero_id        UUID REFERENCES jugadores(id),
    estado              TEXT DEFAULT 'pendiente' CHECK (estado IN ('pendiente','confirmado','rechazado')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(torneo_id, jugador_id)
);

-- Historial de torneos (para archivar cuando se cierra un torneo)
CREATE TABLE torneos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre      TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('fin1', 'fin2')),
    estado      TEXT DEFAULT 'creando' CHECK (estado IN ('creando','en_curso','finalizado')),
    datos_blob  JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Puntos por torneo y categoría
CREATE TABLE puntos_historicos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jugador_id  UUID REFERENCES jugadores(id) ON DELETE CASCADE,
    torneo_id   UUID REFERENCES torneos(id) ON DELETE CASCADE,
    categoria   TEXT NOT NULL,
    posicion    INTEGER,
    puntos      INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(jugador_id, torneo_id)
);
```

---

## Roadmap por Fases

### Fase 1: Vistas Públicas (2-3 días) ← EMPEZAR AQUÍ
**Objetivo:** Cualquiera puede ver el torneo actual sin login.

- Modificar `main.py`: agregar rutas públicas `/grupos`, `/finales`, `/ranking`
- Crear `grupos_publico.html` (copia de `resultados.html` sin teléfono ni franjas)
- Crear `finales_publico.html` (copia de `finales.html` sin datos privados)
- Modificar middleware `verificar_autenticacion` en `main.py:67-86` para permitir rutas públicas
- Actualizar `base.html`: navbar condicional según `g.usuario`
- **Riesgo: cero.** Solo se agregan rutas. El panel admin no cambia.

### Fase 2: Registro y Login de Jugadores (4-5 días)
**Objetivo:** Jugadores crean cuenta y se logean.

- Agregar `SUPABASE_SERVICE_ROLE_KEY` a env vars
- Crear tabla `jugadores` en Supabase
- Nuevo blueprint: `api/routes/auth.py`
  - `POST /api/auth/register` → `supabase.auth.sign_up()`
  - `POST /api/auth/login` → `supabase.auth.sign_in_with_password()`
  - `POST /api/auth/logout`
- Nuevas templates: `registro.html`, extender `login.html` con opción jugador/admin
- Extender `utils/api_helpers.py:verificar_autenticacion_api()` para aceptar Supabase JWTs
- Admin sigue usando su flujo actual (JWT custom) sin cambios

### Fase 3: Inscripciones (3-4 días)
**Objetivo:** Jugador logueado se inscribe al próximo torneo.

- Crear tabla `inscripciones` en Supabase
- Nuevo blueprint: `api/routes/inscripcion.py`
  - `GET /inscripcion` → formulario (categoría + franjas)
  - `POST /api/inscripcion` → graba en `inscripciones`
  - `GET /api/inscripcion/mis-datos` → datos guardados del jugador
- Templates: `inscripcion.html`, `mi_inscripcion.html`
- Panel admin: nueva vista para revisar/confirmar inscripciones y exportar CSV
- El flujo del algoritmo (CSV → grupos) se mantiene igual; admin controla cuándo correrlo

### Fase 4: Puntos y Ranking (3-4 días)
**Objetivo:** Ranking público de jugadores por categoría.

- Crear tablas `torneos` y `puntos_historicos`
- Nuevo blueprint: `api/routes/ranking.py`
  - `GET /ranking` → leaderboard público por categoría
  - `POST /api/admin/puntos/asignar` → admin asigna puntos al cerrar torneo
- Templates: `ranking.html`, `mis_puntos.html`
- Fórmula inicial: 1°=10pts, 2°=7pts, 3°=5pts, participación=2pts

### Fase 5: Historial de Torneos (2-3 días)
**Objetivo:** Archivar torneos anteriores antes de limpiar.

- Agregar `TorneoStorage.archivar()` en `utils/torneo_storage.py`
- `limpiar()` llama `archivar()` antes de borrar
- Rutas públicas: `/torneos` (lista) y `/torneos/<id>` (resultados archivados)

---

## Archivos Críticos

| Archivo | Cambio |
|---|---|
| `main.py:67-86` | Middleware auth: soporte anónimo/jugador/admin |
| `utils/api_helpers.py` | `verificar_autenticacion_api()`: aceptar Supabase JWTs |
| `utils/torneo_storage.py` | Agregar `archivar()` en Fase 5 |
| `web/templates/base.html` | Navbar role-aware con `g.usuario` |
| `config/settings.py` | Agregar `SUPABASE_SERVICE_ROLE_KEY` |

## Archivos que NO tocar
- `core/algoritmo.py`, `core/clasificacion.py`, `core/fixture_*.py`, `core/models.py`
- `utils/calendario_builder.py`, `utils/csv_processor.py`, `utils/exportador.py`
- `gunicorn.conf.py`, `render.yaml`
- `api/routes/parejas.py`, `api/routes/finales.py` (solo extender, no modificar lógica existente)

---

## Refactor Pendiente (independiente de las fases)
`api/routes/parejas.py` tiene ~1900 líneas. Dividir en:
- `parejas.py` → carga, CRUD de parejas
- `grupos.py` → algoritmo, asignaciones, edición de grupos
- `resultados.py` → actualización de resultados, posiciones
- `calendario.py` → generación y consulta de calendario

Esto no afecta funcionalidad, solo mantenibilidad. Hacerlo antes de la Fase 3.

---

## Verificación por Fase
- **Fase 1:** Abrir incógnito, navegar a `/grupos` y `/finales` sin login → deben mostrar datos sin teléfonos. Admin panel sigue funcionando con login.
- **Fase 2:** Registrar jugador con email, confirmar en Supabase Auth dashboard, login como jugador → ver navbar diferente al admin.
- **Fase 3:** Jugador logueado puede inscribirse. Admin ve inscripciones en panel y puede exportar CSV.
- **Fase 4:** Después de cerrar torneo, admin asigna puntos. `/ranking` muestra tabla pública.
- **Fase 5:** Al limpiar torneo, aparece en `/torneos` como historial.
