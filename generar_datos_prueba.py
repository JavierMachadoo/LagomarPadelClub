"""
Genera datos de prueba en formato CSV para simular Google Forms del torneo.

Formato de columnas (igual al export de Google Forms):
  Marca temporal | Nombre y apellido integrante 1 | Nombre y apellido integrante 2 |
  Un celular de contacto | Categoría |
  Viernes 18:00 a 21:00 | Viernes 21:00 a 00:00 |
  Sábado 9:00 a 12:00 | Sábado 12:00 a 15:00 | Sábado 16:00 a 19:00 | Sábado 19:00 a 22:00
"""

import csv
from datetime import datetime, timedelta

# Franjas horarias (sin Jueves)
FRANJAS = [
    "Viernes 18:00 a 21:00",
    "Viernes 21:00 a 00:00",
    "Sábado 9:00 a 12:00",
    "Sábado 12:00 a 15:00",
    "Sábado 16:00 a 19:00",
    "Sábado 19:00 a 22:00"
]

# Datos de parejas: (jugador1, jugador2, telefono, categoria, indices_franjas)
# índices de franjas (0-based sobre la lista FRANJAS)
parejas_data = [
    # Cuarta (12 parejas)
    ("Juan Pérez", "María López", "099123456", "Cuarta", [2, 3]),
    ("Carlos Gómez", "Ana Martínez", "099234567", "Cuarta", [2, 4]),
    ("Pedro Rodríguez", "Laura Fernández", "099345678", "Cuarta", [0, 2]),
    ("Luis García", "Carmen Sánchez", "099456789", "Cuarta", [3, 4]),
    ("Miguel Torres", "Isabel Ramírez", "099567890", "Cuarta", [0, 3]),
    ("Jorge Castro", "Patricia Morales", "099678901", "Cuarta", [3, 5]),
    ("Alejandro Ruiz", "Sofía Díaz", "099789012", "Cuarta", [2, 3]),
    ("Daniel Herrera", "Valentina Cruz", "099890123", "Cuarta", [3, 4, 5]),
    ("Andrés Moreno", "Camila Rojas", "099901234", "Cuarta", [2, 4]),
    ("Sebastián Vargas", "Lucía Méndez", "099012345", "Cuarta", [1, 4, 5]),
    ("Mateo Ortiz", "Emma Jiménez", "099123457", "Cuarta", [0, 5]),
    ("Gabriel Silva", "Victoria Ramos", "099234568", "Cuarta", [0, 1]),

    # Sexta (13 parejas)
    ("Javier Serrano", "Constanza Paz", "099789014", "Sexta", [0, 2]),
    ("Martín Blanco", "Delfina Núñez", "099890125", "Sexta", [0, 4]),
    ("Ignacio Guerrero", "Pilar Domínguez", "099901236", "Sexta", [0, 1]),
    ("Facundo Miranda", "Alma Carrillo", "099012347", "Sexta", [1, 4, 5]),
    ("Valentín Ponce", "Nina Márquez", "099123459", "Sexta", [1, 2, 3]),
    ("Thiago Espinoza", "Jazmín Ríos", "099234570", "Sexta", [2, 3]),
    ("Lautaro Benítez", "Catalina Vera", "099345681", "Sexta", [3, 4]),
    ("Bruno Villalba", "Julieta Peralta", "099456782", "Sexta", [4, 5]),
    ("Alejo Cáceres", "Renata Acosta", "099567893", "Sexta", [4]),
    ("Ian Maldonado", "Luna Ferreira", "099678904", "Sexta", [3, 4]),
    ("Ezequiel Sosa", "Abril Sandoval", "099789015", "Sexta", [3, 5]),
    ("Bautista Rojas", "Lola Montero", "099890126", "Sexta", [4, 5]),
    ("Agustín Figueroa", "Helena Bustos", "099901237", "Sexta", [4, 5]),

    # Quinta (14 parejas)
    ("Roberto Navarro", "Andrea Gil", "099345679", "Quinta", [0, 4]),
    ("Fernando Vega", "Daniela Flores", "099456780", "Quinta", [0, 4]),
    ("Ricardo Peña", "Carolina Castro", "099567891", "Quinta", [0, 5]),
    ("Diego Romero", "Martina Molina", "099678902", "Quinta", [4, 5]),
    ("Pablo Ríos", "Gabriela Mendoza", "099789013", "Quinta", [2, 4]),
    ("Lucas Fuentes", "Olivia Paredes", "099890124", "Quinta", [2, 4]),
    ("Santiago Ibarra", "Isabella Cortés", "099901235", "Quinta", [1, 4, 5]),
    ("Nicolás Campos", "Emilia Reyes", "099012346", "Quinta", [3, 4]),
    ("Joaquín León", "Renata Medina", "099123458", "Quinta", [0, 1]),
    ("Tomás Guzmán", "Julia Soto", "099234569", "Quinta", [0, 2]),
    ("Maximiliano Cruz", "Valentina Torres", "099345680", "Quinta", [1, 2, 3]),
    ("Benjamín Arias", "Luciana Prieto", "099456781", "Quinta", [2, 3]),
    ("Emilio Mora", "Antonella Aguilar", "099567892", "Quinta", [1, 3]),
    ("Matías Delgado", "Mía Cabrera", "099678903", "Quinta", [2, 4]),

    # Séptima (10 parejas)
    ("Felipe Bravo", "Clara Vidal", "099012348", "Séptima", [1, 3]),
    ("Lorenzo Suárez", "Martina Campos", "099123460", "Séptima", [1, 3]),
    ("Francisco Rivas", "Emilia Santos", "099234571", "Séptima", [1, 5]),
    ("Simón Robles", "Sofia Luna", "099345682", "Séptima", [4, 5]),
    ("Manuel Gallardo", "Elena Riveros", "099456783", "Séptima", [4, 5]),
    ("Vicente Valdez", "Paula Cortés", "099567894", "Séptima", [3, 4]),
    ("Rodrigo Lagos", "Isidora Leiva", "099678905", "Séptima", [2, 3]),
    ("Esteban Muñoz", "Florencia Parra", "099789016", "Séptima", [2, 4]),
    ("Cristóbal Tapia", "Magdalena Bravo", "099890127", "Séptima", [3, 4]),
    ("Gonzalo Moya", "Antonia Rubio", "099901238", "Séptima", [0, 1]),

    # Tercera (10 parejas)
    ("Hernán Soto", "Bárbara Fuentes", "099111001", "Tercera", [0, 2]),
    ("Claudio Reyes", "Patricia Lagos", "099111002", "Tercera", [0, 3]),
    ("Patricio Muñoz", "Alejandra Vega", "099111003", "Tercera", [1, 4]),
    ("Mauricio Tapia", "Daniela Rivas", "099111004", "Tercera", [2, 5]),
    ("Rodrigo Parra", "Camila Bravo", "099111005", "Tercera", [2, 4]),
    ("Andrés Leal", "Francisca Díaz", "099111006", "Tercera", [3, 5]),
    ("Pablo Mendoza", "Monserrat Rojas", "099111007", "Tercera", [0, 4]),
    ("Sergio Guzmán", "Valentina Mora", "099111008", "Tercera", [1, 3]),
    ("Carlos Ibáñez", "Andrea Núñez", "099111009", "Tercera", [2, 3]),
    ("Felipe Castillo", "Natalia Vargas", "099111010", "Tercera", [4, 5]),
]


