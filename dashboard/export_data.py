#!/usr/bin/env python3
###############################################################################
# Prueba Técnica UTL Senado 2026 — Reto 4: Dashboard
# export_data.py — Exporta de la BD el JSON que consume dashboard/index.html.
#
# Genera dashboard/data.json con 3 bloques:
#   comparativo    — votos válidos CA totales por municipio
#   por_municipio  — top 10 candidatos CA + partido líder SE, por municipio
#   arrastre       — ratio Verde SE/CA por puesto, por municipio (línea ref 1.0)
#
# Output: dashboard/data.json
###############################################################################

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "puestos_2026.db"
OUT = ROOT / "dashboard" / "data.json"

MUNICIPIOS = ["TUNJA", "DUITAMA", "SOGAMOSO", "PAIPA"]
COLOR_PARTIDO = {  # colores por partido (nombre normalizado; validado con datos 2026)
    "ALIANZA VERDE": "#007C34", "PACTO HISTÓRICO": "#7B2D8B",
    "CENTRO DEMOCRÁTICO": "#1E477D", "PARTIDO CONSERVADOR": "#E07B00",
    "PARTIDO LIBERAL": "#E30716", "SALVACIÓN NACIONAL": "#F5A623",
}


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # --- Comparativo: total votos CA por municipio ------------------------- #
    comparativo = [
        {"municipio": m.title(),
         "votos_ca": con.execute(
             "SELECT COALESCE(SUM(votos_candidato),0) FROM resultado_candidato "
             "WHERE corporacion='CA' AND municipio=?", (m,)).fetchone()[0]}
        for m in MUNICIPIOS
    ]

    # --- Por municipio: top 10 candidatos CA + líder SE -------------------- #
    por_municipio = {}
    for m in MUNICIPIOS:
        top = con.execute(
            """SELECT nombre_candidato, codpar, SUM(votos_candidato) v
               FROM resultado_candidato
               WHERE corporacion='CA' AND codcan<>'0' AND municipio=? AND cedula<>''
               GROUP BY cedula ORDER BY v DESC LIMIT 10""", (m,)).fetchall()
        lider = con.execute(
            """SELECT p.nombre, SUM(r.votos_candidato) v
               FROM resultado_candidato r
               LEFT JOIN partido p ON p.codpar=r.codpar AND p.corporacion='SE'
               WHERE r.corporacion='SE' AND r.circunscripcion='0'
                 AND r.codcan='0' AND r.municipio=?
               GROUP BY r.codpar ORDER BY v DESC LIMIT 1""", (m,)).fetchone()
        por_municipio[m.title()] = {
            "top_ca": [{"nombre": r["nombre_candidato"].title(),
                        "votos": r["v"], "codpar": r["codpar"]} for r in top],
            "lider_se": {"partido": lider["nombre"], "votos": lider["v"]},
        }

    # --- Arrastre Verde SE/CA por puesto ----------------------------------- #
    arrastre = {}
    for m in MUNICIPIOS:
        filas = con.execute(
            """
            WITH ca AS (SELECT puesto_codigo, puesto_nombre, SUM(votos_candidato) v
                        FROM resultado_candidato
                        WHERE corporacion='CA' AND codpar='5' AND codcan='0' AND municipio=?
                        GROUP BY puesto_codigo),
                 se AS (SELECT puesto_codigo, SUM(votos_candidato) v
                        FROM resultado_candidato
                        WHERE corporacion='SE' AND codpar='57' AND codcan='0' AND municipio=?
                        GROUP BY puesto_codigo)
            SELECT ca.puesto_nombre, ca.v ca_v, COALESCE(se.v,0) se_v
            FROM ca LEFT JOIN se ON ca.puesto_codigo=se.puesto_codigo
            WHERE ca.v > 0 ORDER BY ca.puesto_nombre
            """, (m, m)).fetchall()
        arrastre[m.title()] = [
            {"puesto": r["puesto_nombre"], "ca": r["ca_v"], "se": r["se_v"],
             "ratio": round(r["se_v"] / r["ca_v"], 3) if r["ca_v"] else None}
            for r in filas
        ]

    con.close()
    data = {
        "colores_partido": COLOR_PARTIDO,
        "comparativo": comparativo,
        "por_municipio": por_municipio,
        "arrastre": arrastre,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    OUT.write_text(payload, encoding="utf-8")

    # Inyecta los datos en index.html entre los marcadores DATA_START/DATA_END
    # para que el dashboard abra con file:// sin bloqueo CORS de fetch().
    # Idempotente: reemplaza siempre lo que haya entre los marcadores.
    import re
    html_path = ROOT / "dashboard" / "index.html"
    if html_path.exists():
        html = html_path.read_text(encoding="utf-8")
        nuevo, n = re.subn(
            r"/\*DATA_START\*/.*?/\*DATA_END\*/",
            f"/*DATA_START*/{payload}/*DATA_END*/",
            html, count=1, flags=re.DOTALL)
        if n:
            html_path.write_text(nuevo, encoding="utf-8")
            print("  datos inyectados en index.html")

    print(f"data.json escrito ({OUT}) | municipios={len(MUNICIPIOS)} | "
          f"puestos_arrastre={sum(len(v) for v in arrastre.values())}")


if __name__ == "__main__":
    main()
