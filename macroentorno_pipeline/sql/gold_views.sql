-- ============================================================
--  sql/gold_views.sql
--  Proyecto: macroentorno_pipeline
--  Semana 4 — Vistas Gold: 4 base + 2 propias de 6to ciclo
--
--  Fuente: tablas analíticas expandidas por pipeline.py
--  (pib_real, pib_nominal, petroleo_riesgo, iee, enemdu,
--   vab_cantonal, mineduc_amie, supercias_directorio)
--
--  Ejecutar:
--    psql -U marti -d macroentorno_ec -h localhost -f sql/gold_views.sql
-- ============================================================

-- ────────────────────────────────────────────────────────────
--  VISTA AUXILIAR — ultima_extraccion
--  Usada en todas las páginas del dashboard para mostrar
--  cuándo fue la última vez que el RPA actualizó cada fuente.
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS ultima_extraccion CASCADE;

CREATE OR REPLACE VIEW ultima_extraccion AS
SELECT
    indicador,
    MAX(fecha_extraccion)   AS ultima_extraccion,
    COUNT(*)                AS total_registros,
    SUM(CASE WHEN estado = 'COMPLETO'   THEN 1 ELSE 0 END) AS registros_ok,
    SUM(CASE WHEN estado = 'INCOMPLETO' THEN 1 ELSE 0 END) AS registros_error
FROM tab_consolidado
GROUP BY indicador
ORDER BY indicador;

COMMENT ON VIEW ultima_extraccion IS
'Resumen de última extracción por indicador. Power BI la usa para la tarjeta "Última actualización" en cada página del dashboard.';


-- ────────────────────────────────────────────────────────────
--  VISTA 1 — gold_pib_tendencia
--  Página P1: ¿Cómo ha evolucionado la economía en 20 años?
--
--  Fuentes: pib_real + pib_nominal → dim_tiempo
--  Visualizaciones Power BI:
--    - Línea: PIB real anual
--    - Barras con color: variación % (verde/rojo por clasificacion_ciclo)
--    - KPI: último PIB per cápita y variación interanual
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_pib_tendencia CASCADE;

CREATE OR REPLACE VIEW gold_pib_tendencia AS
SELECT
    t.anio,
    t.fecha,
    r.pib_musd,
    r.pib_percapita,
    r.variacion_pct,
    n.pib_percapita_nominal_usd,
    -- Clasificación para color de barras en Power BI
    CASE
        WHEN r.variacion_pct >  2 THEN 'Crecimiento fuerte'
        WHEN r.variacion_pct >  0 THEN 'Crecimiento moderado'
        WHEN r.variacion_pct =  0 THEN 'Estancamiento'
        WHEN r.variacion_pct IS NULL THEN NULL
        ELSE 'Contracción'
    END AS clasificacion_ciclo,
    -- Variación del PIB per cápita nominal vs año anterior (para KPI)
    n.pib_percapita_nominal_usd
        - LAG(n.pib_percapita_nominal_usd) OVER (ORDER BY t.anio)
        AS var_percapita_usd,
    -- Último año disponible (para filtro automático en Power BI)
    MAX(t.anio) OVER () AS ultimo_anio,
    -- Última extracción de esta fuente
    (SELECT MAX(fecha_extraccion) FROM pib_real)  AS ultima_extraccion_pib,
    (SELECT MAX(fecha_extraccion) FROM pib_nominal) AS ultima_extraccion_nominal
FROM pib_real r
JOIN dim_tiempo t ON r.id_tiempo = t.id_tiempo
LEFT JOIN pib_nominal n ON n.id_tiempo = t.id_tiempo
WHERE t.anio >= EXTRACT(YEAR FROM CURRENT_DATE) - 20
ORDER BY t.anio;

COMMENT ON VIEW gold_pib_tendencia IS
'P1 — PIB real y nominal últimos 20 años. Clasifica ciclos económicos para barras con color en Power BI.';


