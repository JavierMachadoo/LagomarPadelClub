"""
Helpers de proyección para templates Jinja2.

Contienen lógica de transformación de datos del dominio al formato
esperado por los templates de renderizado server-side. Se mantienen
separados de utils/calendario_finales_builder.py (que gestiona lógica
de calendarios) para no mezclar responsabilidades.
"""

from typing import Optional, List, Tuple

from utils.calendario_finales_builder import _resolver_ganador_nombre


def build_franjas_finales(calendario: Optional[dict], fixtures: Optional[dict] = None) -> List[Tuple]:
    """Convierte el calendario persistido en lista de (hora, partido_c1, partido_c2).

    Diseñado para renderizar el panel de finales en Jinja2 con la misma
    estética que la fase de grupos. Si se pasa `fixtures`, enriquece cada
    slot con `sets`, `ganador` y `ganador_nombre` matcheando por `partido_id`.

    Args:
        calendario: calendario_finales (cancha_1, cancha_2, sin_asignar)
        fixtures:   fixtures_finales — {categoria: fixture_dict} — opcional.
                    Sin este param, los slots se devuelven sin enriquecer
                    (backward-compat con call-sites que no pasan fixtures).

    Returns:
        Lista de tuplas (hora_str, slot_c1_o_None, slot_c2_o_None)
        ordenadas cronológicamente.
    """
    if not calendario:
        return []

    # Construir índice partido_id → partido_dict
    partido_index: dict = {}
    if fixtures:
        for cat, fixture in fixtures.items():
            if not fixture:
                continue
            for fase_key in ['octavos', 'cuartos', 'semifinales']:
                for partido in fixture.get(fase_key, []):
                    if partido and partido.get('id'):
                        partido_index[partido['id']] = partido
            final = fixture.get('final')
            if final and final.get('id'):
                partido_index[final['id']] = final

    def _enriquecer(slot: Optional[dict]) -> Optional[dict]:
        if not slot:
            return slot
        pid = slot.get('partido_id')
        if pid and pid in partido_index:
            partido = partido_index[pid]
            slot['sets'] = partido.get('sets', [])
            ganador_dict = partido.get('ganador')
            slot['ganador'] = ganador_dict
            slot['ganador_nombre'] = _resolver_ganador_nombre(partido, ganador_dict)
        return slot

    por_hora: dict = {}
    for p in calendario.get('cancha_1', []):
        por_hora.setdefault(p['hora_inicio'], [None, None])[0] = _enriquecer(p)
    for p in calendario.get('cancha_2', []):
        por_hora.setdefault(p['hora_inicio'], [None, None])[1] = _enriquecer(p)

    return [(h, slots[0], slots[1]) for h, slots in sorted(por_hora.items())]
