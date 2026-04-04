"""
Sistema de almacenamiento persistente del torneo activo.

En producción (Render, Railway, etc.) usa Supabase para persistencia real.
En desarrollo local, cae a JSON si no hay variables de Supabase configuradas.

Variables de entorno requeridas para Supabase:
    SUPABASE_URL              → URL del proyecto Supabase
    SUPABASE_SERVICE_ROLE_KEY → clave service_role (bypasea RLS — solo para backend)
    SUPABASE_ANON_KEY         → fallback si no hay service_role key
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ConflictError(Exception):
    """Otro proceso escribió el torneo entre el cargar() y el guardar().
    El caller debe devolver HTTP 409 y pedirle al admin que recargue."""


# Directorio base del proyecto (dos niveles arriba de este archivo)
_BASE_DIR = Path(__file__).resolve().parent.parent

# ── Detectar si Supabase está disponible ──────────────────────────────────────
_SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
# El storage es código de servidor puro → usa service_role key para bypassar RLS.
# La anon_key queda para clientes del browser que sí deben pasar por RLS.
_SUPABASE_KEY = (
    os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
    or os.getenv('SUPABASE_ANON_KEY', '').strip()
)
_USE_SUPABASE = bool(_SUPABASE_URL and _SUPABASE_KEY)

if _USE_SUPABASE:
    try:
        from supabase import create_client, Client as SupabaseClient
    except ImportError:
        logger.warning('supabase package no instalado. Usando almacenamiento JSON.')
        _USE_SUPABASE = False

# ─────────────────────────────────────────────────────────────────────────────


class TorneoStorage:
    """Gestiona el almacenamiento persistente de un único torneo.

    Backend:
        - Supabase (JSONB)  → cuando SUPABASE_URL y SUPABASE_ANON_KEY están definidas
        - JSON local        → fallback para desarrollo sin Supabase
    """

    # Paths locales (solo se usan si no hay Supabase)
    _TORNEOS_DIR: Path = _BASE_DIR / 'data' / 'torneos'
    _TORNEO_FILE: Path = _TORNEOS_DIR / 'torneo_actual.json'

    # Nombre de la tabla en Supabase
    _TABLE = 'torneo_actual'

    # TTL del caché en memoria (segundos).
    # Con 2 workers en Railway, cada proceso tiene su propia copia — stale acotado a 5s.
    # Aceptable para lecturas de jugadores. Escrituras protegidas por optimistic locking.
    _CACHE_TTL = 5

    def __init__(self) -> None:
        self._cache: Optional[Dict] = None
        self._cache_ts: float = 0.0

        if _USE_SUPABASE:
            self._sb: SupabaseClient = create_client(_SUPABASE_URL, _SUPABASE_KEY)
            logger.info('TorneoStorage: usando Supabase')
        else:
            self._TORNEOS_DIR.mkdir(parents=True, exist_ok=True)
            if not self._TORNEO_FILE.exists():
                self._crear_torneo_default()
            logger.info('TorneoStorage: usando JSON local (%s)', self._TORNEO_FILE)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _torneo_vacio(self) -> Dict:
        """Devuelve la estructura de un torneo nuevo."""
        now = datetime.now().isoformat()
        return {
            'nombre': '',
            'fecha_creacion': now,
            'fecha_modificacion': now,
            'parejas': [],
            'resultado_algoritmo': None,
            'num_canchas': 2,
            'estado': 'creando',
            'fase': 'espera',
            'tipo_torneo': 'fin1',
            'torneo_id': str(uuid.uuid4()),
            'version': 0,
        }

    def _crear_torneo_default(self) -> None:
        self._guardar_sin_version(self._torneo_vacio())

    def _reset_campos_torneo(self, torneo: Dict) -> None:
        """Resetea los campos de juego del torneo (helper compartido por limpiar y transicion_a_espera)."""
        torneo['parejas'] = []
        torneo['resultado_algoritmo'] = None
        torneo['fixtures_finales'] = {}
        torneo['estado'] = 'creando'
        torneo['torneo_id'] = str(uuid.uuid4())
        torneo.pop('proximo_torneo', None)

    # ── API pública ───────────────────────────────────────────────────────────

    def _guardar_sin_version(self, datos: Dict) -> None:
        """Escritura incondicional — no verifica versión.

        Solo para operaciones internas (init, limpiar, transiciones de fase).
        Para escrituras de admin usar guardar_con_version().
        """
        datos['fecha_modificacion'] = datetime.now().isoformat()

        if _USE_SUPABASE:
            self._sb.table(self._TABLE).upsert(
                {'id': 1, 'datos': datos}
            ).execute()
        else:
            with open(self._TORNEO_FILE, 'w', encoding='utf-8') as f:
                json.dump(datos, f, indent=2, ensure_ascii=False)

        # Actualizar caché con los datos recién guardados
        self._cache = datos
        self._cache_ts = time.monotonic()

    def guardar_con_version(self, datos: Dict) -> None:
        """Persiste el torneo solo si la versión no cambió desde el último cargar().

        Implementa optimistic locking: lee la versión actual del dict, intenta
        escribir condicionalmente en Supabase vía RPC. Si otro proceso se adelantó,
        la RPC devuelve False y se lanza ConflictError.

        El caller debe capturar ConflictError y devolver HTTP 409.
        """
        expected_version = datos.get('version', 0)
        datos['version'] = expected_version + 1
        datos['fecha_modificacion'] = datetime.now().isoformat()

        if _USE_SUPABASE:
            resp = self._sb.rpc('guardar_torneo_con_version', {
                'p_datos': datos,
                'p_expected_version': expected_version,
            }).execute()
            if not resp.data:
                # Revertir el incremento de versión para no dejar el dict en estado sucio
                datos['version'] = expected_version
                raise ConflictError(
                    'Otro administrador modificó los datos. Recargá la página para continuar.'
                )
        else:
            # Fallback JSON: verificar versión directamente desde el archivo
            try:
                with open(self._TORNEO_FILE, encoding='utf-8') as f:
                    current = json.load(f)
                if current.get('version', 0) != expected_version:
                    datos['version'] = expected_version
                    raise ConflictError(
                        'Conflicto de versión en almacenamiento local.'
                    )
            except (FileNotFoundError, json.JSONDecodeError):
                pass  # Archivo no existe o corrupto — escribir de todas formas
            with open(self._TORNEO_FILE, 'w', encoding='utf-8') as f:
                json.dump(datos, f, indent=2, ensure_ascii=False)

        self._cache = datos
        self._cache_ts = time.monotonic()

    def cargar(self) -> Dict:
        """Carga y devuelve el diccionario completo del torneo.

        Si el caché es reciente (< TTL) lo devuelve directamente
        sin ir a Supabase → latencia ~0 ms en vez de ~200 ms.
        """
        # ── Caché en memoria ──────────────────────────────────────────────────
        if self._cache is not None:
            if time.monotonic() - self._cache_ts < self._CACHE_TTL:
                return self._cache
        # ─────────────────────────────────────────────────────────────────────

        if _USE_SUPABASE:
            try:
                resp = self._sb.table(self._TABLE).select('datos').eq('id', 1).execute()
                if resp.data:
                    datos = resp.data[0]['datos']
                    self._cache = datos
                    self._cache_ts = time.monotonic()
                    return datos
            except Exception as e:
                logger.error('Error al cargar desde Supabase: %s', e)
                # Si falla Supabase devolver caché aunque esté vencido
                if self._cache is not None:
                    logger.warning('Usando caché vencido por error de Supabase')
                    return self._cache

            # Primera ejecución: no hay fila todavía
            default = self._torneo_vacio()
            self._guardar_sin_version(default)
            return default

        # ── JSON local ────────────────────────────────────────────────────────
        if not self._TORNEO_FILE.exists():
            self._crear_torneo_default()


        try:
            with open(self._TORNEO_FILE, encoding='utf-8') as f:
                datos = json.load(f)
                self._cache = datos
                self._cache_ts = time.monotonic()
                return datos
        except (json.JSONDecodeError, IOError) as e:
            logger.error('Error al cargar torneo JSON: %s', e)
            self._crear_torneo_default()
            return self.cargar()


    def limpiar(self) -> None:
        """Reinicia el torneo preservando nombre y tipo configurados en estado espera."""
        torneo = self.cargar()
        nombre_actual = torneo.get('nombre', '')
        tipo_actual = torneo.get('tipo_torneo', 'fin1')
        self._reset_campos_torneo(torneo)
        torneo['fase'] = 'inscripcion'
        torneo['nombre'] = nombre_actual
        torneo['tipo_torneo'] = tipo_actual
        torneo.pop('ultimo_torneo_id', None)
        self._guardar_sin_version(torneo)
        self.inicializar_torneo_id()  # sincroniza el nuevo torneo_id con la tabla torneos en Supabase

    def get_torneo_id(self) -> str:
        """Devuelve el UUID del torneo activo (solo lectura).

        Si no existe torneo_id (torneos pre-Fase 1), delega a inicializar_torneo_id().
        Para operaciones normales no tiene side effects.
        """
        torneo_id = self.cargar().get('torneo_id')
        if not torneo_id:
            return self.inicializar_torneo_id()
        return torneo_id

    def inicializar_torneo_id(self) -> str:
        """Genera un torneo_id si no existe y sincroniza con la tabla torneos.

        Llamar explícitamente al crear un torneo nuevo. No se debe llamar en
        operaciones de lectura normales — usar get_torneo_id() para eso.
        """
        torneo = self.cargar()
        torneo_id = torneo.get('torneo_id') or str(uuid.uuid4())
        torneo['torneo_id'] = torneo_id
        self._guardar_sin_version(torneo)

        if _USE_SUPABASE:
            try:
                self._sb.table('torneos').upsert({
                    'id':     torneo_id,
                    'nombre': torneo.get('nombre', 'Torneo'),
                    'tipo':   torneo.get('tipo_torneo', 'fin1'),
                    'estado': torneo.get('fase', 'inscripcion'),
                }, on_conflict='id').execute()
            except Exception as e:
                logger.warning('No se pudo sincronizar torneo_id con tabla torneos: %s', e)

        return torneo_id

    def get_fase(self) -> str:
        """Devuelve la fase actual del torneo ('inscripcion' | 'torneo' | 'espera')."""
        torneo = self.cargar()
        return torneo.get('fase', 'espera')

    def set_fase(self, nueva_fase: str) -> None:
        """Cambia la fase del torneo. Valida que sea un valor permitido."""
        if nueva_fase not in ('inscripcion', 'torneo', 'espera'):
            raise ValueError(f"Fase inválida: {nueva_fase}")
        torneo = self.cargar()
        torneo['fase'] = nueva_fase
        self.guardar_con_version(torneo)

    def transicion_a_espera(self, ultimo_torneo_id: str) -> None:
        """Transiciona a estado 'espera' tras archivar un torneo."""
        torneo = self.cargar()
        self._reset_campos_torneo(torneo)
        torneo['fase'] = 'espera'
        torneo['nombre'] = ''
        torneo['tipo_torneo'] = 'fin1'
        torneo['ultimo_torneo_id'] = ultimo_torneo_id
        self._guardar_sin_version(torneo)

    def get_ultimo_torneo_id(self) -> Optional[str]:
        """Devuelve el ID del último torneo archivado (usado en estado 'espera')."""
        torneo = self.cargar()
        return torneo.get('ultimo_torneo_id')

    def set_proximo_torneo(self, fecha: str, nombre: str, tipo_torneo: str = 'fin1',
                           categorias: list = None, descripcion: str = '') -> None:
        """Guarda la info del próximo torneo y la aplica directamente al blob activo.

        El nombre y tipo_torneo se guardan en el blob del torneo activo para que
        sobrevivan la transición a estado inscripcion (limpiar() los preserva).
        """
        torneo = self.cargar()
        torneo['nombre'] = nombre
        torneo['tipo_torneo'] = tipo_torneo
        torneo['proximo_torneo'] = {
            'fecha': fecha,
            'nombre': nombre,
            'tipo_torneo': tipo_torneo,
            'categorias': categorias or [],
            'descripcion': descripcion,
        }
        self.guardar_con_version(torneo)

    def get_proximo_torneo(self) -> Optional[Dict]:
        """Devuelve la info del próximo torneo, o None si no está configurado."""
        torneo = self.cargar()
        return torneo.get('proximo_torneo')

    def get_tipo_torneo(self) -> str:
        """Devuelve el tipo de torneo activo ('fin1' o 'fin2')."""
        torneo = self.cargar()
        return torneo.get('tipo_torneo', 'fin1')

    def set_tipo_torneo(self, tipo: str) -> None:
        """Cambia el tipo de torneo activo."""
        torneo = self.cargar()
        torneo['tipo_torneo'] = tipo
        self.guardar_con_version(torneo)


    def actualizar_nombre(self, nuevo_nombre: str) -> bool:
        """Actualiza el nombre del torneo. Devuelve True si tuvo éxito."""
        try:
            torneo = self.cargar()
            torneo['nombre'] = nuevo_nombre
            self.guardar_con_version(torneo)
            return True
        except Exception as e:
            logger.error('Error al actualizar nombre: %s', e)
            return False


# Instancia global compartida por todos los módulos
storage = TorneoStorage()
