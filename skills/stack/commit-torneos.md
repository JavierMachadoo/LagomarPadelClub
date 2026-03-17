---
name: commit-torneos
description: >
  Realiza git add . y crea un commit con mensaje en estilo conventional commits: tipo(scope): descripción breve.
  Trigger: Cuando el usuario pide "commitea esto", "hace un commit", "guardá los cambios" o similar.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root]
  auto_invoke: "Committing changes"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Flujo de Commit (REQUIRED)

Siempre seguir este orden exacto (IMPORTANTE durante el proceso no pedirme que acepte si podes ejecutar ESTOS comandos simplemente ejecutalos):

```bash
# 1. Revisar qué cambió
git status
git diff --staged

# 2. Agregar todos los cambios
git add .

# 3. Commitear con mensaje conventional
git commit -m "<tipo>(<scope>): <descripción breve en español>"
```

## Formato del Mensaje

`<tipo>(<scope>): <descripción>`

- **tipo** — obligatorio, en minúsculas
- **scope** — opcional, indica el módulo afectado
- **descripción** — breve, en infinitivo, sin punto final, en español

```bash
# ✅ Ejemplos correctos
git commit -m "feat(algoritmo): agrega scoring por compatibilidad de día"
git commit -m "fix(storage): corrige cache que no se invalidaba al limpiar torneo"
git commit -m "refactor(models): convierte Pareja a dataclass"
git commit -m "docs(agents): agrega skills de dominio al proyecto"
git commit -m "style(frontend): ajusta colores de categorías en tabla de grupos"
git commit -m "test(algoritmo): agrega tests parametrizados por categoría"
git commit -m "chore(deps): actualiza supabase a 2.10.0"

# ❌ NUNCA mensajes vagos o sin tipo
git commit -m "fix bug"
git commit -m "cambios"
git commit -m "wip"
```

## Tipos Disponibles

| Tipo | Cuándo usarlo |
|------|---------------|
| `feat` | Nueva funcionalidad visible para el usuario |
| `fix` | Corrección de un bug |
| `refactor` | Cambio de código sin nueva funcionalidad ni fix |
| `style` | Cambios visuales o de formato (CSS, HTML) |
| `test` | Agregar o modificar tests |
| `docs` | Documentación, AGENTS.md, skills |
| `chore` | Dependencias, configuración, archivos de build |
| `perf` | Mejora de rendimiento |

## Scopes del Proyecto

| Scope | Archivos |
|-------|----------|
| `algoritmo` | `core/algoritmo.py` |
| `models` | `core/models.py` |
| `storage` | `utils/torneo_storage.py` |
| `csv` | `utils/csv_processor.py` |
| `api` | `api/routes/` |
| `frontend` | `web/templates/`, `web/static/` |
| `auth` | `utils/jwt_handler.py`, login |
| `finales` | `core/fixture_finales_generator.py`, `api/routes/finales.py` |
| `config` | `config/` |
| `agents` | `AGENTS.md`, `skills/` |
| `deps` | `requirements.txt` |

## Ejemplo Real del Proyecto

Al agregar los skills de dominio técnico:

```bash
git add .
git commit -m "docs(agents): agrega skills de dominio técnico al proyecto"
```

Al corregir que la tabla de posiciones no mostraba datos:

```bash
git add .
git commit -m "fix(frontend): muestra tabla posiciones en resultados"
```

## Referencias

- `AGENTS.md` — tabla Auto-invoke con esta skill registrada
- Convención: [Conventional Commits v1.0](https://www.conventionalcommits.org/)
- Historial del proyecto: `git log --oneline` para ver estilo existente