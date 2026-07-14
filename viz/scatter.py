#!/usr/bin/env python3
###############################################################################
# Prueba Técnica UTL Senado 2026 — Reto 5.2: Scatter CA vs SE
# scatter.py — Dispersión de votos válidos Cámara (CA) vs. Senado (SE) por
#              PUESTO de votación, con recta OLS y r de Pearson.
#
# La API 2026 publica hasta nivel PUESTO (no mesa individual): cada punto es
# un puesto. El script imprime  r=X.XXX | pendiente=X.XXX | n_mesas=NNN
# (n_mesas = nº de puestos), que el manifest captura automáticamente.
#
# Output: viz/scatter_ca_se.png
###############################################################################

import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # backend sin pantalla (reproducible en cualquier entorno)
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "puestos_2026.db"
OUT = ROOT / "viz" / "scatter_ca_se.png"

# Colores de municipio (paleta obligatoria de la prueba reutilizada por municipio)
COLORES = {
    "TUNJA": "#007C34", "PAIPA": "#1E477D",
    "SOGAMOSO": "#E07B00", "DUITAMA": "#7B2D8B",
}


def cargar_puntos():
    """Votos válidos (voto de lista, codcan='0') CA y SE por puesto y municipio."""
    con = sqlite3.connect(DB)
    filas = con.execute(
        """
        SELECT municipio, puesto_codigo,
               SUM(CASE WHEN corporacion='CA' AND codcan='0'
                        THEN votos_candidato ELSE 0 END) AS ca,
               SUM(CASE WHEN corporacion='SE' AND codcan='0'
                        THEN votos_candidato ELSE 0 END) AS se
        FROM resultado_candidato
        GROUP BY municipio, puesto_codigo
        HAVING ca > 0 AND se > 0
        ORDER BY municipio, puesto_codigo
        """
    ).fetchall()
    con.close()
    return filas


def main():
    filas = cargar_puntos()
    munis = [f[0] for f in filas]
    ca = np.array([f[2] for f in filas], dtype=float)
    se = np.array([f[3] for f in filas], dtype=float)
    n = len(filas)

    # Recta OLS y r de Pearson
    pendiente, intercepto = np.polyfit(ca, se, 1)
    r = float(np.corrcoef(ca, se)[0, 1])

    fig, ax = plt.subplots(figsize=(9, 6))
    for muni, color in COLORES.items():
        idx = [i for i, m in enumerate(munis) if m == muni]
        ax.scatter(ca[idx], se[idx], c=color, label=muni.title(),
                   s=55, alpha=0.8, edgecolors="white", linewidths=0.5)

    xs = np.linspace(ca.min(), ca.max(), 100)
    ax.plot(xs, pendiente * xs + intercepto, color="#333333", lw=1.8,
            ls="--", label=f"OLS (pendiente={pendiente:.3f})")

    ax.annotate(f"r de Pearson = {r:.3f}\nn = {n} puestos",
                xy=(0.04, 0.90), xycoords="axes fraction",
                fontsize=11, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.4", fc="#F5F5F5", ec="#999999"))

    ax.set_xlabel("Votos válidos Cámara (CA) por puesto", fontsize=11)
    ax.set_ylabel("Votos válidos Senado (SE) por puesto", fontsize=11)
    ax.set_title("Relación voto Cámara vs. Senado por puesto — Boyacá 2026",
                 fontsize=13, fontweight="bold")
    ax.legend(frameon=True, fontsize=9, loc="lower right")
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=130)
    plt.close(fig)

    # Línea que el manifest captura automáticamente
    print(f"r={r:.3f} | pendiente={pendiente:.3f} | n_mesas={n}")
    print(f"Figura guardada en {OUT}")


if __name__ == "__main__":
    main()
