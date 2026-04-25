# Roadmap de Mejoras — Algoritmo Torneos

Mejoras ordenadas por impacto en la experiencia del usuario real.
Actualizado: 2026-04-25.

---

## Criterio de priorización

```
P0 — Bloquea el torneo actual o es una vulnerabilidad de seguridad
P1 — Afecta directamente la experiencia del jugador hoy
P2 — Mejora significativa, puede esperar al siguiente torneo
P3 — Nice to have, evaluar según demanda real
```

---

## P0 — Críticos (hacer antes de que lleguen los jugadores)

### 0. Gestión de usuario + verificación de teléfono (multi-fase)

**Problema**: Hoy solo se verifica email. Para mandar avisos del torneo por WhatsApp el día de mañana, necesitamos teléfono validado. Además el usuario no puede editar sus datos (nombre, apellido, teléfono) y el header solo tiene un botón de Logout suelto.

**Objetivo end-state**:
- Dropdown `Hola, {primer_nombre}` en el header (reemplaza el Logout suelto)
- Página "Mi cuenta" con edición de nombre, apellido, teléfono. Email read-only en esta entrega
- Verificación de teléfono por OTP de WhatsApp
- Indicador visual (puntito rojo + toast) cuando el teléfono no está verificado
- Base para enviar avisos de torneo por WhatsApp vía n8n (fase posterior)

**Decisiones arquitectónicas**:
- **Proveedor OTP**: WhatsApp Cloud API de Meta. Descartado Supabase Auth Phone (Twilio, pago) y Telegram (baja adopción Uruguay)
- **Costo**: tier gratis Meta cubre 1000 conversaciones servicio/mes; OTP ~USD 0.04 c/u en Uruguay → despreciable para volumen del club
- **Setup Meta**: cuenta Meta Business verificada + número WhatsApp Business dedicado + plantilla OTP aprobada. Burocracia de días, **arrancar en paralelo desde ya**
- **Teléfono NO es identificador**: solo dato verificado del perfil. Login sigue siendo email/password + Google
- **Cambio de teléfono → se desverifica automáticamente**, hay que re-validar
- **Email read-only en esta entrega**: editarlo dispara flow de Supabase Auth (link de confirmación), va aparte
- **Notificaciones de torneo (fase posterior)**: backend dispara webhook → n8n orquesta → n8n manda por WhatsApp Cloud API. NO usar proveedores no oficiales (Evolution/Baileys) — Meta banea números automatizados

**Schema (Supabase)**:
```sql
-- Fase 1
ALTER TABLE usuarios ADD COLUMN telefono_verificado BOOLEAN DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN telefono_verificado_at TIMESTAMPTZ;

-- Fase 2
CREATE TABLE verificaciones_telefono (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES usuarios(id) ON DELETE CASCADE,
  telefono_e164 TEXT NOT NULL,
  codigo_hash TEXT NOT NULL,           -- hasheado, NUNCA plain
  expira_en TIMESTAMPTZ NOT NULL,      -- now() + 10 min
  intentos INT NOT NULL DEFAULT 0,
  verificado BOOLEAN NOT NULL DEFAULT FALSE,
  creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_verif_telefono_usuario ON verificaciones_telefono(usuario_id);
```

