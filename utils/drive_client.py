"""
Cliente para Google Drive API v3.
Accede a carpetas públicas ("anyone with link") sin OAuth — solo API Key.
"""
import logging
import re
import time
from typing import Optional, TypedDict

import requests

logger = logging.getLogger(__name__)

DRIVE_API_URL = "https://www.googleapis.com/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"
_FOLDER_REGEX = re.compile(r"/folders/([a-zA-Z0-9_-]+)")
_BARE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{10,}$")
_CACHE_TTL_SECONDS = 600  # 10 min
_REQUEST_TIMEOUT = 6


class Foto(TypedDict):
    id: str
    nombre: str
    thumbnail_url: str
    full_url: str
    download_url: str


class Subcarpeta(TypedDict):
    nombre: str
    folder_id: str
    fotos: list[Foto]


# cache: folder_id raíz -> (timestamp, list[Subcarpeta])
_cache: dict[str, tuple[float, list]] = {}


def extraer_folder_id(valor: str) -> Optional[str]:
    """Acepta URL completa de Drive o ID pelado. Devuelve folder_id o None."""
    if not valor or not isinstance(valor, str):
        return None
    valor = valor.strip()
    m = _FOLDER_REGEX.search(valor)
    if m:
        return m.group(1)
    if _BARE_ID_REGEX.match(valor):
        return valor
    return None


def _drive_get(params: dict) -> dict:
    """GET a Drive v3. Lanza RuntimeError si falta API key, HTTPError en 4xx/5xx."""
    from config.settings import GOOGLE_DRIVE_API_KEY
    if not GOOGLE_DRIVE_API_KEY:
        raise RuntimeError("GOOGLE_DRIVE_API_KEY no configurada")
    params = {**params, "key": GOOGLE_DRIVE_API_KEY}
    r = requests.get(DRIVE_API_URL, params=params, timeout=_REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _listar_items(folder_id: str) -> list[dict]:
    """Lista hijos directos de un folder (archivos y subcarpetas). No recursivo."""
    data = _drive_get({
        "q": f"'{folder_id}' in parents and trashed=false",
        "fields": "files(id,name,mimeType)",
        "orderBy": "name",
        "pageSize": 1000,
    })
    return data.get("files", [])


def _to_foto(archivo: dict) -> Foto:
    fid = archivo["id"]
    return {
        "id": fid,
        "nombre": archivo.get("name", ""),
        "thumbnail_url": f"https://drive.google.com/thumbnail?id={fid}&sz=w400",
        "full_url": f"https://drive.google.com/thumbnail?id={fid}&sz=w1600",
        "download_url": f"https://drive.google.com/uc?export=download&id={fid}",
    }


def obtener_galeria(folder_id: str) -> list:
    """Devuelve galería agrupada por subcarpeta, con caché de 10 min.

    - Si la raíz tiene subcarpetas → una entrada por subcarpeta con sus imágenes.
    - Si solo tiene imágenes directas → una entrada "Fotos".
    - Lista vacía si Drive falla o no hay nada visible.
    """
    now = time.time()
    hit = _cache.get(folder_id)
    if hit and (now - hit[0]) < _CACHE_TTL_SECONDS:
        return hit[1]

    try:
        items = _listar_items(folder_id)
    except Exception as e:
        logger.warning("Drive API error folder=%s: %s", folder_id, e)
        return []

    subfolders = [i for i in items if i.get("mimeType") == FOLDER_MIME]
    imagenes_root = [i for i in items if (i.get("mimeType") or "").startswith("image/")]

    resultado: list = []

    if subfolders:
        for sub in subfolders:
            sub_id = sub["id"]
            try:
                hijos = _listar_items(sub_id)
            except Exception as e:
                logger.warning("Drive API error subfolder=%s: %s", sub_id, e)
                continue
            fotos = [_to_foto(h) for h in hijos if (h.get("mimeType") or "").startswith("image/")]
            if fotos:
                resultado.append({
                    "nombre": sub.get("name", "Fotos"),
                    "folder_id": sub_id,
                    "fotos": fotos,
                })
    elif imagenes_root:
        resultado.append({
            "nombre": "Fotos",
            "folder_id": folder_id,
            "fotos": [_to_foto(i) for i in imagenes_root],
        })

    _cache[folder_id] = (now, resultado)
    return resultado


def invalidar_cache(folder_id: Optional[str] = None) -> None:
    """Invalida entrada específica o toda la caché."""
    if folder_id is None:
        _cache.clear()
    else:
        _cache.pop(folder_id, None)
