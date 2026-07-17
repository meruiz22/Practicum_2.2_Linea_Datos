-- ============================================================
--  sql/create_tables.sql
--  Proyecto: macroentorno_pipeline
--  Base de datos: macroentorno_ec (PostgreSQL 18)
--
--  ARQUITECTURA:
--  El RPA deposita los datos en TAB_CONSOLIDADO (Oracle).
--  Este script crea la misma tabla en PostgreSQL más las tablas
--  analíticas (expandidas del JSON) que alimentan el dashboard.
--
--  Tablas:
--    1. tab_consolidado      ← espejo de Oracle, recibe del RPA
--    2. dim_tiempo           ← dimensión temporal compartida
--    3. dim_geografia        ← dimensión geográfica compartida
--    4. pib_real             ← expandida de PIB_REAL_PER_CAPITA
--    5. pib_nominal          ← expandida de PIB_NOMINAL_PER_CAPITA
--    6. petroleo_riesgo      ← expandida de PRECIO_PETROLEO_WTI + RIESGO_PAIS
--    7. iee                  ← expandida de BCE_IEE_GLOBAL
--    8. enemdu               ← expandida de INEC_ENEMDU_POBLACIONES
--    9. vab_cantonal         ← expandida de VAB_CANTONAL_CIIU
--   10. matriz_empleo        ← expandida de MATRIZ_EMPLEO_VAB + MATRIZ_EMPLEO_TOTAL
--   11. censo_actividad      ← expandida de CENSO_RAMA_ACTIVIDAD
--   12. censo_ocupacion      ← expandida de CENSO_GRUPO_OCUPACION
--   13. mineduc_amie         ← expandida de MINEDUC_AMIE_COSTA
--   14. supercias_directorio ← expandida de SUPERCIAS_DIRECTORIO
--
--  Ejecutar:
--    psql -U marti -d macroentorno_ec -h localhost -f sql/create_tables.sql
-- ============================================================

-- ────────────────────────────────────────────────────────────
--  DROP en orden (tablas analíticas primero, luego dimensiones)
-- ────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS supercias_directorio CASCADE;
DROP TABLE IF EXISTS mineduc_amie         CASCADE;
DROP TABLE IF EXISTS censo_ocupacion      CASCADE;
DROP TABLE IF EXISTS censo_actividad      CASCADE;
DROP TABLE IF EXISTS matriz_empleo        CASCADE;
DROP TABLE IF EXISTS vab_cantonal         CASCADE;
DROP TABLE IF EXISTS enemdu               CASCADE;
DROP TABLE IF EXISTS iee                  CASCADE;
DROP TABLE IF EXISTS petroleo_riesgo      CASCADE;
DROP TABLE IF EXISTS pib_nominal          CASCADE;
DROP TABLE IF EXISTS pib_real             CASCADE;
DROP TABLE IF EXISTS dim_geografia        CASCADE;
DROP TABLE IF EXISTS dim_tiempo           CASCADE;
DROP TABLE IF EXISTS tab_consolidado      CASCADE;

-- ────────────────────────────────────────────────────────────
--  1. tab_consolidado
--     Espejo exacto de la TAB_CONSOLIDADO de Oracle.
--     El pipeline.py lee de esta tabla y expande los JSON
--     a las tablas analíticas de abajo.
--
--  Columnas del RPA:
--    INDICADOR       → nombre de la fuente (ej: PRECIO_PETROLEO_WTI)
--    FECHA_EXTRACCION→ cuándo el RPA extrajo el dato
--    ESTADO          → COMPLETO / INCOMPLETO
--    NECESITA_RESPALDO → 0 o 1
--    DETALLE_ERROR   → NULL si ok, texto si falló
--    DATOS_JSON      → el dato completo en JSON
--    DATO_CLAVE      → clave única por fila (fecha, código, etc.)
--    HASH_CONTENIDO  → MD5 del JSON para detectar cambios
-- ────────────────────────────────────────────────────────────
CREATE TABLE tab_consolidado (
    id                  BIGSERIAL       PRIMARY KEY,
    indicador           VARCHAR(50)     NOT NULL,
    fecha_extraccion    TIMESTAMP       NOT NULL DEFAULT NOW(),
    estado              VARCHAR(15)     NOT NULL CHECK (estado IN ('COMPLETO','INCOMPLETO')),
    necesita_respaldo   SMALLINT        NOT NULL DEFAULT 0,
    detalle_error       VARCHAR(4000),
    datos_json          JSONB           NOT NULL,
    dato_clave          VARCHAR(200)    NOT NULL,
    hash_contenido      VARCHAR(32)     NOT NULL,
    UNIQUE (indicador, dato_clave)
);

