---
name: skill-creator
description: >
  Crea nuevas skills para este proyecto siguiendo el formato estándar con frontmatter YAML, reglas técnicas, ejemplo real y referencias.
  Trigger: Al crear una nueva skill o al pedirte que documentes un dominio técnico como skill.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root]
  auto_invoke: "Creating a new skill file"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Estructura Obligatoria de una Skill

Cada skill es un archivo `.md` en `/skills/business-logic/` o `/skills/stack/` según su naturaleza, con frontmatter YAML y secciones en este orden:

```
skills/
├── business-logic/   # lógica específica del dominio del proyecto
│   └── <nombre-skill>.md
└── stack/            # patrones del stack tecnológico
    └── <nombre-skill>.md
```

### Frontmatter (REQUIRED)

```yaml
---
name: nombre-del-skill           # kebab-case, igual que el nombre del archivo
description: >
  Una línea describiendo qué hace el skill.
  Trigger: Cuándo invocar este skill (acción específica, no genérica).
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root]                  # carpetas donde aplica: root, api, core, utils, web
  auto_invoke: "Acción que dispara este skill"   # debe coincidir con la tabla en AGENTS.md
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---
```

### Secciones del Cuerpo (en orden)

1. **Regla principal (REQUIRED)** — La regla más importante, con `# Título (REQUIRED)` y bloques `✅` / `❌`
2. **Reglas adicionales** — 2 a 4 reglas más, cada una con su sección `##`
3. **Ejemplo Real del Proyecto** — Código extraído del proyecto real (no inventado)
4. **Referencias** — Lista de archivos relevantes con descripción breve

## Convenciones de Formato

```markdown
## Nombre de Regla (REQUIRED)

Explicación en 1–2 oraciones.

​```python
# ✅ Buena práctica
codigo_correcto()

# ❌ NUNCA hacer esto
codigo_incorrecto()  # razón específica
​```
```

- Usar `# ✅ CORRECTO:` o `# ✅` para ejemplos buenos
- Usar `# ❌ NUNCA` para antipatrones — siempre explicar por qué
- Los bloques de código deben ser copiables y ejecutables
- Si la regla aplica solo en ciertos contextos, indicarlo explícitamente

## Scope — Cuándo Aplica

| Valor | Significa |
|-------|-----------|
| `root` | Aplica en todo el proyecto |
| `api` | Solo en `api/routes/` |
| `core` | Solo en `core/` |
| `utils` | Solo en `utils/` |
| `web` | Solo en `web/templates/` o `web/static/` |

Un skill puede tener múltiples scopes: `scope: [root, api, core]`

## Después de Crear una Skill

1. Agregar el skill a la tabla **Available Skills** en `AGENTS.md`
2. Agregar la acción correspondiente a la tabla **Auto-invoke Skills** en `AGENTS.md`

```markdown
# En AGENTS.md — Available Skills
| `nombre-skill` | Descripción breve |

# En AGENTS.md — Auto-invoke Skills
| Acción que dispara el skill | `nombre-skill` |
```

## Ejemplo Real del Proyecto

La skill `flask-torneos.md` sigue este formato. Su frontmatter:

```yaml
---
name: flask-torneos
description: >
  Patrones Flask para este proyecto: JWT middleware, blueprints, rutas protegidas y formato de respuestas API.
  Trigger: Al modificar rutas en main.py, api/routes/parejas.py o api/routes/finales.py.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root, api]
  auto_invoke: "Modifying routes or API endpoints"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---
```

Y su sección de ejemplo toma código real de `api/routes/finales.py`, no código inventado.

## Referencias

- `skills/stack/flask-torneos.md` — ejemplo de skill para capa API
- `skills/business-logic/algoritmo-torneos.md` — ejemplo de skill para lógica de negocio
- `skills/stack/pytest-torneos.md` — ejemplo de skill para testing
- `AGENTS.md` — tablas de Available Skills y Auto-invoke (actualizar después de crear)