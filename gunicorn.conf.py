# Configuración de Gunicorn para Render Free Tier
# 512 MB RAM | CPU compartida

import os

# ── Workers ────────────────────────────────────────────────────────────────────
# App de un único administrador → 1 worker es suficiente y NECESARIO.
# Con 2+ workers cada proceso tiene su propio caché en memoria:
# una escritura en Worker A no invalida el caché de Worker B → datos stale.
workers = 1

# Worker class sync es la correcta para Flask standard (no async)
worker_class = "sync"

# ── Timeouts ───────────────────────────────────────────────────────────────────
# 60s: suficiente para requests lentos a Supabase o el primer wake-up
timeout = 60

# Keep-alive: mantener conexiones HTTP abiertas 5s (reduce overhead de TCP)
keepalive = 5

# ── Binding ────────────────────────────────────────────────────────────────────
# Render inyecta el PORT en la variable de entorno
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"

# ── Logging ────────────────────────────────────────────────────────────────────
# "warning" minimiza I/O de logs → más performance que "info"
loglevel = "warning"
accesslog = "-"   # stdout (Render lo captura)
errorlog  = "-"   # stderr

# ── Optimizaciones de memoria ──────────────────────────────────────────────────
# Reiniciar workers después de N requests para evitar memory leaks graduales
max_requests = 500
max_requests_jitter = 50  # ±50 requests de variación aleatoria (evita restart simultáneo)

# Precarga la app antes de hacer fork de los workers.
# Reduce RAM porque el código queda en memoria compartida entre workers.
preload_app = True
