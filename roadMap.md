# Roadmap — Algoritmo-Torneos

## Estado actual del sistema

Plataforma funcional con flujo completo: inscripciones → grupos → resultados → historial.
Próximo objetivo: estado `espera` entre torneos para mostrar calendario del club y próximo torneo.

**Implementado:**
- State machine del torneo (`inscripcion` ↔ `torneo` → `finalizado`)
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
| Base de datos | Migración incremental (tablas nuevas junto al blob) | No romper lo que funciona |
| Deployment | Único servicio Render | Sin razón para dividir |

---

## Tablas Supabase actuales

```sql
torneo_actual   (id, datos JSONB)                          -- 1 fila, estado mutable
torneos         (id, nombre, tipo, estado, datos_blob JSONB, created_at)
inscripciones   (id, torneo_id, jugador_id, integrante1, integrante2,
                 telefono, categoria, franjas_disponibles, estado,
                 jugador2_id UUID, created_at)
invitacion_tokens (id, inscripcion_id, token, expira_at, usado, created_at)
grupos          (id, torneo_id, categoria, franja, cancha, created_at)
parejas_grupo   (grupo_id, nombre, posicion)               -- PK compuesta
partidos        (id, grupo_id, pareja1, pareja2, resultado JSONB)
partidos_finales(id, torneo_id, categoria, fase, pareja1, pareja2, ganador)
```

---

## Próximos pasos (en orden)

### Paso 1 — Estado `espera` entre torneos ← ACTUAL

**Problema:** Hoy al terminar un torneo el sistema salta directo a inscripciones. No hay un período "entre torneos" donde los jugadores consulten resultados del último torneo y vean cuándo es el próximo. El club publica un calendario anual y necesita mostrar esta info.

**Solución:** Nuevo estado `espera` en la máquina de estados. Al terminar un torneo se entra en espera; el admin configura fecha y categorías del próximo torneo; cuando esté listo abre inscripciones manualmente.

**Máquina de estados nueva:**
```
inscripcion ↔ torneo → (terminar+archivar) → espera → inscripcion
```

**Decisiones tomadas:**

| Decisión | Opción | Razón |
|---|---|---|
| Info del próximo torneo | Campo `proximo_torneo` en `torneo_actual` | Aprovecha storage existente, sin tabla nueva |
| Mostrar último torneo en espera | Guardar `ultimo_torneo_id` y cargar desde tabla `torneos` | Evita datos duplicados en `torneo_actual` |
| Transición espera → inscripcion | Admin dispara manualmente desde el panel | Mismo patrón que cambio de fase actual |
| Cuándo se configura próximo torneo | Durante el estado `espera` | Formulario en el panel admin |

**Comportamiento por vista durante `espera`:**

| Vista | Qué muestra |
|-------|-------------|
| `/grupos` | Datos del **último torneo archivado** con banner "Último torneo: [nombre]" |
| `/calendario` | Calendario del **último torneo archivado** con mismo banner |
| Pantalla principal (público) | "Próximo torneo: [fecha], [categorías]" |
| Tab inscripción (navbar) | **Oculto** |
| Panel admin | Badge "Entre Torneos" + form próximo torneo + botón "Abrir Inscripciones" |

**Cambios en storage (`utils/torneo_storage.py`):**
- `set_fase()` acepta `'espera'` como fase válida
- Nuevo método `transicion_a_espera(ultimo_torneo_id)` — limpia datos, genera nuevo UUID, pone fase `espera`, guarda referencia al último torneo
- `limpiar()` existente se usa solo para la transición espera → inscripcion
- Nuevos métodos: `set_proximo_torneo(fecha, categorias, descripcion)`, `get_proximo_torneo()`, `get_ultimo_torneo_id()`

**Nuevos endpoints:**
- `POST /api/admin/abrir-inscripciones` — transiciona de espera a inscripcion (llama `storage.limpiar()`)
- `POST /api/admin/proximo-torneo` — guarda fecha, categorías y descripción del próximo torneo
- `GET /api/proximo-torneo` — público, devuelve info del próximo torneo

**Cambios en endpoints existentes:**
- `POST /api/admin/terminar-torneo` — en vez de `storage.limpiar()`, llama `storage.transicion_a_espera(torneo_id)` para ir a espera
- `POST /api/cambiar-fase` — acepta `'espera'` como fase válida

**Cambios en rutas (`main.py`):**
- `/grupos` y `/calendario` — si fase == 'espera', cargar último torneo archivado y renderizar con flag `es_ultimo_torneo=True`

**Frontend:**
- `homePanel.html` — nuevo case para `espera`: badge "Entre Torneos", form próximo torneo, botón "Abrir Inscripciones". Mejorar label del input nombre al terminar → "Nombre para archivar el torneo"
- `base.html` — banner de próximo torneo cuando fase == 'espera'
- `grupos_publico.html` + `calendario_publico.html` — banner superior "Resultados del último torneo: [nombre]"
- `organizando.html` — manejo del estado espera con info de próximo torneo

**Archivos a modificar:**
- `utils/torneo_storage.py` (media complejidad)
- `api/routes/historial.py` (media)
- `api/routes/grupos.py` (baja)
- `main.py` (media)
- `web/templates/homePanel.html` (media)
- `web/templates/base.html` (baja)
- `web/templates/grupos_publico.html` (baja)
- `web/templates/calendario_publico.html` (baja)
- `web/templates/organizando.html` (baja)

**Edge case:** Si no hay último torneo archivado (primer uso), `/grupos` y `/calendario` muestran `organizando.html` normal.

---

### Paso 2 — Ranking Anual por Categoría

**Prerequisito:** tablas relacionales disponibles — ya hecho. Sistema de invitaciones — Paso 1 anterior (completado).

- Ranking **anual** acumulado, una tabla de posiciones por categoría
- Crear tabla `puntos_historicos`
- Blueprint `api/routes/ranking.py`
  - `GET /ranking` → leaderboard público con tabs por categoría + filtro por año
  - `GET /ranking/<categoria>` → tabla de una categoría específica
  - `POST /api/admin/puntos/asignar` → admin asigna puntos al finalizar torneo
- Templates: `ranking.html`, `mis_puntos.html` (historial del jugador)
- Fórmula inicial: 1°=10pts, 2°=7pts, 3°=5pts, participación=2pts
- Agregar "Ranking" al nav de jugador y público

---

## Archivos que NO tocar

- `core/algoritmo.py`, `core/clasificacion.py`, `core/fixture_*.py`
- `utils/csv_processor.py`, `utils/calendario_builder.py`, `utils/exportador.py`
- `gunicorn.conf.py`, `render.yaml`
- `api/routes/parejas.py`, `api/routes/finales.py`, `api/routes/resultados.py`, `api/routes/calendario.py`
