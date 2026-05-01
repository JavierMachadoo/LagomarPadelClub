# Deuda Técnica — LagomarPadelClub

> Review por: Senior Engineer  
> Fecha: 2026-05-01  
> Branch: Feature/JugadoresIdentidad

---

## Resumen Ejecutivo

El codebase está en una etapa que podría describirse como "adolescencia arquitectónica": arrancó como un script de administración de torneos, fue creciendo con funcionalidad real (auth, inscripciones, ranking, historial), y ya tiene demasiada complejidad para seguir siendo un monolito Flask con un único blob JSON en Supabase. La buena noticia: hay una separación de capas que está _intentando_ existir (services/, blueprints, storage abstraction). La mala: esa separación es inconsistente y convive con prácticas que no escalan.

El riesgo principal no es técnico sino operacional: el modelo de **un único torneo activo persistido como un JSONB de varios MB** en una sola fila de Supabase se convierte en un punto único de fallo con optimistic locking. Cada operación relevante del torneo (inscripción, resultado, asignación) lee y escribe ese blob entero. Con volumen real de inscripciones concurrentes, los `ConflictError` van a cascadear. Hoy con 1 admin esto no se nota; con jugadores haciendo inscripciones simultáneas sí.

La segunda deuda urgente está en `main.py`: tiene ~660 líneas que mezclan factory de app, rutas públicas, funciones helper de negocio (`_build_calendario_index`, `_enriquecer_calendario_con_resultados`, `_build_franjas_finales`), el flujo OAuth completo, y el callback de confirmación de email. Esto hace imposible testear esas rutas de forma aislada. La deuda de tests en las rutas de `main.py` es total: cero cobertura en el auth callback.

La tercera preocupación es seguridad: el rate limiter en producción (Render + 2+ workers) usa `memory://` como backend, lo que hace que el límite sea *por worker*, no global. Un atacante puede triplicar su tasa de intentos si hay 3 workers. Esto es un bug silencioso que probablemente no se noto porque Railway tiene 1 worker, pero la nota en `gunicorn.conf.py` dice "2 workers en Railway prod".

---

## Tabla de Severidad

| # | Problema | Severidad | Área |
|---|----------|-----------|------|
| 1 | Rate limiter con backend `memory://` + múltiples workers | 🔴 CRÍTICO | Seguridad |
| 2 | `main.py` con 660 líneas: rutas + helpers de negocio + OAuth completo | 🔴 CRÍTICO | Arquitectura |
| 3 | JSONB blob único como estado mutable del torneo activo | 🟠 ALTO | Arquitectura / Datos |
| 4 | `inscripcion.py`: N+1 queries sin resolver en `invitaciones_pendientes` | 🟠 ALTO | Performance |
| 5 | `_uuid_to_int_id()`: colisiones de hash para IDs de parejas | 🟠 ALTO | Correctitud |
| 6 | `crear_respuesta_con_token_actualizado()` genera tokens anónimos sin rol | 🟠 ALTO | Seguridad |
| 7 | `ADMIN_PASSWORD` hardcodeado con valor por defecto en `settings.py` | 🟠 ALTO | Seguridad |
| 8 | Lógica de negocio en `main.py`: `_enriquecer_calendario_con_resultados`, `_auto_generar_fixtures` en ruta GET | 🟠 ALTO | Clean Code |
| 9 | Sin CSRF protection para rutas que modifican estado (POST sin token CSRF) | 🟠 ALTO | Seguridad |
| 10 | `auth_jugador.py:134` — `list_users()` sin paginación puede fallar con muchos usuarios | 🟡 MEDIO | Performance |
| 11 | `dashboard.html` de 216KB con lógica de negocio embebida en Jinja2 | 🟡 MEDIO | Frontend |
| 12 | `config/__init__.py` es `from .settings import *` — wildcard import | 🟡 MEDIO | Clean Code |
| 13 | Magic strings duplicados para nombres de franjas horarias | 🟡 MEDIO | Mantenibilidad |
| 14 | `sincronizar_con_storage_y_token()` guarda sin versión en rutas críticas | 🟡 MEDIO | Correctitud |
| 15 | `ResultadoAlgoritmo` no tiene `to_dict()` ni `from_dict()` — serialización manual dispersa | 🟡 MEDIO | Modelo |
| 16 | Tests de integración en `conftest.py` crean app real (Supabase) sin aislar cold start | 🟡 MEDIO | Testabilidad |
| 17 | Ausencia total de tests para `main.py`, `auth_jugador.py`, `inscripcion.py` | 🟡 MEDIO | Testabilidad |
| 18 | `gunicorn.conf.py` tiene `loglevel = "warning"` — pierde INFO de producción | 🔵 BAJO | Operabilidad |
| 19 | `validar_longitud()` no valida ausencia o tipo — solo longitud máxima | 🔵 BAJO | Seguridad |
| 20 | `pandas` como dependencia solo para leer CSV | 🔵 BAJO | Dependencias |

---

## 1. Arquitectura

