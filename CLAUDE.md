# Instrucciones críticas

- Responder siempre en **español**
- **Nunca aumentar el número de workers de Gunicorn** — está fijo en 1 para evitar caché stale entre procesos
- `web/templates/resultados.html` pesa ~215KB y tiene lógica embebida — buscar el bloque exacto con Grep antes de editar, no editar a ciegas
- La autenticación usa **JWT en cookie HttpOnly** — nunca mover el token a localStorage ni al body de la respuesta

@agents.md