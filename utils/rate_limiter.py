"""Rate limiter compartido — se inicializa con init_app() en main.py."""

import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Permite configurar el backend de almacenamiento del rate limiter.
# En desarrollo (1 solo worker) se puede usar memory:// (valor por defecto).
# En producción con varios workers/procesos se debe usar un storage compartido,
# por ejemplo: RATE_LIMIT_STORAGE_URI="redis://localhost:6379/0".
RATE_LIMIT_STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],              # Sin límite global, solo en rutas decoradas
    storage_uri=RATE_LIMIT_STORAGE_URI,
)