### `main.py` como God Object — 660 líneas
**Severidad:** 🔴 CRÍTICO  
**Dónde:** `main.py:56–663`  
**Problema:** `crear_app()` hace demasiado. Contiene: factory de app, registro de blueprints, middleware de auth, rutas (`/`, `/admin`, `/dashboard`, `/finales`, `/grupos`, `/calendario`, `/cuadro`, `/registro`, `/auth/callback`), helpers de negocio (`_build_calendario_index`, `_enriquecer_calendario_con_resultados`, `_build_franjas_finales`, `_jugador_ya_inscripto`), y el flujo OAuth completo de Supabase con creación de perfiles. Las funciones helper están definidas _dentro_ de `crear_app()`, lo que hace que sean closures no testeables.  
**Impacto:** Imposible testear `/auth/callback`, `/grupos`, `/calendario` de forma aislada. Cualquier cambio en auth toca el mismo archivo que maneja el calendario.  
**Qué haría yo:** Mover las rutas de páginas públicas a un blueprint `web_bp` en `api/routes/web.py`. Mover el flujo OAuth a `api/routes/auth_jugador.py` (donde debería vivir conceptualmente). Extraer los helpers de negocio a `services/` o a `utils/`. Dejar `main.py` en < 100 líneas: solo factory, registro de blueprints, y `_registrar_extras`.

---

### Modelo JSONB de torneo único activo
**Severidad:** 🟠 ALTO  
**Dónde:** `utils/torneo_storage.py:52–355`, tabla `torneo_actual` en Supabase  
**Problema:** Todo el estado mutable del torneo activo (parejas, grupos, resultados, fixtures, calendario) vive en un único JSONB en una única fila (`id=1`). Cada escritura reemplaza el blob entero. El optimistic locking via RPC (`guardar_torneo_con_version`) es correcto para un solo admin, pero en el flujo de inscripciones los jugadores también escriben (`_auto_asignar_en_grupos` en `inscripcion.py:161` llama a `storage.guardar_con_version`). Con 10 jugadores inscribiéndose simultáneamente, la mayoría recibirá `ConflictError` y su inscripción se guardará en `inscripciones` (Supabase relacional) pero NO quedará reflejada en el blob. Esto crea inconsistencia de datos: la inscripción existe en la tabla `inscripciones` pero la pareja no aparece en el resultado del algoritmo.  
**Impacto:** Corrupción silenciosa de datos en concurrencia moderada. El jugador ve su inscripción confirmada pero el admin no la ve en el dashboard.  
**Qué haría yo:** Separar el estado de "torneo activo" en dos partes: (1) datos mutables por inscripción → tabla `inscripciones` relacional (ya existe), (2) resultado del algoritmo → tabla separada con versión, editable solo por admin. El blob solo guardaría configuración del torneo, no el estado de inscripciones.

---

### Falta de separación clara Domain / Application / Infrastructure
**Severidad:** 🟠 ALTO  
**Dónde:** Todo el proyecto  
**Problema:** Hay una estructura `services/` que intenta ser capa de aplicación, pero los modelos en `core/models.py` tienen `to_dict()` y `from_dict()` (infraestructura de serialización mezclada con dominio), los blueprints en `api/routes/` acceden directamente a `storage` (infraestructura), y la lógica de negocio de inscripciones (validar-no-inscripto, cancelar-pendiente, auto-asignar) vive en el blueprint en vez de en un service. `inscripcion.py` es especialmente problemático: tiene 1072 líneas con 8+ funciones helper privadas que son servicios de dominio disfrazados de helpers de ruta.  
**Impacto:** Imposible reusar lógica de inscripción desde otro punto de entrada (CLI, tests, otro blueprint). Testear la lógica de negocio requiere montar Flask completo.  
**Qué haría yo:** Crear `services/inscripcion_service.py` que contenga `crear_inscripcion()`, `aceptar_invitacion()`, `rechazar_invitacion()`, `cancelar_inscripcion()`. Las funciones `_auto_asignar_en_grupos`, `_auto_eliminar_de_grupos`, `_ejecutar_aceptar_invitacion` ya son servicios — moverlas ahí directamente.

---

## 2. Modelo de Datos

### `_uuid_to_int_id()`: colisiones garantizadas
**Severidad:** 🟠 ALTO  
**Dónde:** `api/routes/inscripcion.py:69–71`  
**Problema:**
```python
def _uuid_to_int_id(uuid_str: str) -> int:
    return int(uuid_str.replace('-', '')[:8], 16)
```
Toma los primeros 8 caracteres hex del UUID (32 bits) y los convierte a int. El espacio de colisión es `2^32 = ~4 mil millones`. Con la paradoja del cumpleaños, la probabilidad de colisión a 10.000 registros es insignificante, pero a 100.000 registros supera el 1%. Más grave: si dos inscripciones distintas generan el mismo `int_id`, `_es_la_pareja()` confunde una pareja con otra, pudiendo eliminar la pareja incorrecta del torneo cuando alguien cancela su inscripción.  
**Impacto:** Bug de correctitud con consecuencias silenciosas: la pareja equivocada puede ser removida del torneo activo sin ningún error visible.  
**Qué haría yo:** El `Pareja.id` debería ser el `inscripcion_id` (UUID string) directamente. El hecho de que `Pareja.id` sea `int` (definido en `core/models.py:157`) mientras todas las identidades reales del sistema son UUIDs es la raíz del problema. Cambiar `Pareja.id: int` a `Pareja.id: str` y usar el UUID directamente.