**Endpoints nuevos** (`api/routes/perfil.py` o extensión de `auth_jugador.py`):

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/auth/perfil` | Devuelve nombre, apellido, email, teléfono, telefono_verificado |
| PUT | `/api/auth/perfil` | Actualiza nombre/apellido/teléfono. Cambio de teléfono → desverifica |
| POST | `/api/auth/telefono/enviar-codigo` | Genera OTP, guarda hash, manda por WA Cloud API |
| POST | `/api/auth/telefono/verificar-codigo` | Valida código, marca verificado |

**Reglas de negocio**:
- Código: 6 dígitos numéricos, expira 10 min, hasheado en DB (sha256 o bcrypt)
- Teléfono normalizado a E.164 Uruguay (`+5989XXXXXXX`) antes de guardar
- Teléfono único por usuario activo
- Rate limit OTP: **3 envíos/hora/usuario**, **5 intentos por código**
- Validación de inputs reusa `utils/input_validation.py`

**Frontend**:
- Reemplazar botón Logout del header por dropdown `Hola, {primer_nombre}` (`nombre.split()[0]`) con opciones "Mi cuenta" y "Cerrar sesión"
- Puntito rojo sobre el saludo cuando `telefono_verificado === false`
- Toast post-login dismissable: "Verificá tu teléfono para recibir avisos del torneo"
- Página/modal "Mi cuenta": form con nombre, apellido, email (disabled), teléfono + botón "Verificar teléfono"
- Modal verificación: input 6 dígitos + botón "Reenviar código" (deshabilitado 60s tras envío)

**Archivos críticos**:
- Backend: `api/routes/auth_jugador.py`, nuevo `api/routes/perfil.py`, nuevo `utils/whatsapp_client.py`, `utils/input_validation.py`, `utils/rate_limiter.py`
- Frontend: `web/templates/base.html` (header), `web/templates/dashboard.html` (~216KB, usar Grep), `web/static/js/app.js`, nuevo `web/templates/mi_cuenta.html`
- Tests: `tests/test_perfil.py` nuevo, `tests/test_verificacion_telefono.py` nuevo

### Fases con cronograma

**Fase 1 — Antes del 17 de mayo (torneo)** — Gestión de usuario base
- ALTER TABLE `usuarios` con `telefono_verificado` y `telefono_verificado_at` (default false → nadie verificado todavía, OK)
- GET/PUT `/api/auth/perfil`
- Dropdown "Hola, {primer_nombre}" en header
- Página Mi cuenta con edición de nombre/apellido/teléfono (sin OTP)
- Tests pytest del endpoint
- **Esfuerzo**: 6-8h

**Fase 2 — Post-torneo de mayo** — Verificación de teléfono
- Setup Meta Business + plantilla OTP (en paralelo, arrancar YA — depende de Meta)
- Tabla `verificaciones_telefono`
- Cliente `utils/whatsapp_client.py` para WA Cloud API
- Endpoints `enviar-codigo` y `verificar-codigo` con rate limit
- Modal de verificación en frontend
- Puntito rojo + toast de teléfono no verificado
- **Esfuerzo**: 8-12h código + tiempo Meta

**Fase 3 — P1, posterior** — Notificaciones de torneo por WhatsApp vía n8n
- Eventos del backend que disparan webhook (compañero aceptó, partido programado, etc.)
- Flujos n8n: webhook in → template WA out (Cloud API)
- Solo a usuarios con `telefono_verificado = TRUE`
- **Esfuerzo**: 4-6h backend + diseño de flujos n8n

---

### 1. Rate limiting en POST /api/inscripcion

**Problema**: Cualquiera puede crear 1.000 inscripciones spam en segundos.
**Fix**: Una línea en `api/routes/inscripcion.py`
```python
@limiter.limit("5/minute")
```
**Esfuerzo**: 1 min

---

---

### 3. Tokens legacy sin campo `role` no deben asumir admin

**Problema**: En `main.py:136`, si el token no tiene campo `role`, se asume admin.
**Fix**: Cambiar la condición
```python
# Antes (inseguro):
if role is None or role == 'admin':
# Después:
if role == 'admin':
```
**Esfuerzo**: 1 min

---

## P1 — Alta prioridad (primer torneo)

### 3. Franja horaria preferida del jugador

**Descripción**: El jugador elige 1 franja preferida al inscribirse online. El algoritmo le da un soft bonus (+0.5 pts de compatibilidad) cuando puede asignarlo a esa franja, sin garantizarlo. Es opcional — si no elige, el sistema funciona igual que antes.

**Alcance**:
- Nuevo campo `franja_preferida: Optional[str] = None` en el modelo `Pareja` (`core/models.py`) con serialización `to_dict`/`from_dict`
- Soft bonus `SCORE_FRANJA_PREFERENCIA = 0.5` en `_calcular_compatibilidad` y `_elegir_franja` (`core/algoritmo.py`)
- Aceptar y validar `franja_preferida` en la API de inscripción — debe ser una de las franjas disponibles del jugador (`api/routes/inscripcion.py`)
- UI dinámica en el formulario de inscripción web: dropdown que se repopula con JS según las franjas disponibles que el jugador marcó (`web/templates/inscripcion.html` + `web/static/js/app.js`)
- Evaluar si la tabla `inscripciones` en Supabase requiere una migration para agregar la columna (depende de si usa columnas explícitas o JSONB)

**Archivos críticos**: `core/models.py:116-170`, `core/algoritmo.py:8-12,189-225`, `api/routes/inscripcion.py:73-97`, `web/templates/inscripcion.html`, `web/static/js/app.js`

**Esfuerzo**: Medio (4-6h)

---

### 4. Feedback claro cuando la invitación expiró

**Problema**: Cuando un jugador sigue el link de invitación vencido (48h), probablemente ve un error genérico. Para alguien no técnico, eso es frustrante y confuso.
**Mejora**: Página amigable con mensaje "Esta invitación venció. Pedile a tu compañero/a que te envíe un nuevo link." y botón para ir al registro.
**Archivo**: `web/templates/invitacion.html`

---

## P2 — Mediana prioridad (segundo torneo)

### 11. Notificación cuando el compañero acepta la invitación

**Problema**: El jugador que creó la inscripción no sabe cuándo su compañero aceptó, a menos que entre a la app.
**Mejora**: Email automático cuando el estado cambia a `confirmada`.
**Dependencia**: Integración con servicio de email (Resend ya está en el stack para confirmación de registro).
**Archivo**: `api/routes/inscripcion.py` + template de email

---

### 12. Vista de mis resultados históricos

**Problema**: El jugador puede ver el torneo actual, pero no sus resultados en torneos anteriores.
**Mejora**: En el dashboard, sección "Mis torneos anteriores" con un resumen de cada torneo en el que participó.
**Dependencia**: El historial ya existe, hay que filtrar por jugador_id.
**Archivo**: `api/routes/historial.py` + `web/templates/dashboard.html`

---

## P3 — Baja prioridad / evaluación post-temporada

### 18. Sistema de ranking anual

**Descripción**: Acumular puntos por posición en cada torneo. Requiere diseño de sistema de puntos, persistencia y UI de tabla de posiciones.
**Dependencia**: Al menos 2-3 torneos archivados para que tenga sentido.
**Esfuerzo**: Alto (semana de trabajo).

---

## Deuda técnica

No son features de usuario, pero si no se atienden van a picar en algún momento:

| # | Deuda | Impacto | Esfuerzo |
|---|-------|---------|----------|
| DT-2 | `dashboard.html` ~216KB con lógica embebida | Difícil de mantener, lento de cargar | Alto |
| DT-3 | Rutas públicas como lista hardcodeada en `main.py` | Cada ruta nueva requiere acordarse de actualizar la lista | Medio |
| DT-5 | `str(e)` expuesto en respuestas 500 | Expone detalles internos a atacantes | Bajo (5 min) |
| DT-6 | Migrations de Supabase no versionadas | Schema prod puede diferir de dev sin que te des cuenta | Medio |

---

## Lo que ya funciona bien y no tocar

- Algoritmo de agrupación: backtracking con poda — eficiente y correcto
- JWT en HttpOnly cookie — no cambiar a localStorage ni al body
- TTL 5s de caché — no bajar (carga innecesaria en BD) ni subir mucho (datos stale)
- Gunicorn 1 worker en prod hasta evaluar impacto caché con 2+ — documentado en DESPLIEGUE.md
- Supabase service role key solo en backend — nunca al cliente
- Optimistic locking en guardar_con_version() — protege concurrencia correctamente
