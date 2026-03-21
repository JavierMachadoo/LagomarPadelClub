# Repository Guidelines

## How to Use This Guide

- Start here for project norms and architecture context.
- All routes, models, and storage patterns are described in the Architecture section.
- Component docs (if added) override this file when guidance conflicts.

## Available Skills

Use these skills for detailed patterns on-demand:

### Business Logic Skills (`skills/business-logic/`)
Lógica específica del dominio — no reemplazable por skills genéricas.

| Skill | Description | File |
|-------|-------------|------|
| `algoritmo-torneos` | Backtracking, scoring de compatibilidad, fallback greedy | [SKILL.md](skills/business-logic/algoritmo-torneos.md) |
| `torneo-storage` | Single-tournament model, cache TTL, Supabase/JSON fallback | [SKILL.md](skills/business-logic/torneo-storage.md) |
| `modelos-torneos` | Dataclasses, serialización, Grupo/Pareja/ResultadoPartido | [SKILL.md](skills/business-logic/modelos-torneos.md) |
| `csv-torneos` | Procesamiento CSV/Excel, normalización de columnas | [SKILL.md](skills/business-logic/csv-torneos.md) |
| `supabase-torneos` | Upsert JSONB, detección de backend, schema de una sola fila, fallback graceful | [SKILL.md](skills/business-logic/supabase-torneos.md) |
| `dataclasses-torneos` | to_dict/from_dict en par, Enum.value, field(default_factory), .get() con default | [SKILL.md](skills/business-logic/dataclasses-torneos.md) |

### Stack Skills (`skills/stack/`)
Patrones del stack tecnológico — complementan las skills instaladas globalmente.

| Skill | Description | File |
|-------|-------------|------|
| `flask-torneos` | JWT middleware, blueprints, respuestas API | [SKILL.md](skills/stack/flask-torneos.md) |
| `frontend-torneos` | Jinja2, Bootstrap 5, JWT helper, Toast notifications | [SKILL.md](skills/stack/frontend-torneos.md) |
| `pytest-torneos` | Fixtures Flask, mock storage, parametrize por categoría | [SKILL.md](skills/stack/pytest-torneos.md) |
| `commit-torneos` | git add . + commit con mensaje conventional commits en español | [SKILL.md](skills/stack/commit-torneos.md) |
| `skill-creator` | Crear nuevas skills con el formato estándar del proyecto | [SKILL.md](skills/stack/skill-creator.md) |
| `debug-torneos` | Inspeccionar estado del torneo, reproducir algoritmo, testear endpoints con curl | [SKILL.md](skills/stack/debug-torneos.md) |
| `security-torneos` | JWT HttpOnly cookies, validación de CSV upload, XSS con tojson, rutas públicas | [SKILL.md](skills/stack/security-torneos.md) |

### Generic Skills (Any Project)
Instaladas globalmente vía `npx skills`.

| Skill | Description |
|-------|-------------|
| `tdd` | Test-Driven Development workflow |
| `simplify` | Review changed code for reuse, quality, and efficiency |
| `pytest` | Pytest avanzado: fixtures, parametrize, mocking, async (instalada globalmente) |

### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|
| Modifying routes or API endpoints | `flask-torneos` |
| Modifying group formation algorithm or compatibility scoring | `algoritmo-torneos` |
| Modifying storage layer or tournament persistence | `torneo-storage` |
| Modifying data models or adding new domain entities | `modelos-torneos` |
| Modifying Jinja2 templates or frontend JS | `frontend-torneos` |
| Modifying CSV import or file upload processing | `csv-torneos` |
| Writing or modifying tests | `pytest-torneos` |
| Creating a new skill file | `skill-creator` |
| Committing changes | `commit-torneos` |
| Fixing a bug | `tdd` |
| Implementing a feature | `tdd` |
| Refactoring code | `tdd` |
| Reviewing code quality | `simplify` |
| Modifying Supabase schema or queries | `supabase-torneos` |
| Adding fields to existing models or modifying serialization in core/models.py | `dataclasses-torneos` |
| Debugging algorithm output or tournament state | `debug-torneos` |
| Modifying authentication, file upload validation, or rendering user data in templates | `security-torneos` |

---

## Project Overview

Flask web application for managing padel tennis tournaments. Optimizes group formation (triplets of 3 couples) based on schedule compatibility, then generates match fixtures and finals brackets.

| Component | Location | Tech Stack |
|-----------|----------|------------|
| Core Algorithm | `core/algoritmo.py` | Python, combinatorial optimization |
| Models | `core/models.py` | Python dataclasses |
| Storage | `utils/torneo_storage.py` | Supabase (JSONB) / local JSON fallback |
| API Blueprints | `api/routes/` | Flask, JWT auth |
| Frontend | `web/templates/`, `web/static/` | Bootstrap 5, vanilla JS |
| ⚠️ Template grande | `web/templates/dashboard.html` | ~216KB con lógica embebida — usar Grep antes de editar |
| Configuration | `config/` | `.env`, categories, time slots |

