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

_USE_SUPABASE = bool(
    os.getenv('SUPABASE_URL', '').strip()
    and os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
)

if _USE_SUPABASE:
    try:
        from utils.supabase_client import get_supabase_admin as _get_supabase_admin  # noqa: F401
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
            from utils.supabase_client import get_supabase_admin
            self._sb = get_supabase_admin()
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
        query = self._sb.table(_TABLE).select('*').eq('activo', True)
        for word in q.split():
            patron = f'%{word}%'
            query = query.or_(f'nombre.ilike.{patron},apellido.ilike.{patron}')
        return query.order('apellido').execute().data or []

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
            if j.get('activo', True) and patron in (
                f"{j.get('nombre', '')} {j.get('apellido', '')}".lower()
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

    def listar_rechazos(self) -> set:
        """Devuelve el conjunto de pares rechazados como frozensets {catalogo_id, registrado_id}."""
        if self._use_supabase:
            rows = self._sb.table('rechazos_vinculacion').select('catalogo_id,registrado_id').execute().data or []
            return {frozenset((r['catalogo_id'], r['registrado_id'])) for r in rows}
        return {
            frozenset(k.split('|', 1))
            for k in self._json_rechazos_leer()
        }

    def rechazar(self, catalogo_id: str, registrado_id: str) -> None:
        if self._use_supabase:
            self._sb.table('rechazos_vinculacion').upsert(
                {'catalogo_id': catalogo_id, 'registrado_id': registrado_id}
            ).execute()
        else:
            rechazos = self._json_rechazos_leer()
            key = f'{catalogo_id}|{registrado_id}'
            if key not in rechazos:
                rechazos.append(key)
                self._json_rechazos_escribir(rechazos)

    def _json_rechazos_leer(self) -> list:
        path = self._jugadores_file.parent / 'rechazos_vinculacion.json'
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _json_rechazos_escribir(self, datos: list) -> None:
        path = self._jugadores_file.parent / 'rechazos_vinculacion.json'
        path.write_text(json.dumps(datos, indent=2), encoding='utf-8')

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

    def fusionar(self, catalogo_id: str, registrado_id: str) -> dict:
        """
        Fusiona el jugador del catálogo (admin) con el jugador registrado (auth).

        Mueve las referencias históricas de catalogo_id → registrado_id,
        copia los datos canónicos del catálogo al registrado, y desactiva
        la fila del catálogo. El jugador registrado (auth UUID) queda como
        el canónico con historial completo.
        """
        if not self._use_supabase:
            raise ValueError('Fusión solo disponible con Supabase')

        cat = self._sb_obtener(catalogo_id)
        if not cat:
            raise ValueError(f'Jugador catálogo {catalogo_id} no encontrado')

        reg = self._sb_obtener(registrado_id)
        if not reg:
            raise ValueError(f'Jugador registrado {registrado_id} no encontrado')

        # Mover referencias históricas — cada tabla en try/except para no abortar
        # si una columna no existe en el schema actual (dev vs prod)
        _FKS = [
            ('puntos_jugador', 'jugador_id'),
            ('parejas',        'jugador1_id'),
            ('parejas',        'jugador2_id'),
            ('inscripciones',  'jugador_id'),
            ('inscripciones',  'jugador2_id'),
        ]
        for tabla, columna in _FKS:
            try:
                self._sb.table(tabla).update({columna: registrado_id}).eq(columna, catalogo_id).execute()
            except Exception as e:
                logger.warning('fusionar: no se pudo actualizar %s.%s — %s', tabla, columna, e)

        # Copiar datos canónicos del catálogo al jugador registrado
        campos_canonicos = {k: cat[k] for k in ('nombre', 'apellido', 'telefono') if cat.get(k)}
        if campos_canonicos:
            self._sb.table(_TABLE).update(campos_canonicos).eq('id', registrado_id).execute()

        # Desactivar la fila del catálogo (no se elimina)
        self._sb.table(_TABLE).update({'activo': False}).eq('id', catalogo_id).execute()

        return self._sb_obtener(registrado_id) or {}


jugadores_storage = JugadoresStorage()
