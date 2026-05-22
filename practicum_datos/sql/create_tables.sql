-- =============================================================
-- sql/create_tables.sql
-- DDL del modelo relacional AMIE — MINEDUC Ecuador
-- Prácticum Datos · 6to ciclo
-- Basado en: registro-administrativo-historico_2009-2024-inicio.xlsx
-- =============================================================

DROP TABLE IF EXISTS fact_matricula   CASCADE;
DROP TABLE IF EXISTS dim_institucion  CASCADE;
DROP TABLE IF EXISTS dim_ubicacion    CASCADE;


-- -------------------------------------------------------------
-- 1. dim_ubicacion
--    Combinaciones únicas de campos geográficos.
-- -------------------------------------------------------------
CREATE TABLE dim_ubicacion (
    id_ubicacion    SERIAL          PRIMARY KEY,
    provincia       VARCHAR(80)     NOT NULL,
    cod_provincia   CHAR(2),
    canton          VARCHAR(80),
    cod_canton      CHAR(4),
    parroquia       VARCHAR(80),
    cod_parroquia   CHAR(6),
    zona            VARCHAR(20),        -- Zona 1 … Zona 9
    regimen_escolar VARCHAR(20)         -- Sierra / Costa / Amazónica
);

COMMENT ON TABLE  dim_ubicacion IS
    'Dimensión geográfica. Una fila por combinación única provincia-cantón-parroquia.';
COMMENT ON COLUMN dim_ubicacion.zona IS
    'Zona de planificación del SENPLADES (Zona 1 a Zona 9).';


-- -------------------------------------------------------------
-- 2. dim_institucion
--    Características estructurales de cada institución.
-- -------------------------------------------------------------
CREATE TABLE dim_institucion (
    cod_amie            VARCHAR(8)      PRIMARY KEY,
    nombre_institucion  VARCHAR(300),
    tipo_educacion      VARCHAR(30),    -- Ordinaria / Especial / Popular Permanente
    sostenimiento       VARCHAR(30),    -- Fiscal / Particular / Fiscomisional / Municipal
    modalidad           VARCHAR(50),    -- Presencial / Semipresencial / A distancia
    jornada             VARCHAR(30),    -- Matutina / Vespertina / Nocturna / Completa
    area                VARCHAR(10),    -- Urbana / Rural
    nivel_educacion     VARCHAR(80),    -- Inicial/EGB/Bachillerato / combinaciones
    id_ubicacion        INTEGER         NOT NULL
                            REFERENCES dim_ubicacion(id_ubicacion)
                            ON DELETE RESTRICT
);

COMMENT ON TABLE  dim_institucion IS
    'Dimensión de instituciones educativas. Una fila por código AMIE.';
COMMENT ON COLUMN dim_institucion.nivel_educacion IS
    'Combinación de niveles que atiende la institución. Ej: Inicial/EGB/Bachillerato';


-- -------------------------------------------------------------
-- 3. fact_matricula
--    Una fila por (cod_amie, anio_lectivo).
--    Cubre 14 períodos: 2009-2010 hasta 2022-2023.
-- -------------------------------------------------------------
CREATE TABLE fact_matricula (
    cod_amie                VARCHAR(8)      NOT NULL
                                REFERENCES dim_institucion(cod_amie)
                                ON DELETE RESTRICT,
    anio_lectivo            VARCHAR(9)      NOT NULL,   -- ej. '2022-2023'
    total_estudiantes       INTEGER         DEFAULT 0,
    estudiantes_f           INTEGER         DEFAULT 0,
    estudiantes_m           INTEGER         DEFAULT 0,
    total_docentes          INTEGER         DEFAULT 0,
    docentes_f              INTEGER         DEFAULT 0,
    docentes_m              INTEGER         DEFAULT 0,
    ratio_est_docente       NUMERIC(6,2),               -- NULL si docentes = 0
    inconsistente_genero    SMALLINT        DEFAULT 0,  -- 1 si total ≠ f+m
    PRIMARY KEY (cod_amie, anio_lectivo)
);

COMMENT ON TABLE  fact_matricula IS
    'Tabla de hechos. Una fila por institución por año lectivo (2009-2022).';
COMMENT ON COLUMN fact_matricula.ratio_est_docente IS
    'Estudiantes por docente. NULL cuando total_docentes = 0.';
COMMENT ON COLUMN fact_matricula.inconsistente_genero IS
    '1 si total_estudiantes ≠ estudiantes_f + estudiantes_m.';


-- -------------------------------------------------------------
-- Índices de apoyo a las consultas del dashboard
-- -------------------------------------------------------------
CREATE INDEX idx_fact_anio        ON fact_matricula (anio_lectivo);
CREATE INDEX idx_fact_total_est   ON fact_matricula (total_estudiantes);
CREATE INDEX idx_inst_nivel       ON dim_institucion (nivel_educacion);
CREATE INDEX idx_inst_sost        ON dim_institucion (sostenimiento);
CREATE INDEX idx_ub_provincia     ON dim_ubicacion   (provincia);
CREATE INDEX idx_ub_zona          ON dim_ubicacion   (zona);