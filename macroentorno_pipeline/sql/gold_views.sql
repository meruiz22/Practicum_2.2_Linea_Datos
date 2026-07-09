-- ============================================================
--  sql/gold_views.sql
--  Proyecto: macroentorno_pipeline
--  Vistas que genera:
--    Base:
--      gold_pib_tendencia           → P1: evolución PIB 20 años
--      gold_petroleo_30dias         → P1: contexto petróleo y riesgo
--      gold_empleo_tendencia        → P2: mercado laboral histórico
--      gold_bachilleres_vs_empresas → P3: cruce MINEDUC × Supercias
--    Propias 6to ciclo:
--      gold_iee_vs_pib              → P1: correlación expectativas vs PIB
--      gold_vab_por_sector          → P2: concentración sectorial provincial
-- ============================================================

-- ────────────────────────────────────────────────────────────
--  VISTA 1 — gold_pib_tendencia
--  Pregunta P1: ¿Cómo ha evolucionado la economía ecuatoriana
--  en los últimos 20 años?
--
--  Fuente: fact_macro_anual → dim_tiempo
--  Visualizaciones:
--    - Línea: PIB real anual
--    - Barras con color: variación % con clasificación de ciclo
--    - KPI: último PIB per cápita y variación interanual
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_pib_tendencia CASCADE;

CREATE OR REPLACE VIEW gold_pib_tendencia AS
SELECT
    t.anio,
    m.pib_real_musd,
    m.pib_percapita_nominal,
    m.variacion_pib_pct,
    -- Clasificación de ciclo económico para barras con color en Power BI
    CASE
        WHEN m.variacion_pib_pct >  2 THEN 'Crecimiento fuerte'
        WHEN m.variacion_pib_pct >  0 THEN 'Crecimiento moderado'
        WHEN m.variacion_pib_pct =  0 THEN 'Estancamiento'
        WHEN m.variacion_pib_pct IS NULL THEN NULL
        ELSE 'Contracción'
    END AS clasificacion_ciclo,
    -- Último año disponible para KPI en Power BI
    MAX(t.anio) OVER () AS ultimo_anio,
    -- Variación interanual del PIB per cápita (para KPI secundario)
    m.pib_percapita_nominal
        - LAG(m.pib_percapita_nominal) OVER (ORDER BY t.anio)
        AS var_percapita_usd
FROM fact_macro_anual m
JOIN dim_tiempo t ON m.id_tiempo = t.id_tiempo
-- Últimos 20 años para el dashboard (ajustar si se quiere toda la serie)
WHERE t.anio >= EXTRACT(YEAR FROM CURRENT_DATE) - 20
ORDER BY t.anio;

COMMENT ON VIEW gold_pib_tendencia IS
'P1 — Evolución PIB últimos 20 años. Clasifica ciclos económicos para barras con color. Fuente: fact_macro_anual.';


-- ────────────────────────────────────────────────────────────
--  VISTA 2 — gold_petroleo_30dias
--  Pregunta P1: contexto de coyuntura — petróleo y riesgo país
--
--  Fuente: fact_indicadores_diarios → dim_tiempo
--  Visualizaciones:
--    - Línea dual: WTI y crudo ecuatoriano
--    - Línea secundaria: riesgo país EMBI
--    - Promedio móvil 30 días del WTI para suavizar volatilidad
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_petroleo_30dias CASCADE;

