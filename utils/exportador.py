import json
import csv
from typing import List, Dict
from pathlib import Path


class DataExporter:
    @staticmethod
    def exportar_json(datos: dict, archivo: str):
        with open(archivo, 'w', encoding='utf-8') as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
    
    @staticmethod
    def exportar_csv_grupos(resultado_algoritmo, archivo: str):
        with open(archivo, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            writer.writerow([
                'Grupo ID', 'Categoría', 'Franja Horaria', 
                'Pareja 1', 'Pareja 2', 'Pareja 3', 
                'Teléfono 1', 'Teléfono 2', 'Teléfono 3',
                'Score Compatibilidad'
            ])
            
            for categoria, grupos in resultado_algoritmo.grupos_por_categoria.items():
                for grupo in grupos:
                    parejas = grupo.parejas + [None] * (3 - len(grupo.parejas))
                    
                    writer.writerow([
                        grupo.id,
                        grupo.categoria,
                        grupo.franja_horaria or 'Por coordinar',
                        parejas[0].nombre if parejas[0] else '-',
                        parejas[1].nombre if parejas[1] else '-',
                        parejas[2].nombre if parejas[2] else '-',
                        parejas[0].telefono if parejas[0] else '-',
                        parejas[1].telefono if parejas[1] else '-',
                        parejas[2].telefono if parejas[2] else '-',
                        grupo.score_compatibilidad
                    ])
    
    @staticmethod
    def exportar_csv_parejas_sin_asignar(parejas: List, archivo: str):
        with open(archivo, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            writer.writerow(['Nombre', 'Categoría', 'Teléfono', 'Franjas Disponibles'])
            
            for pareja in parejas:
                franjas = ', '.join(pareja.franjas_disponibles) if pareja.franjas_disponibles else 'Ninguna'
                writer.writerow([
                    pareja.nombre,
                    pareja.categoria,
                    pareja.telefono,
                    franjas
                ])
