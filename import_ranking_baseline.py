#!/usr/bin/env python3
"""
Importación del ranking histórico acumulado hasta Abril 2026.

Qué hace:
  1. Crea un torneo "Historial Acumulado 2026" en la tabla torneos (idempotente).
  2. Por cada jugador, busca en la tabla `jugadores` por nombre+apellido.
     - Si existe: reutiliza su id (preserva el link a usuario si lo tiene).
     - Si no existe: lo crea.
  3. Inserta en `puntos_jugador` (UPSERT — seguro de correr más de una vez).

Requisito previo: crear la tabla `puntos_jugador` en Supabase con el SQL
del final de supabase_schema.sql.

Uso:
    python import_ranking_baseline.py          # modo real
    python import_ranking_baseline.py --dry-run  # solo muestra qué haría
"""

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── setup path ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

# ── datos del ranking ─────────────────────────────────────────────────────────
# Formato: (nombre, apellido, categoria, puntos)
# Nombres tal como aparecen en el Excel — el script los normaliza para buscar.
# Categorías usan el nombre canónico del sistema (con tilde).
RANKING_DATA = [
    # === TERCERA ===
    ("DIEGO",     "VIOTTI",       "Tercera", 250),
    ("FEDE",      "NODAR",        "Tercera", 250),
    ("FEFO",      "ARUS",         "Tercera", 250),
    ("RODRIGO",   "ARUS",         "Tercera", 250),
    ("SANTI",     "NIEVA",        "Tercera", 250),
    ("VICTOR",    "LICANDRO",     "Tercera", 250),
    ("Hernán",    "Gyalog",       "Tercera", 185),
    ("Maximo",    "Licandro",     "Tercera", 175),
    ("Nicolas",   "Silvera",      "Tercera", 175),
    ("Rodrigo",   "Franco",       "Tercera", 175),
    ("DEMETRIO",  "FERREIRA",     "Tercera", 150),
    ("JOAQUIN",   "OLIVEIRA",     "Tercera", 150),
    ("MATEO",     "CARENA",       "Tercera", 135),
    ("FRAN",      "DI LAVELLO",   "Tercera", 110),
    ("MARTIN",    "ALCALA",       "Tercera", 100),
    ("PANCHO",    "LEBBRONI",     "Tercera", 100),
    ("MARCELO",   "CARRO",        "Tercera", 75),
    ("NACHO",     "NOVELLE",      "Tercera", 75),
    ("FACUNDO",   "LUQUE",        "Tercera", 70),
    ("DIEGO",     "SACARELLO",    "Tercera", 35),
    ("EMANUEL",   "FERREIRA",     "Tercera", 35),
    ("LUCAS",     "LABANDERA",    "Tercera", 35),
    ("MANUEL",    "IPAR",         "Tercera", 35),
    ("TOMAS",     "GONZALEZ",     "Tercera", 35),
    ("RODRIGO",   "ARCE",         "Tercera", 35),

    # === CUARTA ===
    ("Enrique",     "Fraga",        "Cuarta", 500),
    ("DEMETRIO",    "FERREIRA",     "Cuarta", 500),
    ("Maximo",      "Licandro",     "Cuarta", 175),
    ("JOAQUIN",     "OLIVEIRA",     "Cuarta", 175),
    ("ALFONSO",     "ODRIOZOLA",    "Cuarta", 175),
    ("DIEGO",       "LEIROS",       "Cuarta", 175),
    ("FRAN",        "DI LAVELLO",   "Cuarta", 150),
    ("MATEO",       "CARENA",       "Cuarta", 150),
    ("Nicolás",     "Martínez",     "Cuarta", 150),
    ("LUCAS",       "LABANDERA",    "Cuarta", 150),
    ("Facundo",     "Spira",        "Cuarta", 150),
    ("Hernán",      "Gyalog",       "Cuarta", 150),
    ("MATEO",       "IGUINI",       "Cuarta", 150),
    ("RODRIGO",     "FRANCO",       "Cuarta", 135),
    ("ALBERTO",     "VAZQUEZ",      "Cuarta", 110),
    ("FABRIZZIO",   "OVIEDO",       "Cuarta", 110),
    ("FACUNDO",     "LUQUE",        "Cuarta", 110),
    ("RODRIGO",     "LUCERO",       "Cuarta", 100),
    ("MARCELO",     "MARTELLOTA",   "Cuarta", 100),
    ("FABRIZIO",    "PERINI",       "Cuarta", 100),
    ("GONZALO",     "TAGLIAFICO",   "Cuarta", 75),
    ("JUAN PABLO",  "REGUEIRA",     "Cuarta", 75),
    ("Alejandro",   "Vazquez",      "Cuarta", 75),
    ("LUCAS",       "VIATRI",       "Cuarta", 70),
    ("NICOLAS",     "MIÑON",        "Cuarta", 35),
    ("MARCELO",     "CARRO",        "Cuarta", 35),
    ("MARTIN",      "ORTIZ",        "Cuarta", 35),
    ("RODRIGO",     "OVIEDO",       "Cuarta", 35),
    ("SCHUBERT",    "",             "Cuarta", 35),  # solo apellido
    ("LEO",         "MACHADO",      "Cuarta", 35),
    ("AUGUSTO",     "BACCINO",      "Cuarta", 35),
    ("MICHAEL",     "DOSSI",        "Cuarta", 35),
    ("JULIO",       "SILVERA",      "Cuarta", 35),
    ("NICOLAS",     "FRAGA",        "Cuarta", 35),

    # === QUINTA ===
    ("MATEO",        "IGUINI",      "Quinta", 325),
    ("ALBERTO",      "VAZQUEZ",     "Quinta", 250),
    ("LEONARDO",     "MACHADO",     "Quinta", 250),
    ("DAMIAN",       "GERONA",      "Quinta", 250),
    ("RODRIGO",      "OVIEDO",      "Quinta", 225),
    ("MARTIN",       "ORTIZ",       "Quinta", 225),
    ("JOSE",         "MIQUEIRO",    "Quinta", 175),
    ("PABLO",        "ANDRADE",     "Quinta", 175),
    ("Nicolás",      "Martínez",    "Quinta", 150),
    ("JUAN PABLO",   "REGUEIRA",    "Quinta", 150),
    ("DANIEL",       "CARDOZO",     "Quinta", 150),
    ("SCHUBERT",     "",            "Quinta", 110),
    ("Alejandro",    "Vazquez",     "Quinta", 110),
    ("AUGUSTO",      "BACCINO",     "Quinta", 110),
    ("IGNACIO",      "PORRAS",      "Quinta", 110),
    ("LUCAS",        "VIATRI",      "Quinta", 110),
    ("GONZALO",      "TAGLIAFICO",  "Quinta", 110),
    ("ANDRES",       "SALORT",      "Quinta", 100),
    ("ESTEBAN",      "PAREDEZ",     "Quinta", 100),
    ("MARCELO",      "RUBINI",      "Quinta", 100),
    ("MAXIMILIANO",  "SICA",        "Quinta", 100),
    ("LUCAS",        "LABANDERA",   "Quinta", 100),
    ("FACUNDO",      "MOURA",       "Quinta", 100),
    ("SEBA",         "SILVA",       "Quinta", 75),
    ("MAURICIO",     "SILVERA",     "Quinta", 75),
    ("MARCELO",      "PARDO",       "Quinta", 75),
    ("ENZO",         "VEGA",        "Quinta", 70),
    ("ENZO",         "SABOREDO",    "Quinta", 70),
    ("GABRIEL",      "CACERES",     "Quinta", 35),
    ("RODRIGO",      "HARISPE",     "Quinta", 35),
    ("DANIEL",       "FEDORZCUCK",  "Quinta", 35),
    ("DIEGO",        "ACOSTA",      "Quinta", 35),
    ("JAVIER",       "MACHADO",     "Quinta", 35),
    ("MATIAS",       "PORRAS",      "Quinta", 35),

    # === SEXTA ===
    ("ENZO",       "VEGA",         "Sexta", 250),
    ("IGNACIO",    "PORRAS",       "Sexta", 250),
    ("Gonza",      "Olivera",      "Sexta", 250),
    ("MATIAS",     "VIERA",        "Sexta", 250),
    ("SANTIAGO",   "OLIVERA",      "Sexta", 250),
    ("BRUNO",      "GUIGOU",       "Sexta", 250),
    ("FEDERICO",   "LAMAS",        "Sexta", 225),
    ("LUCAS",      "JAUREGUI",     "Sexta", 225),
    ("JAVIER",     "MACHADO",      "Sexta", 175),
    ("FACUNDO",    "SILVA",        "Sexta", 135),
    ("ALDO",       "MAZZA",        "Sexta", 125),
    ("JONA",       "FERRI",        "Sexta", 125),
    ("AGUSTIN",    "BONILLA",      "Sexta", 110),
    ("Agustín",    "Torena",       "Sexta", 110),
    ("FERNANDO",   "FAGALDES",     "Sexta", 110),
    ("SEBASTIAN",  "SILVA",        "Sexta", 100),
    ("JOAQUIN",    "GONZALEZ",     "Sexta", 100),
    ("DIEGO",      "BORGES",       "Sexta", 100),
    ("GABY",       "REGALADO",     "Sexta", 85),
    ("JUAN",       "FRAGA",        "Sexta", 85),
    ("BAUTI",      "DI LAVELLO",   "Sexta", 75),
    ("SEBASTIAN",  "ALVAREZ",      "Sexta", 75),
    ("NICOLAS",    "ROMAY",        "Sexta", 75),
    ("FERNANDO",   "PIGNATTA",     "Sexta", 75),
    ("NICOLAS",    "CABRERA",      "Sexta", 75),
    ("FACUNDO",    "ROSANO",       "Sexta", 75),
    ("LORENZO",    "SILVERA",      "Sexta", 75),
    ("WILLY",      "",             "Sexta", 75),   # solo apodo
    ("MATHIAS",    "HARTWICH",     "Sexta", 70),
    ("NICOLAS",    "DIAZ",         "Sexta", 35),
    ("MATIAS",     "BARENCHI",     "Sexta", 35),
    ("CARLOS",     "FAGALDES",     "Sexta", 35),
    ("DIEGO",      "ACOSTA",       "Sexta", 35),
    ("FERNANDO",   "EMED",         "Sexta", 35),
    ("NICOLAS",    "HERNANDEZ",    "Sexta", 35),
    ("MARIO",      "LARROSA",      "Sexta", 35),
    ("PEDRO",      "",             "Sexta", 35),   # solo nombre

    # === SÉPTIMA ===
    ("Gonza",       "Olivera",      "Séptima", 500),
    ("SEBASTIAN",   "ORDEIX",       "Séptima", 250),
    ("LU",          "RAZQUIN",      "Séptima", 250),
    ("GABY",        "REGALADO",     "Séptima", 225),
    ("JONA",        "FERRI",        "Séptima", 175),
    ("ALEJANDRO",   "BENTANCOUR",   "Séptima", 150),
    ("GUZI",        "",             "Séptima", 150),  # solo apodo
    ("MONE",        "",             "Séptima", 150),  # solo apodo
    ("SERGIO",      "RIOLFO",       "Séptima", 110),
    ("FERNANDO",    "ROLDAN",       "Séptima", 110),
    ("NICOLAS",     "CABRERA",      "Séptima", 100),
    ("GABRIEL",     "FERNANDEZ",    "Séptima", 100),
    ("MARIO",       "LARROSA",      "Séptima", 100),
    ("VALERIA",     "ALMADA",       "Séptima", 100),
    ("GONZALO",     "COLLA",        "Séptima", 100),
    ("PETER",       "WIBERG",       "Séptima", 100),
    ("ALE",         "BENTANCOUR",   "Séptima", 75),
    ("ALDO",        "MAZZA",        "Séptima", 75),
    ("MAGDA",       "MOREIRA",      "Séptima", 75),
    ("NICO",        "DIAZ",         "Séptima", 75),
    ("LUCAS",       "BARENCHI",     "Séptima", 75),
    ("IGNACIO",     "PACHECO",      "Séptima", 75),
    ("GONZALO",     "PACHECO",      "Séptima", 75),
    ("DAPHNE",      "MONZA",        "Séptima", 75),
    ("GUILLERMO",   "GAETAN",       "Séptima", 75),
    ("DIEGO",       "ACOSTA",       "Séptima", 75),
    ("EDU",         "LAGOS",        "Séptima", 75),
    ("RICARDO",     "GARCIA",       "Séptima", 70),
    ("INDI",        "BEUX",         "Séptima", 35),
    ("ANDRES",      "CURA",         "Séptima", 35),
    ("NICOLAS",     "ROMAY",        "Séptima", 35),  # "NICOLASROMAY" en el Excel — corregido
    ("JAVIER",      "MACHIN",       "Séptima", 35),
    ("TANO",        "ABADIE",       "Séptima", 35),
    ("EMI",         "FERNANDEZ",    "Séptima", 35),
    ("JUANI",       "SANTIAGO",     "Séptima", 35),
    ("PABLO",       "BEUX",         "Séptima", 35),
    ("JOHNNATAN",   "RODRIGUEZ",    "Séptima", 35),
    ("SILVANA",     "SEIBANE",      "Séptima", 35),

    # === OCTAVA ===
    ("DANIEL",    "VEGA",       "Octava", 250),
    ("GABRIEL",   "NOBLE",      "Octava", 250),
    ("CATALINA",  "QUIROZ",     "Octava", 150),
    ("LEO",       "REPETTO",    "Octava", 150),
    ("MATEO",     "FRAGA",      "Octava", 100),
    ("M. NOEL",   "CERVASIO",   "Octava", 100),
    ("ANDREA",    "CENDON",     "Octava", 100),
    ("LETICIA",   "PEREZ",      "Octava", 100),
    ("FRANCO",    "MATTOS",     "Octava", 35),
    ("JOAQUIN",   "CERIZOLA",   "Octava", 35),
    ("LORE",      "SENORIS",    "Octava", 35),
    ("KARINA",    "DE SOUZA",   "Octava", 35),
]

