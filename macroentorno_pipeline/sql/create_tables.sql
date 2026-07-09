-- ============================================================
--  sql/create_tables.sql
--  Proyecto: macroentorno_pipeline
-- ============================================================

-- ────────────────────────────────────────────────────────────
--  DROP en orden inverso de dependencias (idempotente)
--  Primero las tablas que tienen FK, luego las dimensiones
-- ────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS silver_mineduc              CASCADE;
DROP TABLE IF EXISTS silver_supercias_ranking    CASCADE;
DROP TABLE IF EXISTS silver_supercias_directorio CASCADE;
DROP TABLE IF EXISTS silver_censo                CASCADE;
DROP TABLE IF EXISTS silver_enemdu               CASCADE;
DROP TABLE IF EXISTS silver_iee                  CASCADE;
DROP TABLE IF EXISTS silver_petroleo_riesgo      CASCADE;
DROP TABLE IF EXISTS silver_vab                  CASCADE;
DROP TABLE IF EXISTS silver_pib_nominal          CASCADE;
DROP TABLE IF EXISTS silver_pib_real             CASCADE;
DROP TABLE IF EXISTS fact_macro_anual            CASCADE;
DROP TABLE IF EXISTS fact_empleo                 CASCADE;
-- Dimensiones al final porque las tablas anteriores apuntan a ellas
DROP TABLE IF EXISTS dim_geografia               CASCADE;
DROP TABLE IF EXISTS dim_tiempo                  CASCADE;

-- ────────────────────────────────────────────────────────────
--  DIMENSIONES COMPARTIDAS
--  Se crean primero porque las tablas de hechos las referencian
-- ────────────────────────────────────────────────────────────

-- dim_tiempo
-- Normaliza el tiempo en una sola fuente de verdad.
-- 7 tablas apuntan aquí con FK:
--   fact_macro_anual, fact_empleo, silver_pib_real,
--   silver_petroleo_riesgo, silver_iee, silver_vab, silver_enemdu
CREATE TABLE dim_tiempo (
    id_tiempo   SERIAL      PRIMARY KEY,
    fecha       DATE        NOT NULL UNIQUE,
    anio        INTEGER     NOT NULL,   -- año — filtro principal del dashboard
    mes         INTEGER,                -- 1-12 (NULL para registros anuales)
    trimestre   INTEGER                 -- 1-4  (NULL para registros anuales/mensuales)
);

COMMENT ON TABLE  dim_tiempo IS 'Dimensión temporal compartida. Una fila por fecha única. 7 tablas apuntan aquí con FK.';
COMMENT ON COLUMN dim_tiempo.mes       IS 'NULL para series anuales (silver_pib_real, silver_vab, fact_macro_anual).';
COMMENT ON COLUMN dim_tiempo.trimestre IS 'NULL para series anuales y mensuales. Poblado para ENEMDU trimestral.';

-- dim_geografia
-- Normaliza nombres de provincias y cantones entre fuentes.
-- Resuelve que BCE escriba "Pichincha" y MINEDUC "PICHINCHA".
-- 5 tablas apuntan aquí con FK:
--   silver_vab, silver_supercias_ranking, silver_supercias_directorio,
--   silver_mineduc, silver_censo
CREATE TABLE dim_geografia (
    id_geo          SERIAL      PRIMARY KEY,
    provincia       VARCHAR(60) NOT NULL,   -- nombre normalizado title case
    cod_provincia   CHAR(2)     NOT NULL,   -- código INEC con zfill(2)
    canton          VARCHAR(80),            -- nombre del cantón (NULL si solo provincia)
    cod_canton      CHAR(4),                -- código INEC con zfill(4)
    UNIQUE (cod_provincia, cod_canton)
);

COMMENT ON TABLE  dim_geografia IS 'Dimensión geográfica compartida. Normaliza nombres entre BCE, INEC, Supercias y MINEDUC. 5 tablas apuntan aquí con FK.';
COMMENT ON COLUMN dim_geografia.cod_provincia IS 'Código INEC con zfill(2). Ej: "01" = Azuay.';
COMMENT ON COLUMN dim_geografia.canton        IS 'NULL cuando el registro es solo a nivel provincial.';

