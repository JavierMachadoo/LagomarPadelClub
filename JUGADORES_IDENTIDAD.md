# Ranking Anual — Guía de Deploy

> Estado: implementado, pendiente de validar en dev y aplicar en prod.
> Última actualización: 2026-04-28

---

## Resumen de qué se hizo

- Tabla `puntos_jugador` definida en `supabase_schema.sql`
- Script de importación del histórico: `import_ranking_baseline.py` (todos los jugadores con sus puntos hasta Abril 2026)
- Vista `/ranking` sin filtro de año (muestra todos los torneos finalizados)
- Blueprint `api/routes/ranking.py` limpiado

---

## FASE 1 — Validar en DEV

### Paso 1 · Crear tabla en Supabase dev

Abrí el SQL Editor en **LagomarPadelDB-Dev** y ejecutá este bloque (está al final de `supabase_schema.sql`):

```sql
CREATE TABLE IF NOT EXISTS puntos_jugador (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    jugador_id  UUID        NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    torneo_id   UUID        NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
    categoria   TEXT        NOT NULL,
    puntos      INTEGER     NOT NULL DEFAULT 0,
    concepto    TEXT        NOT NULL DEFAULT 'serie',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (jugador_id, torneo_id, categoria)
);

CREATE INDEX IF NOT EXISTS idx_pj_jugador   ON puntos_jugador(jugador_id);
CREATE INDEX IF NOT EXISTS idx_pj_torneo    ON puntos_jugador(torneo_id);
CREATE INDEX IF NOT EXISTS idx_pj_categoria ON puntos_jugador(categoria);
```

---

### Paso 2 · Dry run del import (sin escribir nada)

Con el `.env` apuntando a dev:

```bash
python import_ranking_baseline.py --dry-run
```

Vas a ver por cada jugador si:
- **`reutiliza`** → ya existe en `jugadores` (vinculado a su cuenta si se registró)
- **`CREADO`** → no existe, el script lo va a crear

Revisá que los nombres que sabés que tienen cuenta los encuentre. Si alguno no matchea (por diferencia de nombre), avisame y lo corrijo en el script antes de correr el real.

---

### Paso 3 · Import real en dev

```bash
python import_ranking_baseline.py
```

Al final te muestra un resumen: cuántos jugadores reutilizó, cuántos creó y cuántas filas insertó en `puntos_jugador`.

---

### Paso 4 · Verificar el ranking en dev

```bash
python main.py
```

Entrá a `http://localhost:5000/ranking` y verificá:

- [ ] Se ven las 6 categorías (Tercera a Octava)
- [ ] Los puntos y nombres son correctos
- [ ] El filtro de año ya no aparece
- [ ] El estado vacío no menciona el año

---

### Paso 5 · Commit y push

Una vez validado en dev:

```bash
git add api/routes/ranking.py web/templates/ranking.html supabase_schema.sql import_ranking_baseline.py JUGADORES_IDENTIDAD.md
git commit -m "feat(ranking): sacar filtro de año y agregar tabla puntos_jugador"
git push
```

---

## FASE 2 — Aplicar en PROD

> Solo hacer esto después de que FASE 1 funcionó bien en dev.

### Paso 1 · Crear tabla en Supabase prod

Mismo SQL del Paso 1 de dev, pero ahora en **LagomarPadelDB** (prod).

---

### Paso 2 · Dry run apuntando a prod

Temporalmente cambiá el `.env` para que apunte a prod (o usá variables de entorno inline):

```bash
SUPABASE_URL=<prod_url> SUPABASE_SERVICE_ROLE_KEY=<prod_key> python import_ranking_baseline.py --dry-run
```

Revisá que los nombres con cuenta en prod también matcheen correctamente.

---

### Paso 3 · Import real en prod

```bash
SUPABASE_URL=<prod_url> SUPABASE_SERVICE_ROLE_KEY=<prod_key> python import_ranking_baseline.py
```

---

### Paso 4 · Deploy en Railway

Railway hace el deploy automático cuando el push llega a `main`. Si el branch aún no fue mergeado:

```bash
# Merge Feature/JugadoresIdentidad → main (o vía PR en GitHub)
```

---

### Paso 5 · Verificar en prod

Entrá a la URL de prod y verificá `/ranking` igual que en dev.

---

## Notas importantes

**Jugadores con cuenta vinculada**: los jugadores que se registraron en la app ya tienen entrada en `jugadores` con su UUID de Supabase Auth como `id`. El import los encuentra por nombre+apellido y reutiliza esa entrada — sus puntos quedan automáticamente ligados a su perfil.

**Nombres sin apellido**: SCHUBERT, GUZI, MONE, WILLY, PEDRO — el script los crea con apellido vacío. Si tenés los apellidos completos, actualizalos en `import_ranking_baseline.py` antes de correrlo.

**Idempotente**: el script usa UPSERT en `puntos_jugador` (constraint UNIQUE por jugador+torneo+categoría). Correrlo dos veces no duplica datos.

**Concepto**: todos los jugadores importados tienen `concepto = 'serie'` porque no tenemos el desglose histórico por torneo. Los próximos torneos que se archiven desde el sistema van a tener el concepto real (campeón, vicecampeón, etc.).
