#!/usr/bin/env python3
"""
Copia tablas clave de prod → dev para testing local.

Tablas copiadas (en orden por FK):
  1. jugadores      — para que import_ranking encuentre jugadores con cuenta
  2. torneos        — historial archivado (FK de puntos_jugador)
  3. torneo_actual  — estado del torneo activo
  4. grupos / parejas_grupo / partidos / partidos_finales

NO copia: inscripciones, invitacion_tokens, puntos_jugador
  - inscripciones: contiene jugador_id FK a auth.users de prod — no sirve en dev
  - puntos_jugador: es lo que vamos a CREAR en dev con import_ranking

Uso:
    python copy_prod_to_dev.py                    # copia todo
    python copy_prod_to_dev.py --solo-jugadores   # solo tabla jugadores (más rápido)
    python copy_prod_to_dev.py --dry-run          # muestra cuántos registros hay, sin escribir
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()


# ── credenciales ──────────────────────────────────────────────────────────────

def get_prod_client():
    url = os.getenv("PROD_SUPABASE_URL", "").strip()
    key = os.getenv("PROD_SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print(
            "ERROR: Necesitás PROD_SUPABASE_URL y PROD_SUPABASE_SERVICE_ROLE_KEY.\n"
            "Podés setearlas temporalmente antes de correr el script:\n\n"
            "  PROD_SUPABASE_URL=https://... PROD_SUPABASE_SERVICE_ROLE_KEY=... "
            "python copy_prod_to_dev.py\n"
        )
        sys.exit(1)
    from supabase import create_client
    return create_client(url, key)


def get_dev_client():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("ERROR: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY no están en .env")
        sys.exit(1)
    from supabase import create_client
    return create_client(url, key)


# ── helpers ───────────────────────────────────────────────────────────────────

def fetch_all(client, table: str, select: str = "*") -> list[dict]:
    """Lee todos los registros de una tabla (paginado por si hay muchos)."""
    rows = []
    PAGE = 1000
    offset = 0
    while True:
        resp = (
            client.table(table)
            .select(select)
            .range(offset, offset + PAGE - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    return rows


def upsert_batch(client, table: str, rows: list[dict], conflict_col: str = "id"):
    """Upsert en lotes de 200 (límite seguro de Supabase)."""
    BATCH = 200
    for i in range(0, len(rows), BATCH):
        client.table(table).upsert(
            rows[i : i + BATCH],
            on_conflict=conflict_col,
        ).execute()


def copy_table(prod, dev, table: str, dry_run: bool, conflict_col: str = "id", select: str = "*"):
    rows = fetch_all(prod, table, select)
    print(f"  {table}: {len(rows)} registros", end="")
    if dry_run or not rows:
        print()
        return
    upsert_batch(dev, table, rows, conflict_col)
    print(" → copiados")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra cuántos registros hay, sin escribir")
    parser.add_argument("--solo-jugadores", action="store_true",
                        help="Copia solo la tabla jugadores (más rápido para probar import_ranking)")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN — no se escribe nada ===\n")

    print("Conectando a prod...")
    prod = get_prod_client()
    print("Conectando a dev...")
    dev = get_dev_client()

    print("\nLeyendo de prod y copiando a dev:\n")

    # Siempre copia jugadores (es el objetivo principal)
    copy_table(prod, dev, "jugadores", args.dry_run)

    if not args.solo_jugadores:
        # torneos antes que los hijos (grupos, partidos_finales, puntos_jugador)
        copy_table(prod, dev, "torneos", args.dry_run)
        copy_table(prod, dev, "torneo_actual", args.dry_run, conflict_col="id")
        copy_table(prod, dev, "grupos", args.dry_run)

        # parejas_grupo tiene PK compuesta (grupo_id, nombre)
        rows_pg = fetch_all(prod, "parejas_grupo")
        print(f"  parejas_grupo: {len(rows_pg)} registros", end="")
        if not args.dry_run and rows_pg:
            BATCH = 200
            for i in range(0, len(rows_pg), BATCH):
                dev.table("parejas_grupo").upsert(
                    rows_pg[i : i + BATCH],
                    on_conflict="grupo_id,nombre",
                ).execute()
            print(" → copiados")
        else:
            print()

        copy_table(prod, dev, "partidos", args.dry_run)
        copy_table(prod, dev, "partidos_finales", args.dry_run)

    print("\n=== Listo ===")
    if args.dry_run:
        print("Corré sin --dry-run para aplicar los cambios.")
    else:
        print("Dev actualizado. Ahora podés correr:")
        print("  python import_ranking_baseline.py --dry-run")


if __name__ == "__main__":
    main()
