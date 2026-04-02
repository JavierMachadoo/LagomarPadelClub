# Plan de Refactor — Clean Code

Diagnóstico completo del codebase. Ordenado por severidad y ROI.
Cada ítem incluye el problema, archivo/línea, y la acción concreta a tomar.

---

## Índice

- [CRÍTICO](#crítico)
- [ALTO](#alto)
- [MEDIO](#medio)
- [BAJO](#bajo)
- [Orden de ejecución sugerido](#orden-de-ejecución-sugerido)

---

## CRÍTICO

### C1 — Falta capa de servicios (SRP total roto en rutas)

**Problema:** No existe capa de servicios. Toda la lógica de negocio vive en `api/routes/`. Los handlers construyen objetos de dominio, calculan posiciones, generan fixtures, consultan Supabase y devuelven respuesta — todo mezclado. `grupos.py` tiene 595 líneas, `finales.py` 497, `parejas.py` 386.

**Archivos afectados:**
- `api/routes/grupos.py` — `ejecutar_algoritmo()` tiene 83 líneas de lógica de negocio pura
- `api/routes/finales.py` — generación de fixtures inline en handlers
- `api/routes/resultados.py` — cálculo de posiciones y clasificación inline
- `api/routes/parejas.py` — validaciones de negocio inline
- `main.py` — `admin_panel()` tiene 50 líneas de enriquecimiento de datos inline

**Acción:**
Crear `services/` con:
- `services/torneo_service.py` — estado del torneo, transiciones de fase
- `services/grupo_service.py` — ejecución del algoritmo, asignación de parejas, intercambio
- `services/fixture_service.py` — generación de fixtures y calendario de finales
- `services/resultado_service.py` — cálculo de posiciones, clasificación, standings

Los handlers deben quedar en 10–15 líneas: parsear request → llamar servicio → devolver respuesta.

---

### C2 — `dashboard.html` — God Template (5120 líneas / 248 KB)

**Problema:** El template contiene CSS embebido (~400 líneas), estructura HTML, modales y 71 funciones JavaScript (2900 líneas) en el scope global del browser. Sin módulos, sin separación de responsabilidades.

**Archivo:** `web/templates/dashboard.html`

**Acción:**
Separar el JavaScript en módulos bajo `web/static/js/`:
- `grupos.js` — drag & drop, CRUD de parejas, visualización de grupos
- `finales.js` — bracket visual, fixture de finales, llaves
- `resultados.js` — ingreso y validación de resultados, tiebreak
- `calendario.js` — vista de calendario, polling

El CSS embebido moverlo a `web/static/css/dashboard.css`.

---

### C3 — `renderizarFixture()` definida dos veces con firmas distintas

**Problema:** La función existe en las líneas ~3300 y ~4907 del mismo archivo. La segunda sobreescribe silenciosamente a la primera. JavaScript no emite ningún warning.

**Archivo:** `web/templates/dashboard.html`, líneas ~3300 y ~4907

**Acción:**
Eliminar la definición obsoleta de la línea ~3300 (tiene el cuerpo vacío con un `console.log` que dice "usar /finales"). Mantener solo la implementación real.

---

### C4 — Health check roto (`app.torneo_storage` no existe)

**Problema:** El endpoint `/_health` hace `storage = app.torneo_storage`, pero ese atributo nunca se asigna en ningún lugar del código. El `try/except` silencia el error. UptimeRobot cree que el keep-alive funciona, pero nunca ejecuta una query real a Supabase. **La funcionalidad de keep-alive está completamente rota.**

**Archivo:** `main.py`, líneas 558–563

**Acción:**
```python
# Reemplazar:
storage = app.torneo_storage

# Por:
from utils.torneo_storage import storage
```

---

## ALTO

### A1 — GET con side effects — vista pública escribe en la base de datos

**Problema:** La ruta GET `/grupos` (sin autenticación) genera fixtures de finales como side effect y llama `storage.guardar()` si no existen. Un GET nunca debe tener efectos secundarios ni escribir en BD. Viola el principio de idempotencia HTTP.

**Archivo:** `main.py`, líneas 382–395

**Acción:**
Mover la generación de fixtures a un endpoint POST explícito (ej: `POST /api/grupos/inicializar-fixtures`) llamado desde el panel de admin al cambiar de fase. La vista pública solo lee.

---

### A2 — Double-fetch pattern (doble viaje a Supabase por operación)

**Problema:** En múltiples handlers se llama `obtener_datos_desde_token()` dos veces en la misma función. Cada llamada hace un viaje a Supabase (o disco), duplicando la latencia sin beneficio.

**Archivos afectados:**
- `api/routes/grupos.py` — `asignar_pareja_a_grupo()`, `intercambiar_pareja()`, `reordenar_grupos()`, `actualizar_pareja_en_grupo()`
- `api/routes/parejas.py` — línea 309

```python
# Patrón incorrecto actual:
resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
# ... lógica ...
datos_actuales = obtener_datos_desde_token()  # ← segundo viaje innecesario

# Patrón correcto:
datos = obtener_datos_desde_token()
resultado_data = datos.get('resultado_algoritmo')
# ... lógica ...
# usar la misma variable `datos`
```

**Acción:** Llamar `obtener_datos_desde_token()` una sola vez al inicio de cada handler y mutar esa copia.

---

### A3 — `guardar()` público cuando debería ser privado

**Problema:** El docstring de `guardar()` dice explícitamente "usar solo para operaciones internas", pero se llama directamente desde `parejas.py`, `main.py` y `historial.py`. Esto bypasea el locking optimista (`guardar_con_version()`) y crea condiciones de carrera silenciosas donde escrituras concurrentes se pierden sin error.

**Archivo:** `utils/torneo_storage.py`, líneas 111–130

**Acción:**
Renombrar a `_guardar_sin_version()`. Actualizar todas las llamadas internas. Exponer solo `guardar_con_version()` para uso externo. Los lugares que hoy usan `guardar()` directamente deben migrar a la versión con locking.

---

### A4 — `PartidoFinal` no tiene campo `sets` — workaround de 30 líneas

**Problema:** `finales.py` guarda los sets antes de llamar `to_dict()`, luego los restaura manualmente porque el modelo no los persiste. El comentario en línea 405 lo reconoce como deuda técnica explícita.

**Archivo:** `api/routes/finales.py`, líneas 405–433 y `core/models.py`

**Acción:**
```python
# Agregar a PartidoFinal en core/models.py:
sets: Optional[List[Dict]] = field(default_factory=list)

# Incluirlo en to_dict() y from_dict()
# Eliminar el workaround de 30 líneas en finales.py
```

---

### A5 — Clientes Supabase creados en cada request — sin singleton centralizado

**Problema:** `create_client()` se instancia en 5 lugares distintos del codebase. `historial.py` lo llama hasta 3 veces por request dentro de `_sb_admin()`. Cada instanciación inicializa un pool HTTP + TLS.

**Archivos afectados:**
- `api/routes/historial.py`, líneas 36–39
- `api/routes/grupos.py`, líneas 54–74
- `main.py`, línea 489
- `api/routes/_helpers.py`, línea 24
- (vs. `inscripcion.py` que sí usa singleton — es el patrón correcto)

**Acción:**
Crear `utils/supabase_client.py`:
```python
from supabase import create_client
from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

_client = None

def get_supabase_admin():
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _client
```

Reemplazar todas las instanciaciones inline con `get_supabase_admin()`.

---

### A6 — UUID truncado a 8 chars sin manejo de colisiones

**Problema:** `int(insc['id'].replace('-', '')[:8], 16)` usa solo 32 bits del UUID. Con datos históricos acumulados, las colisiones de ID son posibles. Además, el cálculo está duplicado: inline en `grupos.py` y como función en `inscripcion.py`.

**Archivos afectados:**
- `api/routes/grupos.py`, línea 64
- `api/routes/inscripcion.py`, líneas 77–79

**Acción:**
Centralizar en `inscripcion.py::_uuid_to_int_id()` y eliminar el inline de `grupos.py`. Evaluar migrar a usar el UUID completo como string ID en los modelos.

---

### A7 — `franjas_a_horas_mapa` duplicado y desincronizado

**Problema:** El mismo diccionario de 8 entradas está copiado textualmente en dos archivos. Peor: contiene entradas `'Jueves 18:00'` y `'Jueves 20:00'` que no existen en `config/settings.py::FRANJAS_HORARIAS`. Ya están desincronizados.

**Archivos afectados:**
- `api/routes/grupos.py`, líneas 330–359
- `api/routes/parejas.py`, líneas 310–346

**Acción:**
Mover `FRANJAS_A_HORAS_MAP` a `config/settings.py` como constante única. Importar desde ambos archivos. Eliminar la duplicación y las entradas inválidas.

---

### A8 — `actualizarTodasCategorias()` omite la categoría `Tercera`

**Problema:** La lista hardcodeada es `['Cuarta', 'Quinta', 'Sexta', 'Séptima']`. Para torneos `fin1` (Tercera, Quinta, Séptima), `Tercera` nunca se actualiza.

**Archivo:** `web/templates/dashboard.html`, línea ~4160

**Acción:**
```javascript
// Reemplazar la lista hardcodeada por la variable ya disponible en el scope:
function actualizarTodasCategorias() {
    return Promise.all(CATEGORIAS_TORNEO_FINALES.map(cat => actualizarCategoria(cat)));
}
```

---

### A9 — 60 `console.log` de debug en producción

**Problema:** Incluye logs como `console.log('=== actualizarPartidos ===')` que exponen estructura interna del sistema en la consola de cualquier usuario.

**Archivo:** `web/templates/dashboard.html` (60 ocurrencias)

**Acción:**
Eliminar todos los `console.log`, `console.warn` y `console.error` de debug. Si se necesita logging condicional, usar un flag `const DEBUG = false` y condicionar con `if (DEBUG) console.log(...)`.

---

### A10 — `inicializarDragAndDrop()` es un stub vacío — drag & drop roto en DOM dinámico

**Problema:** La función no hace nada (`// Esta función es por si en el futuro...`), pero se llama desde 4 lugares. El drag & drop usa atributos `ondragstart/ondrop` HTML inline que se pierden cuando el DOM se regenera con `innerHTML`. Los elementos creados dinámicamente no tienen drag & drop funcional.

**Archivo:** `web/templates/dashboard.html`, líneas ~4205–4208

**Acción:**
Implementar delegación de eventos:
```javascript
document.addEventListener('dragstart', (e) => {
    const el = e.target.closest('[data-pareja-id]');
    if (el) handleDragStart(e, el.dataset.parejaId);
});
document.addEventListener('drop', (e) => { ... });
```
Eliminar todos los atributos `ondragstart/ondrop` inline del HTML.

---

### A11 — `_helpers.py::regenerar_fixtures_categoria()` usa la API incorrecta de `GeneradorFixtureFinales`

**Problema:** Instancia `GeneradorFixtureFinales()` y llama `generador.generar_fixture(grupos, NUM_CANCHAS_DEFAULT)`, pero en todos los demás usos del codebase se llama como `GeneradorFixtureFinales.generar_fixture(categoria, grupos)` — firma distinta, como método de clase. Una de las dos invocaciones está usando la API incorrectamente.

**Archivo:** `api/routes/_helpers.py`, líneas 277–278

**Acción:**
Verificar la firma real en `GeneradorFixtureFinales` y normalizar todas las llamadas al mismo patrón.

---

### A12 — Mapas de categorías/colores redefinidos 4 veces en el mismo archivo JS

**Problema:** Los objetos `clasesCategoria`, `emojisCategoria`, `coloresCategoria` aparecen redefinidos en líneas ~2175, ~2427, ~3470 y ~4042. Cualquier cambio requiere actualizar 4 lugares.

**Archivo:** `web/templates/dashboard.html`

**Acción:**
Definir un único objeto `CATEGORIA_CONFIG` al inicio del bloque `<script>`:
```javascript
const CATEGORIA_CONFIG = {
    'Tercera': { clase: 'tercera', emoji: '🥇', color: '#...' },
    // ...
};
```
Referenciar desde todas las funciones. Eliminar las 3 redefiniciones.

---

### A13 — `finales.py` tiene búsqueda lineal O(n) duplicada en dos funciones

**Problema:** El patrón "buscar en qué categoría está el partido iterando todos los fixtures y todas las fases" está copiado casi textualmente entre `actualizar_ganador_partido()` (líneas 241–256) y `guardar_resultado_partido()` (líneas 335–358).

**Archivo:** `api/routes/finales.py`

**Acción:**
Extraer `_buscar_partido_en_fixtures(fixtures_dict, partido_id) -> Optional[Tuple[str, str, int]]` como función helper privada del módulo.

---

### A14 — `intercambiar_pareja()` no valida que `grupo_origen_obj` no sea None

**Problema:** Si se produce una condición de carrera donde la pareja es encontrada (pop exitoso) pero `grupo_destino_obj` es None, el código llega a `grupo_origen_obj['parejas'].append(...)` con posible `TypeError` sin capturar.

**Archivo:** `api/routes/grupos.py`, líneas 151–177

**Acción:**
Agregar validación explícita antes de mutar:
```python
if not grupo_origen_obj or not grupo_destino_obj:
    return jsonify({'error': 'Grupo no encontrado'}), 404
```

---

## MEDIO

### M1 — `limpiar()` y `transicion_a_espera()` duplican ~15 líneas de reset

**Archivo:** `utils/torneo_storage.py`, líneas 223–242 y 285–302

**Acción:**
Extraer `_reset_campos_torneo(torneo, *, preservar_nombre=False, preservar_tipo=False)` como helper privado y usarlo en ambos métodos.

---

### M2 — `get_torneo_id()` tiene side effect implícito

**Problema:** Un getter puede crear una fila en Supabase y escribir en storage. Viola el principio de menor sorpresa.

**Archivo:** `utils/torneo_storage.py`, líneas 244–270

**Acción:**
Separar en `get_torneo_id()` (solo lectura, retorna `None` si no existe) e `inicializar_torneo_id()` (escritura explícita, llamado solo al crear un torneo).

---

### M3 — Lógica OAuth de 50 líneas inline en `main.py`

**Archivo:** `main.py`, líneas 469–543

**Acción:**
Extraer a `services/auth_service.py::procesar_oauth_callback(user_data) -> str` que recibe los datos del usuario OAuth y retorna el JWT. El handler queda en ~10 líneas.

---

### M4 — `datetime.utcnow()` deprecado en Python 3.12

**Archivo:** `utils/jwt_handler.py`, líneas 47–48

**Acción:**
```python
# Reemplazar:
from datetime import datetime, timedelta
datetime.utcnow()

# Por:
from datetime import datetime, timedelta, timezone
datetime.now(tz=timezone.utc)
```

---

### M5 — `cambiar_fase()` genera fixtures dentro del handler (58 líneas de lógica)

**Archivo:** `api/routes/grupos.py`, líneas 536–594

**Acción:**
Mover la generación de fixtures y calendario al `FixtureService` propuesto en C1. El handler solo llama `fixture_service.generar_para_categoria(categoria, grupos)`.

---

### M6 — Validación de tiebreak duplicada en JS y Python

**Problema:** La lógica `sP1 === 1 && sP2 === 1` para detectar necesidad de tiebreak está tanto en `dashboard.html` como en `core/models.py`. Si cambian las reglas, hay que actualizar en dos lugares.

**Acción:**
El backend debe ser la fuente de verdad para las reglas de negocio. El frontend puede hacer validación UX básica (campos vacíos, números negativos), pero la validación de reglas de juego solo vive en Python.

---

### M7 — Serialización manual repetitiva en dataclasses (~150 líneas de boilerplate)

**Problema:** Cada dataclass implementa `to_dict()` y `from_dict()` manualmente. Con 5 dataclasses, son ~150 líneas propensas a quedar desincronizadas cuando se agregan campos.

**Archivo:** `core/models.py`

**Acción:**
Usar `dataclasses.asdict()` como base con post-procesamiento para campos especiales (Enum → `.value`, `Optional`). Alternativamente, evaluar `dacite` para el `from_dict()` automático.

---

### M8 — Polling cada 60s sin backoff ni cancelación ante errores

**Archivo:** `web/templates/dashboard.html`, línea ~4849

**Acción:**
```javascript
let pollInterval = 60000;
let pollTimer = null;

function iniciarPolling() {
    pollTimer = setTimeout(async () => {
        try {
            await cargarFixtures(true);
            pollInterval = 60000; // reset al éxito
        } catch {
            pollInterval = Math.min(pollInterval * 2, 300000); // max 5 min
        }
        iniciarPolling();
    }, pollInterval);
}

function detenerPolling() {
    clearTimeout(pollTimer);
}
```

---

### M9 — `admin_panel()` tiene lógica de enriquecimiento de datos de 50 líneas inline

**Archivo:** `main.py`, líneas 167–216

**Acción:**
Extraer a `services/torneo_service.py::enriquecer_parejas_con_grupo(parejas, grupos_por_cat)`.

---

### M10 — `calcular_ganador()` no maneja tiebreak empatado

**Problema:** Si ambos tiebreaks son iguales (ej: 10–10), el método retorna `None` silenciosamente mientras `esta_completo()` dice que el partido está completo. Inconsistencia de estado.

**Archivo:** `core/models.py`, líneas 51–58

**Acción:**
Agregar validación:
```python
if self.tiebreak_pareja1 == self.tiebreak_pareja2:
    raise ValueError("Tiebreak no puede terminar en empate")
```
O que `esta_completo()` verifique que `calcular_ganador()` no sea `None`.

---

## BAJO

### B1 — `guardar_estado_torneo()` es dead code — stub vacío llamado 8 veces

**Problema:** Marcado como deprecated, cuerpo vacío (`pass`). Importado y llamado en `parejas.py` (4 veces), `grupos.py` (3 veces), `calendario.py` (1 vez). También existe `guardar_estado_torneo_legacy()` que es igualmente dead code.

**Archivo:** `api/routes/_helpers.py`, líneas 310–328

**Acción:**
Eliminar ambas funciones y todas sus importaciones y llamadas.

---

### B2 — Lista de rutas públicas hardcodeada como array de strings

**Problema:** Cada nueva ruta pública requiere acordarse de agregarla a este array en `main.py`. Si se olvida, la ruta queda bloqueada por el middleware silenciosamente, sin error en ningún log.

**Archivo:** `main.py`, línea 121

**Acción:**
Usar un decorator `@public_route` que marque las rutas exentas:
```python
def public_route(f):
    f._is_public = True
    return f

# En el middleware:
if getattr(current_app.view_functions.get(request.endpoint), '_is_public', False):
    return
```
O bien, invertir la lógica: usar `@login_required` explícito en rutas privadas y dejar el default como público.

---

### B3 — `jwt-helper.js` es dead code de arquitectura anterior

**Problema:** El archivo intenta manejar JWT desde el browser, pero la arquitectura actual usa cookies `HttpOnly` — el JWT nunca está accesible desde JS (precisamente por el flag `httponly`). Es un remanente.

**Archivo:** `web/static/js/jwt-helper.js`

**Acción:**
Auditar qué funciones de `jwt-helper.js` se usan realmente desde los templates. Las que no se usen, eliminar. El archivo probablemente se puede borrar en su totalidad.

---

### B4 — Error handlers 404/500 renderizan `base.html` vacío

**Archivo:** `main.py`, líneas 571 y 579

**Acción:**
Crear `web/templates/404.html` y `web/templates/500.html` con mensajes claros y un enlace de vuelta al inicio.

---

### B5 — Magic numbers de score en `algoritmo.py` sin constantes

**Archivo:** `core/algoritmo.py`, líneas 196, 212, 213, 217, 219, 331–332

**Acción:**
```python
SCORE_FRANJA_EXACTA = 1.0
SCORE_FRANJA_DIA = 0.5
SCORE_MAXIMO = 3.0
SCORE_COMPATIBILIDAD_PARCIAL_MIN = 2.0
```

---

### B6 — Selección de franja no-determinista en el algoritmo

**Problema:** `list(set)[0]` produce resultados distintos entre ejecuciones de Python. Con el mismo input, dos corridas consecutivas pueden asignar franjas distintas.

**Archivo:** `core/algoritmo.py`, líneas 194–195

**Acción:**
```python
# Reemplazar:
return 3.0, list(franjas_comunes_todas)[0]

# Por:
return 3.0, sorted(franjas_comunes_todas)[0]
```

---

### B7 — `PartidoFinal.from_dict()` reconstruye `parejas_map` en cada llamada O(n)

**Problema:** `FixtureFinales.from_dict()` llama a `PartidoFinal.from_dict()` una vez por partido (~14 veces). Cada llamada itera todos los grupos × parejas para construir el mapa.

**Archivo:** `core/models.py`, líneas 303–327

**Acción:**
Construir `parejas_map` una sola vez en `FixtureFinales.from_dict()` y pasarlo como parámetro a `PartidoFinal.from_dict()`.

---

### B8 — `PosicionGrupo` Enum se usa inconsistentemente

**Problema:** El Enum existe pero en `resultados.py` se usa su `.value` (entero crudo) directamente, perdiendo el beneficio del tipo.

**Archivos:** `core/models.py` líneas 6–10 y `api/routes/resultados.py` líneas 54, 200–201

**Acción:**
Decidir una convención: o se usa siempre el Enum (comparaciones con `PosicionGrupo.PRIMERO`) o siempre el entero. Eliminar la inconsistencia.

---

### B9 — `app.js` expone `window.torneoUtils` pero nadie lo usa

**Problema:** `app.js` define `TorneoApp` con `validarTelefono`, `exportarTablaCSV`, `toggleBotonCargando` y las exporta como `window.torneoUtils`. Estas funciones son reimplementadas inline en `dashboard.html`. La API pública existe pero está desconectada del uso real.

**Archivo:** `web/static/js/app.js`, línea 221

**Acción:**
Al separar `dashboard.html` en módulos (C2), usar `torneoUtils` desde `app.js` en vez de reimplementar.

---

### B10 — Validación de teléfono diverge entre frontend y backend

**Problema:** `app.js` valida `>= 10 dígitos`, pero `utils/input_validation.py` solo valida longitud máxima, no formato ni mínimo.

**Acción:**
Alinear ambas validaciones. El backend debería rechazar teléfonos con menos de 9 dígitos si esa es la regla de negocio.

---

### B11 — `cargarFixtures()` tiene mapa de renombrado hardcodeado frágil

**Problema:** `if (data.fixtures['Tercera']) fixtures['3era'] = data.fixtures['Tercera']` — puente manual entre nombres de la API y abreviaturas del DOM. Si se agrega una categoría, hay que actualizar 3 estructuras distintas.

**Archivo:** `web/templates/dashboard.html`, líneas ~4864–4868

**Acción:**
Normalizar: la API devuelve los nombres canónicos y el DOM usa los mismos nombres. Eliminar el mapeo.

---

### B12 — `_calcular_compatibilidad` viola SRP — calcula score Y elige franja

**Archivo:** `core/algoritmo.py`, líneas 183–225

**Acción:**
Separar en `_calcular_score_compatibilidad(p1, p2) -> float` y `_elegir_franja(p1, p2) -> Optional[str]`. Permite testear cada responsabilidad por separado.

---

### B13 — `oauth_callback()` sin servicio de autenticación

Ver M3 — aplica al mismo handler.

---

## Orden de ejecución sugerido

El orden está pensado para maximizar impacto con mínima fricción. Cada etapa deja el código en un estado estable y deployable.

### Etapa 1 — Bugs reales (sin refactor, solo fixes)
Cosas rotas hoy que hay que arreglar independientemente del refactor.

| # | Item | Impacto |
|---|------|---------|
| 1 | C4 — health check roto (`app.torneo_storage`) | Keep-alive de producción roto |
| 2 | A8 — `actualizarTodasCategorias()` omite `Tercera` | Bug visible en torneos fin1 |
| 3 | B6 — selección de franja no-determinista | Algoritmo no reproducible |
| 4 | M10 — `calcular_ganador()` retorna None silenciosamente | Estado inconsistente en partido |

### Etapa 2 — Quick wins (alto ROI, bajo riesgo)

| # | Item | Impacto |
|---|------|---------|
| 5 | B1 — eliminar `guardar_estado_torneo()` stub (8 llamadas) | Menos ruido, código más claro |
| 6 | A9 — eliminar 60 `console.log` en producción | Seguridad básica |
| 7 | M4 — reemplazar `datetime.utcnow()` por `datetime.now(tz=timezone.utc)` | Compatibilidad Python 3.12 |
| 8 | A7 — centralizar `franjas_a_horas_mapa` en `config/settings.py` | Elimina duplicación + entradas inválidas |
| 9 | A5 — centralizar Supabase client en `utils/supabase_client.py` | Elimina 5 instanciaciones |

### Etapa 3 — Refactor de capa de datos

| # | Item | Impacto |
|---|------|---------|
| 10 | A3 — hacer `guardar()` privado en TorneoStorage | Cierra condiciones de carrera |
| 11 | M1 — extraer helper de reset en TorneoStorage | Elimina duplicación |
| 12 | M2 — separar `get_torneo_id()` de `inicializar_torneo_id()` | Semántica correcta |
| 13 | A4 — agregar campo `sets` a `PartidoFinal` | Elimina workaround de 30 líneas |
| 14 | B7 — `parejas_map` construido una vez en `FixtureFinales.from_dict()` | Performance |

### Etapa 4 — Refactor de capa de rutas

| # | Item | Impacto |
|---|------|---------|
| 15 | A2 — eliminar double-fetch en todos los handlers | Latencia reducida a la mitad |
| 16 | A13 — extraer `_buscar_partido_en_fixtures()` helper | Elimina duplicación en finales.py |
| 17 | A14 — validar `grupo_origen_obj` en `intercambiar_pareja()` | Previene TypeError |
| 18 | A11 — corregir API de `GeneradorFixtureFinales` en `_helpers.py` | Corrige llamada incorrecta |
| 19 | C1 — **crear capa de servicios** | Refactor estructural mayor |

### Etapa 5 — Refactor de frontend

| # | Item | Impacto |
|---|------|---------|
| 20 | C3 — eliminar `renderizarFixture()` duplicado | Elimina shadowing silencioso |
| 21 | A12 — unificar `CATEGORIA_CONFIG` en un solo objeto | Elimina 4 redefiniciones |
| 22 | A10 — implementar delegación de eventos para drag & drop | Drag & drop funcional en DOM dinámico |
| 23 | M8 — polling con backoff exponencial | Resiliencia ante errores de red |
| 24 | C2 — **partir `dashboard.html` en módulos JS** | Refactor estructural mayor |

### Etapa 6 — Limpieza final

| # | Item |
|---|------|
| 25 | B2 — reemplazar lista de rutas públicas con decorator |
| 26 | B3 — auditar y eliminar `jwt-helper.js` |
| 27 | B4 — crear templates 404.html y 500.html |
| 28 | B5 — extraer constantes de score en `algoritmo.py` |
| 29 | B8 — consistencia en uso de `PosicionGrupo` Enum |
| 30 | B9 — conectar `window.torneoUtils` desde los nuevos módulos JS |
| 31 | B10 — alinear validación de teléfono frontend/backend |
| 32 | B11 — eliminar mapa de renombrado en `cargarFixtures()` |
| 33 | B12 — separar `_calcular_compatibilidad()` en dos funciones |
| 34 | M7 — evaluar serialización automática con `dataclasses.asdict()` |

---

## Resumen de deuda técnica

| Severidad | Cantidad |
|-----------|----------|
| CRÍTICO | 4 |
| ALTO | 14 |
| MEDIO | 10 |
| BAJO | 13 |
| **Total** | **41** |

El 80% del impacto se consigue con las Etapas 1–4 (ítems 1–19).
Las Etapas 5–6 son importantes pero no bloquean mantenibilidad diaria.
