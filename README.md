# Practicum_2.2_Linea_Datos

# Modelo Relacional, ETL Modular y Dashboard Analítico con PostgreSQL

Proyecto desarrollado para la asignatura **Prácticum — Datos: Ingeniería, Analítica y Visualización** de la **Universidad Técnica Particular de Loja (UTPL)**.

El proyecto implementa un proceso completo de ingeniería de datos utilizando el dataset histórico **AMIE (Archivo Maestro de Instituciones Educativas)** del Ministerio de Educación del Ecuador, integrando:

- Diseño y normalización de base de datos.
- Proceso ETL modular en Python.
- Almacenamiento en PostgreSQL.
- Consultas analíticas SQL.
- Visualización mediante Power BI.

---

##  Autor

**Martin Emanuel Ruiz Sánchez**

Carrera de Computación  
Universidad Técnica Particular de Loja (UTPL)

---

# Descripción del Proyecto

El dataset **AMIE (Archivo Maestro de Instituciones Educativas)** contiene el registro histórico de instituciones educativas del Ecuador entre los años **2009 y 2024**.

El objetivo principal consiste en transformar los datos originales en un modelo relacional optimizado para análisis, implementar un proceso ETL automatizado y generar indicadores para su visualización en Power BI.

---

# Objetivos

## Objetivo General

Diseñar e implementar una solución de ingeniería de datos basada en PostgreSQL para el análisis histórico de instituciones educativas del Ecuador.

## Objetivos Específicos

- Extraer información desde archivos Excel históricos.
- Limpiar y transformar los datos mediante Python.
- Normalizar la información en un modelo relacional.
- Cargar los datos en PostgreSQL.
- Generar consultas analíticas para Power BI.
- Construir indicadores educativos históricos.

---

# Arquitectura del Proyecto

```text
Archivo AMIE
    │
    ▼
 Extract
    │
    ▼
 Transform
    │
    ▼
 Load
    │
    ▼
 PostgreSQL
    │
    ▼
 Power BI
```

---

# Estructura del Proyecto

```text
practicum_datos/
│
├── config.py
├── .env
├── requirements.txt
│
├── data/
│   └── registro-administrativo-historico_2009-2024-inicio.xlsx
│
├── etl/
│   ├── extract.py
│   ├── transform.py
│   ├── load.py
│   └── pipeline.py
│
└── sql/
    ├── create_tables.sql
    └── queries.sql
```

| Archivo | Descripción |
|----------|-------------|
| extract.py | Lectura del archivo |
| transform.py | Limpieza y transformación de datos |
| load.py | Inserción en PostgreSQL |
| pipeline.py | Orquestador ETL |
| create_tables.sql | Creación de tablas |
| queries.sql | Consultas analíticas |

---

#  Modelo Relacional

El modelo se normaliza en tres tablas principales:

## dim_ubicacion

Dimensión geográfica que almacena:

- Provincia
- Cantón
- Parroquia
- Zona
- Régimen escolar

### Clave primaria

```sql
id_ubicacion
```

---

## dim_institucion

Dimensión institucional con características relativamente estables:

- Código AMIE
- Nombre
- Sostenimiento
- Modalidad
- Jornada
- Área
- Nivel educativo

### Clave primaria

```sql
cod_amie
```

### Clave foránea

```sql
id_ubicacion
```

---

## fact_matricula

Tabla de hechos con indicadores anuales:

- Total estudiantes
- Estudiantes mujeres
- Estudiantes hombres
- Total docentes
- Docentes mujeres
- Docentes hombres
- Ratio estudiante/docente

### Clave primaria compuesta

```sql
(cod_amie, anio_lectivo)
```

---

# Diagrama ER

```text
DIM_UBICACION
      │
      │ 1:N
      ▼
DIM_INSTITUCION
      │
      │ 1:N
      ▼
FACT_MATRICULA
```

---

# Proceso ETL

## Extract

Lectura del archivo:

```python
pd.read_excel(...)
```

Funciones principales:

- Verificación de existencia del archivo.
- Lectura de hojas Excel.
- Estandarización inicial.

---

## Transform

Limpieza y normalización de datos:

### Correcciones aplicadas

| Problema | Solución |
|-----------|-----------|
| Modallidad | modalidad |
| "Inicio" en período | Eliminado |
| Numéricos como texto | Conversión a integer |
| Valores nulos | Reemplazados |
| Duplicados | Eliminados |
| División por cero | NULLIF |
| Inconsistencias de género | Flag de control |

Variables calculadas:

```text
ratio_est_docente
inconsistente_genero
```

---

## Load

Carga hacia PostgreSQL utilizando:

```python
SQLAlchemy
psycopg2
```

Operaciones:

- Inserción de dimensiones.
- Obtención de claves.
- Inserción de hechos.
- Validación de integridad referencial.

---

# Consultas Analíticas

El proyecto incluye consultas SQL para responder preguntas relevantes del sector educativo.

## KPI Nacional

Obtiene:

- Matrícula nacional
- Docentes nacionales
- Instituciones activas
- Ratio estudiantes/docente

---

## Pregunta 1

### ¿En qué provincias existe mayor carga docente?

Indicadores:

- Ratio estudiante/docente
- Total estudiantes
- Total docentes
- Número de instituciones

---

## Pregunta 2

### ¿Qué nivel educativo presenta mayor brecha de género?

Indicadores:

- Mujeres
- Hombres
- % mujeres
- % hombres

---

## Pregunta 3

### ¿Cómo evolucionó la matrícula educativa en Loja entre 2009 y 2023?

Indicadores:

- Matrícula total
- Instituciones activas
---

# Dashboard Power BI

El dashboard incluye:

## KPIs principales

- Matrícula nacional
- Total docentes
- Instituciones activas
- Ratio estudiante/docente

## Visualizaciones

- Evolución temporal de matrícula
- Distribución por género
- Comparación por nivel educativo
- Indicadores por sostenimiento
- Ranking provincial

---

# Requisitos

## Software

- Python 3.10+
- PostgreSQL 14+
- Power BI Desktop

## Entorno virtual 
```bash
python -m venv venv
```
## Librerías Python

```bash
pip install pandas
pip install openpyxl
pip install sqlalchemy
pip install psycopg2-binary
pip install python-dotenv
```

o

```bash
pip install -r requirements.txt
```

---

# Configuración

Crear un archivo `.env`

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=amie_mineduc
DB_USER=postgres
DB_PASSWORD=tu_password
```

---

# Ejecución

## 1. Crear entorno virtual

```bash
python -m venv venv
```

Activar:

### Windows

```bash
venv\Scripts\activate
```

### Linux / Mac

```bash
source venv/bin/activate
```

---

## 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

---

## 3. Crear tablas

```bash
psql -U postgres -d amie_mineduc -f sql/create_tables.sql
```

---

## 4. Ejecutar ETL

```bash
python etl/pipeline.py
```

---

## 5. Conectar Power BI

1. Obtener datos
2. PostgreSQL
3. Conectar a la base de datos
4. Importar:

- dim_ubicacion
- dim_institucion
- fact_matricula

---

# Tecnologías Utilizadas

- Python
- Pandas
- OpenPyXL
- SQLAlchemy
- PostgreSQL
- Power BI
- Git
- GitHub

---

# Fuente de Datos

Ministerio de Educación del Ecuador

**AMIE – Archivo Maestro de Instituciones Educativas**

Período analizado:

```text
2009 - 2024
```

---