-- ────────────────────────────────────────────────────────────
--  VISTA 2 — gold_petroleo_30dias
--  Página P1: contexto de coyuntura (petróleo y riesgo país)
--
--  Fuente: petroleo_riesgo → dim_tiempo
--  Visualizaciones Power BI:
--    - Línea dual: WTI y promedio móvil 30 días
--    - Línea secundaria: riesgo país EMBI
--    - KPI: último WTI y variación diaria
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_petroleo_30dias CASCADE;

CREATE OR REPLACE VIEW gold_petroleo_30dias AS
SELECT
    t.fecha,
    t.anio,
    t.mes,
    p.precio_wti,
    p.riesgo_pais_pb,
    -- Promedio móvil 30 días del WTI
    AVG(p.precio_wti) OVER (
        ORDER BY t.fecha
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS wti_promedio_30d,
    -- Promedio móvil 30 días del riesgo país
    AVG(p.riesgo_pais_pb) OVER (
        ORDER BY t.fecha
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS riesgo_promedio_30d,
    -- Variación diaria WTI %
    ROUND(
        (p.precio_wti - LAG(p.precio_wti) OVER (ORDER BY t.fecha))
        / NULLIF(LAG(p.precio_wti) OVER (ORDER BY t.fecha), 0) * 100
    , 2) AS var_wti_pct_diario,
    -- Última extracción
    (SELECT MAX(fecha_extraccion) FROM petroleo_riesgo) AS ultima_extraccion
FROM petroleo_riesgo p
JOIN dim_tiempo t ON p.id_tiempo = t.id_tiempo
-- Último año por defecto — Power BI permite cambiar el rango
WHERE t.fecha >= CURRENT_DATE - INTERVAL '365 days'
  AND (p.precio_wti IS NOT NULL OR p.riesgo_pais_pb IS NOT NULL)
ORDER BY t.fecha;

COMMENT ON VIEW gold_petroleo_30dias IS
'P1 — Precio WTI y riesgo país EMBI con promedio móvil 30 días. Fuente: petroleo_riesgo.';


-- ────────────────────────────────────────────────────────────
--  VISTA 3 — gold_empleo_tendencia
--  Página P2: ¿Cómo ha evolucionado el mercado laboral?
--
--  Fuente: enemdu → dim_tiempo
--  Visualizaciones Power BI:
--    - Línea: tasa de desempleo Nacional/Urbana/Rural
--    - Barras: empleo adecuado vs subempleo por período
--    - KPI: tasa de desempleo más reciente
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_empleo_tendencia CASCADE;

CREATE OR REPLACE VIEW gold_empleo_tendencia AS
SELECT
    t.fecha,
    t.anio,
    t.mes,
    t.trimestre,
    e.periodo_original,
    e.nombre_indicador,
    e.nacional_total,
    e.area_urbana,
    e.area_rural,
    e.sexo_hombre,
    e.sexo_mujer,
    -- Etiqueta para eje X del gráfico
    t.anio || '-T' || COALESCE(t.trimestre::TEXT, t.mes::TEXT) AS periodo_label,
    -- Flag último dato por indicador (para KPI)
    CASE
        WHEN t.fecha = MAX(t.fecha) OVER (PARTITION BY e.nombre_indicador)
        THEN TRUE ELSE FALSE
    END AS es_ultimo_dato,
    -- Última extracción
    (SELECT MAX(fecha_extraccion) FROM enemdu) AS ultima_extraccion
FROM enemdu e
JOIN dim_tiempo t ON e.id_tiempo = t.id_tiempo
ORDER BY t.fecha, e.nombre_indicador;

COMMENT ON VIEW gold_empleo_tendencia IS
'P2 — Todos los indicadores ENEMDU históricos en formato long. Filtrar por nombre_indicador en Power BI.';


-- ────────────────────────────────────────────────────────────
--  VISTA 4 — gold_bachilleres_vs_empresas
--  Página P3: ¿Dónde están los bachilleres y las empresas?
--
--  Fuentes: mineduc_amie × supercias_directorio × dim_geografia
--  Visualizaciones Power BI:
--    - Barras agrupadas: bachilleres vs empresas por provincia
--    - Tabla: ratio bachilleres/empresas por provincia
--    - KPI: total nacional bachilleres 3ro BACH
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_bachilleres_vs_empresas CASCADE;

CREATE OR REPLACE VIEW gold_bachilleres_vs_empresas AS
WITH bachilleres AS (
    SELECT
        g.provincia,
        g.cod_provincia,
        SUM(m.bach3_total)          AS total_bachilleres_3ro,
        SUM(m.total_estudiantes)    AS total_estudiantes,
        COUNT(DISTINCT m.amie)      AS num_instituciones,
        MAX(m.periodo_lectivo)      AS periodo_lectivo
    FROM mineduc_amie m
    JOIN dim_geografia g ON m.id_geo = g.id_geo
    GROUP BY g.provincia, g.cod_provincia
),
empresas AS (
    SELECT
        g.provincia,
        g.cod_provincia,
        COUNT(DISTINCT s.expediente) AS total_empresas_activas,
        MAX(s.periodo_reporte)       AS periodo_reporte
    FROM supercias_directorio s
    JOIN dim_geografia g ON s.id_geo = g.id_geo
    WHERE s.situacion_legal = 'ACTIVA'
       OR s.situacion_legal IS NULL   -- incluir si no viene el campo
    GROUP BY g.provincia, g.cod_provincia
)
SELECT
    COALESCE(b.provincia, e.provincia)           AS provincia,
    COALESCE(b.cod_provincia, e.cod_provincia)   AS cod_provincia,
    COALESCE(b.total_bachilleres_3ro, 0)         AS total_bachilleres_3ro,
    COALESCE(b.total_estudiantes, 0)             AS total_estudiantes,
    COALESCE(b.num_instituciones, 0)             AS num_instituciones,
    COALESCE(e.total_empresas_activas, 0)        AS total_empresas_activas,
    b.periodo_lectivo,
    e.periodo_reporte,
    -- Ratio clave: bachilleres por empresa activa
    CASE
        WHEN COALESCE(e.total_empresas_activas, 0) = 0 THEN NULL
        ELSE ROUND(
            COALESCE(b.total_bachilleres_3ro, 0)::NUMERIC
            / e.total_empresas_activas, 2
        )
    END AS ratio_bachilleres_por_empresa,
    -- Total nacional (mismo valor en todas las filas → KPI en Power BI)
    SUM(COALESCE(b.total_bachilleres_3ro, 0)) OVER () AS total_nacional_bachilleres,
    SUM(COALESCE(e.total_empresas_activas, 0)) OVER () AS total_nacional_empresas,
    -- Última extracción
    (SELECT MAX(fecha_extraccion) FROM mineduc_amie)      AS ultima_ext_mineduc,
    (SELECT MAX(fecha_extraccion) FROM supercias_directorio) AS ultima_ext_supercias
FROM bachilleres b
FULL OUTER JOIN empresas e ON b.cod_provincia = e.cod_provincia
ORDER BY total_bachilleres_3ro DESC NULLS LAST;

COMMENT ON VIEW gold_bachilleres_vs_empresas IS
'P3 — Cruce MINEDUC × Supercias por provincia. Ratio bachilleres/empresa indica potencial UTPL.';


-- ============================================================
--  VISTAS PROPIAS 6TO CICLO
-- ============================================================

-- ────────────────────────────────────────────────────────────
--  VISTA 5 — gold_iee_vs_pib  [PROPIA 6TO CICLO]
--  Página P1: ¿El IEE anticipa los ciclos del PIB?
--
--  Justificación: el IEE es un indicador adelantado que mide
--  expectativas empresariales antes de que el PIB las refleje.
--  Esta vista permite ver si el sector empresarial ecuatoriano
--  anticipa correctamente las expansiones y contracciones.
--
--  Fuentes: iee + pib_real → dim_tiempo
--  Visualizaciones:
--    - Scatter: IEE promedio vs variación PIB (correlación)
--    - Línea dual: IEE mensual + variación PIB anual superpuestos
--    - KPI: último IEE global con interpretación
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_iee_vs_pib CASCADE;

CREATE OR REPLACE VIEW gold_iee_vs_pib AS
WITH iee_anual AS (
    SELECT
        t.anio,
        ROUND(AVG(i.iee_global)::NUMERIC,       2) AS iee_global_promedio,
        ROUND(AVG(i.iee_comercio)::NUMERIC,     2) AS iee_comercio_promedio,
        ROUND(AVG(i.iee_manufactura)::NUMERIC,  2) AS iee_manufactura_promedio,
        ROUND(AVG(i.iee_construccion)::NUMERIC, 2) AS iee_construccion_promedio,
        ROUND(AVG(i.iee_servicios)::NUMERIC,    2) AS iee_servicios_promedio,
        COUNT(*)                                    AS meses_con_dato
    FROM iee i
    JOIN dim_tiempo t ON i.id_tiempo = t.id_tiempo
    GROUP BY t.anio
),
pib_anual AS (
    SELECT
        t.anio,
        r.pib_musd,
        r.variacion_pct,
        r.pib_percapita
    FROM pib_real r
    JOIN dim_tiempo t ON r.id_tiempo = t.id_tiempo
)
SELECT
    p.anio,
    p.pib_musd,
    p.variacion_pct                             AS variacion_pib_pct,
    p.pib_percapita,
    i.iee_global_promedio,
    i.iee_comercio_promedio,
    i.iee_manufactura_promedio,
    i.iee_construccion_promedio,
    i.iee_servicios_promedio,
    i.meses_con_dato,
    -- IEE del año anterior como señal adelantada
    LAG(i.iee_global_promedio) OVER (ORDER BY p.anio) AS iee_anio_anterior,
    -- Interpretación para tarjeta en dashboard
    CASE
        WHEN i.iee_global_promedio > 55 THEN 'Optimismo alto'
        WHEN i.iee_global_promedio > 50 THEN 'Optimismo moderado'
        WHEN i.iee_global_promedio = 50 THEN 'Equilibrio'
        WHEN i.iee_global_promedio > 45 THEN 'Pesimismo moderado'
        WHEN i.iee_global_promedio IS NULL THEN 'Sin dato IEE'
        ELSE 'Pesimismo alto'
    END AS sentimiento_empresarial,
    -- Última extracción
    (SELECT MAX(fecha_extraccion) FROM iee) AS ultima_extraccion_iee,
    (SELECT MAX(fecha_extraccion) FROM pib_real) AS ultima_extraccion_pib
FROM pib_anual p
LEFT JOIN iee_anual i ON p.anio = i.anio
ORDER BY p.anio;

COMMENT ON VIEW gold_iee_vs_pib IS
'[PROPIA 6TO CICLO] Correlación IEE promedio anual vs variación PIB. IEE como indicador adelantado del ciclo económico ecuatoriano.';


-- ────────────────────────────────────────────────────────────
--  VISTA 6 — gold_vab_por_sector  [PROPIA 6TO CICLO]
--  Página P2: ¿Qué sectores dominan cada provincia?
--
--  Justificación: el VAB por sector CIIU y cantón permite
--  identificar la especialización productiva de cada provincia,
--  revelando si hay concentración económica o diversificación.
--
--  Fuente: vab_cantonal → dim_tiempo + dim_geografia
--  Visualizaciones:
--    - Mapa coroplético: VAB total por provincia
--    - Barras apiladas: composición sectorial top 10 provincias
--    - Línea: evolución VAB 5 provincias más grandes
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_vab_por_sector CASCADE;

CREATE OR REPLACE VIEW gold_vab_por_sector AS
WITH vab_provincia AS (
    -- Agregar VAB cantonal a nivel provincial
    SELECT
        t.anio,
        g.provincia,
        g.cod_provincia,
        v.sector,
        SUM(v.vab_miles_usd) AS vab_miles_usd
    FROM vab_cantonal v
    JOIN dim_geografia g ON v.id_geo  = g.id_geo
    LEFT JOIN dim_tiempo   t ON v.id_tiempo = t.id_tiempo
    GROUP BY t.anio, g.provincia, g.cod_provincia, v.sector
),
vab_total_nacional AS (
    SELECT
        anio,
        SUM(vab_miles_usd) AS vab_nacional
    FROM vab_provincia
    GROUP BY anio
)
SELECT
    vp.anio,
    vp.provincia,
    vp.cod_provincia,
    vp.sector,
    ROUND(vp.vab_miles_usd::NUMERIC, 2)         AS vab_miles_usd,
    ROUND(vn.vab_nacional::NUMERIC, 2)           AS vab_nacional_anio,
    -- Participación del sector en el VAB nacional
    ROUND(
        vp.vab_miles_usd::NUMERIC
        / NULLIF(vn.vab_nacional, 0) * 100
    , 2)                                          AS participacion_sector_pct,
    -- Participación de la provincia en el total de ese sector
    ROUND(
        vp.vab_miles_usd::NUMERIC
        / NULLIF(SUM(vp.vab_miles_usd)
                 OVER (PARTITION BY vp.anio, vp.sector), 0) * 100
    , 2)                                          AS participacion_prov_en_sector_pct,
    -- Ranking de provincia por VAB total ese año
    RANK() OVER (
        PARTITION BY vp.anio
        ORDER BY SUM(vp.vab_miles_usd)
                 OVER (PARTITION BY vp.anio, vp.provincia) DESC
    )                                             AS ranking_provincia,
    -- Variación anual del VAB del sector en la provincia
    ROUND(
        (vp.vab_miles_usd
         - LAG(vp.vab_miles_usd)
           OVER (PARTITION BY vp.provincia, vp.sector ORDER BY vp.anio))
        / NULLIF(
            LAG(vp.vab_miles_usd)
            OVER (PARTITION BY vp.provincia, vp.sector ORDER BY vp.anio)
          , 0) * 100
    , 2)                                          AS variacion_anual_pct,
    -- Clasificación de concentración
    CASE
        WHEN vp.vab_miles_usd / NULLIF(vn.vab_nacional, 0) > 0.20
            THEN 'Alta concentración (>20%)'
        WHEN vp.vab_miles_usd / NULLIF(vn.vab_nacional, 0) > 0.10
            THEN 'Concentración media (10-20%)'
        WHEN vp.vab_miles_usd / NULLIF(vn.vab_nacional, 0) > 0.05
            THEN 'Concentración baja (5-10%)'
        ELSE 'Concentración mínima (<5%)'
    END                                           AS nivel_concentracion,
    -- Última extracción
    (SELECT MAX(fecha_extraccion) FROM vab_cantonal) AS ultima_extraccion
FROM vab_provincia vp
JOIN vab_total_nacional vn ON vp.anio = vn.anio
ORDER BY vp.anio DESC NULLS LAST, vab_miles_usd DESC;

COMMENT ON VIEW gold_vab_por_sector IS
'[PROPIA 6TO CICLO] VAB por provincia y sector CIIU con participación %, ranking y variación anual. Alimenta mapa coroplético P2.';


-- ────────────────────────────────────────────────────────────
--  Verificación de las 7 vistas creadas
-- ────────────────────────────────────────────────────────────
SELECT
    viewname                                        AS vista,
    CASE
        WHEN viewname = 'ultima_extraccion'         THEN 'Auxiliar (dashboard)'
        WHEN viewname IN ('gold_iee_vs_pib',
                          'gold_vab_por_sector')    THEN '6to ciclo (propia)'
        ELSE 'Base (reto)'
    END                                             AS tipo
FROM pg_views
WHERE schemaname = 'public'
  AND viewname IN (
      'ultima_extraccion',
      'gold_pib_tendencia',
      'gold_petroleo_30dias',
      'gold_empleo_tendencia',
      'gold_bachilleres_vs_empresas',
      'gold_iee_vs_pib',
      'gold_vab_por_sector'
  )
ORDER BY viewname;