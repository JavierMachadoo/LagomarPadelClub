"""Validación de longitud e inputs — defensa contra payloads gigantes."""

import re

MAX_NOMBRE = 100
MAX_TELEFONO = 20
MAX_CATEGORIA = 30
MAX_EMAIL = 254
MAX_PASSWORD = 128

_TELEFONO_RE = re.compile(r'^[+\d\s\-(). ]{6,20}$')


def validar_telefono(telefono: str) -> tuple[bool, str]:
    """Valida formato del teléfono. Acepta vacío (campo opcional).

    Returns:
        (True, "") si válido o vacío, (False, mensaje) si inválido.
    """
    if not telefono:
        return True, ""
    if not _TELEFONO_RE.match(telefono) or len(telefono) > MAX_TELEFONO:
        return False, "Teléfono inválido — usá solo dígitos, espacios, guiones o paréntesis (6-20 caracteres)"
    return True, ""


def validar_longitud(campos: dict[str, tuple[str, int]]) -> str | None:
    """Valida que cada campo no exceda su longitud máxima.

    Args:
        campos: dict de nombre → (valor, max_length)

    Returns:
        Mensaje de error o None si todo OK.
    """
    for nombre, (valor, max_len) in campos.items():
        if valor and len(valor) > max_len:
            return f'{nombre} no puede superar {max_len} caracteres'
    return None