-- ────────────────────────────────────────────────────────────
--  TABLAS FACT (agregadas — alimentan directamente las vistas Gold)
-- ────────────────────────────────────────────────────────────

-- fact_macro_anual
-- Consolida los indicadores macroeconómicos anuales nacionales.
-- Alimenta: gold_pib_tendencia (P1 dashboard)
CREATE TABLE fact_macro_anual (
    id_tiempo       INTEGER     PRIMARY KEY REFERENCES dim_tiempo(id_tiempo),
    pib_musd        NUMERIC(14,4),
    pib_percapita   NUMERIC(12,4),
    variacion_pct   NUMERIC(8,4),
    pib_percapita_nominal_usd NUMERIC(12,2)
);

COMMENT ON TABLE fact_macro_anual IS 'Indicadores macroeconómicos anuales consolidados. Fuente: silver_pib_real + silver_pib_nominal. Alimenta gold_pib_tendencia.';

-- fact_empleo
-- Indicadores laborales ENEMDU nacionales/urbanos/rurales.
-- Sin FK a dim_geografia: ENEMDU no tiene desagregación provincial.
-- Alimenta: gold_empleo_tendencia (P2 dashboard)
CREATE TABLE fact_empleo (
    id              SERIAL      PRIMARY KEY,
    id_tiempo       INTEGER     NOT NULL REFERENCES dim_tiempo(id_tiempo),
    encuesta        VARCHAR(20),
    periodo         VARCHAR(10),
    indicador       VARCHAR(120) NOT NULL,
    total_nacional  NUMERIC(10,6),
    total_urbana    NUMERIC(10,6),
    total_rural     NUMERIC(10,6),
    UNIQUE (id_tiempo, indicador)
);

COMMENT ON TABLE  fact_empleo IS 'Indicadores ENEMDU en formato long. Sin FK a dim_geografia (ENEMDU es nacional/urbano/rural, no provincial).';
COMMENT ON COLUMN fact_empleo.indicador IS 'Ej: "Empleo Adecuado/Pleno (%)", "Desempleo (%)".';

-- ────────────────────────────────────────────────────────────
--  1. silver_pib_real
--     Fuente: retropolacion_1965_2024p.xlsx | Hoja: PIB pc nominal
--     Granularidad: anual (1965–2024)
-- ────────────────────────────────────────────────────────────
CREATE TABLE silver_pib_real (
    anio            INTEGER         PRIMARY KEY,
    pib_musd        NUMERIC(14,4),      -- PIB en millones de USD
    poblacion       NUMERIC(14,4),      -- Población en miles
    pib_percapita   NUMERIC(12,4),      -- PIB per cápita en USD
    variacion_pct   NUMERIC(8,4)        -- Variación anual % (NaN en 1965 → NULL)
);

COMMENT ON TABLE  silver_pib_real IS 'PIB real anual Ecuador 1965-2024. Fuente: BCE retropolación.';
COMMENT ON COLUMN silver_pib_real.variacion_pct IS 'NULL en 1965 por ausencia de año anterior. Correcto.';

-- ────────────────────────────────────────────────────────────
--  2. silver_pib_nominal
--     Fuente: pib-per-cpita-nominal.csv
--     Granularidad: anual (2000–2025)
-- ────────────────────────────────────────────────────────────
CREATE TABLE silver_pib_nominal (
    fecha                       DATE        PRIMARY KEY,
    anio                        INTEGER     NOT NULL,
    pib_percapita_nominal_usd   NUMERIC(12,2)
);

COMMENT ON TABLE silver_pib_nominal IS 'PIB per cápita nominal anual 2000-2025. Fuente: BCE.';

-- ────────────────────────────────────────────────────────────
--  3. silver_vab
--     Fuente: Boletin_retropolacion_regionales_2007_2024p_val.xlsx
--     Granularidad: anual × provincial (28 provincias × 18 años = 504 filas)
-- ────────────────────────────────────────────────────────────
CREATE TABLE silver_vab (
    id              SERIAL          PRIMARY KEY,
    anio            INTEGER         NOT NULL,
    cod_provincia   CHAR(2)         NOT NULL,
    provincia       VARCHAR(60)     NOT NULL,
    vab_miles_usd   NUMERIC(16,6),          -- VAB en miles de USD
    UNIQUE (anio, cod_provincia)
);

