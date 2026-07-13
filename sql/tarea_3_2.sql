-- ===========================================================================
-- Reto 3.2 — Dominancia extrema (8 pts)  [query construida desde cero]
-- Puestos donde UN candidato concentra > 60% de los votos de SU partido
-- (dentro de ese puesto y corporación).
--
-- Se excluye el "voto de lista" (codcan='0'), que no es un candidato nominal
-- sino el agregado de la lista; incluirlo distorsionaría la concentración.
-- Se exige un mínimo de votos de partido en el puesto (>=10) para evitar
-- ratios triviales en puestos con casi nada de votación.
-- ===========================================================================

WITH votos_partido_puesto AS (   -- total de votos NOMINALES del partido en el puesto
    SELECT municipio, corporacion, puesto_codigo, puesto_nombre, codpar,
           SUM(votos_candidato) AS votos_partido_nom
    FROM resultado_candidato
    WHERE codcan <> '0'
    GROUP BY municipio, corporacion, puesto_codigo, codpar
),
candidato_puesto AS (            -- votos de cada candidato en el puesto
    SELECT municipio, corporacion, puesto_codigo, codpar,
           nombre_candidato, votos_candidato
    FROM resultado_candidato
    WHERE codcan <> '0'
)
SELECT
    c.municipio,
    c.corporacion,
    c.puesto_codigo,
    v.puesto_nombre,
    p.nombre                                          AS partido,
    c.codpar,
    c.nombre_candidato,
    c.votos_candidato,
    v.votos_partido_nom,
    ROUND(100.0 * c.votos_candidato / v.votos_partido_nom, 1) AS pct_dominancia
FROM candidato_puesto c
JOIN votos_partido_puesto v
    ON  c.municipio    = v.municipio
    AND c.corporacion  = v.corporacion
    AND c.puesto_codigo = v.puesto_codigo
    AND c.codpar       = v.codpar
LEFT JOIN partido p
    ON  p.codpar = c.codpar AND p.corporacion = c.corporacion
WHERE v.votos_partido_nom >= 10
  AND (1.0 * c.votos_candidato / v.votos_partido_nom) > 0.60
ORDER BY pct_dominancia DESC, c.votos_candidato DESC;
