#!/usr/bin/env python3
###############################################################################
# Prueba Técnica UTL Senado 2026 — Reto 5.1: Heatmap
# heatmap.py — Mapa de calor de los 8 candidatos con más votos a Cámara (CA),
#              columnas = 4 municipios, valores = % del total de votos CA de
#              ese municipio. Con anotaciones en cada celda.
#
# Output: viz/heatmap_municipios.png
###############################################################################

import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "puestos_2026.db"
OUT = ROOT / "viz" / "heatmap_municipios.png"

MUNICIPIOS = ["TUNJA", "DUITAMA", "SOGAMOSO", "PAIPA"]


def cargar_matriz():
    """Top 8 candidatos CA (por voto total) y su % del total CA por municipio."""
    con = sqlite3.connect(DB)

    # Total de votos CA por municipio (denominador del %): TODOS los votos a
    # Cámara del municipio (voto de lista + preferentes, todas las
    # circunscripciones). Usar solo el voto de lista subestima el total y puede
    # dar %>100 para candidatos de circunscripciones especiales.
    tot = dict(con.execute(
        """SELECT municipio, SUM(votos_candidato) FROM resultado_candidato
           WHERE corporacion='CA' GROUP BY municipio"""
    ).fetchall())

    # Top 8 candidatos nominales por voto CA consolidado (4 municipios)
    top = con.execute(
        """SELECT cedula, MAX(nombre_candidato) nombre, SUM(votos_candidato) v
           FROM resultado_candidato
           WHERE corporacion='CA' AND codcan<>'0' AND cedula<>''
           GROUP BY cedula ORDER BY v DESC LIMIT 8"""
    ).fetchall()
    cedulas = [t[0] for t in top]
    nombres = [t[1].title() for t in top]

    # % del total CA del municipio para cada candidato
    matriz = np.zeros((len(cedulas), len(MUNICIPIOS)))
    for i, ced in enumerate(cedulas):
        for j, muni in enumerate(MUNICIPIOS):
            v = con.execute(
                """SELECT COALESCE(SUM(votos_candidato),0) FROM resultado_candidato
                   WHERE corporacion='CA' AND cedula=? AND municipio=?""",
                (ced, muni)).fetchone()[0]
            matriz[i, j] = 100.0 * v / tot[muni] if tot.get(muni) else 0.0
    con.close()
    return nombres, matriz


def main():
    nombres, matriz = cargar_matriz()

    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(matriz, cmap="YlGnBu", aspect="auto")

    ax.set_xticks(range(len(MUNICIPIOS)))
    ax.set_xticklabels([m.title() for m in MUNICIPIOS], fontsize=10)
    ax.set_yticks(range(len(nombres)))
    ax.set_yticklabels(nombres, fontsize=9)

    # Anotaciones en cada celda (% con 1 decimal)
    umbral = matriz.max() * 0.6
    for i in range(matriz.shape[0]):
        for j in range(matriz.shape[1]):
            ax.text(j, i, f"{matriz[i, j]:.1f}%", ha="center", va="center",
                    color="white" if matriz[i, j] > umbral else "#222222",
                    fontsize=8.5, fontweight="bold")

    ax.set_title("Top 8 candidatos a Cámara — % del voto CA por municipio\nBoyacá 2026",
                 fontsize=13, fontweight="bold")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("% del voto válido CA del municipio", fontsize=9)
    fig.tight_layout()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=130)
    plt.close(fig)
    print(f"Heatmap guardado en {OUT} ({matriz.shape[0]} candidatos × {matriz.shape[1]} municipios)")


if __name__ == "__main__":
    main()