COMMENT ON TABLE  silver_vab IS 'VAB provincial anual 2007-2024. Fuente: BCE Cuentas Regionales.';
COMMENT ON COLUMN silver_vab.vab_miles_usd IS 'Valor en miles de USD constantes. No convertir para respetar escala original.';

-- ────────────────────────────────────────────────────────────
--  4. silver_petroleo_riesgo
--     Fuentes: petroleo_wti.csv + petroleo_crudo_ecu.csv + riesgo_pais.csv
--     Granularidad: diaria (merge outer)
--     NULLs documentados:
--       precio_petroleo_wti = NULL antes de 2015-01-02
--       riesgo_pais_pb      = NULL antes de 2004-07-29
--       precio_crudo_ecu    = NULL en días sin dato mensual (serie mensual)
-- ────────────────────────────────────────────────────────────
CREATE TABLE silver_petroleo_riesgo (
    fecha                   DATE        PRIMARY KEY,
    precio_petroleo_wti     NUMERIC(10,4),  -- USD por barril (diario, desde 2015)
    precio_crudo_ecu        NUMERIC(10,4),  -- USD por barril (mensual, desde 2000)
    riesgo_pais_pb          NUMERIC(8,2)    -- Puntos básicos EMBI (diario, desde 2004)
);

COMMENT ON TABLE  silver_petroleo_riesgo IS 'Precios petróleo y riesgo país EMBI. Fuente: BCE Sector Externo.';
COMMENT ON COLUMN silver_petroleo_riesgo.precio_petroleo_wti IS 'NULL antes de 2015-01-02. Límite del portal BCE.';
COMMENT ON COLUMN silver_petroleo_riesgo.precio_crudo_ecu    IS 'Serie mensual. NULL en fechas diarias sin dato.';
COMMENT ON COLUMN silver_petroleo_riesgo.riesgo_pais_pb      IS 'NULL antes de 2004-07-29. Valores negativos reemplazados por NULL.';

-- ────────────────────────────────────────────────────────────
--  5. silver_iee
--     Fuente: IEE_Nueva_Metodologia.xlsx
--     Granularidad: mensual (2010-02 → 2026-04)
-- ────────────────────────────────────────────────────────────
CREATE TABLE silver_iee (
    fecha               DATE        PRIMARY KEY,
    iee_global          NUMERIC(6,2),   -- Índice global (base 50 = equilibrio)
    iee_comercio        NUMERIC(6,2),
    iee_construccion    NUMERIC(6,2),
    iee_manufactura     NUMERIC(6,2),
    iee_servicios       NUMERIC(6,2)
);

COMMENT ON TABLE  silver_iee IS 'IEE Expectativas Empresariales mensual. Fuente: BCE Encuestas. Nueva metodología desde 2023, serie recalculada homogénea desde 2010-02.';
COMMENT ON COLUMN silver_iee.iee_global IS 'Base 50 = equilibrio. >50 optimista, <50 pesimista. Rango válido [0,200].';

-- ────────────────────────────────────────────────────────────
--  6. silver_enemdu
--     Fuente: 202605_Tabulados_Mercado_Laboral_EXCEL.XLSX | Hoja: 2. Tasas
--     Granularidad: trimestral/semestral (dic-07 → actualidad)
--     Formato long: una fila por (fecha, indicador)
-- ────────────────────────────────────────────────────────────
CREATE TABLE silver_enemdu (
    id              SERIAL          PRIMARY KEY,
    fecha           DATE            NOT NULL,
    anio            INTEGER         NOT NULL,
    encuesta        VARCHAR(20),
    periodo         VARCHAR(10),            -- 'dic-07', 'jun-08', etc.
    indicador       VARCHAR(120)    NOT NULL,
    total_nacional  NUMERIC(10,6),
    total_urbana    NUMERIC(10,6),
    total_rural     NUMERIC(10,6),
    UNIQUE (fecha, indicador)
);

COMMENT ON TABLE  silver_enemdu IS 'Indicadores laborales ENEMDU en formato long. Fuente: INEC. Sin desagregación provincial (ENEMDU es nacional/urbano/rural).';
COMMENT ON COLUMN silver_enemdu.indicador IS 'Ej: "Empleo Adecuado/Pleno (%)", "Desempleo (%)", etc.';

