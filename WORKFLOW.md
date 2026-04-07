# Workflow de Desarrollo — Algoritmo Torneos

Guía de trabajo para agregar cambios a `main` (producción) sin imprevistos.
Actualizada: 2026-04-07. Si algo cambia, actualizá este archivo.

---

## Regla fundamental

> **`main` = lo que están viendo ~60 jugadores reales ahora mismo.**
> Nunca rompas `main`. Nunca.

El costo de un bug en prod no es "arreglarlo en 5 minutos". Es:
- Jugador que no puede inscribirse → se va y no vuelve
- Pérdida de datos si el storage se corrompe
- Credibilidad del club destruida para el primer torneo

---

## Estructura de branches

```
main           → producción (Railway). Solo recibe merges, nunca commits directos.
develop        → integración. Base para todo desarrollo.
feature/xxx    → feature nueva, creada desde develop
fix/xxx        → bugfix, creado desde develop (o desde main si es hotfix urgente)
hotfix/xxx     → SOLO para bugs críticos en prod — creado desde main, mergeado a main Y develop
```

### Flujo normal

```
develop
  └── feature/mejora-dashboard    ← trabajás acá
        └── PR a develop          ← revisás tú mismo antes de mergear
              └── (testing en dev) → PR a main → Railway redeploya automático
```

### Flujo hotfix (prod está roto)

```
main
  └── hotfix/fix-critico          ← creado desde main
        └── PR a main             ← deploy urgente
        └── PR a develop          ← para no perder el fix en el branch de desarrollo
```

---

## Ambientes: DEV vs PROD

### Variables de entorno

| Variable | DEV (local) | PROD (Railway) |
|----------|-------------|----------------|
| `SUPABASE_URL` | `LagomarPadelDB-Dev` (`slwzrxsjxfboojpkozey`) | `LagomarPadelDB` prod (`mxftowqqjyktxricdemd`) |
| `DEBUG` | `True` | `False` |
| `SECRET_KEY` | Cualquier string local | Key segura, rotada por torneo |
| Workers | 1 | 2 |

**Regla de oro**: NUNCA pongas las credenciales de prod en el `.env` local.
Si necesitás debuggear prod, usá los logs de Railway — no conectes localmente a la BD de prod.

### Supabase: Dev vs Prod

- Cambios de **schema** (tablas, columnas, RLS, RPCs) → primero en Dev, verificar, luego aplicar en Prod
- **Nunca** ejecutes SQL de migración directo en Prod sin haberlo probado en Dev primero
- Guardá todas las migraciones en `supabase/migrations/` con nombre `YYYY-MM-DD_descripcion.sql`
- Si agregás una RPC en Dev, antes de mergear a `main`, aplicala en Prod manualmente (o via migration)

---

## Checklist antes de mergear a `main`

Hacelo mentalmente (o copialo como comentario en el PR) para cada cambio:

### Para cualquier cambio

- [ ] El código corre localmente sin errores (`python main.py`)
- [ ] Las rutas afectadas responden correctamente en el browser
- [ ] No hay `print()` de debug que quedaron
- [ ] No hay `SECRET_KEY` ni credenciales hardcodeadas
- [ ] Si se modificó `requirements.txt`: verificar que `pip install` funciona en ambiente limpio

### Para cambios en Supabase (schema, RLS, RPCs)

- [ ] Migration probada en Dev primero
- [ ] RPC existe en Prod antes de deployar el código que la llama
- [ ] RLS sigue permitiendo que el backend (service role key) opere normalmente

---

**Verificación post-deploy** (2 minutos obligatorios):
1. Entrá a `https://algoritmo-torneos.onrender.com` (o el dominio de Railway cuando migres)
2. Verificá que el login funciona
3. Verificá que la ruta que tocaste funciona
4. Mirá los logs de Railway por 30 segundos — si hay traceback, rollback inmediato

---

## Rollback de emergencia

Si el deploy rompió prod y necesitás revertir rápido:

```bash
# Ver los últimos commits
git log --oneline -5

# Revertir el último commit (crea un commit de revert, no destruye historia)
git revert HEAD
git push origin main
# Railway redeploya al estado anterior
```

