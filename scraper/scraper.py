#!/usr/bin/env python3
###############################################################################
# Prueba Técnica UTL Senado 2026 — Reto 1: Extracción de datos
# scraper.py — Extrae Cámara (CA) y Senado (SE) de la API REST de la
#              Registraduría para los 4 municipios de Boyacá y carga en SQLite.
#
# Uso:
#   python scraper/scraper.py                          # los 4 municipios (CA+SE)
#   python scraper/scraper.py --municipios TUNJA PAIPA # solo los indicados
#   python scraper/scraper.py --preflight              # conteo sin descargar (bonus)
#   python scraper/scraper.py --db ruta.db             # BD destino alternativa
#
# Diseño:
#   - Idempotente: crea el schema si falta y usa INSERT OR IGNORE sobre un
#     UNIQUE natural, de modo que re-ejecutar NO duplica filas.
#   - Retry con backoff exponencial ante fallos de red / 5xx.
#   - Guarda un snapshot crudo de cada JSON en sample_data/ (respaldo si la API
#     cae) — la carpeta funciona como los "datos de muestra provistos".
#   - Grano de carga: municipio × corporación × circunscripción × puesto ×
#     partido × candidato. El PUESTO es la unidad mínima que publica la API 2026
#     (el nivel MESA está declarado en el nomenclator pero no poblado).
###############################################################################

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import requests

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent
DB_DEFAULT = ROOT / "db" / "puestos_2026.db"
SCHEMA_SQL = ROOT / "db" / "schema.sql"
SAMPLE_DIR = ROOT / "sample_data"

BASE_URL = "https://resultadospreccongreso2026.registraduria.gov.co"
NOMENCLATOR_URL = f"{BASE_URL}/json/nomenclator.json"
RESULT_URL = BASE_URL + "/json/ACT/{corp}/{scope}.json"  # corp ∈ {SE, CA}

# Códigos scope internos (NO DANE) de los 4 municipios, idénticos en SE y CA.
# Se resuelven dinámicamente desde el nomenclator; este dict es el orden y
# el fallback de nombres canónicos exigidos por la prueba.
MUNICIPIOS = ["TUNJA", "PAIPA", "SOGAMOSO", "DUITAMA"]
CORPORACIONES = ["SE", "CA"]  # elec 1 = Senado, elec 2 = Cámara

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; utl-prueba-2026-scraper)"}
TIMEOUT = 30
MAX_RETRIES = 4
BACKOFF_BASE = 1.5  # segundos: espera = BACKOFF_BASE ** intento


def log(msg: str) -> None:
    """Log de progreso a stderr (no contamina stdout que captura el manifest)."""
    print(f"[scraper] {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# Descarga con retry / backoff
# --------------------------------------------------------------------------- #
def fetch_json(url: str) -> dict:
    """Descarga JSON con reintentos y backoff exponencial ante red/5xx."""
    last_err = None
    for intento in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            # 4xx distinto de 429 no se reintenta (recurso inexistente)
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                raise requests.HTTPError(f"HTTP {resp.status_code} en {url}")
            last_err = requests.HTTPError(f"HTTP {resp.status_code} en {url}")
        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_err = exc
        espera = BACKOFF_BASE ** intento
        log(f"  reintento {intento}/{MAX_RETRIES} tras error ({last_err}); espera {espera:.1f}s")
        time.sleep(espera)
    raise RuntimeError(f"Fallaron {MAX_RETRIES} intentos para {url}: {last_err}")


# --------------------------------------------------------------------------- #
# Nomenclator: resolver municipio -> código scope y sus puestos
# --------------------------------------------------------------------------- #
def cargar_nomenclator() -> dict:
    """Descarga el nomenclator (con cache local en sample_data/)."""
    cache = SAMPLE_DIR / "nomenclator.json"
    if cache.exists():
        log(f"nomenclator desde cache ({cache.name})")
        return json.loads(cache.read_text(encoding="utf-8"))
    log("descargando nomenclator.json (~8.6 MB)...")
    nom = fetch_json(NOMENCLATOR_URL)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(nom, ensure_ascii=False), encoding="utf-8")
    return nom


def indexar_ambitos(nom: dict, elec: int) -> dict:
    """Devuelve {indice_i: ambito} para una corporación (elec 1=SE, 2=CA)."""
    bloque = next(b for b in nom["amb"] if b["elec"] == elec)
    return {a["i"]: a for a in bloque["ambitos"]}