TORNEO_HISTORICO_NOMBRE = "Historial Acumulado 2026"


def get_supabase():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
           or os.getenv("SUPABASE_ANON_KEY", "").strip())
    if not url or not key:
        print("ERROR: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY deben estar en .env")
        sys.exit(1)
    from supabase import create_client
    return create_client(url, key)


def get_or_create_torneo_historico(sb, dry_run: bool) -> str:
    resp = (
        sb.table("torneos")
        .select("id")
        .eq("nombre", TORNEO_HISTORICO_NOMBRE)
        .execute()
    )
    if resp.data:
        torneo_id = resp.data[0]["id"]
        print(f"  torneo histórico ya existe: {torneo_id}")
        return torneo_id

    torneo_id = str(uuid.uuid4())
    print(f"  creando torneo histórico '{TORNEO_HISTORICO_NOMBRE}' → {torneo_id}")
    if not dry_run:
        sb.table("torneos").insert({
            "id": torneo_id,
            "nombre": TORNEO_HISTORICO_NOMBRE,
            "tipo": "historico",
            "estado": "finalizado",
            "created_at": datetime(2026, 4, 30, tzinfo=timezone.utc).isoformat(),
        }).execute()
    return torneo_id


def find_jugador(sb, nombre: str, apellido: str) -> dict | None:
    """Busca jugador case-insensitive por nombre+apellido."""
    resp = (
        sb.table("jugadores")
        .select("id, nombre, apellido, usuario_id")
        .ilike("nombre", nombre)
        .ilike("apellido", apellido if apellido else "")
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def create_jugador(sb, nombre: str, apellido: str, dry_run: bool) -> str:
    jugador_id = str(uuid.uuid4())
    if not dry_run:
        sb.table("jugadores").insert({
            "id": jugador_id,
            "nombre": nombre.title(),
            "apellido": apellido.title() if apellido else "",
            "activo": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    return jugador_id


def upsert_puntos(sb, jugador_id: str, torneo_id: str,
                  categoria: str, puntos: int, dry_run: bool):
    if not dry_run:
        sb.table("puntos_jugador").upsert({
            "jugador_id": jugador_id,
            "torneo_id": torneo_id,
            "categoria": categoria,
            "puntos": puntos,
            "concepto": "serie",
        }, on_conflict="jugador_id,torneo_id,categoria").execute()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra qué haría sin escribir nada")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN — no se escribe nada ===\n")

    sb = get_supabase()

    print("1. Torneo histórico")
    torneo_id = get_or_create_torneo_historico(sb, args.dry_run)

    print("\n2. Procesando jugadores y puntos")
    creados = 0
    reutilizados = 0
    puntos_insertados = 0

    for nombre, apellido, categoria, puntos in RANKING_DATA:
        jugador = find_jugador(sb, nombre, apellido)

        if jugador:
            jugador_id = jugador["id"]
            tiene_usuario = "✓ usuario vinculado" if jugador.get("usuario_id") else ""
            print(f"  [{categoria}] {nombre} {apellido} → reutiliza {jugador_id[:8]}... {tiene_usuario}")
            reutilizados += 1
        else:
            jugador_id = create_jugador(sb, nombre, apellido, args.dry_run)
            print(f"  [{categoria}] {nombre} {apellido} → CREADO {jugador_id[:8]}...")
            creados += 1

        upsert_puntos(sb, jugador_id, torneo_id, categoria, puntos, args.dry_run)
        puntos_insertados += 1

    print(f"\n=== Resumen ===")
    print(f"  Jugadores reutilizados: {reutilizados}")
    print(f"  Jugadores creados:      {creados}")
    print(f"  Filas puntos_jugador:   {puntos_insertados}")
    if args.dry_run:
        print("\n  (nada fue escrito — corré sin --dry-run para aplicar)")


if __name__ == "__main__":
    main()
