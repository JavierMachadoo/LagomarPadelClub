"""
Almacenamiento persistente del catálogo de jugadores.

El catálogo es cross-torneo — no pertenece al JSONB del torneo.
Backend:
    - Supabase tabla `jugadores`  → cuando SUPABASE_URL y key están definidas
    - JSON local data/jugadores.json → fallback para desarrollo sin Supabase
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
_SUPABASE_KEY = (
    os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
    or os.getenv('SUPABASE_ANON_KEY', '').strip()
)
_USE_SUPABASE = bool(_SUPABASE_URL and _SUPABASE_KEY)

if _USE_SUPABASE:
    try:
        from supabase import create_client
    except ImportError:
        logger.warning('supabase package no instalado. Usando almacenamiento JSON.')
        _USE_SUPABASE = False

_BASE_DIR = Path(__file__).resolve().parent.parent
_TABLE = 'jugadores'


class JugadoresStorage:
    """Catálogo persistente de jugadores individuales."""

    _JUGADORES_FILE: Path = _BASE_DIR / 'data' / 'jugadores.json'

    def __init__(self) -> None:
        self._use_supabase = _USE_SUPABASE
        self._jugadores_file = self._JUGADORES_FILE

        if self._use_supabase:
            self._sb = create_client(_SUPABASE_URL, _SUPABASE_KEY)
            logger.info('JugadoresStorage: usando Supabase')
        else:
            self._jugadores_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info('JugadoresStorage: usando JSON local (%s)', self._jugadores_file)

    # ── Supabase ──────────────────────────────────────────────────────────────

    def _sb_listar(self, activos_only: bool) -> list:
        q = self._sb.table(_TABLE).select('*')
        if activos_only:
            q = q.eq('activo', True)
        return q.order('apellido').execute().data or []

    def _sb_buscar(self, q: str) -> list:
        patron = f'%{q}%'
        return (
            self._sb.table(_TABLE)
            .select('*')
            .ilike('nombre', patron)
            .eq('activo', True)
            .order('apellido')
            .execute()
            .data or []
        )

    def _sb_crear(self, payload: dict) -> dict:
        payload_con_id = {'id': str(uuid.uuid4()), **payload}
        resp = self._sb.table(_TABLE).insert(payload_con_id).execute()
        return resp.data[0]

    def _sb_obtener(self, jugador_id: str) -> Optional[dict]:
        resp = self._sb.table(_TABLE).select('*').eq('id', jugador_id).execute()
        return resp.data[0] if resp.data else None

    def _sb_actualizar(self, jugador_id: str, campos: dict) -> dict:
        resp = self._sb.table(_TABLE).update(campos).eq('id', jugador_id).execute()
        return resp.data[0]

    # ── JSON fallback ─────────────────────────────────────────────────────────

    def _json_leer(self) -> list:
        try:
            return json.loads(self._jugadores_file.read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _json_escribir(self, datos: list) -> None:
        self._jugadores_file.write_text(
            json.dumps(datos, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )

    # ── API pública ───────────────────────────────────────────────────────────

    def listar(self, activos_only: bool = True) -> list:
        if self._use_supabase:
            return self._sb_listar(activos_only)
        datos = self._json_leer()
        if activos_only:
            datos = [j for j in datos if j.get('activo', True)]
        return datos

    def buscar(self, q: str) -> list:
        if not q:
            return self.listar()
        if self._use_supabase:
            return self._sb_buscar(q)
        patron = q.lower()
        return [
            j for j in self._json_leer()
            if j.get('activo', True) and (
                patron in j.get('nombre', '').lower()
                or patron in j.get('apellido', '').lower()
            )
        ]

    def crear(self, nombre: str, apellido: str,
              telefono: str = None, email: str = None) -> dict:
        payload = {
            'nombre': nombre,
            'apellido': apellido,
            'telefono': telefono,
            'email': email,
            'activo': True,
        }
        if self._use_supabase:
            return self._sb_crear(payload)
        nuevo = {
            **payload,
            'id': str(uuid.uuid4()),
            'usuario_id': None,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'telefono_verificado': False,
        }
        datos = self._json_leer()
        datos.append(nuevo)
        self._json_escribir(datos)
        return nuevo

    def obtener(self, jugador_id: str) -> Optional[dict]:
        if self._use_supabase:
            return self._sb_obtener(jugador_id)
        return next(
            (j for j in self._json_leer() if j.get('id') == jugador_id),
            None,
        )

    def vincular_usuario(self, jugador_id: str, usuario_id: str) -> dict:
        if self._use_supabase:
            return self._sb_actualizar(jugador_id, {'usuario_id': usuario_id})
        datos = self._json_leer()
        for j in datos:
            if j.get('id') == jugador_id:
                j['usuario_id'] = usuario_id
                self._json_escribir(datos)
                return j
        raise ValueError(f'Jugador {jugador_id} no encontrado')


jugadores_storage = JugadoresStorage()
