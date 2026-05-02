# Roadmap de Mejoras — Algoritmo Torneos

Mejoras ordenadas por impacto en la experiencia del usuario real.
Actualizado: 2026-04-15.

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


---

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