def generar_csv():
    """Genera el archivo CSV con datos de prueba en formato Google Forms."""
    fecha_base = datetime(2025, 10, 15, 8, 0, 0)

    with open('data/datos_prueba.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Encabezados igual al export de Google Forms
        headers = [
            'Marca temporal',
            'Nombre y apellido integrante 1',
            'Nombre y apellido integrante 2',
            'Un celular de contacto',
            'Categoría',
        ]
        headers.extend(FRANJAS)
        writer.writerow(headers)

        # Datos
        for idx, (jugador1, jugador2, telefono, categoria, indices_franjas) in enumerate(parejas_data):
            timestamp = fecha_base + timedelta(hours=idx * 1.5)
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')

            fila = [timestamp_str, jugador1, jugador2, telefono, categoria]

            # Marcar la celda con el texto de la franja si está seleccionada, vacía si no
            for i, franja in enumerate(FRANJAS):
                fila.append(franja if i in indices_franjas else '')

            writer.writerow(fila)

    print(f"✅ Archivo CSV generado: data/datos_prueba.csv")
    print(f"📊 Total de parejas: {len(parejas_data)}")

    por_categoria = {}
    for _, _, _, cat, _ in parejas_data:
        por_categoria[cat] = por_categoria.get(cat, 0) + 1

    print("\nDistribución por categoría:")
    for cat, count in sorted(por_categoria.items()):
        print(f"  {cat}: {count} parejas")


if __name__ == "__main__":
    generar_csv()
