# Pipeline de Datos del Macroentorno Ecuatoriano
## Resumen técnico completo — 6to ciclo | Practicum 2.2 | Línea Datos
**Universidad Técnica Particular de Loja**

---

## Qué es el proyecto

Un pipeline de datos end-to-end que transforma archivos crudos de 9 fuentes públicas ecuatorianas en un dashboard analítico de Power BI que responde 3 preguntas estratégicas sobre la economía del Ecuador. Sigue la arquitectura medallón: **Bronze → Silver → Gold → Dashboard**.

---

## Cómo fluye la información

```
FUENTES PÚBLICAS              BRONZE              SILVER (PostgreSQL)         GOLD (Vistas SQL)       DASHBOARD
─────────────────             ──────              ──────────────────          ─────────────────       ─────────
BCE (5 archivos)  ──────────► datos_crudos/  ──► transform/bce.py      ──► gold_pib_tendencia   ──► P1: Evolución
INEC (2 archivos) ──────────►     bce/       ──► transform/inec.py     ──► gold_petroleo_30dias      economía
Supercias (2 CSV) ──────────►     inec/      ──► transform/supercias.py──► gold_iee_vs_pib            20 años
MINEDUC (1 CSV)   ──────────►     supercias/ ──► transform/mineduc.py  ──► gold_empleo_tendencia ──► P2: Sectores
                              ─►  mineduc/                              ──► gold_vab_por_sector        y provincias
Semana 5+:                                                              ──► gold_bachilleres     ──► P3: Bachilleres
RPA deposita  ────────────►  datos_macroentorno/  ──► pipeline.py           _vs_empresas              vs empresas
archivos auto.                                         (detecta y procesa)
```

---

## Estructura de carpetas del proyecto

```
macroentorno_pipeline/          ← raíz del proyecto (en GitHub)
│
├── .env                        ← credenciales PostgreSQL (NO en Git)
├── .gitignore                  ← excluye datos_crudos/, .env, venv_datos/
├── requirements.txt            ← dependencias Python
├── pipeline.py                 ← orquestador semana 5 (detecta archivos RPA)
├── leer_pib.py                 ← exploración inicial PIB (semana 1)
│
├── transform/                  ← scripts ETL por fuente
│   ├── bce.py                  ← limpia y carga 5 tablas Silver del BCE
│   ├── inec.py                 ← limpia y carga ENEMDU + Censo 2022
│   ├── supercias.py            ← limpia y carga ranking + directorio
│   └── mineduc.py              ← limpia y carga AMIE 2023-2024
│
├── sql/
│   ├── create_tables.sql       ← crea 14 tablas en PostgreSQL
│   └── gold_views.sql          ← crea 6 vistas Gold
│
├── datos_crudos/               ← Bronze (en .gitignore — no sube a Git)
│   ├── bce/                    ← 7 archivos BCE
│   ├── inec/                   ← 2 archivos INEC
│   ├── supercias/              ← 2 archivos Supercias
│   └── mineduc/                ← 1 archivo MINEDUC
│
├── datos_macroentorno/         ← carpeta donde RPA deposita archivos (semana 5+)
│
└── venv_datos/                 ← entorno virtual Python (en .gitignore)
```

---

## Archivos fuente (Bronze)

### Banco Central del Ecuador
| Archivo | Fuente | Formato | Rango | Filas |
|---|---|---|---|---|
| `retropolacion_1965_2024p.xlsx` | BCE Cuentas Nacionales | Excel | 1965–2024 | 60 |
| `pib-per-cpita-nominal.csv` | BCE | CSV sep=; | 2000–2025 | 26 |
| `Boletin_retropolacion_regionales_2007_2024p_val.xlsx` | BCE Cuentas Regionales | Excel | 2007–2024 | wide→504 |
| `petroleo_wti.csv` | BCE Sector Externo | CSV sep=; | 2015–2026 | 3.803 |
| `petroleo_crudo_ecu.csv` | BCE Sector Externo | CSV sep=; | 2000–2026 | 315 |
| `riesgo_pais.csv` | BCE Sector Externo | CSV sep=; | 2004–2026 | 7.303 |
| `IEE_Nueva_Metodologia.xlsx` | BCE Encuestas | Excel | 2010–2026 | 196 |

### INEC
| Archivo | Fuente | Formato | Detalle |
|---|---|---|---|
| `202605_Tabulados_Mercado_Laboral_EXCEL.XLSX` | INEC ENEMDU | Excel | Estructura pivotada → melt() |
| `CPV_2022_Población_Cantón.csv` | Censo 2022 | CSV | Nivel cantón, corte único |

### Supercias
| Archivo | Formato | Filas |
|---|---|---|
| `bi_ranking.csv` | CSV sep=, | ~1.670.000 |
| `bi_compania.csv` | CSV sep=, | ~338.000 |

### MINEDUC
| Archivo | Formato | Filas | Detalle |
|---|---|---|---|
| `2_MINEDUC_RegistrosAdministrativos_2023-2024-Fin-1.csv` | CSV sep=; utf-8-sig | 16.206 | header=10 |

---

## Scripts Python (transform/)

### `bce.py` — 5 funciones, 5 tablas Silver

