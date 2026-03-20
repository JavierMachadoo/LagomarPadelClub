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
- Tablas relacionales para ranking cross-torneo (`grupos`, `parejas_grupo`, `partidos`, `partidos_finales`)
- Dev/Prod Supabase separados (`LagomarPadelDB-Dev` / `LagomarPadelDB`)
- Keep-alive: UptimeRobot → `/_health` (query real) para Render+prod; `pg_cron` para dev

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
grupos          (id, torneo_id, categoria, franja, cancha, created_at)
parejas_grupo   (grupo_id, nombre, posicion)               -- PK compuesta
partidos        (id, grupo_id, pareja1, pareja2, resultado JSONB)
partidos_finales(id, torneo_id, categoria, fase, pareja1, pareja2, ganador)
```

---

## Próximos pasos (en orden)

### Paso 1 — Ranking Anual por Categoría ← ACTUAL

**Prerequisito:** Paso 1 completado (tablas relacionales disponibles — ya hecho).

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
