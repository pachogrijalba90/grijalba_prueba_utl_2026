# GRIJALBA — Prueba Técnica UTL Senado 2026

Pipeline de datos electorales del Congreso 2026 para cuatro municipios de Boyacá
(**Tunja, Paipa, Sogamoso, Duitama**): extracción desde la API de la Registraduría,
carga en SQLite, y análisis SQL de arrastre electoral. Datos **reales y definitivos**
(escrutinio 100%).

> **Alcance de esta entrega:** Retos **1, 2 y 3** (extracción + base de datos + SQL
> analítico), más el manifiesto de evaluación automatizado. Los retos 4 (dashboard) y
> 5 (visualizaciones) no se incluyen en esta versión.

## Candidato

- **Nombre:** GRIJALBA
- **Email:** _(pendiente de completar en `outputs/generar_manifest.py` → `META`)_
- **Repositorio:** https://github.com/pachogrijalba90/grijalba_prueba_utl_2026

## Instalación

Requiere Python 3.9+ y `pip`.

```bash
pip install -r requirements.txt
```

La única dependencia externa es `requests`; el resto del pipeline usa la librería
estándar (`sqlite3`, `json`, `argparse`).

## Pipeline de ejecución

Reproduce todo el pipeline desde cero en menos de 10 minutos:

```bash
# 1) Extracción — descarga los 4 municipios (Cámara + Senado) y carga en SQLite.
#    Idempotente: re-ejecutar NO duplica filas (INSERT OR IGNORE sobre UNIQUE).
python scraper/scraper.py

#    Variantes:
python scraper/scraper.py --municipios TUNJA PAIPA   # subconjunto
python scraper/scraper.py --preflight                # conteo sin descargar (bonus)

# 2) ETL — normaliza nombres, enriquece partidos (nombre + color), registra carga_log.
python db/etl.py

# 3) SQL analítico — las 3 queries corren sobre los 4 municipios combinados.
sqlite3 db/puestos_2026.db < sql/tarea_3_1.sql
sqlite3 db/puestos_2026.db < sql/tarea_3_2.sql
sqlite3 db/puestos_2026.db < sql/tarea_3_3.sql

# 4) Manifiesto — valida el pipeline y captura resultados automáticamente.
python outputs/generar_manifest.py     # imprime "4/4 municipios" y "SQL OK"
```

La base de datos (`db/puestos_2026.db`, 23 MB) y el snapshot crudo de la API
(`sample_data/`, 39 MB) se versionan en el repositorio (ambos < 50 MB).

## API

**Base:** `https://resultadospreccongreso2026.registraduria.gov.co`

Es una SPA que consume JSON estáticos servidos por el mismo host. No requiere
cabeceras especiales (un `GET` desnudo devuelve 200; se envía un `User-Agent` por
cortesía).

**Endpoints usados:**

| Endpoint | Descripción |
|---|---|
| `GET /json/nomenclator.json` | Árbol divipol (País→Departamento→Municipio→Zona→Puesto) + catálogo de partidos. ~8.6 MB. |
| `GET /json/ACT/{corp}/{scopeCode}.json` | Resultados definitivos por ámbito. `corp` ∈ `{SE, CA}`. |

**Cómo obtener el nomenclator y resolver los municipios:** se descarga
`nomenclator.json` una vez; en el bloque de la corporación se filtran los ámbitos de
nivel municipio (`l == 3`) por nombre para obtener su **código scope interno** (NO
DANE). Descendiendo por los hijos (`h`) se llega a los puestos (`l == 6`), cuyos
scopeCode alimentan el endpoint de resultados.

| Municipio | scopeCode | Puestos |
|---|---|---|
| TUNJA | `0700001` | 26 |
| DUITAMA | `0700079` | 22 |
| SOGAMOSO | `0700277` | 18 |
| PAIPA | `0700181` | 7 |