```
limpiar_pib_real()          → silver_pib_real         (60 filas anuales 1965-2024)
limpiar_pib_nominal()       → silver_pib_nominal       (26 filas anuales 2000-2025)
limpiar_vab()               → silver_vab               (504 filas: 28 prov × 18 años)
limpiar_petroleo_riesgo()   → silver_petroleo_riesgo   (~8.500 filas diarias/mensuales)
limpiar_iee()               → silver_iee               (196 filas mensuales 2010-2026)
```

**Decisiones de limpieza documentadas:**
- `retropolacion_1965_2024p.xlsx`: `header=9`, primeras 5 columnas, `2024 (p)` → entero, `variacion_pct` 1965 = NULL correcto
- VAB: estructura wide → `melt()` a formato long
- Petróleo: 3 CSVs separados con `merge outer` por fecha → NULLs documentados
- IEE: `header=7`, valores fuera de [0,200] → NaN

### `inec.py` — 2 funciones, 2 tablas Silver

```
limpiar_enemdu()  → silver_enemdu   (estructura pivotada → melt(), periodo 'dic-07' → fecha real)
limpiar_censo()   → silver_censo    (nivel cantón, COLS_MAPA ajustable)
```

### `supercias.py` — 2 funciones, 2 tablas Silver

```
limpiar_ranking()    → silver_supercias_ranking    (~1.67M filas, lectura en chunks 100k)
limpiar_directorio() → silver_supercias_directorio (~338k empresas, RUC validado 13 dígitos)
```

### `mineduc.py` — 1 función, 1 tabla Silver

```
limpiar_mineduc() → silver_mineduc (header=10, calcula bach3_total, '-' → NULL)
```

---

## Base de datos PostgreSQL 18

### 14 tablas en total

```
DIMENSIONES (2)                    TABLAS FACT (3)
───────────────────────────────    ────────────────────────────────────
dim_tiempo                         fact_macro_anual      → dim_tiempo
dim_geografia                      fact_indicadores_diarios → dim_tiempo
                                   fact_empleo           → dim_tiempo

TABLAS SILVER BCE (5)              TABLAS SILVER INEC/SUPER/MINE (4)
───────────────────────────────    ────────────────────────────────────
silver_pib_real    → dim_tiempo    silver_enemdu         → dim_tiempo
silver_pib_nominal → dim_tiempo    silver_censo          → dim_geografia
silver_vab   → dim_tiempo          silver_supercias_ranking → dim_geografia
             → dim_geografia       silver_supercias_directorio → dim_geografia
silver_petroleo_riesgo → dim_t     silver_mineduc        → dim_geografia
silver_iee         → dim_tiempo    silver_censo_actividad → dim_geografia
```


## Vistas Gold (sql/gold_views.sql)

| Vista | Dashboard | Tipo | Qué calcula |
|---|---|---|---|
| `gold_pib_tendencia` | P1 | Base | PIB + clasificación ciclo económico + variación per cápita |
| `gold_petroleo_30dias` | P1 | Base | WTI + crudo ECU + promedio móvil 30 días + variación diaria |
| `gold_empleo_tendencia` | P2 | Base | ENEMDU histórico: desempleo, subempleo, empleo adecuado |
| `gold_bachilleres_vs_empresas` | P3 | Base | MINEDUC × Supercias por provincia + ratio bachilleres/empresa |
| `gold_iee_vs_pib` | P1 | **6to ciclo** | IEE promedio anual vs variación PIB (indicador adelantado) |
| `gold_vab_por_sector` | P2 | **6to ciclo** | VAB por provincia: participación %, ranking, variación anual |

---

## Archivos del repositorio

| Archivo | Carpeta | Qué hace |
|---|---|---|
| `bce.py` | `transform/` | ETL fuentes BCE |
| `inec.py` | `transform/` | ETL fuentes INEC |
| `supercias.py` | `transform/` | ETL fuentes Supercias |
| `mineduc.py` | `transform/` | ETL fuente MINEDUC |
| `create_tables.sql` | `sql/` | Crea 14 tablas + 17 índices en PostgreSQL |
| `gold_views.sql` | `sql/` | Crea 6 vistas Gold |
| `requirements.txt` | raíz | Dependencias Python |
| `dbdiagram.txt` | raíz o docs/ | Modelo ER para dbdiagram.io |

---

---

## Estado del proyecto por semana del reto

| Semana | Entregable | Estado |
|---|---|---|
| 1 — Entorno y diagrama | Diagrama ER aprobado + exploración PIB | ✅ Completa |
| 2 — Limpieza BCE | `transform/bce.py` + 5 tablas Silver | ✅ Scripts listos |
| 3 — Limpieza INEC/Supercias/MINEDUC | 3 scripts + 5 tablas Silver | ✅ Scripts listos |
| 4 — Modelo relacional + vistas Gold | `create_tables.sql` + `gold_views.sql` | ✅ Completa |
| 5 — Dashboard P1/P2 + integración RPA | Power BI + `pipeline.py` | ✅ Completa|
| 6 — Dashboard P3 + refinamiento | Página P3 + párrafos análisis | ✅ Completa |
| 7 — Documentación + demo | Informe técnico + presentación | ✅ Completa |

---


