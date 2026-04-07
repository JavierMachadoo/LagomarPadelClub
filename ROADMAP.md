# Roadmap de Mejoras — Algoritmo Torneos

Mejoras ordenadas por impacto en la experiencia del usuario real.
Actualizado: 2026-04-07.

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

### 22. Logs de auditoría de acciones admin

**Descripción**: Registrar qué hizo el admin (generó grupos, modificó resultados, archivó torneo) con timestamp.
**Útil para**: Debug de problemas post-torneo, especialmente si hay quejas sobre resultados.
**Esfuerzo**: Medio.

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