COMMENT ON TABLE  tab_consolidado IS 'Espejo de TAB_CONSOLIDADO Oracle. Recibe los datos del RPA vía pipeline.py. Una fila por (indicador, dato_clave).';
COMMENT ON COLUMN tab_consolidado.dato_clave      IS 'Clave única por fila. Ej: fecha para series diarias, cod_canton_ciiu para VAB.';
COMMENT ON COLUMN tab_consolidado.hash_contenido  IS 'MD5 del JSON. Si cambia → el RPA actualiza el registro.';
COMMENT ON COLUMN tab_consolidado.datos_json      IS 'JSONB permite indexar y consultar campos internos directamente en PostgreSQL.';

CREATE INDEX idx_tc_indicador       ON tab_consolidado(indicador);
CREATE INDEX idx_tc_fecha_ext       ON tab_consolidado(fecha_extraccion);
CREATE INDEX idx_tc_estado          ON tab_consolidado(estado);
CREATE INDEX idx_tc_dato_clave      ON tab_consolidado(dato_clave);
CREATE INDEX idx_tc_json            ON tab_consolidado USING gin(datos_json);

-- ────────────────────────────────────────────────────────────
--  2. dim_tiempo
--     Dimensión temporal compartida.
--     Alimentada automáticamente por pipeline.py al expandir JSONs.
-- ────────────────────────────────────────────────────────────
CREATE TABLE dim_tiempo (
    id_tiempo   SERIAL      PRIMARY KEY,
    fecha       DATE        NOT NULL UNIQUE,
    anio        INTEGER     NOT NULL,
    mes         INTEGER,                    -- NULL para registros anuales
    trimestre   INTEGER                     -- NULL para series no trimestrales
);

COMMENT ON TABLE dim_tiempo IS 'Dimensión temporal. Una fila por fecha única. Alimentada por pipeline.py.';

CREATE INDEX idx_dt_anio  ON dim_tiempo(anio);
CREATE INDEX idx_dt_fecha ON dim_tiempo(fecha);

-- ────────────────────────────────────────────────────────────
--  3. dim_geografia
--     Dimensión geográfica compartida.
--     Resuelve diferencias de escritura entre fuentes.
-- ────────────────────────────────────────────────────────────
CREATE TABLE dim_geografia (
    id_geo          SERIAL      PRIMARY KEY,
    provincia       VARCHAR(60) NOT NULL,
    cod_provincia   CHAR(2)     NOT NULL,
    canton          VARCHAR(80),
    cod_canton      CHAR(4),
    UNIQUE (cod_provincia, COALESCE(cod_canton, '0000'))
);

COMMENT ON TABLE dim_geografia IS 'Dimensión geográfica. Normaliza nombres entre BCE, INEC, Supercias y MINEDUC.';

CREATE INDEX idx_dg_provincia ON dim_geografia(cod_provincia);

-- ────────────────────────────────────────────────────────────
--  4. pib_real
--     Fuente RPA: PIB_REAL_PER_CAPITA
--     JSON: {anio_fiscal, pib_real_musd, poblacion,
--            pib_percapita, variacion_pct}
-- ────────────────────────────────────────────────────────────
CREATE TABLE pib_real (
    id              SERIAL      PRIMARY KEY,
    id_tiempo       INTEGER     NOT NULL REFERENCES dim_tiempo(id_tiempo),
    pib_musd        NUMERIC(14,4),
    poblacion       NUMERIC(14,4),
    pib_percapita   NUMERIC(12,4),
    variacion_pct   NUMERIC(8,4),           -- NULL en primer año
    fecha_extraccion TIMESTAMP,
    UNIQUE (id_tiempo)
);

COMMENT ON TABLE pib_real IS 'PIB real anual 1965-2024. Expandida de tab_consolidado WHERE indicador=PIB_REAL_PER_CAPITA.';

-- ────────────────────────────────────────────────────────────
--  5. pib_nominal
--     Fuente RPA: PIB_NOMINAL_PER_CAPITA
--     JSON: {anio_fiscal, pib_percapita_nominal_usd}
-- ────────────────────────────────────────────────────────────
CREATE TABLE pib_nominal (
    id                          SERIAL      PRIMARY KEY,
    id_tiempo                   INTEGER     NOT NULL REFERENCES dim_tiempo(id_tiempo),
    pib_percapita_nominal_usd   NUMERIC(12,2),
    fecha_extraccion            TIMESTAMP,
    UNIQUE (id_tiempo)
);