def resolver_municipio(by_i: dict, nombre: str) -> dict:
    """Encuentra el ámbito de nivel municipio (l==3) por nombre."""
    objetivo = nombre.upper().strip()
    for a in by_i.values():
        if a.get("l") == 3 and str(a.get("n", "")).upper().strip() == objetivo:
            return a
    raise KeyError(f"Municipio no encontrado en el nomenclator: {nombre}")


def puestos_de(by_i: dict, muni: dict) -> list:
    """Lista de ámbitos de nivel puesto (l==6) descendientes de un municipio."""
    puestos, frontera, vistos = [], [muni], set()
    while frontera:
        siguiente = []
        for nodo in frontera:
            for h in nodo.get("h", []):
                for idx in h.get("p", []):
                    hijo = by_i.get(idx)
                    if hijo is None or hijo["i"] in vistos:
                        continue
                    vistos.add(hijo["i"])
                    if hijo["l"] == 6:
                        puestos.append(hijo)
                    else:
                        siguiente.append(hijo)
        frontera = siguiente
    return sorted(puestos, key=lambda p: p["c"])


# --------------------------------------------------------------------------- #
# Parseo de un JSON de resultados (nivel puesto)
# --------------------------------------------------------------------------- #
def a_int(valor) -> int:
    """Convierte '20651' o '20.651' a entero (los votos no traen separador)."""
    if valor is None:
        return 0
    s = str(valor).strip().replace(".", "").replace(",", "")
    return int(s) if s.lstrip("-").isdigit() else 0


def norm_nombre(*partes) -> str:
    """Normaliza un nombre: colapsa espacios, mayúsculas, sin bordes."""
    txt = " ".join(p for p in partes if p and str(p).strip())
    return " ".join(txt.upper().split())


def parsear_resultado(doc: dict, municipio: str, corporacion: str, puesto_c: str,
                      puesto_n: str) -> list:
    """Aplana un JSON de resultados en filas candidato-nivel-puesto.

    Devuelve una lista de dicts, uno por (partido, candidato) del puesto.
    Recorre TODAS las circunscripciones (camaras[]) presentes.
    """
    filas = []
    for cam in doc.get("camaras", []):
        cam_id = str(cam.get("cam", ""))
        cir = str(cam.get("cir", ""))
        for part in cam.get("partotabla", []):
            act = part.get("act", part)
            codpar = str(act.get("codpar", ""))
            votos_partido = a_int(act.get("vot"))
            for cand in act.get("cantotabla", []):
                filas.append({
                    "municipio": municipio,
                    "corporacion": corporacion,
                    "circunscripcion": cam_id,
                    "puesto_codigo": puesto_c,
                    "puesto_nombre": puesto_n,
                    "codpar": codpar,
                    "votos_partido": votos_partido,
                    "codcan": str(cand.get("codcan", "")),
                    "cedula": str(cand.get("cedula", "")),
                    "nombre_candidato": norm_nombre(
                        cand.get("nomcan"), cand.get("nomcan2"),
                        cand.get("apecan"), cand.get("apecan2"),
                    ),
                    "votos_candidato": a_int(cand.get("vot")),
                    "es_preferente": int(str(cand.get("pref", "0")) == "1"),
                })
    return filas


