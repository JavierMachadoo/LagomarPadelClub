# Arreglo parche — torneo actual

## Sacar el parche de Séptima

En `core/fixture_finales_generator.py`, método `_generar_4_grupos`, reemplazar el bloque completo del parche:

```python
# PARCHE torneo actual: Séptima usa cruces distintos — sacar cuando se defina regla general
if categoria == 'Séptima':
    slots = [
        {'p1': (primeros, 0), 'p2': (segundos, 2), 'info1': '1° Grupo A', 'info2': '2° Grupo C'},
        {'p1': (primeros, 3), 'p2': (segundos, 1), 'info1': '1° Grupo D', 'info2': '2° Grupo B'},
        {'p1': (primeros, 1), 'p2': (segundos, 3), 'info1': '1° Grupo B', 'info2': '2° Grupo D'},
        {'p1': (primeros, 2), 'p2': (segundos, 0), 'info1': '1° Grupo C', 'info2': '2° Grupo A'},
    ]
else:
    slots = [
        {'p1': (primeros, 0), 'p2': (segundos, 3), 'info1': '1° Grupo A', 'info2': '2° Grupo D'},
        {'p1': (primeros, 1), 'p2': (segundos, 2), 'info1': '1° Grupo B', 'info2': '2° Grupo C'},
        {'p1': (primeros, 2), 'p2': (segundos, 1), 'info1': '1° Grupo C', 'info2': '2° Grupo B'},
        {'p1': (primeros, 3), 'p2': (segundos, 0), 'info1': '1° Grupo D', 'info2': '2° Grupo A'},
    ]
```

Por esto:

```python
slots = [
    {'p1': (primeros, 0), 'p2': (segundos, 3), 'info1': '1° Grupo A', 'info2': '2° Grupo D'},
    {'p1': (primeros, 1), 'p2': (segundos, 2), 'info1': '1° Grupo B', 'info2': '2° Grupo C'},
    {'p1': (primeros, 2), 'p2': (segundos, 1), 'info1': '1° Grupo C', 'info2': '2° Grupo B'},
    {'p1': (primeros, 3), 'p2': (segundos, 0), 'info1': '1° Grupo D', 'info2': '2° Grupo A'},
]
```

Todas las categorías con 4 grupos quedan con los cruces correctos (A-D / B-C / C-B / D-A).
