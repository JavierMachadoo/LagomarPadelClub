from typing import Dict
import unicodedata
from config import HORARIOS_POR_DIA


def _normalizar_franja(franja: str) -> str:
    """Normaliza una franja horaria limpiando caracteres UTF-8 corruptos.
    
    Maneja casos donde 'Sábado' se ha guardado como 'SÃ¡bado' (UTF-8 double-encoded).
    También normaliza espacios y diacríticos.
    """
    if not franja:
        return franja
    
    # Intenta múltiples formas de arreglar la corrupción UTF-8
    try:
        # Opción 1: Si contiene caracteres problemáticos como Ã
        if 'Ã' in franja or '¡' in franja:
            # Re-codificar como latin-1 y decodificar como UTF-8
            franja = franja.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        # Si eso falla, dejar como está
        pass
    
    # Normaliza espacios y diacríticos
    franja = unicodedata.normalize('NFKD', franja)  # Separar caracteres base y diacríticos
    franja = ''.join(c for c in franja if unicodedata.category(c) != 'Mn')  # Remover diacríticos
    franja = unicodedata.normalize('NFKC', franja).strip()  # Normalizar composición normal
    
    # Reconstruir con el acento correcto (si era Sábado)
    if 'Sabado' in franja and 'Sábado' not in franja:
        franja = franja.replace('Sabado', 'Sábado')
    
    return franja


class CalendarioBuilder:
    def __init__(self, num_canchas: int = 2):
        self.num_canchas = num_canchas
    
    def construir_calendario_vacio(self) -> Dict:
        calendario = {}
        for dia, horas in HORARIOS_POR_DIA.items():
            calendario[dia] = {hora: [None] * self.num_canchas for hora in horas}
        return calendario
    
    def organizar_partidos(self, resultado_algoritmo, canchas_por_grupo=None) -> Dict:
        """Organiza los partidos en el calendario.
        
        Args:
            resultado_algoritmo: Resultado del algoritmo con los grupos
            canchas_por_grupo: Dict opcional con {grupo_id: numero_cancha}
        """
        calendario = self.construir_calendario_vacio()
        franjas_a_horas = self._mapear_franjas_a_horas()
        
        # Crear mapeo de grupo_id a letra por categoría
        grupo_a_letra = self._crear_mapeo_grupos_a_letras(resultado_algoritmo)
        
        for categoria, grupos in resultado_algoritmo.grupos_por_categoria.items():
            for grupo in grupos:
                if not grupo.franja_horaria:
                    continue
                
                # Obtener la cancha asignada al grupo si existe
                cancha_asignada = None
                if canchas_por_grupo and grupo.id in canchas_por_grupo:
                    cancha_asignada = canchas_por_grupo[grupo.id]
                
                self._asignar_partidos_grupo(
                    calendario, grupo, categoria, franjas_a_horas, 
                    cancha_asignada, grupo_a_letra.get(grupo.id, 'A')
                )
        
        return calendario
    
    def _crear_mapeo_grupos_a_letras(self, resultado_algoritmo) -> Dict:
        """Crea un diccionario que mapea grupo_id a letra (A, B, C, D)."""
        letras = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        grupo_a_letra = {}
        
        for categoria, grupos in resultado_algoritmo.grupos_por_categoria.items():
            # Ordenar grupos por ID para mantener consistencia
            grupos_ordenados = sorted(grupos, key=lambda g: g.id)
            for idx, grupo in enumerate(grupos_ordenados):
                letra = letras[idx] if idx < len(letras) else str(idx + 1)
                grupo_a_letra[grupo.id] = letra
        
        return grupo_a_letra
    
    def _mapear_franjas_a_horas(self) -> Dict:
        return {
            'Viernes 18:00': ('Viernes', ['18:00', '19:00', '20:00']),
            'Viernes 21:00': ('Viernes', ['21:00', '22:00', '23:00']),
            'Sábado 09:00': ('Sábado', ['09:00', '10:00', '11:00']),
            'Sábado 9:00': ('Sábado', ['09:00', '10:00', '11:00']),
            'Sábado 12:00': ('Sábado', ['12:00', '13:00', '14:00']),
            'Sábado 16:00': ('Sábado', ['16:00', '17:00', '18:00']),
            'Sábado 19:00': ('Sábado', ['19:00', '20:00', '21:00']),
        }
    
    def _asignar_partidos_grupo(self, calendario, grupo, categoria, franjas_a_horas, cancha_asignada=None, grupo_letra='A'):
        franja_grupo = _normalizar_franja(grupo.franja_horaria) if grupo.franja_horaria else None
        
        for franja_key, (dia, horas_disponibles) in franjas_a_horas.items():
            franja_key_normalizado = _normalizar_franja(franja_key)
            if franja_key_normalizado and franja_grupo and franja_key_normalizado in franja_grupo:
                hora_idx = 0
                for partido_num, (p1, p2) in enumerate(grupo.partidos):
                    if hora_idx >= len(horas_disponibles):
                        break
                    
                    hora = horas_disponibles[hora_idx]
                    
                    # Usar la cancha asignada si existe, sino buscar una libre
                    if cancha_asignada is not None:
                        cancha_idx = int(cancha_asignada) - 1  # Convertir de 1-indexed a 0-indexed
                    else:
                        cancha_idx = self._buscar_cancha_libre(calendario[dia][hora])
                    
                    if cancha_idx is not None and cancha_idx < self.num_canchas:
                        partido = {
                            'categoria': categoria,
                            'grupo_id': grupo.id,
                            'grupo_letra': grupo_letra,
                            'pareja1': p1.nombre,
                            'pareja2': p2.nombre
                        }
                        calendario[dia][hora][cancha_idx] = partido
                        hora_idx += 1
                
                break
    
    def _buscar_cancha_libre(self, canchas) -> int:
        for idx, cancha in enumerate(canchas):
            if cancha is None:
                return idx
        return None