CREATE OR REPLACE VIEW gold_petroleo_30dias AS
SELECT
    t.fecha,
    t.anio,
    t.mes,
    f.precio_petroleo_wti,
    f.precio_crudo_ecu,
    f.riesgo_pais_pb,
    -- Promedio móvil 30 días del WTI
    AVG(f.precio_petroleo_wti) OVER (
        ORDER BY t.fecha
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS wti_promedio_30d,
    -- Promedio móvil 30 días del riesgo país
    AVG(f.riesgo_pais_pb) OVER (
        ORDER BY t.fecha
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS riesgo_promedio_30d,
    -- Variación diaria del WTI en porcentaje
    ROUND(
        (f.precio_petroleo_wti
            - LAG(f.precio_petroleo_wti) OVER (ORDER BY t.fecha))
        / NULLIF(LAG(f.precio_petroleo_wti) OVER (ORDER BY t.fecha), 0) * 100
    , 2) AS var_wti_pct
FROM fact_indicadores_diarios f
JOIN dim_tiempo t ON f.id_tiempo = t.id_tiempo
-- Último año por defecto — Power BI permite filtrar el rango desde el panel
WHERE t.fecha >= CURRENT_DATE - INTERVAL '365 days'
ORDER BY t.fecha;

COMMENT ON VIEW gold_petroleo_30dias IS
'P1 — Contexto coyuntura petróleo y riesgo país. Incluye promedio móvil 30 días WTI. Fuente: fact_indicadores_diarios.';


-- ────────────────────────────────────────────────────────────
--  VISTA 3 — gold_empleo_tendencia
--  Pregunta P2: ¿En qué sectores y provincias se concentran
--  la actividad económica y el empleo?
--
--  Fuente: fact_empleo → dim_tiempo
--  Visualizaciones:
--    - Línea: tasa de desempleo histórica Nacional/Urbana/Rural
--    - KPI: tasa de desempleo más reciente
--    - Barras: empleo adecuado vs subempleo por período
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_empleo_tendencia CASCADE;

CREATE OR REPLACE VIEW gold_empleo_tendencia AS
SELECT
    t.fecha,
    t.anio,
    t.mes,
    t.trimestre,
    e.indicador,
    e.total_nacional,
    e.total_urbana,
    e.total_rural,
    -- Período formateado para eje X del gráfico (ej: "2024-T1")
    t.anio || '-T' || COALESCE(t.trimestre::TEXT, '?') AS periodo_label,
    -- Indicador si es el dato más reciente (para KPI en Power BI)
    CASE WHEN t.fecha = MAX(t.fecha) OVER (PARTITION BY e.indicador)
         THEN TRUE ELSE FALSE
    END AS es_ultimo_dato
FROM fact_empleo e
JOIN dim_tiempo t ON e.id_tiempo = t.id_tiempo
-- Filtrar solo los indicadores clave para el dashboard
WHERE e.indicador IN (
    'Empleo Adecuado/Pleno (%)',
    'Subempleo (%)',
    'Desempleo (%)',
    'No remunerado (%)',
    'Otro empleo no pleno (%)'
)
ORDER BY t.fecha, e.indicador;

COMMENT ON VIEW gold_empleo_tendencia IS
'P2 — Indicadores ENEMDU históricos: desempleo, subempleo, empleo adecuado. Nacional/Urbana/Rural. Fuente: fact_empleo.';


-- ────────────────────────────────────────────────────────────
--  VISTA 4 — gold_bachilleres_vs_empresas
--  Pregunta P3: ¿Dónde están los bachilleres del Ecuador
--  y cuántas empresas hay en cada provincia?
--
--  Fuente: silver_mineduc × silver_supercias_directorio × dim_geografia
--  Visualizaciones:
--    - Barras agrupadas: bachilleres 3ro BACH vs empresas activas por provincia
--    - Tabla: provincias con mayor ratio bachilleres/empresas
--    - KPI: total bachilleres 3ro año nacional
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_bachilleres_vs_empresas CASCADE;

CREATE OR REPLACE VIEW gold_bachilleres_vs_empresas AS
WITH bachilleres AS (
    -- Total de estudiantes en 3ro de Bachillerato por provincia
    SELECT
        g.provincia,
        g.cod_provincia,
        SUM(m.bach3_total)          AS total_bachilleres_3ro,
        SUM(m.total_estudiantes)    AS total_estudiantes_todos_niveles,
        COUNT(DISTINCT m.amie)      AS num_instituciones
    FROM silver_mineduc m
    JOIN dim_geografia g ON m.id_geo = g.id_geo
    -- Filtrar solo nivel Bachillerato
    WHERE LOWER(m.nivel_educacion) LIKE '%bachillerato%'
    GROUP BY g.provincia, g.cod_provincia
),
empresas AS (
    -- Total de empresas activas por provincia
    SELECT
        g.provincia,
        g.cod_provincia,
        COUNT(DISTINCT d.expediente)    AS total_empresas_activas,
        COUNT(DISTINCT d.ruc)           AS total_ruc_activos
    FROM silver_supercias_directorio d
    JOIN dim_geografia g ON d.id_geo = g.id_geo
    GROUP BY g.provincia, g.cod_provincia
)
SELECT
    COALESCE(b.provincia, e.provincia)          AS provincia,
    COALESCE(b.cod_provincia, e.cod_provincia)  AS cod_provincia,
    COALESCE(b.total_bachilleres_3ro, 0)        AS total_bachilleres_3ro,
    COALESCE(b.total_estudiantes_todos_niveles, 0) AS total_estudiantes,
    COALESCE(b.num_instituciones, 0)            AS num_instituciones,
    COALESCE(e.total_empresas_activas, 0)       AS total_empresas_activas,
    -- Ratio: bachilleres por empresa (indicador estratégico UTPL)
    CASE
        WHEN COALESCE(e.total_empresas_activas, 0) = 0 THEN NULL
        ELSE ROUND(
            COALESCE(b.total_bachilleres_3ro, 0)::NUMERIC
            / e.total_empresas_activas, 2
        )
    END AS ratio_bachilleres_por_empresa,
    -- Total nacional para KPI (mismo valor en todas las filas)
    SUM(COALESCE(b.total_bachilleres_3ro, 0)) OVER () AS total_nacional_bachilleres
FROM bachilleres b
FULL OUTER JOIN empresas e
    ON b.cod_provincia = e.cod_provincia
ORDER BY total_bachilleres_3ro DESC NULLS LAST;

COMMENT ON VIEW gold_bachilleres_vs_empresas IS
'P3 — Cruce MINEDUC × Supercias por provincia. Ratio bachilleres/empresas indica potencial demanda educación superior UTPL. Fuente: silver_mineduc + silver_supercias_directorio.';


-- ============================================================
--  VISTAS PROPIAS 6TO CICLO
--  Propuestas y justificadas por el estudiante.
--  Responden preguntas analíticas no cubiertas por las 4 base.
-- ============================================================

-- ────────────────────────────────────────────────────────────
--  VISTA 5 — gold_iee_vs_pib  [PROPIA 6TO CICLO]
--  Correlación entre expectativas empresariales y crecimiento del PIB
--
--  Justificación: el IEE es un indicador adelantado — mide expectativas
--  antes de que el PIB las refleje. Correlacionarlo con la variación
--  del PIB permite identificar si el sector empresarial ecuatoriano
--  anticipa correctamente los ciclos económicos.
--
--  Fuente: silver_iee × fact_macro_anual × dim_tiempo
--  Visualización sugerida:
--    - Línea dual: IEE global (mensual) vs variación PIB (anual)
--    - Scatter: IEE promedio anual vs variación PIB para ver correlación
--    - KPI: último IEE global y su interpretación (>50 optimista)
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_iee_vs_pib CASCADE;

CREATE OR REPLACE VIEW gold_iee_vs_pib AS
WITH iee_anual AS (
    -- Promediar IEE mensual por año para cruzar con PIB anual
    SELECT
        t.anio,
        ROUND(AVG(s.iee_global)::NUMERIC, 2)       AS iee_global_promedio,
        ROUND(AVG(s.iee_comercio)::NUMERIC, 2)     AS iee_comercio_promedio,
        ROUND(AVG(s.iee_manufactura)::NUMERIC, 2)  AS iee_manufactura_promedio,
        ROUND(AVG(s.iee_construccion)::NUMERIC, 2) AS iee_construccion_promedio,
        ROUND(AVG(s.iee_servicios)::NUMERIC, 2)    AS iee_servicios_promedio,
        COUNT(*)                                    AS meses_con_dato
    FROM silver_iee s
    JOIN dim_tiempo t ON s.id_tiempo = t.id_tiempo
    GROUP BY t.anio
),
pib_anual AS (
    SELECT
        t.anio,
        m.pib_real_musd,
        m.variacion_pib_pct,
        m.pib_percapita_nominal
    FROM fact_macro_anual m
    JOIN dim_tiempo t ON m.id_tiempo = t.id_tiempo
)
SELECT
    p.anio,
    p.pib_real_musd,
    p.variacion_pib_pct,
    p.pib_percapita_nominal,
    i.iee_global_promedio,
    i.iee_comercio_promedio,
    i.iee_manufactura_promedio,
    i.iee_construccion_promedio,
    i.iee_servicios_promedio,
    i.meses_con_dato,
    -- Señal adelantada: IEE del año anterior vs variación PIB actual
    LAG(i.iee_global_promedio) OVER (ORDER BY p.anio) AS iee_anio_anterior,
    -- Interpretación del IEE para el párrafo analítico del dashboard
    CASE
        WHEN i.iee_global_promedio > 55 THEN 'Optimismo alto'
        WHEN i.iee_global_promedio > 50 THEN 'Optimismo moderado'
        WHEN i.iee_global_promedio = 50 THEN 'Equilibrio'
        WHEN i.iee_global_promedio > 45 THEN 'Pesimismo moderado'
        WHEN i.iee_global_promedio IS NULL THEN NULL
        ELSE 'Pesimismo alto'
    END AS sentimiento_empresarial
FROM pib_anual p
LEFT JOIN iee_anual i ON p.anio = i.anio
-- IEE disponible desde 2010; antes de eso los campos IEE serán NULL
ORDER BY p.anio;

COMMENT ON VIEW gold_iee_vs_pib IS
'[PROPIA 6TO CICLO] Correlación IEE mensual vs variación PIB anual. El IEE como indicador adelantado del ciclo económico. Fuente: silver_iee + fact_macro_anual.';


-- ────────────────────────────────────────────────────────────
--  VISTA 6 — gold_vab_por_sector  [PROPIA 6TO CICLO]
--  Concentración del VAB por sector económico y provincia
--
--  Justificación: el VAB provincial permite identificar qué sectores
--  CIIU dominan la producción en cada provincia. Cruzado con el Censo
--  de actividad, responde si las provincias con mayor VAB también
--  concentran más empleo formal — información estratégica para P2.
--
--  Fuente: silver_vab × dim_geografia × dim_tiempo
--  Visualización sugerida:
--    - Mapa coroplético: VAB total por provincia (Power BI mapa)
--    - Barras apiladas: composición sectorial VAB por provincia top 10
--    - Línea: evolución VAB de las 5 provincias más grandes 2007-2024
-- ────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS gold_vab_por_sector CASCADE;

CREATE OR REPLACE VIEW gold_vab_por_sector AS
WITH vab_base AS (
    SELECT
        t.anio,
        g.provincia,
        g.cod_provincia,
        v.vab_miles_usd,
        -- Total VAB nacional ese año (para calcular participación %)
        SUM(v.vab_miles_usd) OVER (PARTITION BY t.anio) AS vab_nacional_anio
    FROM silver_vab v
    JOIN dim_tiempo     t ON v.id_tiempo = t.id_tiempo
    JOIN dim_geografia  g ON v.id_geo    = g.id_geo
)
SELECT
    anio,
    provincia,
    cod_provincia,
    ROUND(vab_miles_usd::NUMERIC, 2)            AS vab_miles_usd,
    ROUND(vab_nacional_anio::NUMERIC, 2)        AS vab_nacional_anio,
    -- Participación provincial en el VAB nacional
    ROUND(
        vab_miles_usd::NUMERIC / NULLIF(vab_nacional_anio, 0) * 100
    , 2)                                         AS participacion_pct,
    -- Ranking de provincia por VAB ese año
    RANK() OVER (
        PARTITION BY anio
        ORDER BY vab_miles_usd DESC
    )                                            AS ranking_provincia,
    -- Variación anual del VAB de la provincia
    ROUND(
        (vab_miles_usd
            - LAG(vab_miles_usd) OVER (PARTITION BY provincia ORDER BY anio))
        / NULLIF(
            LAG(vab_miles_usd) OVER (PARTITION BY provincia ORDER BY anio), 0
          ) * 100
    , 2)                                         AS variacion_anual_pct,
    -- VAB per cápita aproximado (requiere silver_pib_real para población)
    -- Se deja como referencia; calcular en pipeline.py si se necesita
    -- Clasificación de concentración para el análisis ejecutivo
    CASE
        WHEN vab_miles_usd / NULLIF(vab_nacional_anio, 0) > 0.20
            THEN 'Alta concentración (>20%)'
        WHEN vab_miles_usd / NULLIF(vab_nacional_anio, 0) > 0.10
            THEN 'Concentración media (10-20%)'
        WHEN vab_miles_usd / NULLIF(vab_nacional_anio, 0) > 0.05
            THEN 'Concentración baja (5-10%)'
        ELSE 'Concentración mínima (<5%)'
    END AS nivel_concentracion
FROM vab_base
ORDER BY anio DESC, vab_miles_usd DESC;

COMMENT ON VIEW gold_vab_por_sector IS
'[PROPIA 6TO CICLO] VAB por provincia con participación % y ranking. Alimenta mapa coroplético P2 y análisis de concentración económica. Fuente: silver_vab.';


-- ────────────────────────────────────────────────────────────
--  Verificación de las 6 vistas
-- ────────────────────────────────────────────────────────────
SELECT
    viewname                    AS vista,
    CASE
        WHEN viewname LIKE '%iee%' OR viewname LIKE '%vab%'
        THEN '6to ciclo (propia)'
        ELSE 'Base (reto)'
    END                         AS tipo
FROM pg_views
WHERE schemaname = 'public'
  AND viewname   LIKE 'gold_%'
ORDER BY viewname;