# --------------------------------------------------------------------------- #
# Persistencia SQLite (idempotente)
# --------------------------------------------------------------------------- #
def conectar(db_path: Path) -> sqlite3.Connection:
    """Abre la BD, garantiza el schema y activa FKs."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    return con


def guardar_snapshot(corp: str, scope: str, doc: dict) -> None:
    """Guarda el JSON crudo en sample_data/ (respaldo/reproducibilidad)."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    dest = SAMPLE_DIR / f"ACT_{corp}_{scope}.json"
    dest.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def upsert_filas(con: sqlite3.Connection, filas: list) -> tuple:
    """Inserta filas con INSERT OR IGNORE. Devuelve (insertadas, omitidas)."""
    cur = con.cursor()
    antes = con.total_changes
    insertadas = omitidas = 0
    for f in filas:
        # partido (dedup) — nombre real se completa en el ETL; aquí basta el código
        cur.execute(
            "INSERT OR IGNORE INTO partido (codpar, corporacion) VALUES (?, ?)",
            (f["codpar"], f["corporacion"]),
        )
        cur.execute(
            """INSERT OR IGNORE INTO resultado_candidato
               (municipio, corporacion, circunscripcion, puesto_codigo,
                puesto_nombre, codpar, votos_partido, codcan, cedula,
                nombre_candidato, votos_candidato, es_preferente)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f["municipio"], f["corporacion"], f["circunscripcion"],
             f["puesto_codigo"], f["puesto_nombre"], f["codpar"],
             f["votos_partido"], f["codcan"], f["cedula"],
             f["nombre_candidato"], f["votos_candidato"], f["es_preferente"]),
        )
        if con.total_changes > antes:
            insertadas += 1
        else:
            omitidas += 1
        antes = con.total_changes
    return insertadas, omitidas


# --------------------------------------------------------------------------- #
# Orquestación
# --------------------------------------------------------------------------- #
def preflight(municipios: list) -> None:
    """Muestra el conteo de puestos por municipio SIN descargar resultados."""
    nom = cargar_nomenclator()
    by_i = indexar_ambitos(nom, elec=1)  # la topología es idéntica en SE y CA
    log("PREFLIGHT — conteo de puestos por municipio (sin descargar resultados):")
    total = 0
    for m in municipios:
        muni = resolver_municipio(by_i, m)
        n = len(puestos_de(by_i, muni))
        total += n
        print(f"  {m:9s} scope={muni['c']}  puestos={n}")
    print(f"  {'TOTAL':9s}            puestos={total}  "
          f"(× {len(CORPORACIONES)} corporaciones = {total * len(CORPORACIONES)} descargas)")


def scrape(municipios: list, db_path: Path) -> None:
    """Extrae y carga los municipios indicados para CA y SE."""
    nom = cargar_nomenclator()
    idx = {"SE": indexar_ambitos(nom, 1), "CA": indexar_ambitos(nom, 2)}
    con = conectar(db_path)

    resumen = {}
    for corp in CORPORACIONES:
        by_i = idx[corp]
        for m in municipios:
            muni = resolver_municipio(by_i, m)
            puestos = puestos_de(by_i, muni)
            log(f"{corp} {m}: {len(puestos)} puestos (scope municipio {muni['c']})")
            ins_tot = omi_tot = 0
            for j, p in enumerate(puestos, 1):
                doc = fetch_json(RESULT_URL.format(corp=corp, scope=p["c"]))
                guardar_snapshot(corp, p["c"], doc)
                filas = parsear_resultado(doc, m, corp, p["c"], p.get("n", ""))
                ins, omi = upsert_filas(con, filas)
                ins_tot += ins
                omi_tot += omi
                if j % 5 == 0 or j == len(puestos):
                    log(f"    {corp} {m}: {j}/{len(puestos)} puestos procesados")
            con.execute(
                """INSERT INTO carga_log
                   (municipio, corporacion, puestos, filas_insertadas, filas_omitidas)
                   VALUES (?,?,?,?,?)""",
                (m, corp, len(puestos), ins_tot, omi_tot),
            )
            con.commit()
            resumen[(corp, m)] = (len(puestos), ins_tot, omi_tot)
            log(f"  -> {corp} {m}: insertadas={ins_tot} omitidas={omi_tot}")

    con.close()
    log("=" * 60)
    log("RESUMEN DE CARGA")
    for (corp, m), (np_, ins, omi) in sorted(resumen.items()):
        log(f"  {corp} {m:9s} puestos={np_:3d} insertadas={ins:6d} omitidas={omi:6d}")
    log(f"BD: {db_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Scraper electoral Registraduría 2026 (Boyacá)")
    ap.add_argument("--municipios", nargs="+", default=MUNICIPIOS,
                    help="Municipios a extraer (default: los 4)")
    ap.add_argument("--preflight", action="store_true",
                    help="Muestra conteo de puestos sin descargar (bonus +3)")
    ap.add_argument("--db", type=Path, default=DB_DEFAULT, help="Ruta de la BD SQLite")
    args = ap.parse_args()

    municipios = [m.upper() for m in args.municipios]
    for m in municipios:
        if m not in MUNICIPIOS:
            log(f"AVISO: '{m}' no es uno de los 4 municipios canónicos {MUNICIPIOS}")

    if args.preflight:
        preflight(municipios)
    else:
        scrape(municipios, args.db)


if __name__ == "__main__":
    main()
