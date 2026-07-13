-- ===========================================================================
-- Reto 3.1 — Arrastre electoral Verde CA -> SE (9 pts)
-- Ratio  votos_SE_Verde / votos_CA_Verde  por PUESTO y municipio.
-- Homologación de la prueba:  codpar_CA = 5  ->  codpar_SE = 57.
--
-- "Votos del partido en un puesto" = voto de lista (candidato codcan='0'),
-- que en los JSON de la Registraduría concentra el total de la lista.
-- El PUESTO es la unidad mínima publicada por la API 2026.
--
-- Un ratio > 1.0 indica que la lista Verde arrastró MÁS votos al Senado que a
-- la Cámara en ese puesto (y viceversa < 1.0).
-- ===========================================================================

WITH verde_ca AS (              -- votos de lista Verde en Cámara (codpar 5) por puesto
    SELECT municipio, puesto_codigo, puesto_nombre,
           SUM(votos_candidato) AS votos_ca_verde
    FROM resultado_candidato
    WHERE corporacion = 'CA' AND codpar = '5' AND codcan = '0'
    GROUP BY municipio, puesto_codigo, puesto_nombre
),
verde_se AS (                  -- votos de lista Verde en Senado (codpar 57) por puesto
    SELECT municipio, puesto_codigo,
           SUM(votos_candidato) AS votos_se_verde
    FROM resultado_candidato
    WHERE corporacion = 'SE' AND codpar = '57' AND codcan = '0'
    GROUP BY municipio, puesto_codigo
)
SELECT
    ca.municipio,
    ca.puesto_codigo,
    ca.puesto_nombre,
    ca.votos_ca_verde,
    COALESCE(se.votos_se_verde, 0)                         AS votos_se_verde,
    ROUND(
        CAST(COALESCE(se.votos_se_verde, 0) AS REAL)
        / NULLIF(ca.votos_ca_verde, 0), 3
    )                                                       AS ratio_arrastre_se_ca
FROM verde_ca ca
LEFT JOIN verde_se se
    ON ca.municipio = se.municipio
   AND ca.puesto_codigo = se.puesto_codigo
ORDER BY ca.municipio, ratio_arrastre_se_ca DESC;
