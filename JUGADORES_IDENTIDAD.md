# Ranking Anual — Guía de Deploy

> Estado: import ejecutado en dev ✅ — pendiente verificar /ranking en dev y aplicar en prod.
> Última actualización: 2026-04-29

---

## Resumen de qué se hizo

- Tabla `puntos_jugador` definida en `supabase_schema.sql`
- Script de importación del histórico: `import_ranking_baseline.py` (180 jugadores con sus puntos hasta Abril 2026)
- Vista `/ranking` sin filtro de año (muestra todos los torneos finalizados)
- Blueprint `api/routes/ranking.py` limpiado
- Script `copy_prod_to_dev.py` para copiar tablas clave de prod → dev (via supabase-py)

---

## Hallazgos importantes — correcciones de nombres

Durante el dry-run descubrimos que PostgreSQL `ILIKE` **no normaliza acentos** — `'HERNAN'` no matchea `'Hernán'` porque `'a' ≠ 'á'` a nivel Unicode.

Se corrigieron 15 entradas en `RANKING_DATA` dentro de `import_ranking_baseline.py` para que los nombres coincidan exactamente con los registrados en prod:

| Antes | Después |
|-------|---------|
| `HERNAN GYALOG` | `Hernán Gyalog` |
| `MAXI LICANDRO` | `Maximo Licandro` |
| `NICO SILVERA` | `Nicolas Silvera` |
| `RODRI FRANCO` | `Rodrigo Franco` |
| `QUIQUE FRAGA` | `Enrique Fraga` |
| `NICO MARTINEZ` | `Nicolás Martínez` |
| `FACU SPIRA` | `Facundo Spira` |
| `ALE VAZQUEZ` | `Alejandro Vazquez` |
| `AGUSTIN TORENA` | `Agustín Torena` |
| `GONZALO OLIVERA` | `Gonza Olivera` |

Resultado del import real en dev:
- **102 reutilizados** — jugadores ya existentes en `jugadores` (ligados a su cuenta si se registraron)
- **78 creados** — jugadores históricos que aún no se registraron en la app
- **180 filas** insertadas en `puntos_jugador`

---

## Divergencia de schema prod ↔ dev — jugadores

La tabla `jugadores` tiene esquemas distintos en prod y dev:

| Columna | Prod | Dev |
|---------|------|-----|
| id | UUID PK, FK → auth.users | UUID PK (no FK) |
| nombre | ✅ | ✅ |
| apellido | ✅ | ✅ |
| telefono | ✅ | ✅ |
| created_at | ✅ | ✅ |
| usuario_id | ❌ | UUID, FK → auth.users |
| email | ❌ | ✅ |
| activo | ❌ | BOOLEAN DEFAULT true |
| telefono_verificado | ❌ | ✅ |
| telefono_verificado_at | ❌ | ✅ |

Al copiar prod → dev se insertan solo las 5 columnas comunes. Dev completa el resto con defaults.

---

## FASE 1 — Validar en DEV ✅ COMPLETADO

### Paso 1 · Crear tabla en Supabase dev ✅

SQL ejecutado en **LagomarPadelDB-Dev** (ya existe, no re-ejecutar):

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

### Paso 2 · Copiar prod → dev ✅

Se copió vía Supabase MCP (tablas en orden por FK):
1. `torneos` (FK padre de grupos y puntos_jugador)
2. `jugadores` (solo 5 columnas comunes)
3. `grupos` (FK → torneos)
4. `parejas_grupo` (FK → grupos)
5. `partidos` (FK → grupos)
6. `partidos_finales` (FK → torneos)

NO se copiaron: `inscripciones` (FK a auth.users de prod — incompatible con dev), `invitacion_tokens`, `puntos_jugador`.

Para volver a copiar en el futuro:
```bash
python copy_prod_to_dev.py                  # copia todo
python copy_prod_to_dev.py --solo-jugadores # solo jugadores (más rápido)
python copy_prod_to_dev.py --dry-run        # preview sin escribir
```
Requiere `PROD_SUPABASE_URL` y `PROD_SUPABASE_SERVICE_ROLE_KEY` en `.env`.

### Paso 3 · Import real en dev ✅

```bash
PYTHONIOENCODING=utf-8 python import_ranking_baseline.py
```

Resultado:
```
=== Resumen ===
  Jugadores reutilizados: 102
  Jugadores creados:      78
  Filas puntos_jugador:   180
```

### Paso 4 · Verificar el ranking en dev ⬜ PENDIENTE

```bash
python main.py
```

Entrá a `http://localhost:5000/ranking` y verificá:

- [ ] Se ven las 6 categorías (Tercera a Octava)
- [ ] Los puntos y nombres son correctos
- [ ] El filtro de año ya no aparece
- [ ] El estado vacío no menciona el año

### Paso 5 · Commit y push

Una vez validado en dev:

```bash
git add api/routes/ranking.py web/templates/ranking.html supabase_schema.sql \
        import_ranking_baseline.py copy_prod_to_dev.py JUGADORES_IDENTIDAD.md
git commit -m "feat(ranking): tabla puntos_jugador, import histórico baseline y vista /ranking sin filtro de año"
git push
```

---

## FASE 2 — Aplicar en PROD ⬜ PENDIENTE

> Solo hacer esto después de que FASE 1 funcionó bien en dev.

### Paso 1 · Crear tabla en Supabase prod

Mismo SQL del Paso 1 de FASE 1, pero ahora en **LagomarPadelDB** (prod).

---

### Paso 2 · Dry run apuntando a prod

```bash
SUPABASE_URL=<prod_url> SUPABASE_SERVICE_ROLE_KEY=<prod_key> \
PYTHONIOENCODING=utf-8 python import_ranking_baseline.py --dry-run
```

Revisá que todos los jugadores con cuenta en prod matcheen correctamente.
Deberían salir ~102 reutilizados (los mismos que en dev — el script busca por nombre+apellido).

---

### Paso 3 · Import real en prod

```bash
SUPABASE_URL=<prod_url> SUPABASE_SERVICE_ROLE_KEY=<prod_key> \
PYTHONIOENCODING=utf-8 python import_ranking_baseline.py
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

**ILIKE no normaliza acentos**: `'HERNAN' ILIKE 'Hernán'` → FALSE en PostgreSQL. Los nombres en `RANKING_DATA` deben coincidir exactamente (incluyendo tildes) con los registrados en la tabla `jugadores`.

**Jugadores con cuenta vinculada**: los jugadores que se registraron en la app ya tienen entrada en `jugadores`. El import los encuentra por nombre+apellido y reutiliza esa entrada — sus puntos quedan automáticamente ligados a su perfil.

**Nombres sin apellido**: SCHUBERT, GUZI, MONE, WILLY, PEDRO — el script los crea con apellido vacío. Si tenés los apellidos completos, actualizalos en `import_ranking_baseline.py` antes de aplicar en prod.

**Idempotente**: el script usa UPSERT en `puntos_jugador` (constraint UNIQUE por jugador+torneo+categoría). Correrlo dos veces no duplica datos.

**Windows / encoding**: si el terminal da `UnicodeEncodeError`, correr con `PYTHONIOENCODING=utf-8` como prefijo.

**Concepto**: todos los jugadores importados tienen `concepto = 'serie'` porque no tenemos el desglose histórico por torneo. Los próximos torneos que se archiven desde el sistema van a tener el concepto real (campeón, vicecampeón, etc.).
