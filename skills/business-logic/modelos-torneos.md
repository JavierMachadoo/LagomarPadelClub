---
name: modelos-torneos
description: >
  Patrones para los modelos de datos del proyecto: dataclasses, serialización, enums y reglas de negocio en core/models.py.
  Trigger: Al modificar core/models.py o al agregar nuevas entidades al dominio del torneo.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root, core]
  auto_invoke: "Modifying data models or adding new domain entities"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Usar Dataclasses (REQUIRED)

Todos los modelos de dominio usan `@dataclass`. No usar dicts planos para pasar datos entre capas.

```python
# ✅ Modelo con dataclass
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Pareja:
    id: str
    nombre: str
    categoria: str
    telefono: str
    franjas_disponibles: List[str] = field(default_factory=list)
    jugador1: str = ""
    jugador2: str = ""

# ❌ NUNCA pasar dicts con estructura implícita entre módulos de core/
pareja = {"id": "1", "nombre": "Los Campeones"}  # no tipado, propenso a errores
```

## Serialización

Los modelos deben poder convertirse a dict para el storage. Usar `dataclasses.asdict()` o métodos `to_dict()`.

```python
# ✅ Serializar con asdict
from dataclasses import asdict

pareja_dict = asdict(pareja)
storage.guardar({"parejas": [asdict(p) for p in parejas]})

# ✅ Deserializar explícitamente
pareja = Pareja(**pareja_dict)

# ❌ NUNCA guardar objetos dataclass directamente en el storage (no son JSON-serializable)
storage.guardar({"parejas": parejas})  # TypeError al serializar
```

## Grupos — Siempre 3 Parejas

`Grupo` está diseñado para exactamente 3 parejas. El fixture generator asume este invariante.

```python
# ✅ Verificar antes de usar
if grupo.esta_completo():  # retorna True solo cuando len(parejas) == 3
    partidos = grupo.generar_partidos()

# ❌ NUNCA agregar una 4ª pareja a un grupo existente
grupo.agregar_pareja(cuarta_pareja)  # rompe el fixture (3 partidos → 6 partidos)
```

## FaseFinal Enum

Usar el enum `FaseFinal` para todas las referencias a fases del torneo. No usar strings literales.

```python
# ✅ Enum tipado
from core.models import FaseFinal

if partido.fase == FaseFinal.SEMIFINAL:
    ...

# Valores disponibles
FaseFinal.OCTAVOS    # "octavos"
FaseFinal.CUARTOS    # "cuartos"
FaseFinal.SEMIFINAL  # "semifinal"
FaseFinal.FINAL      # "final"

# ❌ NUNCA comparar con strings directos
if partido.fase == "semifinal":  # falla si el valor del enum cambia
    ...
```

## ResultadoPartido — Scores con Tiebreak

El modelo soporta sets con tiebreak. `calcular_ganador()` maneja la lógica completa.

```python
# ✅ Crear resultado con tiebreak en el tercer set
resultado = ResultadoPartido(
    sets_pareja1=[6, 4, 7],
    sets_pareja2=[4, 6, 6],
    tiebreak_pareja1=7,   # solo aplica si hay tiebreak en el set decisivo
    tiebreak_pareja2=5
)
ganador = resultado.calcular_ganador()  # retorna id de la pareja ganadora

# ❌ NUNCA calcular el ganador manualmente fuera del modelo
if sets_pareja1[0] > sets_pareja2[0]:  # no maneja tiebreak ni casos edge
    ganador = pareja1
```

## Ejemplo Real del Proyecto

En `core/models.py`, la clase `Grupo` genera exactamente 3 partidos round-robin:

```python
@dataclass
class Grupo:
    id: str
    categoria: str
    parejas: List[Pareja] = field(default_factory=list)
    resultados: List[ResultadoPartido] = field(default_factory=list)

    def generar_partidos(self):
        """Genera los 3 partidos round-robin: P1vP2, P1vP3, P2vP3."""
        if not self.esta_completo():
            raise ValueError("El grupo necesita exactamente 3 parejas")
        p1, p2, p3 = self.parejas
        return [
            (p1, p2),
            (p1, p3),
            (p2, p3),
        ]

    def esta_completo(self):
        return len(self.parejas) == 3
```

## Referencias

- `core/models.py` — todos los modelos: `Pareja`, `Grupo`, `ResultadoPartido`, `PartidoFinal`, `FixtureFinales`
- `core/algoritmo.py` — consume `Pareja` y produce `ResultadoAlgoritmo`
- `core/clasificacion.py` — consume `Grupo` y `ResultadoPartido` para calcular standings
- `core/fixture_generator.py` — consume `Grupo` para generar fixtures de fase de grupos