COMMENT ON TABLE pib_nominal IS 'PIB per cápita nominal anual 2000-2025. Expandida de tab_consolidado WHERE indicador=PIB_NOMINAL_PER_CAPITA.';

-- ────────────────────────────────────────────────────────────
--  6. petroleo_riesgo
--     Fuentes RPA: PRECIO_PETROLEO_WTI + RIESGO_PAIS
--     JSON WTI:    {fecha_fiscal, valor, medida, fuente}
--     JSON Riesgo: {fecha_fiscal, valor, medida, fuente}
--     Merge por fecha → NULLs documentados
-- ────────────────────────────────────────────────────────────
CREATE TABLE petroleo_riesgo (
    id                  SERIAL      PRIMARY KEY,
    id_tiempo           INTEGER     NOT NULL REFERENCES dim_tiempo(id_tiempo),
    precio_wti          NUMERIC(10,4),   -- NULL antes de 2015-01-02
    riesgo_pais_pb      INTEGER,         -- NULL antes de 2004-07-29
    fecha_extraccion    TIMESTAMP,
    UNIQUE (id_tiempo)
);

COMMENT ON TABLE petroleo_riesgo IS 'Precio WTI diario y riesgo país EMBI. Merge de PRECIO_PETROLEO_WTI + RIESGO_PAIS. NULLs documentados por rango de cada fuente.';

CREATE INDEX idx_pr_tiempo ON petroleo_riesgo(id_tiempo);

-- ────────────────────────────────────────────────────────────
--  7. iee
--     Fuente RPA: BCE_IEE_GLOBAL
--     JSON: {periodo_fiscal, fecha_publicacion,
--            metricas:{iee_global, comercio, construccion,
--                      manufactura, servicios}}
-- ────────────────────────────────────────────────────────────
CREATE TABLE iee (
    id                  SERIAL      PRIMARY KEY,
    id_tiempo           INTEGER     NOT NULL REFERENCES dim_tiempo(id_tiempo),
    iee_global          NUMERIC(6,2),
    iee_comercio        NUMERIC(6,2),
    iee_construccion    NUMERIC(6,2),
    iee_manufactura     NUMERIC(6,2),
    iee_servicios       NUMERIC(6,2),
    fecha_extraccion    TIMESTAMP,
    UNIQUE (id_tiempo)
);

COMMENT ON TABLE iee IS 'IEE Expectativas Empresariales mensual 2010-2026. Expandida de BCE_IEE_GLOBAL.';

-- ────────────────────────────────────────────────────────────
--  8. enemdu
--     Fuente RPA: INEC_ENEMDU_POBLACIONES
--     JSON: {encuesta, periodo_original, anio_fiscal, mes_fiscal,
--            nombre_indicador,
--            metricas:{nacional_total, area_urbana, area_rural,
--                      sexo_hombre, sexo_mujer}}
--     Formato long: una fila por (periodo, indicador)
-- ────────────────────────────────────────────────────────────
CREATE TABLE enemdu (
    id                  SERIAL      PRIMARY KEY,
    id_tiempo           INTEGER     NOT NULL REFERENCES dim_tiempo(id_tiempo),
    periodo_original    VARCHAR(10),        -- ej: 'mar-19'
    nombre_indicador    VARCHAR(120) NOT NULL,
    nacional_total      NUMERIC(14,2),
    area_urbana         NUMERIC(14,2),
    area_rural          NUMERIC(14,2),
    sexo_hombre         NUMERIC(14,2),
    sexo_mujer          NUMERIC(14,2),
    fecha_extraccion    TIMESTAMP,
    UNIQUE (id_tiempo, nombre_indicador)
);

COMMENT ON TABLE  enemdu IS 'Indicadores ENEMDU en formato long. Una fila por (periodo, indicador). Expandida de INEC_ENEMDU_POBLACIONES.';
COMMENT ON COLUMN enemdu.nombre_indicador IS 'Ej: "Población en Edad de Trabajar (PET)", "Empleo Adecuado (%)"';

CREATE INDEX idx_enemdu_indicador ON enemdu(nombre_indicador);

-- ────────────────────────────────────────────────────────────
--  9. vab_cantonal
--     Fuente RPA: VAB_CANTONAL_CIIU
--     JSON: {anio, codigo_provincia, provincia, codigo_canton,
--            canton, sectores:{agricultura, minas, manufactura, ...}}
--     Formato long: una fila por (anio, canton, sector)
-- ────────────────────────────────────────────────────────────
CREATE TABLE vab_cantonal (
    id                  SERIAL      PRIMARY KEY,
    id_tiempo           INTEGER     REFERENCES dim_tiempo(id_tiempo),  -- NULL si anio=null en JSON
    id_geo              INTEGER     NOT NULL REFERENCES dim_geografia(id_geo),
    sector              VARCHAR(80) NOT NULL,   -- nombre del sector CIIU
    vab_miles_usd       NUMERIC(16,4),
    fecha_extraccion    TIMESTAMP,
    UNIQUE (id_tiempo, id_geo, sector)
);

