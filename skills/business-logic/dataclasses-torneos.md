---
name: dataclasses-torneos
description: >
  Patrones de serialización/deserialización de los dataclasses del proyecto: to_dict(), from_dict(), Enum handling y field(default_factory).
  Trigger: Al añadir campos a modelos existentes, crear modelos nuevos o modificar serialización en core/models.py.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root, core]
  auto_invoke: "Adding fields to existing models or modifying serialization in core/models.py"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## to_dict() y from_dict() van siempre en par (REQUIRED)

Todo dataclass que se persiste en Supabase/JSON debe tener `to_dict()` y `from_dict()`. Si añades un campo, actualiza **ambos métodos** en el mismo commit.

```python
# ✅ CORRECTO: campo añadido en los dos métodos
@dataclass
class Pareja:
    nivel: str = ""  # campo nuevo

    def to_dict(self):
        return {
            ...
            'nivel': self.nivel,  # ← añadir aquí
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            ...
            nivel=data.get('nivel', ''),  # ← y aquí, con default seguro
        )

# ❌ NUNCA usar dataclasses.asdict() directamente para persistencia
from dataclasses import asdict
storage.guardar({'pareja': asdict(pareja)})
# asdict() no maneja Enum.value ni lógica custom de campos como posicion_grupo
```

## Enum: serializar con .value, deserializar con Enum(valor)

Los Enum (`PosicionGrupo`, `FaseFinal`) deben serializarse como su `.value` (string/int) para que el JSON sea legible.

```python
# ✅ CORRECTO: to_dict() convierte Enum → valor primitivo
def to_dict(self):
    return {
        'posicion_grupo': self.posicion_grupo.value if self.posicion_grupo else None,
        # PosicionGrupo.PRIMERO → 1
    }

# ✅ CORRECTO: from_dict() reconstruye Enum desde valor
@classmethod
def from_dict(cls, data: dict):
    posicion = data.get('posicion_grupo')
    return cls(
        posicion_grupo=PosicionGrupo(posicion) if posicion else None,
    )

# ❌ NUNCA guardar el objeto Enum directamente
def to_dict(self):
    return {'posicion_grupo': self.posicion_grupo}  # → no serializable a JSON
```

## Campos mutables: siempre field(default_factory)

Listas y dicts como valores default deben usar `field(default_factory=...)`. Un default mutable compartido entre instancias es un bug silencioso.

```python
# ✅ CORRECTO
@dataclass
class Grupo:
    parejas: List[Pareja] = field(default_factory=list)
    resultados: Dict[str, ResultadoPartido] = field(default_factory=dict)
    partidos: List[Tuple[Pareja, Pareja]] = field(default_factory=list)

# ❌ NUNCA: default mutable compartido entre todas las instancias
@dataclass
class Grupo:
    parejas: List[Pareja] = []   # todas las instancias comparten la misma lista
    resultados: Dict = {}        # bug clásico de Python
```

## from_dict() usa .get() con default para campos opcionales

Los datos en Supabase pueden venir de versiones anteriores del modelo (campos que no existían). Siempre usar `.get()` con un default seguro para campos que no son de la primera versión.

```python
# ✅ CORRECTO: resiliente a datos de versiones antiguas
@classmethod
def from_dict(cls, data: dict):
    return cls(
        id=data['id'],            # obligatorio: KeyError si falta está bien
        nombre=data['nombre'],    # obligatorio
        telefono=data.get('telefono', 'Sin teléfono'),  # opcional con default
        jugador1=data.get('jugador1', ''),              # campo añadido en v2
        jugador2=data.get('jugador2', ''),
        grupo_asignado=data.get('grupo_asignado'),      # None si no existe
    )

# ❌ NUNCA: data['campo_nuevo'] sin .get() rompe datos históricos en Supabase
return cls(jugador1=data['jugador1'])  # KeyError en torneos creados antes del campo
```

## franjas_disponibles: normalizar tipo en from_dict()

El campo `franjas_disponibles` puede venir como lista o string (bug histórico del CSV). Siempre normalizar en `from_dict()`.

```python
# ✅ CORRECTO: patrón de normalización real del proyecto
@classmethod
def from_dict(cls, data: dict):
    franjas_raw = data.get('franjas_disponibles', [])
    if isinstance(franjas_raw, str):
        franjas_raw = [f.strip() for f in franjas_raw.split(',') if f.strip()] if franjas_raw else []
    return cls(
        franjas_disponibles=franjas_raw,
        ...
    )
```

## Ejemplo Real del Proyecto

`ResultadoPartido.to_dict()` en `core/models.py` — incluye campo calculado `ganador_id` que no está en el dataclass:

```python
def to_dict(self):
    return {
        'pareja1_id': self.pareja1_id,
        'pareja2_id': self.pareja2_id,
        'sets_pareja1': self.sets_pareja1,
        'sets_pareja2': self.sets_pareja2,
        'games_set1_pareja1': self.games_set1_pareja1,
        'games_set1_pareja2': self.games_set1_pareja2,
        'games_set2_pareja1': self.games_set2_pareja1,
        'games_set2_pareja2': self.games_set2_pareja2,
        'tiebreak_pareja1': self.tiebreak_pareja1,
        'tiebreak_pareja2': self.tiebreak_pareja2,
        'ganador_id': self.calcular_ganador()  # campo derivado, no del dataclass
    }
```

`from_dict()` no lee `ganador_id` porque es calculado — correcto, no persistir lógica derivada.

## Referencias

- `core/models.py` — todos los dataclasses: `Pareja`, `Grupo`, `ResultadoPartido`, `PartidoFinal`, `FixtureFinales`
- `utils/torneo_storage.py` — serializa/deserializa el torneo completo vía `to_dict()` / `from_dict()`
- `core/clasificacion.py` — usa los modelos para calcular standings
