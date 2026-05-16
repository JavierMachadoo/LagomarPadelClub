# Bug Ranking — Plan de solución a largo plazo

## Contexto

El sistema soporta dos formas de incorporar parejas a un torneo:

1. **Inscripción** (self-service o admin via "Entrada manual" en `homePanel.html`):
   crea/linkea `Jugador` reales con `jugador_id` y `jugador2_id` en la tabla
   `inscripciones`. Suman puntos al ranking al cerrar el torneo.

2. **Agregar pareja string** (botón en `dashboard.html`):
   crea una pareja como **solo texto**, sin `jugador_id` asociado.
   Sirve como **placeholder temporal** para poder activar un torneo y mostrar
   los grupos antes de tener todas las parejas confirmadas.

El placeholder NUNCA debería llegar a jugar partidos: el admin debe reemplazarlo
por una pareja real antes de cargar resultados.

## Qué pasó en el torneo Mayo 2026

El admin desconocía la diferencia entre los dos caminos. Dos errores se
combinaron:

1. Algunas parejas se cargaron directamente desde "Agregar pareja" (string)
   en vez de "Entrada manual". → No quedaron linkeadas a `Jugador`.
2. Los placeholders `A confirmar / A confirmar` se **editaron** directamente
   cambiándoles el nombre, en lugar de crear una pareja nueva vía entrada
   manual y hacer swap. → La pareja siguió siendo string después de la edición.

**Resultado**: parejas que jugaron partidos quedaron sin `jugador_id` en el
JSONB de `torneo_actual`, y al cerrar el torneo nadie suma puntos al ranking
(`_calcular_y_guardar_puntos()` en `api/routes/historial.py` filtra por
`if not jugador_id: return`).

## Causa raíz

**No es un problema del admin, es un problema del sistema.** La UI ofrece dos
caminos que se ven equivalentes pero uno rompe el sistema en silencio:

- El camino correcto (entrada manual → swap) requiere disciplina y
  conocimiento implícito.
- El camino peligroso (agregar string + editar nombre) es el más visible
  y el más intuitivo.

Buen diseño hace que **lo correcto sea fácil y lo peligroso sea imposible**.
Hoy es al revés.

## Fix obligatorio previo (bug #123)

Antes de cualquier mejora UX, hay que arreglar la base:

**Archivo**: `services/grupo_service.py` → `_cargar_inscripciones_supabase()`

Agregar al dict de cada pareja construida desde la tabla `inscripciones`:

```python
'jugador1_id': insc.get('jugador_id'),   # en inscripciones se llama jugador_id
'jugador2_id': insc.get('jugador2_id'),
```

Sin esto, ni siquiera las parejas inscriptas correctamente quedan con IDs en
el JSONB. Es la base sobre la que se apoya todo lo demás.

---

## Solución a largo plazo — 3 cambios

### Cambio 1 — "Editar pareja" deja de aceptar nombres string

**Dónde**: `dashboard.html` → modal de edición de pareja.

**Comportamiento actual**: el admin abre "Editar pareja" y puede modificar los
nombres como texto libre. Eso convirtió los placeholders en parejas string
con nombres reales pero sin `jugador_id`.

**Comportamiento nuevo**:

- El modal muestra los dos jugadores actuales como **lectura**, no como inputs
  de texto editables.
- En lugar de "editar nombre", cada slot ofrece un botón **"Cambiar jugador"**.
- "Cambiar jugador" abre el mismo flujo que **Entrada manual**:
  - Buscador de jugadores existentes por nombre.
  - Si se encuentra → se linkea el `Jugador` y se actualizan los `jugador_id`
    en TODOS los niveles del JSONB.
  - Si no se encuentra → prompt "no encontré 'X', ¿crear jugador nuevo?".
- El admin nunca más puede dejar una pareja en estado string editando texto.

**Por qué funciona**: convierte el camino que rompió Mayo 2026 (editar
nombre a mano) en el camino correcto (search/create + link). El admin hace
lo natural (editar) y el sistema lo guía bien.

**Detalle técnico crítico**: la operación de "cambiar jugador" debe propagar
los `jugador_id` a los DOS niveles donde viven las parejas en el JSONB:

- `datos.parejas[]`
- `datos.resultado_algoritmo.grupos_por_categoria[cat][grupo].parejas[]`

Hoy parece que solo se toca uno de los dos. Esto explica por qué incluso
algunos swaps de Mayo 2026 quedaron incompletos.

### Cambio 2 — Indicador visual de "pareja sin jugador asignado"

**Dónde**: vistas del admin (`dashboard.html`, `homePanel.html` y donde se
listen parejas).

**Comportamiento**:

- Parejas sin `jugador1_id` o `jugador2_id` se muestran en **color rojo**
  con un badge tipo "⚠️ Sin jugador asignado".
- Tooltip al pasar el mouse: "Esta pareja no suma puntos al ranking. Asignale
  un jugador antes de cargar resultados".
- Solo visible para el **admin**. Los jugadores no ven este marcador en sus
  vistas (no es información que necesiten).

**Por qué funciona**: hace visible un problema que hoy es invisible. El admin
no tiene forma de saber que algo está mal hasta que el torneo cerró y nadie
sumó puntos. Con el indicador rojo lo ve apenas entra al panel.

### Cambio 3 — NO bloquear el cierre del torneo

**Decisión consciente**: el cierre del torneo NO debe validar que todas las
parejas tengan `jugador_id`.

**Por qué**:

- El admin necesita poder **activar el torneo** con placeholders presentes,
  para mostrar grupos y empezar a operar.
- Durante el torneo, mientras un grupo no tenga resultados cargados, el admin
  debe poder cambiar parejas y jugadores.
- Una vez que un grupo recibe el primer resultado, **el sistema ya lo bloquea**
  (no se puede mover, editar ni cambiar). Ese es el gate natural.
- Por lo tanto: si una pareja tiene `jugador_id: null` y su grupo ya tiene
  resultados, esa pareja ya no se va a poder corregir → es un edge case que
  se cubre con el Cambio 1 (no se podría haber llegado a este estado si
  "editar pareja" hubiese funcionado bien).

**Lo único que se mantiene como hoy**: el cálculo de puntos al cerrar filtra
parejas sin `jugador_id` (`if not jugador_id: return`). Si por algún motivo
queda una sin asignar, no rompe el cierre, simplemente no suma puntos para
esa pareja (comportamiento actual).

---

## Fuera de alcance (descartado)

Se consideró y descartó la opción de modelar el placeholder como un `Jugador`
con `estado='placeholder'` + operación de MERGE. Justificación: el placeholder
**nunca llega a jugar** (el admin lo reemplaza antes de cargar resultados),
así que no necesita identidad propia ni acumular historia. Sería sobreingeniería.

El modelo actual (Jugador + Usuario opcional + Inscripción con FKs + placeholder
string temporal) es correcto. El problema está en el flujo de UI, no en el
modelo de dominio.

---

## Orden de implementación sugerido

1. **Fix bug #123** (`_cargar_inscripciones_supabase`) — base obligatoria.
2. **Cambio 1** (editar pareja sin nombre libre) — mata la causa raíz.
3. **Cambio 2** (indicador visual rojo) — hace visible el problema residual.
4. (Cambio 3 es una decisión de no hacer nada — no requiere implementación.)
