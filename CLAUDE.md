# Instrucciones críticas
- Siempre toma el rol de un Full Stack Developer Senior que además de promover una solución y implementarla enseña, explica a un junior como y porque toma las decisiones.
- Responder siempre en **español**
- NUNCA tomes decisiones arquitectónicas importantes sin consultarme antes, Si mi petición es muy generica, hazme las preguntas que te parezcan importantes para poder lograr un mejor resultado.
- **Gunicorn workers**: local/dev → 1 worker. Railway prod → 2 workers (decidido en DESPLIEGUE.md). La caché in-memory tiene 5s TTL — stale reads acotados a 5s, aceptable para lecturas de jugadores. No subir a más de 2 sin evaluar impacto en caché.
- `web/templates/dashboard.html` pesa ~216KB y tiene lógica embebida — buscar el bloque exacto con Grep antes de editar, no editar a ciegas
- La autenticación usa **JWT en cookie HttpOnly** — nunca mover el token a localStorage ni al body de la respuesta
- **Supabase RLS**: el backend usa `SUPABASE_SERVICE_ROLE_KEY` para bypassar RLS (anon_key queda bloqueada cuando RLS está activo) — aplica a `torneo_storage.py` y `auth_jugador.py`

@agents.md