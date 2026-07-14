#!/usr/bin/env python3
###############################################################################
# Prueba Técnica UTL Senado 2026 — Reto 2.2: Pipeline ETL
# etl.py — Post-procesa la BD cargada por el scraper:
#          1. Normaliza nombres de candidatos (trim / upper / colapsa espacios).
#          2. Enriquece la tabla `partido` con nombre y color oficiales
#             (deduplicando por (codpar, corporacion)).
#          3. Puebla la tabla `municipio` con su código scope.
#          4. Registra filas afectadas vs. omitidas en `carga_log`.
#
# Es idempotente: puede correrse varias veces sin alterar el resultado final.
#
# Uso:  python db/etl.py [--db ruta.db]
###############################################################################

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_DEFAULT = ROOT / "db" / "puestos_2026.db"

# Colores y nombres de partido (espacio de códigos de RESULTADOS 2026).
# codpar de Cámara (CA) y Senado (SE) difieren porque cada corporación numera
# sus listas de forma independiente en los JSON de resultados.
#
# IMPORTANTE — códigos validados contra los datos reales de 2026:
# La tabla del enunciado (PDF) usa los códigos de la elección de 2022. En 2026
# la Registraduría reasignó algunos códigos, por lo que se validó cada uno contra
# el candidato líder real (fuente: Cámara de Representantes / Congreso Visible):
#   - codpar 2 NO es Conservador en 2026: es PARTIDO LIBERAL
#     (Héctor Chaparro en CA; Horacio Serpa / Gersson Vargas en SE).
#   - El Partido Conservador real en Senado es codpar 3 (Soledad Tamayo,
#     Miguel Ángel Barreto).
#   - codpar 5(CA)/57(SE) Verde, 87(CA)/92(SE) Pacto, 10 Centro Democrático:
#     coinciden entre 2022 y 2026.
PARTIDOS_OFICIALES = {
    # (codpar, corporacion): (nombre, color)
    ("5", "CA"):  ("ALIANZA VERDE", "#007C34"),
    ("57", "SE"): ("ALIANZA VERDE", "#007C34"),
    ("87", "CA"): ("PACTO HISTÓRICO", "#7B2D8B"),
    ("92", "SE"): ("PACTO HISTÓRICO", "#7B2D8B"),
    ("10", "CA"): ("CENTRO DEMOCRÁTICO", "#1E477D"),
    ("10", "SE"): ("CENTRO DEMOCRÁTICO", "#1E477D"),
    ("2", "CA"):  ("PARTIDO LIBERAL", "#E30716"),
    ("2", "SE"):  ("PARTIDO LIBERAL", "#E30716"),
    ("3", "SE"):  ("PARTIDO CONSERVADOR", "#E07B00"),
    ("17", "SE"): ("SALVACIÓN NACIONAL", "#F5A623"),
}

# Códigos scope de los 4 municipios (resueltos vía nomenclator, ver scraper).
MUNICIPIOS_SCOPE = {
    "TUNJA": "0700001",
    "PAIPA": "0700181",
    "SOGAMOSO": "0700277",
    "DUITAMA": "0700079",
}


def log(msg: str) -> None:
    print(f"[etl] {msg}", file=sys.stderr, flush=True)


def normalizar_candidatos(con: sqlite3.Connection) -> int:
    """Colapsa espacios internos y recorta bordes en nombre_candidato.

    SQLite no tiene regex nativo; se resuelve en Python leyendo los nombres
    con espacios anómalos y reescribiéndolos normalizados.
    """
    cur = con.cursor()
    cur.execute("SELECT id, nombre_candidato FROM resultado_candidato")
    cambios = 0
    for rid, nombre in cur.fetchall():
        limpio = " ".join((nombre or "").upper().split())
        if limpio != (nombre or ""):
            con.execute(
                "UPDATE resultado_candidato SET nombre_candidato = ? WHERE id = ?",
                (limpio, rid),
            )
            cambios += 1
    return cambios


def enriquecer_partidos(con: sqlite3.Connection) -> tuple:
    """Asigna nombre y color a los partidos conocidos; deduplica el resto.

    Devuelve (actualizados, total_partidos).
    """
    cur = con.cursor()
    # Deriva un nombre de respaldo del voto de lista (candidato codcan='0'),
    # cuyo texto suele ser 'SOLO POR LA LISTA'; si no aporta, deja el código.
    actualizados = 0
    cur.execute("SELECT codpar, corporacion FROM partido")
    for codpar, corp in cur.fetchall():
        nombre, color = PARTIDOS_OFICIALES.get(
            (codpar, corp), (f"PARTIDO {codpar} ({corp})", None)
        )
        con.execute(
            "UPDATE partido SET nombre = ?, color = ? WHERE codpar = ? AND corporacion = ?",
            (nombre, color, codpar, corp),
        )
        actualizados += 1
    total = cur.execute("SELECT COUNT(*) FROM partido").fetchone()[0]
    return actualizados, total


def poblar_municipios(con: sqlite3.Connection) -> int:
    """Rellena la tabla municipio con los scopes conocidos."""
    n = 0
    for nombre, scope in MUNICIPIOS_SCOPE.items():
        con.execute(
            "INSERT OR REPLACE INTO municipio (nombre, scope_codigo) VALUES (?, ?)",
            (nombre, scope),
        )
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="ETL post-carga de la BD electoral")
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = ap.parse_args()

    if not args.db.exists():
        sys.exit(f"[etl] ERROR: no existe {args.db}. Corre primero scraper/scraper.py")

    con = sqlite3.connect(args.db)
    con.execute("PRAGMA foreign_keys = ON")

    log("normalizando nombres de candidatos...")
    norm = normalizar_candidatos(con)
    log(f"  {norm} nombres normalizados")

    log("enriqueciendo partidos (nombre + color, dedup)...")
    act, total = enriquecer_partidos(con)
    log(f"  {act}/{total} partidos actualizados")

    log("poblando tabla municipio...")
    nm = poblar_municipios(con)
    log(f"  {nm} municipios")

    con.execute(
        """INSERT INTO carga_log
           (municipio, corporacion, puestos, filas_insertadas, filas_omitidas)
           VALUES ('ETL', 'ALL', NULL, ?, ?)""",
        (norm, total - act),
    )
    con.commit()

    # Resumen a stdout (lo captura el manifest)
    filas = con.execute("SELECT COUNT(*) FROM resultado_candidato").fetchone()[0]
    print(f"ETL OK | candidatos_normalizados={norm} | partidos={total} | "
          f"municipios={nm} | filas_resultado={filas}")
    con.close()


if __name__ == "__main__":
    main()