COMMENT ON TABLE  vab_cantonal IS 'VAB por cantón y sector CIIU. Formato long: una fila por (anio, canton, sector). Expandida de VAB_CANTONAL_CIIU.';
COMMENT ON COLUMN vab_cantonal.id_tiempo IS 'NULL cuando el JSON del RPA tiene anio=null (datos sin año asignado).';

CREATE INDEX idx_vab_geo    ON vab_cantonal(id_geo);
CREATE INDEX idx_vab_sector ON vab_cantonal(sector);

-- ────────────────────────────────────────────────────────────
-- 10. matriz_empleo
--     Fuentes RPA: MATRIZ_EMPLEO_VAB + MATRIZ_EMPLEO_TOTAL
--     JSON: {anio, codigo_cie, seccion, industria, valor, unidad}
-- ────────────────────────────────────────────────────────────
CREATE TABLE matriz_empleo (
    id                  SERIAL      PRIMARY KEY,
    id_tiempo           INTEGER     NOT NULL REFERENCES dim_tiempo(id_tiempo),
    codigo_cie          VARCHAR(10),
    seccion             VARCHAR(100),
    industria           VARCHAR(150),
    valor               NUMERIC(16,2),
    unidad              VARCHAR(50),    -- 'Miles de USD' o 'Número de personas'
    tipo                VARCHAR(20),    -- 'VAB' o 'EMPLEO_TOTAL'
    fecha_extraccion    TIMESTAMP,
    UNIQUE (id_tiempo, codigo_cie, tipo)
);

COMMENT ON TABLE  matriz_empleo IS 'Matriz de empleo por industria. Combina VAB (Miles de USD) y empleo total (personas). Expandida de MATRIZ_EMPLEO_VAB + MATRIZ_EMPLEO_TOTAL.';
COMMENT ON COLUMN matriz_empleo.tipo IS 'VAB = producción en miles USD | EMPLEO_TOTAL = número de personas empleadas.';

CREATE INDEX idx_me_industria ON matriz_empleo(industria);
CREATE INDEX idx_me_tipo      ON matriz_empleo(tipo);

-- ────────────────────────────────────────────────────────────
-- 11. censo_actividad
--     Fuente RPA: CENSO_RAMA_ACTIVIDAD
--     JSON: {anio_censo, provincia, canton, sexo, rango_edad,
--            total_ocupados, ramas_actividad:{...}}
--     Formato long: una fila por (canton, sexo, edad, rama)
-- ────────────────────────────────────────────────────────────
CREATE TABLE censo_actividad (
    id                  SERIAL      PRIMARY KEY,
    id_geo              INTEGER     NOT NULL REFERENCES dim_geografia(id_geo),
    anio_censo          INTEGER     NOT NULL DEFAULT 2022,
    sexo                VARCHAR(20),
    rango_edad          VARCHAR(20),
    rama_actividad      VARCHAR(80) NOT NULL,
    personas_ocupadas   INTEGER,
    fecha_extraccion    TIMESTAMP,
    UNIQUE (id_geo, sexo, rango_edad, rama_actividad)
);

COMMENT ON TABLE censo_actividad IS 'Ocupados por rama de actividad CIIU, cantón, sexo y edad. Censo 2022. Expandida de CENSO_RAMA_ACTIVIDAD.';

CREATE INDEX idx_ca_geo  ON censo_actividad(id_geo);
CREATE INDEX idx_ca_rama ON censo_actividad(rama_actividad);

-- ────────────────────────────────────────────────────────────
-- 12. censo_ocupacion
--     Fuente RPA: CENSO_GRUPO_OCUPACION
--     JSON: {anio_censo, provincia, canton, sexo, rango_edad,
--            total_ocupados, grupos_ocupacion:{...}}
-- ────────────────────────────────────────────────────────────
CREATE TABLE censo_ocupacion (
    id                  SERIAL      PRIMARY KEY,
    id_geo              INTEGER     NOT NULL REFERENCES dim_geografia(id_geo),
    anio_censo          INTEGER     NOT NULL DEFAULT 2022,
    sexo                VARCHAR(20),
    rango_edad          VARCHAR(20),
    grupo_ocupacion     VARCHAR(80) NOT NULL,
    personas            INTEGER,
    fecha_extraccion    TIMESTAMP,
    UNIQUE (id_geo, sexo, rango_edad, grupo_ocupacion)
);

