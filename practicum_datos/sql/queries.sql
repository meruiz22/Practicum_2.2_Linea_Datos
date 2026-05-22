-- =============================================================
-- sql/queries.sql
-- Consultas analíticas del dashboard — 6to ciclo
-- Dataset: AMIE Histórico 2009-2024 
-- =============================================================

-- -------------------------------------------------------------
-- KPI GLOBAL — encabezado del dashboard (último período)
-- -------------------------------------------------------------
SELECT
    SUM(total_estudiantes)                          AS matricula_nacional,
    SUM(total_docentes)                             AS docentes_nacional,
    COUNT(DISTINCT cod_amie)                        AS instituciones_activas,
    ROUND(
        SUM(total_estudiantes)::NUMERIC
        / NULLIF(SUM(total_docentes), 0), 1
    )                                               AS ratio_nacional
FROM fact_matricula
WHERE anio_lectivo = '2022-2023';


-- -------------------------------------------------------------
-- P1 — ¿En qué provincias hay mayor carga docente?
--      Ratio estudiantes / docente por provincia · último año
-- -------------------------------------------------------------
SELECT
    u.provincia,
    ROUND(
        SUM(f.total_estudiantes)::NUMERIC
        / NULLIF(SUM(f.total_docentes), 0), 1
    )                                               AS ratio_est_docente,
    SUM(f.total_estudiantes)                        AS total_estudiantes,
    SUM(f.total_docentes)                           AS total_docentes,
    COUNT(DISTINCT f.cod_amie)                      AS num_instituciones
FROM fact_matricula    f
JOIN dim_institucion   i USING (cod_amie)
JOIN dim_ubicacion     u USING (id_ubicacion)
WHERE f.anio_lectivo = '2022-2023'
GROUP BY u.provincia
ORDER BY ratio_est_docente DESC NULLS LAST;


-- -------------------------------------------------------------
-- P2 — ¿En qué nivel educativo hay mayor brecha de género?
--      % matrícula femenina por nivel · último año
-- -------------------------------------------------------------
SELECT
    i.nivel_educacion,
    SUM(f.estudiantes_f)                            AS mujeres,
    SUM(f.estudiantes_m)                            AS hombres,
    SUM(f.total_estudiantes)                        AS total,
    ROUND(
        100.0 * SUM(f.estudiantes_f)
        / NULLIF(SUM(f.total_estudiantes), 0), 1
    )                                               AS pct_mujeres,
    ROUND(
        100.0 * SUM(f.estudiantes_m)
        / NULLIF(SUM(f.total_estudiantes), 0), 1
    )                                               AS pct_hombres
FROM fact_matricula    f
JOIN dim_institucion   i USING (cod_amie)
WHERE f.anio_lectivo = '2022-2023'
  AND f.inconsistente_genero = 0          -- excluir datos inconsistentes
GROUP BY i.nivel_educacion
ORDER BY pct_mujeres ASC;




-- -------------------------------------------------------------
-- P3 — ¿Cómo evolucionó la matrícula en Loja entre 2009 y 2023?
--      Instituciones activas y total estudiantes por año   
-- -------------------------------------------------------------
SELECT
    f.anio_lectivo,
    COUNT(DISTINCT f.cod_amie)                      AS instituciones_activas,
    SUM(f.total_estudiantes)                        AS total_estudiantes,
    SUM(f.estudiantes_f)                            AS estudiantes_f,
    SUM(f.estudiantes_m)                            AS estudiantes_m,
    ROUND(
        100.0 * SUM(f.estudiantes_f)
        / NULLIF(SUM(f.total_estudiantes), 0), 1
    )                                               AS pct_mujeres,
    SUM(f.total_docentes)                           AS total_docentes,
    ROUND(
        SUM(f.total_estudiantes)::NUMERIC
        / NULLIF(SUM(f.total_docentes), 0), 1
    )                                               AS ratio_est_docente
FROM fact_matricula    f
JOIN dim_institucion   i USING (cod_amie)
JOIN dim_ubicacion     u USING (id_ubicacion)
WHERE u.provincia    = 'LOJA'
  AND f.anio_lectivo >= '2009-2010'
GROUP BY f.anio_lectivo
ORDER BY f.anio_lectivo ASC;




-- -------------------------------------------------------------
-- CONSULTA EXTRA — Evolución nacional 2009-2023 (todas las provincias)
--    Permite comparar la tendencia de Loja con el promedio nacional
-- -------------------------------------------------------------
SELECT
    f.anio_lectivo,
    COUNT(DISTINCT f.cod_amie)                      AS instituciones_nacional,
    SUM(f.total_estudiantes)                        AS matricula_nacional,
    ROUND(
        SUM(f.total_estudiantes)::NUMERIC
        / NULLIF(SUM(f.total_docentes), 0), 1
    )                                               AS ratio_nacional
FROM fact_matricula f
GROUP BY f.anio_lectivo
ORDER BY f.anio_lectivo ASC;