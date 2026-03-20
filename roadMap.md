# Roadmap — Algoritmo-Torneos

## Estado actual del sistema

Plataforma funcional con flujo completo: inscripciones → grupos → resultados → historial.
Próximo objetivo: ranking anual por categoría.

**Implementado:**
- State machine del torneo (`inscripcion` ↔ `torneo` → `finalizado`)
- Inscripciones de jugadores con auto-asignación
- Vistas públicas con filtros "Mi Grupo" y "Mi Calendario"
- Historial de torneos archivados (`/torneos`, `/torneos/<id>`)
- Navegación por rol (público / jugador / admin)

---

## Decisiones de Arquitectura

| Decisión | Opción elegida | Razón |
|---|---|---|
| Auth jugadores | Supabase Auth (email + contraseña) | Ya usan Supabase; maneja JWT, refresh, password reset gratis |
| Google OAuth | Posponer | Complejidad extra sin beneficio suficiente al inicio |
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
                 telefono, categoria, franjas_disponibles, estado, created_at)
```

---

## Próximos pasos (en orden)

### Paso 1 — Refactor blob → tablas relacionales

**Por qué primero:** el entorno actual no tiene usuarios reales. Conviene hacer el refactor sobre el único proyecto Supabase existente ahora, antes de crear dev/prod. Así cuando se cree el proyecto dev, nace directamente con el schema final y no hace falta migrarlo después.

**Por qué es necesario:** el ranking necesita consultas cross-torneo ("todos los partidos ganados por la pareja X en el año") — imposible sobre un JSONB blob sin deserializarlo entero.

**Qué crear:**
```sql
CREATE TABLE grupos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    torneo_id   UUID REFERENCES torneos(id) ON DELETE CASCADE,
    categoria   TEXT NOT NULL,
    franja      TEXT,
    cancha      INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE parejas_grupo (
    grupo_id    UUID REFERENCES grupos(id) ON DELETE CASCADE,
    nombre      TEXT NOT NULL,
    posicion    INTEGER,  -- 1°, 2°, 3°
    PRIMARY KEY (grupo_id, nombre)
);

CREATE TABLE partidos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grupo_id    UUID REFERENCES grupos(id) ON DELETE CASCADE,
    pareja1     TEXT NOT NULL,
    pareja2     TEXT NOT NULL,
    resultado   JSONB
);

CREATE TABLE partidos_finales (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    torneo_id   UUID REFERENCES torneos(id) ON DELETE CASCADE,
    categoria   TEXT NOT NULL,
    fase        TEXT NOT NULL,
    pareja1     TEXT,
    pareja2     TEXT,
    ganador     TEXT
);
```

**Estrategia:** el blob se mantiene como cache de lectura para el dashboard. Las tablas relacionales son la fuente de verdad para ranking y consultas históricas. Al archivar un torneo, poblar ambos.

---

### Paso 2 — Setup Dev/Prod Supabase

**Por qué después del refactor:** el proyecto `LagomarPadelDB-Dev` se crea con el schema final ya incorporado desde el día 1. No hay que migrarlo.

**Acciones:**
1. Crear proyecto `LagomarPadelDB-Dev` en Supabase
2. Ejecutar el schema completo en el proyecto dev (7 tablas ya definitivas)
3. Actualizar `.env` local para apuntar al proyecto dev
4. Prod Supabase queda intacto — Render sigue apuntando a él

**Variables locales (`.env`):**
```
SUPABASE_URL=<url del proyecto dev>
SUPABASE_ANON_KEY=<anon key del proyecto dev>
```

> `SUPABASE_SERVICE_ROLE_KEY` está en Render pero el código no la usa actualmente. No eliminarla.

---

### Paso 3 — Keep-Alive (Render + Supabase)

**Contexto:** el torneo se juega ~1 vez al mes. Pueden pasar semanas sin tráfico real:
- **Render free tier**: se duerme tras 15 min sin requests → cold start de ~30s
- **Supabase free tier**: pausa el proyecto tras 7 días sin actividad de API

**Problema con `/_health` actual:** solo devuelve `{'status': 'ok'}` sin consultar la BD. No sirve para mantener Supabase activo. Hay que modificarlo para hacer una query real — así un ping mantiene vivos tanto Render como Supabase de una sola vez.

**Estrategia:**

| Objetivo | Herramienta | Frecuencia |
|---|---|---|
| Render (prod) despierto | cron-job.org → `/_health` | Cada 12 minutos |
| Supabase prod activo | GitHub Actions → `/_health` (con query real) | 2 veces por semana |
| Supabase dev activo | `pg_cron` dentro del propio Supabase dev | Cada 5 días |

- **cron-job.org para Render:** mantenerlo despierto requiere ~7.200 pings/mes. GitHub Actions tiene 2.000 min/mes — se agotarían. cron-job.org es gratuito e ilimitado.
- **GitHub Actions para Supabase prod:** 2 pings/semana (~2 segundos c/u). Entra en free tier y queda versionado en el repo.
- **pg_cron para Supabase dev:** no hay app deployada que apunte a dev, así que el keep-alive tiene que ser interno al propio proyecto Supabase.

---

### Paso 4 — Fase 3: Ranking Anual por Categoría

**Prerequisito:** Paso 1 completado (tablas relacionales disponibles).

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
