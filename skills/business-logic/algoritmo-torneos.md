---
name: algoritmo-torneos
description: >
  Reglas para modificar el algoritmo de formación de grupos: backtracking con poda, scoring de compatibilidad y fallback greedy.
  Trigger: Al modificar core/algoritmo.py o cualquier lógica de agrupamiento de parejas.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root, core]
  auto_invoke: "Modifying group formation algorithm or compatibility scoring"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Escala de Compatibilidad (REQUIRED)

El score de un grupo de 3 parejas va de 0.0 a 3.0. No cambiar esta escala sin actualizar estadísticas y UI.

```python
# ✅ Escala correcta
# 3.0 — las 3 parejas comparten al menos una franja horaria
# 2.0 — 2 de 3 comparten franja, la tercera comparte día
# 1.5 — 2 de 3 comparten franja, la tercera no comparte nada
# 0.5 — por cada pareja que comparte día pero no franja exacta
# 0.0 — sin disponibilidad en común

# ❌ NUNCA usar scores fuera de 0–3 o comparar con umbral distinto
if score > 5:  # umbral incorrecto
    ...
```

## Backtracking con Poda

El método `_buscar_distribucion_optima()` usa backtracking. Los límites de exploración son críticos para rendimiento.

```python
# ✅ Límites vigentes (no reducir sin medir impacto en calidad)
if len(parejas) <= 9:
    max_combos = None       # explorar todo
elif len(parejas) <= 12:
    max_combos = 20
else:
    max_combos = 15

# ✅ Poda: si el máximo posible no supera el mejor encontrado, cortar
max_posible = score_actual + len(grupos_restantes) * 3.0
if max_posible <= mejor_score:
    return  # poda

# ❌ NUNCA eliminar la poda: convierte O(n³) en exponencial
```

## Fallback Greedy

Para categorías con pocos o muchos grupos (fuera del rango 2–6), se usa el algoritmo greedy.

```python
# ✅ Siempre hay fallback
def _formar_grupos_categoria(self, parejas):
    n_grupos = len(parejas) // 3
    if 2 <= n_grupos <= 6:
        return self._buscar_distribucion_optima(parejas)
    else:
        return self._algoritmo_greedy(parejas)  # fallback obligatorio
```

## Grupos Incompletos

Las parejas sin grupo van a `parejas_sin_asignar` en `ResultadoAlgoritmo`. No forzar grupos de 2.

```python
# ✅ Resto de parejas que no forman triplete completo
sobrantes = parejas[n_grupos * 3:]
resultado.parejas_sin_asignar.extend(sobrantes)

# ❌ NUNCA crear grupos de 2 — el fixture asume exactamente 3 parejas por grupo
```

## Ejemplo Real del Proyecto

Scoring en `core/algoritmo.py` — cómo se evalúa si 3 parejas comparten una franja:

```python
def _calcular_compatibilidad(self, pareja1, pareja2, pareja3):
    """Retorna score 0.0–3.0 según solapamiento de franjas horarias."""
    score = 0.0
    for franja in FRANJAS_HORARIAS:
        disponibles = sum(
            1 for p in [pareja1, pareja2, pareja3]
            if franja in p.franjas_disponibles
        )
        if disponibles == 3:
            score += 3.0
            break  # franja perfecta encontrada, no seguir sumando
        elif disponibles == 2:
            score += 0.5
    return min(score, 3.0)
```

## Referencias

- `core/algoritmo.py` — `AlgoritmoGrupos`, `_buscar_distribucion_optima`, `_calcular_compatibilidad`
- `core/models.py` — `ResultadoAlgoritmo`, `Pareja`, `Grupo`
- `config/settings.py` — `FRANJAS_HORARIAS` (define el universo de franjas válidas)