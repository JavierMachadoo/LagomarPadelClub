"""
Helpers compartidos para el flujo de autenticación de jugadores.
Usados por api/routes/auth_jugador.py y main.py (callback).
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def auto_aceptar_invitacion_post_registro(sb, token: str, jugador_id: str, nombre_jugador: str) -> None:
    """Auto-acepta una invitación pendiente tras confirmación de email.
    Fire-and-forget: no debe bloquear el flujo principal."""
    token_resp = (sb.table('invitacion_tokens')
                  .select('inscripcion_id, expira_at, usado')
                  .eq('token', token)
                  .execute())

    if not token_resp.data:
        return

    token_data = token_resp.data[0]
    if token_data['usado']:
        return

    expira = datetime.fromisoformat(token_data['expira_at'].replace('Z', '+00:00'))
    if datetime.now(timezone.utc) > expira:
        return

    ins_resp = (sb.table('inscripciones')
                .select('*')
                .eq('id', token_data['inscripcion_id'])
                .eq('estado', 'pendiente_companero')
                .execute())

    if not ins_resp.data:
        return

    inscripcion = ins_resp.data[0]

    if inscripcion['jugador_id'] == jugador_id:
        return

    if inscripcion.get('jugador2_id') and inscripcion['jugador2_id'] != jugador_id:
        return

    sb.table('inscripciones').update({
        'jugador2_id': jugador_id,
        'integrante2': nombre_jugador,
        'estado':      'confirmado',
    }).eq('id', inscripcion['id']).execute()

    sb.table('invitacion_tokens').update({'usado': True}).eq('token', token).execute()


def crear_perfil_jugador(sb_admin, user_id: str, nombre: str, apellido: str, telefono: str | None) -> None:
    """Inserta el perfil en `jugadores` si todavía no existe."""
    existing = sb_admin.table('jugadores').select('id, usuario_id').eq('id', user_id).execute()
    if existing.data:
        if not existing.data[0].get('usuario_id'):
            sb_admin.table('jugadores').update({'usuario_id': user_id}).eq('id', user_id).execute()
            logger.info('usuario_id parcheado para jugador %s', user_id)
        return
    sb_admin.table('jugadores').insert({
        'id':         user_id,
        'usuario_id': user_id,
        'nombre':     nombre,
        'apellido':   apellido,
        'telefono':   telefono or None,
    }).execute()
    logger.info('Perfil creado para jugador %s', user_id)