-- ────────────────────────────────────────────────────────────
--  7. silver_censo
--     Fuente: CPV_2022_Población_Cantón.csv (Censo 2022)
--     Granularidad: cantonal (corte único 2022)
-- ────────────────────────────────────────────────────────────
CREATE TABLE silver_censo (
    id              SERIAL          PRIMARY KEY,
    provincia       VARCHAR(60),
    canton          VARCHAR(80),
    ciiu            VARCHAR(10),    -- Rama de actividad económica CIIU
    sexo            VARCHAR(20),
    personas        NUMERIC(12,0),
    anio_censo      INTEGER         DEFAULT 2022
);

COMMENT ON TABLE silver_censo IS 'Censo de Población y Vivienda 2022. Datos por cantón y rama de actividad. Fuente: INEC censoecuador.gob.ec.';

-- ────────────────────────────────────────────────────────────
--  8. silver_supercias_directorio
--     Fuente: bi_compania.csv
--     ~338k empresas activas con EEFF presentados
-- ────────────────────────────────────────────────────────────
CREATE TABLE silver_supercias_directorio (
    expediente      BIGINT          PRIMARY KEY,
    ruc             CHAR(13)        NOT NULL,
    nombre          VARCHAR(250),
    tipo            VARCHAR(80),
    pro_codigo      CHAR(2),        -- Código provincia (zfill 2, coincide con silver_vab)
    provincia       VARCHAR(60)
);

COMMENT ON TABLE  silver_supercias_directorio IS 'Directorio de compañías activas. Fuente: Supercias bi_compania.csv. Actualización diaria.';
COMMENT ON COLUMN silver_supercias_directorio.pro_codigo IS 'Código provincia con zfill(2). Permite JOIN con silver_vab.cod_provincia.';

-- ────────────────────────────────────────────────────────────
--  9. silver_supercias_ranking
--     Fuente: bi_ranking.csv
--     ~1.67M filas | años 2008–2025 | 54 indicadores financieros
-- ────────────────────────────────────────────────────────────
CREATE TABLE silver_supercias_ranking (
    id                      SERIAL          PRIMARY KEY,
    anio                    INTEGER,
    expediente              BIGINT,
    posicion_general        INTEGER,
    ingresos_ventas         NUMERIC(20,4),
    activos                 NUMERIC(20,4),
    patrimonio              NUMERIC(20,4),
    utilidad_an_imp         NUMERIC(20,4),
    impuesto_renta          NUMERIC(20,4),
    n_empleados             NUMERIC(10,0),
    ingresos_totales        NUMERIC(20,4),
    utilidad_ejercicio      NUMERIC(20,4),
    utilidad_neta           NUMERIC(20,4),
    cod_segmento            VARCHAR(10),
    ciiu_n1                 VARCHAR(5),
    ciiu_n6                 VARCHAR(10),
    -- Indicadores financieros adicionales
    liquidez_corriente      NUMERIC(14,6),
    prueba_acida            NUMERIC(14,6),
    roe                     NUMERIC(14,6),
    roa                     NUMERIC(14,6),
    margen_bruto            NUMERIC(14,6),
    margen_operacional      NUMERIC(14,6),
    rent_neta_ventas        NUMERIC(14,6),
    deuda_total             NUMERIC(20,4),
    UNIQUE (anio, expediente)
);

COMMENT ON TABLE  silver_supercias_ranking IS 'Ranking financiero de compañías 2008-2025. Fuente: Supercias bi_ranking.csv. 1.67M filas.';
COMMENT ON COLUMN silver_supercias_ranking.ciiu_n1 IS 'CIIU nivel 1 (sector). String para preservar ceros.';
COMMENT ON COLUMN silver_supercias_ranking.ciiu_n6 IS 'CIIU nivel 6 (actividad específica).';

