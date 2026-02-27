import pandas as pd
import re
from typing import List, Dict
from config import FRANJAS_HORARIAS


class CSVProcessor:
    @staticmethod
    def _normalizar_franja(texto: str):
        """
        Dado el encabezado de una columna de horario (ej. 'Viernes 18:00 a 21:00'
        o 'Sábado 9:00 a 12:00'), retorna la clave normalizada que corresponde a
        FRANJAS_HORARIAS (ej. 'Viernes 18:00', 'Sábado 09:00'), o None si no coincide.
        """
        match = re.search(r'(\w+)\s+(\d{1,2}):(\d{2})', texto)
        if not match:
            return None
        dia = match.group(1)
        hora = match.group(2).zfill(2)
        minutos = match.group(3)
        clave = f"{dia} {hora}:{minutos}"
        return clave if clave in FRANJAS_HORARIAS else None

    @staticmethod
    def procesar_dataframe(df: pd.DataFrame) -> List[Dict]:
        """
        Procesa un DataFrame exportado desde el Google Form del torneo.

        Formato esperado de columnas (en cualquier orden):
          - Marca temporal                          (ignorada)
          - Nombre y apellido integrante 1          → jugador1
          - Nombre y apellido integrante 2          → jugador2
          - Un celular de contacto                  → telefono
          - Categoría                               → categoria
          - <franja horaria> (ej. Viernes 18:00 a 21:00)  → franjas_disponibles
            (una columna por opción; celda con texto = seleccionada, vacía = no)
        """
        parejas = []

        for _, fila in df.iterrows():
            jugador1 = ''
            jugador2 = ''
            telefono = None
            categoria = None
            franjas: List[str] = []

            for col, valor in fila.items():
                col_lower = col.lower()
                valor_str = str(valor).strip() if pd.notna(valor) else ''
                es_vacio = valor_str in ('', 'nan', 'NaN')

                # Integrante 1
                if 'integrante 1' in col_lower or 'integrante1' in col_lower:
                    if not es_vacio:
                        jugador1 = valor_str

                # Integrante 2
                elif 'integrante 2' in col_lower or 'integrante2' in col_lower:
                    if not es_vacio:
                        jugador2 = valor_str

                # Teléfono / celular de contacto
                elif any(p in col_lower for p in ['celular', 'teléfono', 'telefono', 'tel', 'phone']):
                    if not es_vacio:
                        telefono = valor_str

                # Categoría
                elif 'categor' in col_lower:
                    if not es_vacio:
                        categoria = valor_str.title()

                # Franjas horarias – dos formatos posibles:
                #   a) Columna única "Horarios" con valores separados por ";"
                #      Ej: "Sábado 12:00 a 15:00; Viernes 21:00 a 00:00"
                #   b) Google Forms: una columna por franja; celda con contenido = seleccionada.
                elif 'horario' in col_lower:
                    if not es_vacio:
                        for parte in re.split(r'[;,]', valor_str):
                            parte = parte.strip()
                            if parte:
                                franja = CSVProcessor._normalizar_franja(parte)
                                if franja and franja not in franjas:
                                    franjas.append(franja)
                else:
                    if not es_vacio:
                        franja = CSVProcessor._normalizar_franja(col)
                        if franja and franja not in franjas:
                            franjas.append(franja)

            # Validar datos mínimos: jugador1, jugador2 y categoría
            if jugador1 and jugador2 and categoria:
                nombre = f"{jugador1} / {jugador2}"
                parejas.append({
                    'categoria': categoria,
                    'franjas_disponibles': franjas,
                    'id': len(parejas) + 1,
                    'nombre': nombre,
                    'jugador1': jugador1,
                    'jugador2': jugador2,
                    'telefono': telefono or 'Sin teléfono'
                })

        return parejas

    @staticmethod
    def validar_archivo(filename: str) -> bool:
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv', 'xlsx'}
