import os
from pathlib import Path
import secrets
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar .env si existe (desarrollo local); en producción las vars vienen del entorno
load_dotenv(BASE_DIR / '.env')

# SECRET_KEY: DEBE estar en .env en producción
# Si no existe, genera uno temporal (solo para desarrollo)
_default_secret = secrets.token_urlsafe(32) if os.getenv('SECRET_KEY') is None else None
SECRET_KEY = os.getenv('SECRET_KEY', _default_secret)

if _default_secret and not os.getenv('DEBUG', 'True') == 'True':
    import warnings
    warnings.warn('⚠️  SECRET_KEY no configurado! Usando secret temporal. Configure SECRET_KEY en .env')

DEBUG = os.getenv('DEBUG', 'True') == 'True'

# Credenciales de acceso - CAMBIAR EN PRODUCCIÓN
# Para mayor seguridad, usa variables de entorno
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'torneopadel2026')

# Supabase - requerido en producción para persistencia de datos
# En desarrollo local, si no están definidas, se usa almacenamiento JSON
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '')

UPLOAD_FOLDER = BASE_DIR / 'data' / 'uploads'
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'csv', 'xlsx'}

# Franjas horarias exactas del formulario de Google Forms
FRANJAS_HORARIAS = [
    "Viernes 18:00",     # Viernes 18:00 a 21:00
    "Viernes 21:00",     # Viernes 21:00 a 00:00
    "Sábado 09:00",      # Sábado 9:00 a 12:00
    "Sábado 12:00",      # Sábado 12:00 a 15:00
    "Sábado 16:00",      # Sábado 16:00 a 19:00
    "Sábado 19:00"       # Sábado 19:00 a 22:00
]

CATEGORIAS = ["Tercera", "Cuarta", "Quinta", "Sexta", "Séptima"]

# Tipos de torneo: define qué categorías se juegan cada fin de semana
TIPOS_TORNEO = {
    "fin1": ["Tercera", "Quinta", "Séptima"],   # 1er fin de semana
    "fin2": ["Cuarta", "Sexta"],                 # 2do fin de semana
}

COLORES_CATEGORIA = {
    "Cuarta": "#28a745",
    "Quinta": "#ffc107",
    "Sexta": "#007bff",
    "Séptima": "#6f42c1",
    "Tercera": "#e83e8c"
}

EMOJI_CATEGORIA = {
    "Cuarta": "🟢",
    "Quinta": "🟡",
    "Sexta": "🔵",
    "Séptima": "🟣",
    "Tercera": "🔴"
}

NUM_CANCHAS_DEFAULT = 2
DURACION_PARTIDO_DEFAULT = 1

# Horarios por día según las franjas del formulario
HORARIOS_POR_DIA = {
    'Viernes': ['18:00', '19:00', '20:00', '21:00', '22:00', '23:00'],
    'Sábado': ['09:00', '10:00', '11:00', '12:00', '13:00', '14:00', 
               '16:00', '17:00', '18:00', '19:00', '20:00', '21:00']
}
