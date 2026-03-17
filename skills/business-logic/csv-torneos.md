---
name: csv-torneos
description: >
  Patrones para el procesamiento de CSV/Excel de inscripciones: normalización de columnas, mapeo de franjas y generación de Pareja.
  Trigger: Al modificar utils/csv_processor.py o el flujo de importación de parejas.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root, utils]
  auto_invoke: "Modifying CSV import or file upload processing"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Formato de Entrada Esperado

El CSV proviene de Google Forms. Las columnas tienen nombres verbosos que se normalizan al procesar.

```
# Encabezados del Google Form (entrada real)
Nombre,Teléfono,Categoría,Viernes 18:00 a 21:00,Viernes 21:00 a 00:00,Sábado 09:00 a 12:00,...

# Mapeo interno a franjas cortas
"Viernes 18:00 a 21:00"  →  "Viernes 18:00"
"Viernes 21:00 a 00:00"  →  "Viernes 21:00"
"Sábado 09:00 a 12:00"   →  "Sábado 09:00"
```

Los valores de disponibilidad son `Sí` / `No` (con tilde). Manejar también `Si` sin tilde como fallback.

## Validación de Archivo (REQUIRED)

Solo aceptar `.csv` y `.xlsx`. Usar la whitelist de extensiones de `CSVProcessor.validar_archivo()`.

```python
# ✅ CORRECTO: whitelist de extensiones
EXTENSIONES_PERMITIDAS = {'.csv', '.xlsx'}

def validar_archivo(filename):
    ext = Path(filename).suffix.lower()
    return ext in EXTENSIONES_PERMITIDAS

# ❌ NUNCA validar por MIME type del request (fácil de falsificar)
if request.files['file'].content_type == 'text/csv':  # no confiable
    ...
```

## Generación de IDs de Pareja

Los IDs se generan a partir del nombre para ser reproducibles. No usar `uuid4()` que cambia en cada carga.

```python
# ✅ ID reproducible basado en nombre normalizado
import hashlib

def generar_id_pareja(nombre: str) -> str:
    return hashlib.md5(nombre.strip().lower().encode()).hexdigest()[:8]

# ❌ NUNCA usar UUIDs aleatorios para parejas
import uuid
pareja_id = str(uuid.uuid4())  # cambia en cada re-importación, rompe referencias
```

## Manejo de Columnas Faltantes

El CSV puede tener columnas de franjas parciales. Tratar columnas ausentes como `No disponible`.

```python
# ✅ Verificar existencia antes de acceder
def procesar_fila(row, columnas_franja):
    franjas_disponibles = []
    for franja_larga, franja_corta in MAPEO_FRANJAS.items():
        if franja_larga in row and str(row[franja_larga]).strip() in ('Sí', 'Si', 'sí', 'si'):
            franjas_disponibles.append(franja_corta)
    return franjas_disponibles

# ❌ NUNCA asumir que todas las columnas existen
disponible = row['Viernes 18:00 a 21:00']  # KeyError si la columna no existe
```

## Nombre de Pareja

El nombre de la pareja se forma con los dos integrantes. Normalizar espacios y capitalización.

```python
# ✅ Construir nombre limpio
def construir_nombre_pareja(jugador1: str, jugador2: str) -> str:
    j1 = jugador1.strip().title()
    j2 = jugador2.strip().title()
    return f"{j1} / {j2}"

# ❌ NUNCA dejar espacios extra ni capitalización inconsistente
nombre = row['Integrante 1'] + " " + row['Integrante 2']
```

## Ejemplo Real del Proyecto

En `utils/csv_processor.py`, el flujo completo de procesamiento de una fila:

```python
def procesar_dataframe(self, df: pd.DataFrame) -> List[Pareja]:
    parejas = []
    for _, row in df.iterrows():
        jugador1 = str(row.get('Integrante 1', '')).strip()
        jugador2 = str(row.get('Integrante 2', '')).strip()
        nombre = f"{jugador1} / {jugador2}"
        telefono = str(row.get('Celular', '')).strip()
        categoria = str(row.get('Categoría', '')).strip()

        franjas = []
        for col_larga, franja_corta in self.MAPEO_FRANJAS.items():
            valor = str(row.get(col_larga, 'No')).strip()
            if valor in ('Sí', 'Si', 'sí', 'si', 'SÍ'):
                franjas.append(franja_corta)

        pareja = Pareja(
            id=self._generar_id(nombre),
            nombre=nombre,
            categoria=categoria,
            telefono=telefono,
            franjas_disponibles=franjas,
            jugador1=jugador1,
            jugador2=jugador2
        )
        parejas.append(pareja)
    return parejas
```

## Referencias

- `utils/csv_processor.py` — `CSVProcessor`, `procesar_dataframe()`, `validar_archivo()`
- `core/models.py` — `Pareja` (objeto de salida del procesador)
- `config/settings.py` — `FRANJAS_HORARIAS` (valores válidos de franjas cortas)
- `api/routes/parejas.py` — endpoint de upload que invoca `CSVProcessor`