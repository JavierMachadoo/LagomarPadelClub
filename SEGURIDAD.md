# Plan de Seguridad — Pre-Deploy Producción

Estado actual: deploy en **Render (Ohio) + Supabase Free (Ohio)** — entorno de validación.
Objetivo: migrar a **Railway (São Paulo) + Supabase Free (São Paulo)** con estos fixes aplicados.

---

## Índice

- [Críticos — bloqueantes](#críticos--bloqueantes-antes-de-publicar)
- [Importantes — no bloqueantes](#importantes--no-bloqueantes-pero-necesarios)
- [Recomendados — mejoras](#recomendados--mejoras)
- [Lo que ya está bien](#lo-que-ya-está-bien--no-tocar)

---

## Críticos — bloqueantes antes de publicar

Estos fixes DEBEN estar aplicados antes de que cualquier jugador real use la app.

---
---

### 3. `str(e)` expuesto en respuestas API — information leak

**Archivos con el problema:**

| Archivo | Línea | Severidad |
|---------|-------|-----------|
| `api/routes/inscripcion.py` | 529 | ALTA — tiene comentario "Exponer el error real de Supabase para facilitar el debugging" |
| `api/routes/auth_jugador.py` | 172-176 | ALTA — puede exponer mensajes de Supabase Auth |
| `api/routes/finales.py` | 37, 52, 67, 87, 105, 118 | MEDIA |
| `api/routes/calendario.py` | 77, 100, 172, 200 | MEDIA |
| `api/routes/historial.py` | 252, 279, 315 | MEDIA |

**Qué información puede filtrar `str(e)`:**
- Nombres de tablas de Supabase
- Queries SQL internas
- Stack traces parciales
- Tipo de error de base de datos (útil para atacantes)

**Fix:**
- Loguear `str(e)` al servidor (ya está hecho con `logger.error`).
- Nunca retornar `str(e)` al cliente. Usar mensajes genéricos.

```python
# ANTES (inscripcion.py:529)
return jsonify({'error': f'Error al guardar la inscripción: {error_msg}'}), 500

# DESPUÉS
logger.error('Error al crear inscripción: %s', error_msg)
return jsonify({'error': 'Error al guardar la inscripción. Intentá de nuevo.'}), 500
```

**Esfuerzo:** 30 minutos (revisar todos los archivos listados).

---

### 4. Token JWT en el body de la respuesta

**Archivo:** `utils/jwt_handler.py:143-145`

```python
response_data = {
    'token': token,   # ← el token también va en el JSON
    'data': data
}
```

**Impacto real:**
- La cookie es HttpOnly — JS no puede leerla. Bien.
- Pero el token también está en el body del response. Si algún handler JS hace `response.token` y lo guarda en `localStorage` o `sessionStorage`, la protección HttpOnly queda anulada por completo.
- Actualmente el JS no parece guardarlo (revisado `app.js`, `dashboard-*.js`) — pero el vector de ataque existe y puede aparecer en código futuro sin darse cuenta.

**Fix:**
- Eliminar `'token'` del body de la respuesta. La cookie ya es suficiente.

```python
response_data = {
    'data': data  # sin 'token'
}
if mensaje:
    response_data['mensaje'] = mensaje
```

**Esfuerzo:** 10 minutos. Verificar que ningún JS consume `response.token`.

---

## Importantes — no bloqueantes pero necesarios

No impiden el deploy, pero deben aplicarse en las primeras semanas de producción.

---

### 5. Sin security headers HTTP

**Impacto:** clickjacking, MIME sniffing, XSS reflejado, filtrado de URLs en referrer.

**Fix — agregar en `main.py` dentro de `crear_app()`:**

```python
@app.after_request
def agregar_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    # HSTS: solo activar cuando el dominio custom esté confirmado con HTTPS
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response
```

**Nota:** no usar `flask-talisman` sin revisar — puede romper Bootstrap CDN si CSP es muy restrictivo. Empezar con estos headers básicos es suficiente.

**Esfuerzo:** 15 minutos.
---

### 8. RLS incompleto en Supabase

**Contexto:** el backend usa `SUPABASE_SERVICE_ROLE_KEY` que bypasea RLS — correcto. Pero si en algún momento un bug expone la `anon_key` o hay un endpoint que la usa sin querer, RLS es la última línea de defensa.

**Fix:**
- Verificar que **todas** las tablas tienen RLS habilitado: `inscripciones`, `torneos`, `jugadores`, etc.
- La política mínima: `USING (false)` en `anon_key` para bloquear cualquier acceso directo que no sea via service role.

**Esfuerzo:** 30 minutos (revisar en Supabase Dashboard → Table Editor → RLS).

---

## Recomendados — mejoras

Estas mejoras elevan la calidad pero no son urgentes.

---

### 9. Logging estructurado para errores 5xx

**Situación actual:** los `logger.error(...)` van a stdout de Railway — se pueden ver, pero no hay alertas.

**Mejora:** agregar un handler de errores global en `crear_app()` que logea todos los 500 con contexto (ruta, método, user agent).

```python
@app.errorhandler(500)
def error_500(e):
    logger.error('Error 500 en %s %s: %s', request.method, request.path, e)
    return jsonify({'error': 'Error interno del servidor'}), 500
```

**Bonus:** Railway tiene un tab de "Logs" — buscar `ERROR 500` te muestra todos los fallos.

**Esfuerzo:** 15 minutos.

---

### 10. Content-Security-Policy (CSP)

No se incluye en los headers básicos del punto 5 porque requiere auditar todos los scripts inline y los CDNs usados (Bootstrap, etc.).

**Cuando estén listos para esto:**
1. Usar [CSP Evaluator](https://csp-evaluator.withgoogle.com/) para construir la política
2. Empezar en modo `Content-Security-Policy-Report-Only` (no bloquea, solo reporta)
3. Ajustar hasta que no haya violaciones, luego activar

**Esfuerzo:** 2-4 horas. Dejarlo para después del primer torneo en producción.

---

### 11. Verificar inputs de búsqueda de jugadores

**Archivo:** `api/routes/inscripcion.py` — endpoint `/api/jugadores/buscar` es ruta pública.

Verificar que el término de búsqueda está sanitizado antes de pasarlo a Supabase (el SDK de Supabase usa queries parametrizadas, pero vale confirmarlo).

---

## Lo que ya está bien — no tocar

| Item | Detalle |
|------|---------|
| JWT en HttpOnly cookie | JS no puede leer el token |
| `SameSite=Lax` | Protección CSRF básica |
| `ProxyFix` configurado | `x_for=1, x_proto=1, x_host=1` — correcto para Railway |
| `MAX_CONTENT_LENGTH = 5MB` | Protección DoS en uploads |
| Rate limiter en login/registro | `flask-limiter` con decoradores en las rutas correctas |
| `SUPABASE_SERVICE_ROLE_KEY` solo server-side | Nunca expuesta al cliente |
| `max_requests=500` en Gunicorn | Previene memory leaks graduales |
| `/_health` hace query real | Mantiene Supabase activa via UptimeRobot |
| `sessionStorage` solo para UI state | Solo guarda tab activo y scroll — no auth |
| `requirements.txt` con versiones pineadas | Builds reproducibles |
| `SUPABASE_SERVICE_ROLE_KEY` bypass RLS | Patrón correcto para acceso backend |

---

## Checklist pre-deploy Railway

### Críticos (todos deben estar en ✅ antes de publicar)

- [ ] `str(e)` eliminado de todos los responses al cliente
- [ ] Token JWT eliminado del body de la respuesta

### Importantes (primeras 2 semanas post-deploy)

- [ ] Security headers HTTP agregados
- [ ] `COOKIE_SECURE=True` configurado
- [ ] RLS auditado en todas las tablas de Supabase prod
- [ ] Error handler global para 5xx

### Validación

- [ ] Verificar que cookie tiene flags `HttpOnly`, `Secure`, `SameSite=Lax` en producción (DevTools → Application → Cookies)
- [ ] Verificar que errores 500 muestran mensaje genérico (no `str(e)`)
- [ ] Verificar que el rate limiter bloquea después de 5 intentos fallidos de login
- [ ] Verificar que `/_health` responde 200 y Supabase no se pausa

---

## Contexto de infraestructura actual

| Item | Valor |
|------|-------|
| Hosting actual | Render Free — Ohio (us-east-1) — temporal |
| BD actual | Supabase Free — Ohio — temporal |
| Hosting objetivo | Railway Hobby — São Paulo ($5/mes) |
| BD objetivo | Supabase Free — São Paulo (sa-east-1) |
| Keep-alive | UptimeRobot → `/_health` cada 5 min |
| Workers objetivo | 2-3 (requiere fix del rate limiter) |
| Dominio objetivo | `torneos.lagomarpadelclub.uy` |