**Nunca uses `git reset --hard` en main** — destruye la historia y si alguien más tiene el repo puede crear inconsistencias.

---

## Cambios en schema de Supabase

El mayor riesgo de romper prod viene de esquema/RLS cambiado sin avisar al código (o viceversa).

### Workflow de migración seguro

```
1. Escribir el SQL en supabase/migrations/YYYY-MM-DD_descripcion.sql
2. Ejecutarlo en Dev (Supabase dashboard → SQL editor)
3. Verificar que el código funciona en Dev con el nuevo schema
4. Mergear el código a main (Railway redeploya, pero todavía usa schema viejo en Prod)
5. Ejecutar el mismo SQL en Prod
   → El código y el schema quedan sincronizados
```

**Nunca** subas código a `main` que dependa de una columna o RPC que aún no existe en Prod.

### Agregar una columna

```sql
-- SIEMPRE con valor default para no romper rows existentes
ALTER TABLE torneos ADD COLUMN nuevo_campo TEXT DEFAULT '';
-- NO: ALTER TABLE torneos ADD COLUMN nuevo_campo TEXT NOT NULL;  ← rompe rows existentes
```

### Agregar/modificar una RPC

```sql
-- Usar CREATE OR REPLACE para que sea idempotente
CREATE OR REPLACE FUNCTION guardar_torneo_con_version(...)
RETURNS ...
LANGUAGE plpgsql AS $$
...
$$;
```

---

## Qué NO hacer nunca

| ❌ Acción peligrosa | ✅ Alternativa |
|--------------------|---------------|
| Push directo a `main` | PR desde develop |
| `git reset --hard main` | `git revert <commit>` |
| Editar variables de entorno en Railway sin avisar | Documentar el cambio |
| Aplicar SQL en Prod sin probar en Dev | Flujo de migración (arriba) |
| Editar `dashboard.html` sin Grep primero | Buscar el bloque exacto |
| Subir `SUPABASE_SERVICE_ROLE_KEY` a un PR | Usar `.env` local (en `.gitignore`) |
| Agregar campo NOT NULL sin default | `ADD COLUMN campo TYPE DEFAULT valor` |
| Subir workers a 3+ sin evaluar caché | Decisión documentada en DESPLIEGUE.md §4 |
| `git add -A` con archivos temporales | `git add <archivo-específico>` |

---

## Convención de commits

Seguir [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(scope): descripción en imperativo, presente
fix(scope): descripción
chore(scope): descripción
docs(scope): descripción
refactor(scope): descripción
test(scope): descripción
```

Scopes útiles en este proyecto: `inscripcion`, `grupos`, `finales`, `auth`, `storage`, `api`, `frontend`, `deploy`

Ejemplos reales:
```
feat(inscripcion): permitir editar franjas horarias antes del cierre
fix(storage): corregir race condition en auto-asignación de grupos
chore(deps): actualizar Flask a 3.1.3 por CVE-XXXX
docs(deploy): agregar checklist post-migración Railway
```

---

## Monitoreo en producción

| Herramienta | Qué monitorea | URL |
|-------------|--------------|-----|
| UptimeRobot | `/_health` cada 5 min (app + BD) | Panel UptimeRobot |
| Railway logs | Errores de aplicación en tiempo real | railway.app → proyecto → logs |
| Supabase dashboard | Queries lentas, uso de BD, errores Auth | supabase.com → proyecto prod |

**Ruido a ignorar**: Los logs de `/_health` cada 5 min son esperados — es el keep-alive de Supabase.

**Señal de alarma**: Errores 5xx repetidos, `ConflictError` frecuentes (workers compitiendo), timeouts a Supabase.

---

## Frecuencia de releases recomendada

- **Durante torneo activo**: Deploy mínimo. Solo fixes críticos. Avisar al admin antes.
- **Entre torneos (estado espera)**: Momento ideal para features nuevas y refactors.
- **Pre-inscripción**: Feature freeze 48h antes de abrir inscripciones.

El torneo tiene un ciclo predecible. Planificá los cambios grandes para el estado `espera`.
