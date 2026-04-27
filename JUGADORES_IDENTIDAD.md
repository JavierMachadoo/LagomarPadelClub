# Sistema de Identidad de Jugadores — Diseño

> Estado: Diseño aprobado. Pendiente de implementación.
> Fecha de diseño: 2026-04-27
> Prioridad en roadmap: P3 (prerequisito para ranking anual)

---

## Problema

Hoy una "pareja" es un string libre con teléfono. No existe el concepto de jugador individual como entidad. Esto hace imposible acumular puntos entre torneos porque no hay forma de decir "este Juan Pérez del torneo de mayo es el mismo que el del torneo de agosto".

---

## Decisión

Separar dos conceptos que hoy están mezclados:

- **`Usuario`** — cuenta con email/contraseña. Existe en Supabase Auth. Puede loguearse.
- **`Jugador`** — persona real que juega en el club. Puede o no tener cuenta.

Un jugador puede existir sin cuenta. Si algún día crea una cuenta, se vincula retroactivamente y todos sus torneos históricos quedan asociados.

---

## Modelo de datos

### Tabla `jugadores` (nueva)

```sql
CREATE TABLE jugadores (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre        TEXT NOT NULL,
  telefono      TEXT,
  email         TEXT,
  usuario_id    UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  activo        BOOLEAN DEFAULT TRUE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

- `usuario_id` es nullable — jugador sin cuenta es válido
- Un jugador puede cambiar de `usuario_id` si el admin lo vincula a una cuenta existente
- `activo = FALSE` para jugadores retirados (no se borran — preservan historial)

### Tabla `parejas` (refactorizada)

```sql
-- Agregar columnas FK
ALTER TABLE parejas
  ADD COLUMN jugador1_id UUID REFERENCES jugadores(id),
  ADD COLUMN jugador2_id UUID REFERENCES jugadores(id);

-- El campo nombre_pareja (string) se mantiene como fallback durante migración
-- Una vez migrados todos los torneos históricos, se puede deprecar
```

---

## Flujo del admin al crear una pareja

1. Admin busca "Roberto" en el catálogo de jugadores
2. Si existe → lo selecciona
3. Si no existe → lo crea ahí mismo (nombre + teléfono opcional) → queda en el catálogo
4. Repite para el segundo jugador
5. Elige categoría y franjas → guarda

El catálogo crece solo con el tiempo. Al segundo torneo, la mayoría de jugadores ya están cargados.

---

## Ranking anual (objetivo final)

Con esta estructura, el ranking es una query directa:

```sql
SELECT
  j.nombre,
  SUM(r.puntos) AS puntos_totales,
  COUNT(DISTINCT r.torneo_id) AS torneos_jugados
FROM resultados_torneos r
JOIN jugadores j ON j.id = r.jugador_id
GROUP BY j.id, j.nombre
ORDER BY puntos_totales DESC;
```

No hay fuzzy matching. No hay confirmaciones manuales. La identidad está resuelta desde la carga.

### Sistema de puntos sugerido (a definir)

| Posición | Puntos |
|----------|--------|
| 1° (Campeón) | 100 |
| 2° (Finalista) | 75 |
| 3°-4° (Semifinalistas) | 50 |
| Cuartos de final | 30 |
| Clasificado a finales | 15 |
| Participación | 5 |

> Los valores son un punto de partida. Ajustar según criterio del club.

---

## Plan de implementación

### Fase 1 — Modelo y catálogo (sin romper lo existente)

- [ ] Crear tabla `jugadores` en Supabase (dev primero, luego prod)
- [ ] Agregar `jugador1_id` / `jugador2_id` a `parejas` (nullable — migración no destructiva)
- [ ] Nuevo modelo `Jugador` en `core/models.py`
- [ ] Endpoint CRUD `/api/jugadores` (listar, crear, buscar por nombre/teléfono, vincular usuario)
- [ ] UI admin: selector de jugadores al crear pareja (con búsqueda + creación inline)

### Fase 2 — Migración de datos históricos

- [ ] Script de migración: para cada pareja histórica con nombre string, crear entidad `Jugador` y vincular
- [ ] El admin revisa y deduplica entidades creadas automáticamente
- [ ] Una vez validado, marcar `nombre_pareja` como deprecated

### Fase 3 — Ranking

- [ ] Tabla `resultados_torneos` (jugador_id, torneo_id, posicion, puntos)
- [ ] Proceso de "calcular puntos" al archivar un torneo
- [ ] Vista pública `/ranking` con tabla anual y filtros por categoría
- [ ] Sección "Mis torneos" en dashboard del jugador (usa `jugador_id` vinculado a su cuenta)

---

## Consideraciones importantes

**Deduplicación**: Es responsabilidad del admin al crear el catálogo, no del sistema. El sistema no hace fuzzy matching — la identidad es explícita.

**Migración no destructiva**: Las columnas `jugador1_id`/`jugador2_id` se agregan como nullable. El campo nombre string se mantiene durante la transición. Cero riesgo de romper torneos ya archivados.

**Vinculación cuenta-jugador**: El admin puede vincular un `Jugador` a una cuenta `Usuario` en cualquier momento. La query de ranking funciona igual con o sin cuenta vinculada — opera sobre `jugador_id`, no sobre `usuario_id`.

**RLS en Supabase**: La tabla `jugadores` debe seguir el mismo patrón que el resto — backend accede con `SUPABASE_SERVICE_ROLE_KEY`, nunca con anon key.

---

## Archivos afectados (estimado)

| Archivo | Cambio |
|---------|--------|
| `core/models.py` | Nuevo dataclass `Jugador`, refactor de `Pareja` |
| `api/routes/parejas.py` | Adaptar CRUD al nuevo modelo |
| `api/routes/` | Nuevo blueprint `jugadores.py` |
| `utils/torneo_storage.py` | Persistencia del catálogo de jugadores |
| `web/templates/homePanel.html` | UI selector de jugadores |
| `web/static/js/app.js` | Lógica de búsqueda + creación inline |
| Supabase | Migration: tabla `jugadores`, ALTER TABLE `parejas` |