COMMENT ON TABLE censo_ocupacion IS 'Ocupados por grupo de ocupación, cantón, sexo y edad. Censo 2022. Expandida de CENSO_GRUPO_OCUPACION.';

-- ────────────────────────────────────────────────────────────
-- 13. mineduc_amie
--     Fuente RPA: MINEDUC_AMIE_COSTA
--     JSON: {periodo_lectivo, anio_base, institucion:{amie, nombre,
--            zona, provincia, canton, parroquia, ...},
--            estudiantes:{total, bach_3ro_total, ...}}
-- ────────────────────────────────────────────────────────────
CREATE TABLE mineduc_amie (
    id                      SERIAL      PRIMARY KEY,
    id_geo                  INTEGER     NOT NULL REFERENCES dim_geografia(id_geo),
    periodo_lectivo         VARCHAR(20),
    anio_base               INTEGER,
    amie                    VARCHAR(10) NOT NULL,
    nombre_institucion      VARCHAR(250),
    zona                    VARCHAR(20),
    parroquia               VARCHAR(80),
    nivel_educacion         VARCHAR(80),
    sostenimiento           VARCHAR(30),
    total_estudiantes       INTEGER,
    bach3_total             INTEGER,    -- 3ro bachillerato total
    bach3_femenino          INTEGER,
    bach3_masculino         INTEGER,
    fecha_extraccion        TIMESTAMP,
    UNIQUE (amie, periodo_lectivo)
);

COMMENT ON TABLE  mineduc_amie IS 'Registros AMIE por institución educativa. Expandida de MINEDUC_AMIE_COSTA. Una fila por (institución, período lectivo).';
COMMENT ON COLUMN mineduc_amie.bach3_total IS 'Estudiantes en 3ro de Bachillerato. Clave para gold_bachilleres_vs_empresas.';

CREATE INDEX idx_ma_geo    ON mineduc_amie(id_geo);
CREATE INDEX idx_ma_nivel  ON mineduc_amie(nivel_educacion);

-- ────────────────────────────────────────────────────────────
-- 14. supercias_directorio
--     Fuente RPA: SUPERCIAS_DIRECTORIO
--     JSON: {periodo_reporte, empresa_metadata:{expediente, ruc,
--            nombre, situacion_legal, tipo_compania, ...},
--            ubicacion:{provincia, canton, ...},
--            financiero_ciiu:{ciiu_nivel1, ciiu_nivel6, ...}}
-- ────────────────────────────────────────────────────────────
CREATE TABLE supercias_directorio (
    id                  SERIAL      PRIMARY KEY,
    id_geo              INTEGER     NOT NULL REFERENCES dim_geografia(id_geo),
    periodo_reporte     VARCHAR(10),            -- ej: '2026-07'
    expediente          BIGINT      NOT NULL,
    ruc                 CHAR(13),
    nombre              VARCHAR(250),
    situacion_legal     VARCHAR(20),
    tipo_compania       VARCHAR(80),
    ciiu_nivel1         VARCHAR(5),
    ciiu_nivel6         VARCHAR(10),
    capital_suscrito    NUMERIC(16,2),
    ultimo_balance_anio INTEGER,
    fecha_extraccion    TIMESTAMP,
    UNIQUE (expediente, periodo_reporte)
);

COMMENT ON TABLE  supercias_directorio IS 'Directorio de compañías activas. Expandida de SUPERCIAS_DIRECTORIO. Una fila por (expediente, periodo_reporte).';
COMMENT ON COLUMN supercias_directorio.periodo_reporte IS 'Mes de corte del reporte Supercias. Ej: 2026-07.';

CREATE INDEX idx_sd_geo        ON supercias_directorio(id_geo);
CREATE INDEX idx_sd_expediente ON supercias_directorio(expediente);
CREATE INDEX idx_sd_ciiu       ON supercias_directorio(ciiu_nivel1);
CREATE INDEX idx_sd_periodo    ON supercias_directorio(periodo_reporte);

-- ────────────────────────────────────────────────────────────
--  Verificación final
-- ────────────────────────────────────────────────────────────
SELECT
    tablename                                                           AS tabla,
    pg_size_pretty(pg_total_relation_size(quote_ident(tablename)))     AS tamaño
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;

-- Resultado esperado (14 tablas):
-- censo_actividad | censo_ocupacion | dim_geografia | dim_tiempo
-- enemdu | iee | matriz_empleo | mineduc_amie | petroleo_riesgo
-- pib_nominal | pib_real | supercias_directorio | tab_consolidado | vab_cantonal