---

### `ResultadoAlgoritmo` no es serializable como entidad de dominio
**Severidad:** 🟡 MEDIO  
**Dónde:** `core/models.py:316–323`  
**Problema:** `ResultadoAlgoritmo` es un dataclass con `grupos_por_categoria: dict` (dict de dicts, no de `List[Grupo]`) y `parejas_sin_asignar: List[Pareja]`. No tiene `to_dict()` ni `from_dict()`. La serialización ocurre ad-hoc en `algoritmo.py` (los grupos se serializan con `.to_dict()`), pero `ResultadoAlgoritmo` en sí nunca se persiste como objeto — se persiste el `resultado.grupos_por_categoria` que ya viene serializado como dict de dicts desde el algoritmo. Esto significa que `ResultadoAlgoritmo` como tipo en el código es un tipo fantasma: existe en el algoritmo pero nunca se reconstruye; lo que se trabaja es siempre el dict crudo.  
**Impacto:** Existe una función `deserializar_resultado` en `api/routes/_helpers.py` que reconstruye el objeto, pero el 90% del código trabaja con el dict crudo, haciendo que el tipado sea engañoso.  
**Qué haría yo:** O implementar `to_dict()`/`from_dict()` en `ResultadoAlgoritmo` de forma consistente, o eliminar el dataclass y usar siempre el dict (siendo honesto sobre lo que es el modelo). La inconsistencia actual es lo más peligroso.

---

### `Jugador` y `Pareja` son entidades separadas sin relación explícita
**Severidad:** 🟡 MEDIO  
**Dónde:** `core/models.py:7–44`, `core/models.py:155–215`  
**Problema:** `Pareja` tiene `jugador1_id` y `jugador2_id` como campos opcionales (`Optional[str]`). Esto significa que una pareja puede existir sin jugadores vinculados (parejas cargadas por CSV). El sistema tiene dos tipos de pareja: las del catálogo de jugadores (tienen UUIDs) y las del CSV (tienen nombre como string). Esta distinción existe pero no está modelada — es una inferencia que el lector debe hacer al ver los campos opcionales. No hay una abstracción `ParejaCSV` vs `ParejaRegistrada`.  
**Impacto:** Código defensivo en todas partes: `if pareja.get('jugador1_id')`, `if inscripcion.get('jugador2_id')`. La lógica de si una pareja tiene identidad digital está dispersa.

---

## 3. Clean Code

### Lógica de negocio embebida en rutas GET de `main.py`
**Severidad:** 🟠 ALTO  
**Dónde:** `main.py:391–409` (auto-generar fixtures en `/grupos` GET)  
**Problema:** La ruta `GET /grupos` (que debería ser idempotente) tiene un bloque que genera y persiste fixtures automáticamente si no existen:
```python
# Auto-generar fixtures para categorías que tengan grupos pero no tengan fixture
if resultado:
    grupos_por_cat = resultado.get('grupos_por_categoria', {})
    guardado = False
    for cat in categorias_torneo:
        if cat not in fixtures and cat in grupos_por_cat:
            ...
            storage.guardar_con_version(torneo)
```
Un GET modifica estado. Si dos usuarios abren `/grupos` simultáneamente, pueden generar un `ConflictError`. Los side effects en GETs son difíciles de debuggear y violan el principio de menor sorpresa.  
**Impacto:** Una request de lectura puede fallar con HTTP 409. Los bots de indexación o health checks pueden disparar generación de fixtures inesperadamente.  
**Qué haría yo:** Mover la generación de fixtures a un evento explícito: cuando el admin cambia la fase a `torneo`, generar los fixtures automáticamente en ese momento (en el endpoint `POST /cambiar-fase`). La ruta GET solo debería leer.

---

### `_enriquecer_calendario_con_resultados` muta el objeto de entrada
**Severidad:** 🟡 MEDIO  
**Dónde:** `main.py:289–329`  
**Problema:** La función recibe `resultado` por referencia y muta los dicts internos del calendario inyectando la clave `'resultado'` en cada partido. Esto es un efecto secundario invisible. Si la función se llama dos veces sobre el mismo objeto (que puede pasar en tests o si el objeto se cachea), los resultados se acumulan incorrectamente.  
**Qué haría yo:** Hacer la función pura: que retorne un nuevo dict enriquecido en vez de mutar el input. Renombrarla `_construir_calendario_con_resultados` para que el nombre refleje que produce algo.

---

### `config/__init__.py` es un wildcard import
**Severidad:** 🟡 MEDIO  
**Dónde:** `config/__init__.py:1`  
**Problema:** `from .settings import *` importa todo lo de settings al namespace de `config`. Esto es el patrón anti-recomendado en Python. Imposibilita saber qué nombres exporta `config` sin leer `settings.py` completo. Si `settings.py` agrega una variable que colisiona con algo en el módulo que importa de `config`, el bug es silencioso.  
**Qué haría yo:**
```python
# config/__init__.py
from .settings import (
    SECRET_KEY, CATEGORIAS, FRANJAS_HORARIAS,
    EMOJI_CATEGORIA, COLORES_CATEGORIA,
    ADMIN_USERNAME, ADMIN_PASSWORD,
    TIPOS_TORNEO, NUM_CANCHAS_DEFAULT,
)
```