---

## Architecture

### Request Flow
1. All routes require JWT auth (checked in middleware in `main.py`)
2. JWT token stored in HttpOnly cookie, 2-hour expiry
3. Routes: `/` (home/upload), `/admin` (panel admin), `/dashboard` (jugador), `/grupos` (grupos públicos), `/calendario` (calendario público), `/finales` (bracket), `/api/*` (REST)

### Storage (`utils/torneo_storage.py`)
- Single-tournament model — one `torneo_actual` per instance
- Uses Supabase (JSONB) if env vars present, otherwise falls back to local JSON files in `data/torneos/`
- In-memory cache with 5-second TTL
- **Gunicorn is configured to 1 worker** to prevent cache staleness — do not increase worker count

### Core Algorithm (`core/algoritmo.py`)
- `AlgoritmoGrupos` forms groups of 3 couples based on schedule slot overlap (compatibility scoring)
- Uses optimization for 2–6 groups; falls back to greedy algorithm for edge cases
- Returns `ResultadoAlgoritmo` with groups, unassigned pairs, calendar, and statistics

### Key Models (`core/models.py`)
- `Pareja` — a couple with category, phone, and available `franjas_horarias` (time slots)
- `Grupo` — 3 couples, holds matches and results
- `ResultadoPartido` — set scores with tiebreak support
- `FaseFinal` enum — octavos, cuartos, semifinal, final

### Configuration (`config/`)
- `settings.py` — loads `.env`, defines categories (Tercera–Séptima) and time slots (Viernes/Sábado 18:00, 21:00, etc.)
- `config/__init__.py` — exports `CATEGORIAS`, `FRANJAS_HORARIAS`, tournament type groupings (`fin1`/`fin2`), and UI color/emoji mappings

### Data Flow for CSV Import
1. User uploads CSV via `/` (inicio page)
2. `utils/csv_processor.py` parses it into `Pareja` objects
3. `AlgoritmoGrupos` groups them into triplets
4. Result stored via `TorneoStorage`
5. `/grupos` renders grupos públicos con standings; `/finales` renders bracket; `/dashboard` renders vista del jugador

### API Blueprints (`api/routes/`)
- `parejas.py` — CRUD for couples/pairs
- `finales.py` — finals fixture management
- `grupos.py` — group generation from confirmed inscriptions
- `inscripcion.py` — player registration for active tournament
- `auth_jugador.py` — Supabase Auth (email/password + Google OAuth)
- `historial.py` — tournament archiving and historical views
- `calendario.py` — public calendar view blueprint

### Frontend
- Bootstrap 5, vanilla JS, mobile-first CSS
- `web/static/js/jwt-helper.js` — handles token refresh and attaches auth headers
- `web/static/js/toast.js` — notification system
- Templates son grandes: `dashboard.html` (~216KB), `homePanel.html` (~64KB), `finales.html` (~59KB) — embed significant logic
- `web/static/js/app.js` — lógica JS principal de la aplicación

---

## Development Commands

```bash
# Run locally
python main.py

# Run with gunicorn (production-like)
gunicorn main:app --config gunicorn.conf.py

# Generate test data
python generar_datos_prueba.py

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Run tests for a specific module
pytest tests/test_algoritmo.py -v

# Run tests with coverage
pytest --cov=core --cov=utils --cov-report=term-missing
```

### Environment Setup
Copy `.env` and set:
- `SECRET_KEY` — JWT signing key
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` — login credentials
- `SUPABASE_URL` / `SUPABASE_ANON_KEY` — Supabase project URL and anon key
- `SUPABASE_SERVICE_ROLE_KEY` — required for auth operations (register/login jugadores); present in Render env vars
- `DEBUG` — True/False

**Dev/Prod setup:**
- Local `.env` → apunta a `LagomarPadelDB-Dev` (`slwzrxsjxfboojpkozey`)
- Render env vars → apuntan a `LagomarPadelDB` prod (`mxftowqqjyktxricdemd`) — no tocar

**Keep-alive:**
- Render + Supabase prod: UptimeRobot pinga `/_health` cada 5 min (endpoint hace query real)
- Supabase dev: `pg_cron` interno corre cada 5 días (`keep_alive_dev`)

---

## CSV Format

```
Nombre,Teléfono,Categoría,Viernes 18:00,Viernes 21:00,Sábado 09:00,...
Pareja Ejemplo,600123456,Tercera,Sí,No,Sí,...
```
Time slot columns use `Sí`/`No` values.

---

## Commit & Pull Request Guidelines

Follow conventional-commit style: `<type>[scope]: <description>`

**Types:** `feat`, `fix`, `docs`, `chore`, `perf`, `refactor`, `style`, `test`

Before creating a PR:
1. Run the app locally and verify the affected flow end-to-end
2. Check that existing CSV import and group formation still work
3. Link screenshots for UI changes

---

## Roadmap

El plan de evolución arquitectónica (vistas públicas, registro de jugadores, inscripciones, ranking, historial) está documentado en `roadMap.md`.