**Campos JSON relevantes (≥8):** `elec` (1=SE, 2=CA), `amb` (código de ámbito),
`mesesc`/`pmesesc` (mesas escrutadas / %), `votant`/`pvotant` (votantes / participación),
`codpar` (código de partido), `vot`/`pvot` (votos / % del partido o candidato),
`codcan` (código de candidato; `0` = voto de lista), `cedula`, `nomcan`/`apecan`
(nombres/apellidos), `pref` (voto preferente). Los valores llegan como **cadenas** y
los porcentajes con **coma decimal** (`"26,30%"`); el ETL los normaliza.

**Nota sobre granularidad (mesa vs. puesto):** el enunciado menciona "mesa". Se validó
exhaustivamente que la API 2026 **publica los resultados agregados hasta nivel PUESTO,
no por mesa individual**: el nomenclator declara el nivel MESA pero tiene 0 nodos de ese
nivel en sus 14.430 puestos; el bundle de la app solo permite navegar por scope hasta
municipio; y todo código de mesa construido devuelve 404 (incluidos los endpoints
`HIST`/`EST`). Por tanto **el PUESTO es la unidad mínima real** y se usa como unidad de
análisis en los retos que piden "mesa". El único desglose por mesa existente son las
actas E-14 escaneadas (imágenes, sistema aparte), fuera del alcance de esta API.

## Municipios en la BD

4/4 municipios cargados, **99.353** filas candidato-puesto, **91** partidos:

| Municipio | Puestos | Líder Senado (voto de lista) |
|---|---|---|
| TUNJA | 26 | Pacto Histórico (20.651) |
| DUITAMA | 22 | Pacto Histórico (15.423) |
| SOGAMOSO | 18 | Pacto Histórico (13.957) |
| PAIPA | 7 | Pacto Histórico (3.669) |

## Hallazgos principales

- **El Pacto Histórico lidera el Senado en los cuatro municipios** por voto de lista,
  pese a que la Cámara está más fragmentada (Alianza Verde y Conservador con fuerte
  presencia territorial).

- **Arrastre Verde CA→SE heterogéneo entre municipios** (ratio = votos de lista Verde al
  Senado / a la Cámara):

  | Municipio | Verde CA | Verde SE | Ratio SE/CA |
  |---|---|---|---|
  | PAIPA | 299 | 426 | **1.43** |
  | DUITAMA | 490 | 586 | 1.20 |
  | TUNJA | 807 | 867 | 1.07 |
  | SOGAMOSO | 669 | 618 | **0.92** |

  En Paipa y Duitama la lista Verde arrastró más votos al Senado que a la Cámara; en
  Sogamoso ocurrió lo contrario (ratio < 1), señal de un voto Verde más "cameral" allí.

- **Dominancia extrema (Reto 3.2):** 144 casos de candidatos que concentran >60% de los
  votos de su partido en un puesto. Destacan liderazgos locales fuertes como Soledad
  Tamayo (Conservador, 97% en Palermo–Paipa) y Yamit Hurtado (Verde, 94% en el mismo
  puesto).

- **El top por voto Cámara NO coincide con el top por atribución Senado (Reto 3.3, bonus):**
  el ranking por atribución SE lo encabezan John Amaya y Ariel Ávila (Alianza Verde) y
  Juan Ostos, mientras que el top de votos a Cámara son otros candidatos (Héctor Chaparro,
  Yamit Hurtado, Jaime Salamanca…). La razón es estructural: Cámara y Senado son listas y
  candidaturas **distintas**, y la atribución `A_ij = (voto_cand/voto_partido)×voto_SE_lista`
  depende del voto de lista al **Senado**, no del desempeño en Cámara. Un candidato puede
  arrasar en Cámara y no aparecer en la atribución SE (no compite allí), y viceversa.

## Bonus implementados

- **1.2 — `--preflight`** (+3): `python scraper/scraper.py --preflight` imprime el conteo
  de puestos por municipio sin descargar resultados.
- **2.1 — 3 índices SQLite** (+2): definidos en `db/schema.sql` con justificación de qué
  consulta optimiza cada uno (join de arrastre, dominancia por puesto, ranking de
  candidatos).
- **3.3 — Explicación top CA ≠ top atribución SE** (+2): ver "Hallazgos principales".