---

### Magic strings de franjas duplicados en templates
**Severidad:** 🟡 MEDIO  
**Dónde:** `web/templates/dashboard.html:215–221`, `web/templates/dashboard.html:275–282`  
**Problema:** Las opciones del select de franjas horarias están hardcodeadas en HTML con los mismos strings que `config/settings.py:FRANJAS_HORARIAS`. Si se agrega una franja al sistema hay que actualizarla en al menos 3 lugares: `settings.py`, el select del modal "Crear Grupo", y el select del modal "Editar Grupo". Ya están desincronizados — `settings.py` tiene 6 franjas; los selects tienen las mismas 6 franjas pero escritas manualmente con el rango de fin de bloque (ej: "18:00 a 21:00") que no viene del config.  
**Qué haría yo:** Pasar `FRANJAS_HORARIAS` al template y renderizar con Jinja2:
```jinja2
{% for franja in franjas %}
<option value="{{ franja }}">{{ franja }}</option>
{% endfor %}
```

---

### Código muerto en `api_helpers.py`
**Severidad:** 🔵 BAJO  
**Dónde:** `utils/api_helpers.py:94–112`  
**Problema:** `actualizar_datos_en_token()` genera un nuevo JWT con datos del torneo. Pero el comentario en `crear_respuesta_con_token_actualizado()` dice explícitamente que el token ya NO almacena datos del torneo. La función es código muerto que genera tokens incorrectos si se llama.  
**Qué haría yo:** Eliminar la función. Dejar solo el comentario de por qué ya no existe.

---

## 4. Seguridad

### Rate limiter con `memory://` + múltiples workers
**Severidad:** 🔴 CRÍTICO  
**Dónde:** `utils/rate_limiter.py:12–18`, `gunicorn.conf.py:9`  
**Problema:** `RATE_LIMIT_STORAGE_URI` por defecto es `memory://`. El comentario en `rate_limiter.py` reconoce que esto requiere un storage compartido en producción con múltiples workers. Pero `gunicorn.conf.py` tiene `workers = 1` *pero* los comentarios en `CLAUDE.md` dicen "Railway prod → 2 workers". Si en algún momento se usa más de 1 worker (o si se deployó con 2 workers en Railway como dice el archivo de configuración mencionado en CLAUDE.md), el rate limit es efectivamente `N_workers × limit` por atacante.

El límite de `/api/auth/login` es 5/minuto. Con 2 workers → 10 intentos/minuto. Con más workers, más aún.  
**Impacto:** Fuerza bruta efectiva contra el login de admin y registro de jugadores.  
**Qué haría yo:** En producción con cualquier número de workers > 1, usar Redis o Memcached como backend. Si no hay Redis disponible, documentar explícitamente que workers DEBE ser 1 y añadir un check en startup:
```python
import os
if int(os.getenv('WEB_CONCURRENCY', 1)) > 1 and RATE_LIMIT_STORAGE_URI == 'memory://':
    raise RuntimeError("Rate limiter memory:// no es seguro con múltiples workers")
```

---

### `ADMIN_PASSWORD` con valor por defecto inseguro
**Severidad:** 🟠 ALTO  
**Dónde:** `config/settings.py:25`  
**Problema:**
```python
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'torneopadel2026')
```
Si la variable de entorno no está seteada, la contraseña es pública y conocida (está en el repo). Aunque en producción debería estar seteada, un deploy incompleto o un error de configuración deja la app con credenciales conocidas. A diferencia de `SECRET_KEY` que tiene advertencia en producción, `ADMIN_PASSWORD` no tiene ningún check.  
**Qué haría yo:** Hacer que en producción (`DEBUG=False`) la app falle en startup si `ADMIN_PASSWORD` no está configurada o si sigue siendo el valor por defecto:
```python
if not DEBUG and ADMIN_PASSWORD == 'torneopadel2026':
    raise RuntimeError("ADMIN_PASSWORD debe cambiarse en producción")
```

---

### `crear_respuesta_con_token_actualizado()` emite tokens sin rol
**Severidad:** 🟠 ALTO  
**Dónde:** `utils/api_helpers.py:115–157`  
**Problema:**
```python
token_data = {
    'authenticated': True,
    'session_id': 'torneo_session',
    'timestamp': int(time.time())
}
```
Este token no tiene campo `'role'`. En `main.py:138–140`:
```python
role = data.get('role')
if role is None or role == 'admin':
    g.es_admin = True
```
El comentario dice "Compatibilidad: tokens previos sin campo 'role' eran siempre admin". Esto significa que cualquier respuesta de la API que actualiza la cookie (agregar pareja, editar grupo, etc.) está emitiendo un token que el middleware interpreta como ADMIN. Si un jugador de alguna forma obtiene uno de estos tokens (por ejemplo, si hay un XSS que lee la cookie... espera, es HttpOnly, entonces no aplica directamente), el problema es de diseño: el sistema tiene tokens de "admin implícito" circulando por diseño.  
**Qué haría yo:** Siempre incluir el rol en el token. Eliminar la compatibilidad hacia atrás con `role is None → admin`. Es mejor romper una sesión vieja que tener tokens que dan admin por defecto.