-- ────────────────────────────────────────────────────────────
-- 10. silver_mineduc
--     Fuente: 2_MINEDUC_RegistrosAdministrativos_2023-2024-Fin-1.csv
--     Granularidad: institución educativa (16.206 filas)
-- ────────────────────────────────────────────────────────────
CREATE TABLE silver_mineduc (
    id                      SERIAL          PRIMARY KEY,
    ao_lectivo              VARCHAR(20),
    amie                    VARCHAR(10),    -- Código único de institución
    nombre_institucion      VARCHAR(250),
    zona                    VARCHAR(20),
    provincia               VARCHAR(60),
    cod_provincia           CHAR(2),
    canton                  VARCHAR(80),
    cod_canton              CHAR(4),
    parroquia               VARCHAR(80),
    tipo_educacion          VARCHAR(40),
    nivel_educacion         VARCHAR(80),
    sostenimiento           VARCHAR(30),
    total_docentes          NUMERIC(8,0),
    total_estudiantes       NUMERIC(10,0),
    estudiantes_femenino    NUMERIC(10,0),
    estudiantes_masculino   NUMERIC(10,0),
    -- 3ro de Bachillerato (los más importantes para gold_bachilleres_vs_empresas)
    bach3_femenino          NUMERIC(8,0),
    bach3_masculino         NUMERIC(8,0),
    bach3_total             NUMERIC(8,0),   -- Calculado: femenino + masculino
    bach3_fem_promovidos    NUMERIC(8,0),
    bach3_masc_promovidos   NUMERIC(8,0),
    bach3_fem_no_promovidos NUMERIC(8,0),
    bach3_masc_no_promovidos NUMERIC(8,0),
    bach3_fem_abandono      NUMERIC(8,0),
    bach3_masc_abandono     NUMERIC(8,0)
);

COMMENT ON TABLE  silver_mineduc IS 'Registros administrativos AMIE 2023-2024 Fin. Fuente: MINEDUC. Una fila por institución.';
COMMENT ON COLUMN silver_mineduc.bach3_total IS 'bach3_femenino + bach3_masculino. NULL si ambos son NULL.';
COMMENT ON COLUMN silver_mineduc.nivel_educacion IS 'No filtrado aquí. Filtrar Bachillerato en vistas Gold.';

-- ────────────────────────────────────────────────────────────
--  Índices para mejorar rendimiento de las vistas Gold
-- ────────────────────────────────────────────────────────────
-- Dimensiones
CREATE INDEX idx_tiempo_anio         ON dim_tiempo(anio);
CREATE INDEX idx_tiempo_fecha        ON dim_tiempo(fecha);
CREATE INDEX idx_geo_cod_provincia   ON dim_geografia(cod_provincia);
CREATE INDEX idx_geo_provincia       ON dim_geografia(provincia);

-- Tablas fact
CREATE INDEX idx_fact_empleo_tiempo  ON fact_empleo(id_tiempo);
CREATE INDEX idx_fact_empleo_ind     ON fact_empleo(indicador);

-- Silver
CREATE INDEX idx_vab_anio           ON silver_vab(anio);
CREATE INDEX idx_vab_provincia      ON silver_vab(cod_provincia);
CREATE INDEX idx_petroleo_fecha     ON silver_petroleo_riesgo(fecha);
CREATE INDEX idx_iee_fecha          ON silver_iee(fecha);
CREATE INDEX idx_enemdu_fecha       ON silver_enemdu(fecha);
CREATE INDEX idx_enemdu_indicador   ON silver_enemdu(indicador);
CREATE INDEX idx_ranking_anio       ON silver_supercias_ranking(anio);
CREATE INDEX idx_ranking_expediente ON silver_supercias_ranking(expediente);
CREATE INDEX idx_ranking_ciiu       ON silver_supercias_ranking(ciiu_n1);
CREATE INDEX idx_directorio_prov    ON silver_supercias_directorio(pro_codigo);
CREATE INDEX idx_mineduc_provincia  ON silver_mineduc(cod_provincia);
CREATE INDEX idx_mineduc_nivel      ON silver_mineduc(nivel_educacion);
CREATE INDEX idx_censo_provincia    ON silver_censo(provincia);

-- ────────────────────────────────────────────────────────────
--  Verificación final
-- ────────────────────────────────────────────────────────────
SELECT
    tablename                                                           AS tabla,
    pg_size_pretty(pg_total_relation_size(quote_ident(tablename)))     AS tamaño
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;

