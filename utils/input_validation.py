"""Validación de longitud de inputs — defensa contra payloads gigantes."""

MAX_NOMBRE = 100
MAX_TELEFONO = 9
MAX_CATEGORIA = 30
MAX_EMAIL = 254
MAX_PASSWORD = 128


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