---

### Sin CSRF protection
**Severidad:** 🟠 ALTO  
**Dónde:** Todo el proyecto  
**Problema:** Flask-WTF no está instalado. No hay CSRF tokens en los formularios HTML ni en las rutas POST. La única mitigación es `samesite='Lax'` en las cookies, que protege contra cross-site requests en navegadores modernos para la mayoría de los casos, pero no cubre:
- Navegadores sin soporte completo de SameSite
- Requests desde el mismo sitio (reflected XSS)
- API endpoints que aceptan JSON (los headers `Content-Type: application/json` no son CSRF-safe por defecto en todos los contextos)

**Qué haría yo:** Dado el modelo de uso (app de club, usuarios conocidos, escala pequeña), `samesite='Lax'` es probablemente aceptable como riesgo residual. Pero documentarlo explícitamente como decisión, no como omisión.

---

### Validación de CSV insuficiente
**Severidad:** 🟡 MEDIO  
**Dónde:** `api/routes/parejas.py:37`, `utils/csv_processor.py:107–108`  
**Problema:** La validación del archivo CSV se limita a:
```python
def validar_archivo(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv', 'xlsx'}
```
Solo valida la extensión del nombre. No hay validación de:
- Content-Type del upload (un atacante puede subir un `.csv` que contiene HTML o scripts)
- Tamaño máximo de filas (el CSV podría tener millones de filas)
- Encoding malicioso
- Fórmulas CSV injection (`=CMD...` en campos de nombre)

`pd.read_csv(file)` en `parejas.py:37` carga el archivo completo en memoria sin límite de filas.  
**Qué haría yo:** Añadir `nrows=10000` al `pd.read_csv()`. Validar Content-Type. Sanear los valores de string con strip antes de procesar.

---

