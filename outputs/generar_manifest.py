#!/usr/bin/env python3
###############################################################################
# Prueba Técnica UTL Senado 2026 — Manifiesto de evaluación
# generar_manifest.py — Valida el pipeline y captura los resultados de los
#                       retos automáticamente en evaluation_manifest.json.
#
# El evaluador ejecuta:  python outputs/generar_manifest.py
# Debe imprimir "4/4 municipios" y "SQL OK" para los 3 retos.
#
# Uso:  python outputs/generar_manifest.py [--db ruta.db]
###############################################################################

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# META — editar antes de entregar (checklist Paso 2 de la prueba)
# --------------------------------------------------------------------------- #
META = {
    "candidato": "GRIJALBA",
    "email": "PENDIENTE@correo.com",
    "repo_url": "https://github.com/pachogrijalba90/grijalba_prueba_utl_2026",
}

ROOT = Path(__file__).resolve().parent.parent
DB_DEFAULT = ROOT / "db" / "puestos_2026.db"
SQL_DIR = ROOT / "sql"
OUT_JSON = ROOT / "outputs" / "evaluation_manifest.json"

MUNICIPIOS_ESPERADOS = ["TUNJA", "PAIPA", "SOGAMOSO", "DUITAMA"]


def q(con, sql, params=()):
    return con.execute(sql, params).fetchall()


def correr_sql(con, archivo: Path) -> dict:
    """Ejecuta un .sql y devuelve estado + primeras filas + nº de filas."""
    if not archivo.exists():
        return {"status": "ERROR", "error": f"no existe {archivo.name}", "rows": []}
    try:
        cur = con.cursor()
        cur.execute("BEGIN")
        rows = cur.execute(archivo.read_text(encoding="utf-8")).fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        con.rollback()  # las queries del reto 3 son de solo lectura
        muestras = [dict(zip(cols, r)) for r in rows[:5]]
        return {"status": "OK", "n_filas": len(rows), "columnas": cols,
                "muestra": muestras}
    except sqlite3.Error as exc:
        con.rollback()
        return {"status": "ERROR", "error": str(exc), "rows": []}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = ap.parse_args()

    if not args.db.exists():
        sys.exit(f"ERROR: no existe {args.db}. Corre scraper/scraper.py y db/etl.py primero.")

    con = sqlite3.connect(args.db)
    manifest = {"meta": META, "retos": {}}
    print("=" * 64)
    print(f"MANIFIESTO DE EVALUACIÓN — candidato: {META['candidato']}")
    print("=" * 64)

    # ---- Reto 1 + 2: extracción y BD -------------------------------------- #
    puestos = dict(q(con, """SELECT municipio, COUNT(DISTINCT puesto_codigo)
                             FROM resultado_candidato GROUP BY municipio"""))
    presentes = [m for m in MUNICIPIOS_ESPERADOS if m in puestos]
    n_ok = len(presentes)
    filas = q(con, "SELECT COUNT(*) FROM resultado_candidato")[0][0]
    n_part = q(con, "SELECT COUNT(*) FROM partido")[0][0]

    # líder de Senado (voto de lista, circunscripción nacional) por municipio
    lideres = {}
    for m in presentes:
        r = q(con, """SELECT codpar, SUM(votos_candidato) v FROM resultado_candidato
                      WHERE municipio=? AND corporacion='SE' AND circunscripcion='0'
                        AND codcan='0' GROUP BY codpar ORDER BY v DESC LIMIT 1""", (m,))
        if r:
            nombre = q(con, "SELECT nombre FROM partido WHERE codpar=? AND corporacion='SE'",
                       (r[0][0],))
            lideres[m] = {"codpar": r[0][0],
                          "partido": nombre[0][0] if nombre else None,
                          "votos_lista_se": r[0][1]}

    manifest["retos"]["reto_1_2"] = {
        "municipios_esperados": len(MUNICIPIOS_ESPERADOS),
        "municipios_presentes": n_ok,
        "puestos_por_municipio": puestos,
        "filas_resultado_candidato": filas,
        "partidos": n_part,
        "lider_se_por_municipio": lideres,
    }
    print(f"\n[Reto 1-2]  {n_ok}/{len(MUNICIPIOS_ESPERADOS)} municipios  "
          f"| {filas} filas | {n_part} partidos")
    for m in MUNICIPIOS_ESPERADOS:
        estado = f"{puestos.get(m,0)} puestos" if m in presentes else "AUSENTE"
        lid = lideres.get(m, {}).get("partido", "-")
        print(f"            {m:9s} {estado:12s} líder SE: {lid}")

    # ---- Reto 3: las 3 queries -------------------------------------------- #
    print("\n[Reto 3]  Ejecutando queries SQL...")
    todo_ok = True
    for tarea in ["tarea_3_1", "tarea_3_2", "tarea_3_3"]:
        res = correr_sql(con, SQL_DIR / f"{tarea}.sql")
        manifest["retos"][tarea] = res
        estado = res["status"]
        todo_ok = todo_ok and estado == "OK"
        detalle = f"{res['n_filas']} filas" if estado == "OK" else res.get("error", "")
        print(f"            {tarea}: SQL {estado}  ({detalle})")

    con.close()

    # ---- Veredicto -------------------------------------------------------- #
    manifest["veredicto"] = {
        "municipios": f"{n_ok}/{len(MUNICIPIOS_ESPERADOS)}",
        "sql_ok": todo_ok,
    }
    OUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print("\n" + "=" * 64)
    print(f"RESULTADO: {n_ok}/4 municipios | SQL {'OK' if todo_ok else 'CON ERRORES'}")
    print(f"Manifiesto escrito en {OUT_JSON.relative_to(ROOT)}")
    print("=" * 64)

    if n_ok < 3 or not todo_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
