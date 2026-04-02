# Skill Registry — algoritmo-torneos

## Compact Rules

### algoritmo-torneos
When modifying `core/algoritmo.py` or group formation logic.
- `AlgoritmoGrupos` uses combinatorial optimization for 2–6 groups, falls back to greedy
- Compatibility scoring in `_calcular_compatibilidad` returns (score, franja)
- Always return `ResultadoAlgoritmo` — never raw lists
- Do NOT change scoring weights without consulting the owner

### torneo-storage
When modifying `utils/torneo_storage.py` or storage layer.
- Single-tournament model — one `torneo_actual` per instance
- In-memory cache with 5s TTL; Gunicorn: 1 worker local, 2 workers prod (Railway) — stale reads bounded to TTL
- Use `guardar_con_version()` for all external writes (optimistic locking)
- Supabase service role key bypasses RLS; anon key is blocked

### modelos-torneos
When modifying `core/models.py` or adding domain entities.
- All dataclasses implement `to_dict()` / `from_dict()` manually
- Enum fields serialize as `.value` in `to_dict()`
- Use `field(default_factory=list)` for list fields, never mutable defaults
- `from_dict()` uses `.get()` with defaults — never assumes key presence

### flask-torneos
When modifying routes or API endpoints in `api/routes/`.
- All routes require JWT auth via middleware in `main.py`
- JWT stored in HttpOnly cookie — NEVER move to localStorage or response body
- Blueprints registered in `main.py`; handlers should be ≤15 lines
- Return `jsonify(...)` with explicit HTTP status codes

### frontend-torneos
When modifying Jinja2 templates or frontend JS.
- `dashboard.html` is ~248KB — use Grep to find exact block before editing
- Bootstrap 5, vanilla JS, mobile-first CSS
- Use `{{ value | tojson }}` for rendering Python data to JS (XSS-safe)
- Toast notifications via `web/static/js/toast.js`

### pytest-torneos
When writing or modifying tests.
- Use pytest fixtures from `conftest.py` for Flask app and storage
- Mock storage with `unittest.mock.patch` for unit tests
- Use `@pytest.mark.parametrize` for category-based tests
- Run: `pytest` / `pytest --cov=core --cov=utils --cov-report=term-missing`

### supabase-torneos
When modifying Supabase schema or queries.
- Always use `SUPABASE_SERVICE_ROLE_KEY` — anon key blocked by RLS
- Single-row JSONB pattern: upsert by `id = 1`
- Graceful fallback to local JSON in `data/torneos/` if env vars missing

### dataclasses-torneos
When adding fields to models or modifying serialization in `core/models.py`.
- Always update BOTH `to_dict()` AND `from_dict()` when adding a field
- Enum → `.value` in `to_dict()`, `EnumClass(raw)` in `from_dict()`
- `Optional` fields: use `.get('field', default)` in `from_dict()`

### csv-torneos
When modifying CSV import or file upload processing.
- Entry: `utils/csv_processor.py` → parses to `Pareja` objects
- Normalize column names (strip, lowercase) before matching
- Validate `Sí`/`No` values for time slots

### security-torneos
When modifying auth, file upload validation, or rendering user data in templates.
- JWT in HttpOnly cookie — no JS access by design
- File uploads: validate extension AND content (not just MIME type)
- Use `{{ value | tojson }}` never `{{ value }}` for user-controlled data
- Rate limits: login 5/min, registration 3/min (flask-limiter)

### commit-torneos
When committing changes.
- `git add .` then conventional commit in Spanish
- Format: `<type>[scope]: <descripción en español>`
- Types: feat, fix, docs, chore, perf, refactor, style, test

### debug-torneos
When debugging algorithm output or tournament state.
- Inspect state via storage singleton: `from utils.torneo_storage import storage`
- Reproduce algorithm: instantiate `AlgoritmoGrupos` with test `Pareja` list
- Test endpoints with curl + JWT cookie

---

## User Skills Trigger Table

| Trigger Context | Skill |
|----------------|-------|
| Modifying routes or API endpoints | `flask-torneos` |
| Modifying group formation algorithm | `algoritmo-torneos` |
| Modifying storage layer or tournament persistence | `torneo-storage` |
| Modifying data models or domain entities | `modelos-torneos` |
| Modifying Jinja2 templates or frontend JS | `frontend-torneos` |
| Modifying CSV import or file upload | `csv-torneos` |
| Writing or modifying tests | `pytest-torneos` |
| Committing changes | `commit-torneos` |
| Fixing a bug | `tdd` (global) |
| Implementing a feature | `tdd` (global) |
| Reviewing code quality | `simplify` (global) |
| Modifying Supabase schema or queries | `supabase-torneos` |
| Adding fields to models or serialization | `dataclasses-torneos` |
| Modifying auth, upload validation, user data render | `security-torneos` |
| Debugging algorithm output or tournament state | `debug-torneos` |
| Creating a new skill file | `skill-creator` |
| Creating a GitHub issue | `issue-creation` (global) |
| Creating a pull request | `branch-pr` (global) |
| Adversarial code review | `judgment-day` (global) |

---

## Convention Files

- `agents.md` — project norms, architecture, auto-invoke trigger table
- `CLAUDE.md` (project) — critical constraints (Gunicorn workers, JWT, RLS, dashboard.html)
- `~/.claude/CLAUDE.md` (global) — persona, language rules, behavior
