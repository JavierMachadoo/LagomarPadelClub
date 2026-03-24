# Roadmap — Algoritmo-Torneos

## Estado actual del sistema

Plataforma funcional con flujo completo: inscripciones → grupos → resultados → historial.
Próximo objetivo: sistema de invitación de compañero (vincular ambos jugadores por cuenta).

**Implementado:**
- State machine del torneo (`inscripcion` ↔ `torneo` → `finalizado`)
- Inscripciones de jugadores con auto-asignación
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

### Paso 1 — Sistema de Invitación de Compañero ← ACTUAL

**Problema:** Hoy Player B es solo texto (`integrante2`). No tiene vínculo con su cuenta, no puede ver sus partidos ni acumular ranking.

**Solución:** Ambos jugadores crean cuenta. Player A invita a Player B (por búsqueda de teléfono o link compartible). Player B acepta y quedan vinculados por UUID.

**Decisiones tomadas:**

| Decisión | Opción | Razón |
|---|---|---|
| Identificación de Player B | UUID de Supabase Auth (no nombre/apellido) | Homónimos, typos, ranking confiable |
| Búsqueda de compañero | Por teléfono | WhatsApp es el medio de comunicación natural |
| Link compartible | Abierto (cualquier registrado puede aceptar) | Máxima simplicidad, el link se comparte de forma privada |
| Expiración de invitación | 48 horas, verificación lazy | Sin cron jobs, simple para la escala actual |
| Si Player B rechaza | Se cancela la inscripción | Decisión del usuario |

**Migración SQL:**
```sql
ALTER TABLE inscripciones ADD COLUMN jugador2_id UUID REFERENCES jugadores(id);
CREATE UNIQUE INDEX idx_unique_jugador2_torneo
  ON inscripciones(torneo_id, jugador2_id) WHERE jugador2_id IS NOT NULL;

CREATE TABLE invitacion_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inscripcion_id UUID NOT NULL REFERENCES inscripciones(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,
    expira_at TIMESTAMPTZ NOT NULL,
    usado BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION expirar_invitaciones(p_torneo_id UUID)
RETURNS void AS $$
  UPDATE inscripciones i SET estado = 'cancelada'
  WHERE i.torneo_id = p_torneo_id AND i.estado = 'pendiente_companero'
    AND NOT EXISTS (
      SELECT 1 FROM invitacion_tokens t
      WHERE t.inscripcion_id = i.id AND t.expira_at > NOW() AND t.usado = FALSE
    );
$$ LANGUAGE sql;
```

**Nuevos endpoints:**
- `GET /api/jugadores/buscar?telefono=XXX` — buscar compañero por teléfono (enmascarado)
- `GET /api/inscripcion/invitaciones-pendientes` — Player B ve sus invitaciones
- `POST /api/inscripcion/<id>/aceptar` — Player B acepta
- `POST /api/inscripcion/<id>/rechazar` — Player B rechaza (cancela inscripción)
- `GET /inscripcion/invitar?token=XXX` — página de invitación por link

**Cambios en endpoints existentes:**
- `POST /api/inscripcion` — acepta `jugador2_id` opcional, genera token, estado `pendiente_companero`
- `POST /api/auth/register` — acepta `invite_token` opcional para auto-aceptar post-registro

**Frontend:**
- `inscripcion.html` — reemplazar campo texto integrante2 por búsqueda + invitación
- `invitacion.html` — **nuevo**, página de invitación por link
- `base.html` — badge de notificación para invitaciones pendientes

**Flujo completo:**
```
Player A → busca compañero por teléfono
  → Encontrado: invita directamente (jugador2_id)
  → No encontrado: genera link compartible (WhatsApp)
Inscripción: estado "pendiente_compañero"
Player B → ve invitación in-app O abre link
  → Acepta: estado → "confirmado", auto-asigna en grupos
  → Rechaza: inscripción cancelada
  → 48h sin respuesta: invitación expira, inscripción cancelada
```

**Archivos a modificar:**
- `api/routes/inscripcion.py` (alta complejidad)
- `web/templates/inscripcion.html` (media)
- `web/templates/invitacion.html` (nuevo, baja)
- `api/routes/auth_jugador.py` (baja)
- `main.py` (baja)
- `web/templates/base.html` (baja)
- `supabase_schema.sql` (documentación)

---

### Paso 2 — Ranking Anual por Categoría

**Prerequisito:** tablas relacionales disponibles — ya hecho. Sistema de invitaciones — Paso 1.

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
