"""
transform/mineduc.py
====================
Semana 3 — Limpieza y carga fuente MINEDUC AMIE 2023-2024 Fin.

Tablas Silver que genera:
  - silver_mineduc   (2_MINEDUC_RegistrosAdministrativos_2023-2024-Fin-1.csv)

Estructura confirmada:
  - sep=; | encoding=utf-8-sig | 16.206 filas (instituciones) | 250 columnas
  - Header real en fila 10 (índice), datos desde fila 11
  - Columnas clave identificadas:
      Año_Lectivo, AMIE, Nombre Institución, Zona, Provincia, Cod_Provincia,
      Cantón, Cod_Cantón, Parroquia, Tipo Educación, Nivel Educación,
      Sostenimiento, Total_Estudiantes,
      EstudiantesFemeninoTercerAñoBACH, EstudiantesMasculinoTercerAñoBACH

Para el dashboard P3 se necesita:
  - Bachilleres de 3ro de bachillerato por provincia (gold_bachilleres_vs_empresas)

Uso:
  python transform/mineduc.py
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/macroentorno_ec")

BASE = r"C:\Users\marti\OneDrive\Documentos\Practicum 2.2\Practicum_2.2_Linea_Datos\macroentorno_pipeline"
BRONZE_MINE = os.path.join(BASE, "datos_crudos", "mineduc")


def get_engine():
    return create_engine(DATABASE_URL)


def cargar_tabla(df, tabla, engine):
    df.to_sql(tabla, engine, if_exists="replace", index=False)
    print(f"  ✅ {tabla}: {len(df)} filas cargadas.")


def resumen(df, nombre):
    print(f"\n{'─'*55}")
    print(f"  {nombre}  |  shape={df.shape}")
    nulos = df.isnull().sum()
    nulos = nulos[nulos > 0]
    if not nulos.empty:
        print(f"  Nulos: {dict(list(nulos.items())[:8])}")
    print(f"  Primeras 3 filas:\n{df.head(3).to_string(index=False)}")


# ─────────────────────────────────────────
# 1. MINEDUC AMIE — silver_mineduc
# ─────────────────────────────────────────
def limpiar_mineduc():
    """
    Fuente: 2_MINEDUC_RegistrosAdministrativos_2023-2024-Fin-1.csv
    Decisiones:
    - sep=; | encoding=utf-8-sig | header=10 (fila 11 del CSV, índice 10)
    - Las 9 primeras filas son metadatos del MINEDUC → se saltan con header=10
    - Se conservan columnas de identificación + Total_Estudiantes + columnas 3ro BACH
    - Valores '-' en columnas numéricas → NaN
    - Total_Estudiantes y columnas de 3ro BACH → numeric
    - Provincia y Cantón → title case para consistencia con dim_geografia
    - Nivel Educación se conserva completo (para filtros posteriores en vistas Gold)
    - NO se filtra aquí por nivel — el filtro de Bachillerato va en la vista Gold
      para mantener la tabla Silver completa y reutilizable
    """
    archivo = os.path.join(BRONZE_MINE,
                           "2_MINEDUC_RegistrosAdministrativos_2023-2024-Fin-1.csv")
    print(f"\n[1] Leyendo {os.path.basename(archivo)} ...")

    df = pd.read_csv(archivo, sep=";", encoding="utf-8-sig",
                     header=10, low_memory=False)

    print(f"  Shape original: {df.shape}")

    # ── Columnas a conservar ──────────────────────────────────────────────
    COLS_ID = [
        "Año_Lectivo", "AMIE", "Nombre Institución",
        "Zona  ",          # ojo: tiene espacios al final en el CSV
        "Provincia", "Cod_Provincia",
        "Cantón", "Cod_Cantón",
        "Parroquia",
        "Tipo Educación", "Nivel Educación", "Sostenimiento",
        "Total_Docentes", "Total_Estudiantes",
        "Estudiantes_Femenino", "Estudiantes_Masculino",
    ]
    COLS_3RO_BACH = [
        "EstudiantesFemeninoTercerAñoBACH",
        "EstudiantesMasculinoTercerAñoBACH",
        "EstudiantesFemeninoPromovidosTercerAñoBACH",
        "EstudiantesMasculinoPromovidosTercerAñoBACH",
        "EstudiantesFemeninoNoPromovidosTercerAñoBACH",
        "EstudiantesMasculinoNoPromovidosTercerAñoBACH",
        "EstudiantesFemeninoAbandonoTercerAñoBACH",
        "EstudiantesMasculinoAbandonoTercerAñoBACH",
    ]

    # Filtrar solo columnas que existen en el DataFrame
    cols_id_ok   = [c for c in COLS_ID        if c in df.columns]
    cols_bach_ok = [c for c in COLS_3RO_BACH  if c in df.columns]
    cols_usar = cols_id_ok + cols_bach_ok

    df = df[cols_usar].copy()

    # ── Renombrar para estandarizar ───────────────────────────────────────
    df = df.rename(columns={
        "Año_Lectivo":       "ao_lectivo",
        "Nombre Institución":"nombre_institucion",
        "Zona  ":            "zona",
        "Provincia":         "provincia",
        "Cod_Provincia":     "cod_provincia",
        "Cantón":            "canton",
        "Cod_Cantón":        "cod_canton",
        "Parroquia":         "parroquia",
        "Tipo Educación":    "tipo_educacion",
        "Nivel Educación":   "nivel_educacion",
        "Sostenimiento":     "sostenimiento",
        "Total_Docentes":    "total_docentes",
        "Total_Estudiantes": "total_estudiantes",
        "Estudiantes_Femenino":  "estudiantes_femenino",
        "Estudiantes_Masculino": "estudiantes_masculino",
        "EstudiantesFemeninoTercerAñoBACH":           "bach3_femenino",
        "EstudiantesMasculinoTercerAñoBACH":          "bach3_masculino",
        "EstudiantesFemeninoPromovidosTercerAñoBACH": "bach3_fem_promovidos",
        "EstudiantesMasculinoPromovidosTercerAñoBACH":"bach3_masc_promovidos",
        "EstudiantesFemeninoNoPromovidosTercerAñoBACH":  "bach3_fem_no_promovidos",
        "EstudiantesMasculinoNoPromovidosTercerAñoBACH": "bach3_masc_no_promovidos",
        "EstudiantesFemeninoAbandonoTercerAñoBACH":   "bach3_fem_abandono",
        "EstudiantesMasculinoAbandonoTercerAñoBACH":  "bach3_masc_abandono",
    })

    # ── Limpiar valores '-' → NaN ─────────────────────────────────────────
    df = df.replace("-", None)
    df = df.replace("", None)

    # ── Columnas numéricas ────────────────────────────────────────────────
    cols_num = [c for c in df.columns if c not in [
        "ao_lectivo", "AMIE", "nombre_institucion", "zona",
        "provincia", "cod_provincia", "canton", "cod_canton",
        "parroquia", "tipo_educacion", "nivel_educacion", "sostenimiento"
    ]]
    for col in cols_num:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Limpiar texto ─────────────────────────────────────────────────────
    df["provincia"] = df["provincia"].astype(str).str.strip().str.title()
    df["canton"]    = df["canton"].astype(str).str.strip().str.title()
    df["parroquia"] = df["parroquia"].astype(str).str.strip().str.title()

    # Código provincia como string con zfill para coincidir con dim_geografia
    df["cod_provincia"] = (df["cod_provincia"]
                           .astype(str).str.split(".").str[0]
                           .str.zfill(2).replace("nan", None))
    df["cod_canton"]    = (df["cod_canton"]
                           .astype(str).str.split(".").str[0]
                           .str.zfill(4).replace("nan", None))

    # ── Calcular total 3ro bachillerato ───────────────────────────────────
    if "bach3_femenino" in df.columns and "bach3_masculino" in df.columns:
        df["bach3_total"] = df["bach3_femenino"].fillna(0) + df["bach3_masculino"].fillna(0)
        # Donde ambos son NaN → bach3_total = NaN
        ambos_nan = df["bach3_femenino"].isna() & df["bach3_masculino"].isna()
        df.loc[ambos_nan, "bach3_total"] = None

    df = df.reset_index(drop=True)
    resumen(df, "silver_mineduc")

    # Resumen por nivel educación
    print("\n  Distribución Nivel Educación:")
    print(df["nivel_educacion"].value_counts().to_string())

    # Preview bachilleres por provincia
    if "bach3_total" in df.columns:
        bach_prov = (df.groupby("provincia")["bach3_total"]
                     .sum().sort_values(ascending=False).head(5))
        print("\n  Top 5 provincias por bachilleres 3ro BACH:")
        print(bach_prov.to_string())

    return df


# ─────────────────────────────────────────
# Orquestador
# ─────────────────────────────────────────
def main():
    print("=" * 60)
    print("  transform/mineduc.py — Limpieza y carga MINEDUC AMIE")
    print("=" * 60)

    engine = get_engine()
    df = limpiar_mineduc()

    print("\n" + "=" * 60)
    print("  Cargando tablas Silver en PostgreSQL ...")
    print("=" * 60)

    cargar_tabla(df, "silver_mineduc", engine)

    print("\n" + "=" * 60)
    print("  Verificación de conteos:")
    with engine.connect() as conn:
        try:
            n = conn.execute(text("SELECT COUNT(*) FROM silver_mineduc")).scalar()
            print(f"    silver_mineduc: {n} filas")
        except Exception as e:
            print(f"    silver_mineduc: ⚠️  {e}")

    print("\n  ✅  MINEDUC procesado.")
    print("=" * 60)


if __name__ == "__main__":
    main()
