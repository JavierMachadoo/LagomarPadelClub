"""Rate limiter compartido — se inicializa con init_app() en main.py."""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],        # Sin límite global, solo en rutas decoradas
    storage_uri="memory://",  # Suficiente para 1 worker
)
