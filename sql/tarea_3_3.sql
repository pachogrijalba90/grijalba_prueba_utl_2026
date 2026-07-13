-- ===========================================================================
-- Reto 3.3 — Atribución determinística SE consolidada (8 pts)
-- Top 5 candidatos por atribución de votos de Senado.
--
-- Fórmula de la prueba:
--     A_ij = (votos_cand_i / votos_partido_j) x votos_SE_partido_j
--
-- Interpretación: reparte los votos de LISTA al Senado de cada partido entre
-- sus candidatos en proporción a su voto preferente. Consolida sobre los 4
-- municipios (suma de votos por candidato y por partido, luego atribuye).
--
-- Nota (bonus): el top por atribución NO coincide necesariamente con el top
-- por voto CA — ver README, sección "Hallazgos principales".
-- ===========================================================================

WITH cand_se AS (                 -- votos preferentes por candidato SE (consolidado 4 munis)
    SELECT codpar, cedula,
           MAX(nombre_candidato)      AS nombre_candidato,
           SUM(votos_candidato)       AS votos_cand
    FROM resultado_candidato
    WHERE corporacion = 'SE' AND circunscripcion = '0' AND codcan <> '0'
    GROUP BY codpar, cedula
),
partido_se AS (                   -- votos preferentes totales del partido (denominador)
    SELECT codpar, SUM(votos_candidato) AS votos_partido_pref
    FROM resultado_candidato
    WHERE corporacion = 'SE' AND circunscripcion = '0' AND codcan <> '0'
    GROUP BY codpar
),
lista_se AS (                     -- votos de LISTA al Senado del partido (codcan='0')
    SELECT codpar, SUM(votos_candidato) AS votos_se_partido
    FROM resultado_candidato
    WHERE corporacion = 'SE' AND circunscripcion = '0' AND codcan = '0'
    GROUP BY codpar
)
SELECT
    c.nombre_candidato,
    p.nombre                                            AS partido,
    c.codpar,
    c.votos_cand,
    l.votos_se_partido,
    ROUND(
        (CAST(c.votos_cand AS REAL) / NULLIF(ps.votos_partido_pref, 0))
        * l.votos_se_partido, 1
    )                                                    AS atribucion_se
FROM cand_se c
JOIN partido_se ps ON c.codpar = ps.codpar
JOIN lista_se   l  ON c.codpar = l.codpar
LEFT JOIN partido p ON p.codpar = c.codpar AND p.corporacion = 'SE'
WHERE ps.votos_partido_pref > 0
ORDER BY atribucion_se DESC
LIMIT 5;
