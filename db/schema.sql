-- ===========================================================================
-- Prueba Técnica UTL Senado 2026 — Reto 2.1: Schema SQLite
-- schema.sql — Esquema de la base de datos de resultados electorales
--              (Cámara + Senado, 4 municipios de Boyacá, nivel puesto).
--
-- Grano de resultado_candidato: municipio × corporación × circunscripción ×
--   puesto × partido × candidato. El PUESTO es la unidad mínima publicada por
--   la API 2026 (nivel MESA declarado en el nomenclator pero no poblado).
--
-- Idempotencia: el UNIQUE natural en resultado_candidato + INSERT OR IGNORE
--   garantiza que re-ejecutar el scraper NO duplica filas.
-- ===========================================================================

PRAGMA foreign_keys = ON;

-- Catálogo de municipios cargados -------------------------------------------
CREATE TABLE IF NOT EXISTS municipio (
    nombre        TEXT PRIMARY KEY,          -- TUNJA, PAIPA, SOGAMOSO, DUITAMA
    scope_codigo  TEXT                        -- código interno Registraduría
);

-- Partidos: clave compuesta (codpar, corporacion) porque el espacio de códigos
-- de partido es propio de cada corporación en los JSON de resultados ---------
CREATE TABLE IF NOT EXISTS partido (
    codpar       TEXT NOT NULL,
    corporacion  TEXT NOT NULL CHECK (corporacion IN ('SE', 'CA')),
    nombre       TEXT,                        -- se completa en el ETL
    color        TEXT,                        -- hex; colores oficiales de la prueba
    PRIMARY KEY (codpar, corporacion)
);

-- Resultados a nivel candidato-puesto ---------------------------------------
CREATE TABLE IF NOT EXISTS resultado_candidato (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    municipio         TEXT NOT NULL,
    corporacion       TEXT NOT NULL CHECK (corporacion IN ('SE', 'CA')),
    circunscripcion   TEXT NOT NULL,          -- cam: SE 0=Nacional; CA 1=Nacional, 5=Territorial; 4=especial
    puesto_codigo     TEXT NOT NULL,
    puesto_nombre     TEXT,
    codpar            TEXT NOT NULL,
    votos_partido     INTEGER NOT NULL DEFAULT 0,
    codcan            TEXT NOT NULL,
    cedula            TEXT,
    nombre_candidato  TEXT NOT NULL,
    votos_candidato   INTEGER NOT NULL DEFAULT 0,
    es_preferente     INTEGER NOT NULL DEFAULT 0,
    -- UNIQUE natural: una fila por candidato dentro de un puesto/corporación --
    UNIQUE (municipio, corporacion, circunscripcion, puesto_codigo, codpar, codcan),
    FOREIGN KEY (codpar, corporacion) REFERENCES partido (codpar, corporacion)
);

-- Bitácora de cargas del ETL / scraper --------------------------------------
CREATE TABLE IF NOT EXISTS carga_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                TEXT NOT NULL DEFAULT (datetime('now')),
    municipio         TEXT,
    corporacion       TEXT,
    puestos           INTEGER,
    filas_insertadas  INTEGER,
    filas_omitidas    INTEGER
);

-- ===========================================================================
-- Índices (Bonus 2.1: 3+ índices con justificación)
-- ===========================================================================

-- 1) Join de arrastre CA→SE y agregaciones por partido/municipio (Reto 3.1,
--    3.3, dashboard): las queries filtran por corporación+partido y agrupan
--    por municipio. Cubre el patrón WHERE corporacion=? AND codpar=? / GROUP BY.
CREATE INDEX IF NOT EXISTS idx_res_corp_par_muni
    ON resultado_candidato (corporacion, codpar, municipio);

-- 2) Dominancia por puesto (Reto 3.2): la query agrupa votos por
--    (municipio, corporacion, codpar, puesto) para hallar el % del candidato
--    líder dentro de su partido en cada puesto.
CREATE INDEX IF NOT EXISTS idx_res_puesto_partido
    ON resultado_candidato (municipio, corporacion, puesto_codigo, codpar);

-- 3) Ranking de candidatos por atribución (Reto 3.3) y top-10 del dashboard:
--    ordena/agrega votos por candidato dentro de partido.
CREATE INDEX IF NOT EXISTS idx_res_candidato
    ON resultado_candidato (corporacion, codpar, codcan);