### `_es_redirect_seguro()` no cubre todos los vectores
**Severidad:** 🔵 BAJO  
**Dónde:** `api/routes/auth_jugador.py:32–47`  
**Problema:** La validación rechaza `//evil.com` pero no valida URLs con `\` (backslash en el path) ni URLs con caracteres de control. La mayoría de los browsers interpretan `\` como `/` en redirects. Aunque la validación actual es correcta para los casos comunes, `urlparse` en Python puede no detectar todos los casos edge.  
**Qué haría yo:** Agregar un check explícito: `and '\\' not in url`.

---

## 5. Performance

### N+1 queries en `invitaciones_pendientes`
**Severidad:** 🟠 ALTO  
**Dónde:** `api/routes/inscripcion.py:626–684`  
**Problema:** La ruta `GET /api/inscripcion/invitaciones-pendientes` hace:
1. Una query para obtener las invitaciones
2. **Por cada invitación**: una query para obtener el perfil del invitador
3. **Por cada invitación**: otra query para obtener la fecha de expiración del token

Con N invitaciones → 1 + 2N queries. Esto es un N+1 clásico.

Cabe señalar que el endpoint `/api/inscripcion/estado` (línea 689) SÍ lo resuelve correctamente con batch queries. Pero el endpoint viejo no fue actualizado y sigue siendo accesible.  
**Impacto:** Con 20 invitaciones pendientes → 41 queries a Supabase. A ~200ms por query → 8 segundos de latencia.  
**Qué haría yo:** O eliminar el endpoint viejo (ya tiene uno nuevo que lo reemplaza), o refactorizarlo usando el mismo patrón de batch queries del `/estado`.

---

### `storage.cargar()` llamado 2-3 veces por request en rutas de admin
**Severidad:** 🟡 MEDIO  
**Dónde:** `main.py:111–122`, `main.py:179`, `main.py:197`, `main.py:237`  
**Problema:** El context processor `inject_globals()` llama a `storage.cargar()` en TODOS los requests (incluyendo los de API JSON). Luego las rutas de página (`/admin`, `/dashboard`) llaman a `storage.cargar()` nuevamente. En total, un request a `/admin` hace 3 llamadas a `storage.cargar()`. Dentro del TTL de 5s, estas son hits de caché (costo ~0), pero si la primera llamada expira el caché, las siguientes llamadas se serializan.

**Qué haría yo:** El context processor no debería llamar a `storage.cargar()` para requests a `/api/*`. Añadir una guarda:
```python
if request.path.startswith('/api/'):
    return dict(es_admin=getattr(g, 'es_admin', False), ...)
```

---

### `auth_jugador.py:134` — `list_users()` carga todos los usuarios en memoria
**Severidad:** 🟡 MEDIO  
**Dónde:** `api/routes/auth_jugador.py:134`  
**Problema:**
```python
all_users = sb_admin.auth.admin.list_users()
existing = next((u for u in all_users if u.email == email), None)
```
`list_users()` sin parámetros devuelve hasta 1000 usuarios por defecto (límite de Supabase Admin API). Esto se ejecuta en el path de recuperación de un registro parcial (cuando el email ya existe en auth pero no en la tabla jugadores). Para un club pequeño no es crítico, pero es un anti-pattern: buscar un usuario por email debería ser una query parametrizada, no un scan completo en memoria.  
**Qué haría yo:** Usar `list_users(filter=f"email eq '{email}'")` o el endpoint `get_user_by_email()` si la SDK lo expone.

---

### Backtracking en `algoritmo.py` sin límite absoluto de tiempo
**Severidad:** 🔵 BAJO  
**Dónde:** `core/algoritmo.py:111–187`  
**Problema:** El backtracking limita la cantidad de combinaciones exploradas (`max_combos = min(15, ...)`) pero no tiene un timeout. Con 18+ parejas en una categoría (6 grupos), el espacio de búsqueda puede ser `C(18,3) × C(15,3) × ...` que con la poda es manejable, pero no hay garantía de término acotado en tiempo.  
**Impacto:** En casos extremos, un request al endpoint `ejecutar-algoritmo` podría tardar más de 60s y Gunicorn mataría el worker (timeout configurado).  
**Qué haría yo:** Agregar un contador de nodos explorados y cortar el backtracking si supera un umbral (10.000 nodos), cayendo al greedy.

---

## 6. Testabilidad

### Cero tests para `main.py`, `auth_jugador.py`, `inscripcion.py`
**Severidad:** 🟡 MEDIO  
**Dónde:** `tests/` (ausencia)  
**Problema:** Los tres archivos más críticos en términos de seguridad y lógica de negocio compleja no tienen tests:
- `main.py`: flujo OAuth, confirmación de email, generación automática de fixtures en GET
- `auth_jugador.py`: login, registro, PKCE OAuth, exchange-token
- `inscripcion.py`: aceptar invitación, rechazar, auto-asignar en grupos, tokens de invitación

Lo que SÍ tiene tests: `AlgoritmoGrupos` (bien), modelos (bien), `JugadoresStorage` (bien). Hay una correlación inversa: los tests cubren las partes más estables y puras, y no cubren las partes más volátiles.  
**Qué haría yo:** Prioridad 1: tests de integración para el flujo de inscripción completo (crear → invitar → aceptar) usando Supabase mockeado. Prioridad 2: tests para el login (caso jugador, caso admin, caso fallback).

---

### `conftest.py`: el fixture `app` tiene scope `session` pero inicializa la app real
**Severidad:** 🟡 MEDIO  
**Dónde:** `tests/conftest.py:19–25`  
**Problema:**
```python
@pytest.fixture(scope="session")
def app():
    flask_app = crear_app()
    ...
```
`crear_app()` inicializa el rate limiter, registra blueprints, y crea el `JWTHandler`. También instancia `storage = TorneoStorage()` a nivel de módulo, que en el import intenta conectarse a Supabase si las variables de entorno están seteadas. Si un desarrollador tiene las variables de Supabase del entorno de dev seteadas localmente, los tests pueden impactar la base de datos de desarrollo.  
**Qué haría yo:** Agregar al setup de tests:
```python
# conftest.py
import os
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_SERVICE_ROLE_KEY', '')
```
Esto garantiza que los tests siempre usen el fallback JSON, independientemente del entorno local.

---

### Tests de storage mockean `utils.torneo_storage.storage` directamente
**Severidad:** 🔵 BAJO  
**Dónde:** `tests/conftest.py:69–77`  
**Problema:** El mock parcha la instancia global `storage`. Esto funciona, pero es frágil: si se agrega un nuevo módulo que importa storage con `from utils.torneo_storage import storage` (en vez de `import utils.torneo_storage`), el mock no lo captura. Los tests de `inscripcion.py` en particular van a fallar cuando se escriban, porque `inscripcion.py` importa storage directamente.  
**Qué haría yo:** Usar `patch("utils.torneo_storage.storage")` como en el conftest, pero asegurarse de que todos los módulos que usan storage lo importen de la misma forma.

---

## 7. Frontend

### `dashboard.html` de 216KB con múltiples responsabilidades
**Severidad:** 🟡 MEDIO  
**Dónde:** `web/templates/dashboard.html`  
**Problema:** El template de 216KB contiene: 6+ modales Bootstrap, tabs de navegación, HTML condicional para admin vs jugador, estilos inline, y referencias a 5+ archivos JS externos. Es un template que no puede leer un humano de corrido. Las primeras 300 líneas son solo modales — el contenido real del dashboard empieza después. Los modales de "Crear Grupo" y "Editar Grupo" (líneas 198-293) tienen las franjas hardcodeadas como se mencionó antes.  
**Impacto:** Tiempo de carga inicial alto (el browser debe parsear 216KB de HTML antes de renderizar nada). Cualquier cambio requiere buscar con grep porque no hay estructura navegable.  
**Qué haría yo:** Como primer paso: extraer los modales a includes de Jinja2 (`{% include 'partials/modal_agregar_pareja.html' %}`). Esto reduce el tamaño percibido y hace que cada modal sea editable en aislamiento. Segundo paso: mover la lógica del dashboard de grupos/resultados a un endpoint JSON y renderizar con JS (ya se hace parcialmente).

---

### Validación de teléfono inconsistente entre frontend y backend
**Severidad:** 🔵 BAJO  
**Dónde:** `web/static/js/app.js:29–33` vs `api/routes/auth_jugador.py:88–89`  
**Problema:** El frontend valida que el teléfono tenga al menos 10 dígitos numéricos. El backend de registro valida con `r'^\d{6,20}$'` (mínimo 6 dígitos). Un número de 7 dígitos pasaría la validación del backend pero el frontend lo rechazaría. No es crítico, pero en el otro sentido (frontend más permisivo que backend) podría generar UX confusa donde el usuario siente que hizo todo bien y el backend falla.

---

## 8. Dependencias

### `pandas` para leer CSV
**Severidad:** 🔵 BAJO  
**Dónde:** `requirements.txt`, `api/routes/parejas.py:37`, `utils/csv_processor.py`  
**Problema:** `pandas` es una dependencia de ~30MB (con numpy) que se usa exclusivamente para `pd.read_csv()` y `df.iterrows()`. La librería `csv` de la stdlib de Python puede reemplazar esto completamente. `pandas==2.3.3` en `requirements.txt` es la dependencia más pesada del proyecto.  
**Impacto:** Tiempo de startup más lento, imagen Docker más grande, y una dependencia con actualizaciones frecuentes que pueden romper la API.  
**Qué haría yo:** Reemplazar con `csv.DictReader` de la stdlib. La lógica en `CSVProcessor.procesar_dataframe()` es simple iteración de filas — no hay operaciones vectorizadas que justifiquen pandas.

---

### Versiones sin rangos — lockfile implícito
**Severidad:** 🔵 BAJO  
**Dónde:** `requirements.txt`  
**Problema:** Todas las dependencias están pineadas exactas (ej: `Flask==3.1.2`). Esto es correcto para reproducibilidad, pero sin un `requirements-dev.txt` separado, las dependencias de testing (`pytest`, `unittest.mock`) están mezcladas con las de producción en el mismo archivo... o no están listadas (pytest no está en `requirements.txt`, lo que sugiere que los tests pueden no correr en CI).  
**Qué haría yo:** Agregar `requirements-dev.txt` con pytest y cualquier otra dependencia de testing. Verificar que el CI instale las dev deps.

---

## 9. Operabilidad

### `gunicorn.conf.py`: `loglevel = "warning"` en producción
**Severidad:** 🔵 BAJO  
**Dónde:** `gunicorn.conf.py:29`  
**Problema:** El nivel `warning` suprime los logs `INFO` de Gunicorn, incluyendo los access logs de requests. `accesslog = "-"` está configurado pero si el nivel es `warning`, los accesos no se loguean. En Render/Railway no hay otro lugar donde ver los requests.  
**Qué haría yo:** Usar `loglevel = "info"` para tener visibilidad de requests. Si el I/O es una preocupación, desactivar el access log (`accesslog = None`) pero mantener `loglevel = "info"` para los errores de la app.

---

### Health check hace query a Supabase pero falla silenciosamente
**Severidad:** 🔵 BAJO  
**Dónde:** `main.py:630–637`  
**Problema:**
```python
try:
    if storage._sb:
        storage._sb.table('torneo_actual').select('id').limit(1).execute()
except Exception:
    pass  # No romper el health check si Supabase está lento o caído
```
El health check retorna `{'status': 'ok'}` aunque Supabase esté caído. UptimeRobot siempre verá la app como "up" incluso si ningún usuario puede hacer login o ver datos. Esto da falsa seguridad.  
**Qué haría yo:** Agregar un campo `supabase_ok: bool` en la respuesta, aunque el status HTTP siga siendo 200. Así el monitoreo puede alertar si Supabase falla sin tumbar el health check de la app:
```python
return jsonify({'status': 'ok', 'supabase': supabase_ok})
```

---

### No hay métricas ni alertas de errores en producción
**Severidad:** 🔵 BAJO  
**Dónde:** Todo el proyecto  
**Problema:** No hay integración con Sentry, Rollbar, ni ningún servicio de error tracking. Los errores 500 se loguean en stdout de Render/Railway, pero no hay alertas proactivas. El handler de 500 en `main.py:647–653` logguea el error pero no lo reporta.  
**Qué haría yo:** Agregar Sentry. Es gratis para proyectos pequeños y tarda 10 minutos en configurar. La línea de código es `sentry_sdk.init(dsn=os.getenv('SENTRY_DSN'))` en `main.py`.

---

## 10. Lo que haría diferente (si arrancara de cero)

### El modelo de datos es el problema raíz

El error de diseño más grande del proyecto es usar Supabase como si fuera un archivo JSON en la nube. Guardar todo el estado del torneo en un único JSONB en una fila es conveniente para empezar, pero crea fricciones que se multiplican con cada feature nueva.

La arquitectura ideal para este dominio sería:

**Tablas relacionales reales (ya están en parte):**
- `torneos` — metadatos del torneo, fase, tipo
- `inscripciones` — inscripciones de jugadores (ya existe)
- `grupos` — grupos del torneo con categoría y franja (ya existe para historial)
- `parejas_grupo` — relación pareja↔grupo con posición
- `partidos` — resultados de partidos de grupo
- `partidos_finales` — bracket de finales

El blob JSONB debería ser solo un caché denormalizado para rendering rápido, no la fuente de verdad. Las operaciones de escritura (guardar resultado, cambiar franja, asignar pareja) deberían operar sobre las tablas relacionales, y el blob se regeneraría cuando sea necesario.

### La capa de servicios está bien pensada pero incompleta

La estructura `services/grupo_service.py`, `services/fixture_service.py`, etc. es el camino correcto. El problema es que no se terminó de aplicar: `inscripcion.py` tiene 1072 líneas con toda la lógica de negocio incrustada en el blueprint. La regla que falta aplicar es: **ningún blueprint debería contener lógica de negocio**. Los blueprints deberían ser adaptadores HTTP puros: leer el request, llamar a un service, formatear la respuesta.

### La autenticación necesita unificación

Actualmente hay tres tipos de tokens en circulación: el JWT custom del admin, el JWT custom del jugador, y el Supabase JWT. Las cookies son `token` y `sb_token` (aunque `sb_token` ya no se usa en los flujos nuevos). El middleware en `main.py:126–159` tiene tres caminos de resolución de rol. Esto crea superficie de ataque y bugs sutiles (como el token sin rol que da admin implícito).

La solución ideal: un único tipo de token JWT custom para todos los usuarios (admin y jugador), con el campo `role` siempre presente. Supabase se usa solo para verificar credenciales, no para emitir tokens que circule por la app. Ya está casi ahí — solo falta aplicarlo consistentemente.

### El frontend debería ser más honesto sobre lo que es

La app usa Bootstrap 5 con JS vanilla y Jinja2. Eso está bien para este tamaño. El error es intentar hacer una SPA dentro de un monolito de templates: hay partes que cargan con Jinja2 y partes que se renderizan por AJAX, y la línea entre las dos no es clara. `dashboard.html` tiene datos del servidor inyectados vía Jinja2 Y fetch calls que traen los mismos datos por JSON. Esto duplica las fuentes de verdad.

La propuesta concreta: definir una política clara. Para páginas que necesitan SEO o acceso sin JS (grupos públicos, calendario): Jinja2 completo. Para páginas de admin interactivas (dashboard, resultados): shell mínima de Jinja2 + todos los datos por fetch. No mezclar en la misma vista.

---

## Plan de Ataque Sugerido

### Sprint 1 — Deuda Crítica (hacer antes de crecer)

- [ ] **Configurar Redis/Upstash para rate limiter en producción** — una variable de entorno y previene fuerza bruta real
- [ ] **Agregar check en startup para `ADMIN_PASSWORD` por defecto en producción**
- [ ] **Corregir `crear_respuesta_con_token_actualizado()` para incluir siempre el rol en el token**
- [ ] **Eliminar la compatibilidad `role is None → admin` en el middleware** (breaking change controlado)
- [ ] **Mover el flujo OAuth completo de `main.py` a `auth_jugador.py`**

### Sprint 2 — Arquitectura (cuando haya estabilidad)

- [ ] **Extraer lógica de inscripción a `services/inscripcion_service.py`** — las funciones `_auto_asignar_en_grupos`, `_auto_eliminar_de_grupos`, `_ejecutar_aceptar_invitacion`
- [ ] **Mover rutas de páginas públicas de `main.py` a un blueprint `web_bp`**
- [ ] **Corregir `_uuid_to_int_id()`** — cambiar `Pareja.id` a `str` y usar UUID directamente
- [ ] **Mover la auto-generación de fixtures del GET `/grupos` al evento `cambiar-fase`**
- [ ] **Reemplazar `pandas` con `csv.DictReader` de stdlib**

### Sprint 3 — Mejoras de calidad

- [ ] **Tests de integración para flujo completo de inscripción** (crear → invitar → aceptar → cancelar)
- [ ] **Tests para `auth_jugador.py`** (login admin, login jugador, fallback, OAuth error)
- [ ] **Reemplazar wildcard import en `config/__init__.py`**
- [ ] **Extraer modales de `dashboard.html` a Jinja2 includes**
- [ ] **Agregar Sentry para error tracking en producción**
- [ ] **Limpiar `invitaciones_pendientes` endpoint** (usar batch queries o deprecar en favor de `/estado`)
- [ ] **Cambiar `loglevel` de gunicorn a `"info"`**

---

## Lo que está bien hecho (y merece destacarse)

- **Optimistic locking con `guardar_con_version()`**: implementación correcta de OCC (Optimistic Concurrency Control) para el único admin. La RPC en Supabase es el approach correcto.
- **PKCE para OAuth de Google**: implementado correctamente en `auth_jugador.py`. No es trivial y está bien hecho.
- **`_es_redirect_seguro()`**: validación de open redirect usando `urlparse` en vez de regex — es el enfoque correcto.
- **`AlgoritmoGrupos` bien aislado**: el algoritmo es pure Python, sin dependencias de Flask ni Supabase. Testeable de forma aislada y con buena cobertura.
- **Backpressure en backtracking**: los límites de `max_combos` y la poda por score máximo posible muestran que se pensó en los casos extremos del algoritmo.
- **Batch queries en `estado_inscripcion()`**: el endpoint consolida las queries N+1 en 3 queries batch. Es el patrón correcto y muestra que se aprendió de los problemas del endpoint viejo.
- **Estructura de tests**: `conftest.py` tiene buenas factories, el fixture `mock_storage` está bien pensado, y los tests del algoritmo documentan el comportamiento esperado (incluyendo los casos borde de canchas).
- **`ConflictError` como excepción de dominio**: separar el error de concurrencia del resto de las excepciones es una buena decisión.
