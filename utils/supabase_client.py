"""
Singleton centralizado para clientes Supabase.

Usar siempre estas funciones en lugar de instanciar create_client() inline.
Cada llamada a create_client() inicializa un pool HTTP + TLS — costoso.
Con Gunicorn en 2 workers (prod) los singletons se inicializan por worker — ver DESPLIEGUE.md §4.
"""
from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY

_admin_client = None
_anon_client = None


def get_supabase_admin():
    """Cliente con SERVICE_ROLE_KEY — bypasea RLS. Solo operaciones server-side."""
    global _admin_client
    if _admin_client is None:
        if not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY no está configurada")
        from supabase import create_client
        _admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _admin_client


def get_supabase_anon():
    """Cliente con ANON_KEY — para operaciones públicas de autenticación."""
    global _anon_client
    if _anon_client is None:
        if not SUPABASE_ANON_KEY:
            raise RuntimeError("SUPABASE_ANON_KEY no está configurada")
        from supabase import create_client
        _anon_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _anon_client
