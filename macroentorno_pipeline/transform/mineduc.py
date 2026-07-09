"""
transform/mineduc.py
====================
Semana 3 — Limpieza y carga MINEDUC AMIE 2023-2024 Fin.

Tablas Silver:
  - silver_mineduc (2_MINEDUC_RegistrosAdministrativos_2023-2024-Fin-1.csv)

Estructura confirmada:
  sep=; | encoding=utf-8-sig | 16.206 filas | 250 columnas | header=10
  Columnas clave: Provincia, Cantón, Nivel Educación, Total_Estudiantes,
                  EstudiantesFemeninoTercerAñoBACH, EstudiantesMasculinoTercerAñoBACH

Uso:
  python transform/mineduc.py
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL  = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/macroentorno_ec")

BASE          = os.path.expanduser("~/macroentorno_pipeline")
BRONZE_MINE   = os.path.join(BASE, "datos_crudos", "mineduc")


def get_engine():
    return create_engine(DATABASE_URL)

def cargar_tabla(df, tabla, engine):
    df.to_sql(tabla, engine, if_exists="replace", index=False, chunksize=10_000, method="multi")
    print(f"  ✅ {tabla}: {len(df)} filas cargadas.")

def resumen(df, nombre):
    print(f"\n{'─'*55}")
    print(f"  {nombre}  |  shape={df.shape}")
    nulos = df.isnull().sum()
    nulos = nulos[nulos > 0]
    if not nulos.empty:
        print(f"  Nulos (top 8): {dict(list(nulos.items())[:8])}")
    print(f"  Primeras 3 filas:\n{df.head(3).to_string(index=False)}")


def limpiar_mineduc():
    """
    2_MINEDUC_RegistrosAdministrativos_2023-2024-Fin-1.csv
    - sep=; | encoding=utf-8-sig | header=10 (filas 0-9 son metadatos del MINEDUC)
    - Se conservan columnas de ID + Total_Estudiantes + 3ro BACH desglosado
    - Valores '-' → NaN
    - cod_provincia con zfill(2), cod_canton con zfill(4)
    - Se calcula bach3_total = femenino + masculino de 3ro BACH
    - NO se filtra por nivel aquí — el filtro va en las vistas Gold
    """
    archivo = os.path.join(BRONZE_MINE,
                           "2_MINEDUC_RegistrosAdministrativos_2023-2024-Fin-1.csv")
    print(f"\n[1] {os.path.basename(archivo)}")

    df = pd.read_csv(archivo, sep=";", encoding="utf-8-sig", header=10, low_memory=False)
    print(f"  Shape original: {df.shape}")

    COLS_ID = [
        "Año_Lectivo", "AMIE", "Nombre Institución",
        "Zona  ", "Provincia", "Cod_Provincia",
        "Cantón", "Cod_Cantón", "Parroquia",
        "Tipo Educación", "Nivel Educación", "Sostenimiento",
        "Total_Docentes", "Total_Estudiantes",
        "Estudiantes_Femenino", "Estudiantes_Masculino",
    ]
    COLS_BACH = [
        "EstudiantesFemeninoTercerAñoBACH",
        "EstudiantesMasculinoTercerAñoBACH",
        "EstudiantesFemeninoPromovidosTercerAñoBACH",
        "EstudiantesMasculinoPromovidosTercerAñoBACH",
        "EstudiantesFemeninoNoPromovidosTercerAñoBACH",
        "EstudiantesMasculinoNoPromovidosTercerAñoBACH",
        "EstudiantesFemeninoAbandonoTercerAñoBACH",
        "EstudiantesMasculinoAbandonoTercerAñoBACH",
    ]
    cols_usar = [c for c in COLS_ID + COLS_BACH if c in df.columns]
    df = df[cols_usar].copy()

    df = df.rename(columns={
        "Año_Lectivo":           "ao_lectivo",
        "Nombre Institución":    "nombre_institucion",
        "Zona  ":                "zona",
        "Provincia":             "provincia",
        "Cod_Provincia":         "cod_provincia",
        "Cantón":                "canton",
        "Cod_Cantón":            "cod_canton",
        "Parroquia":             "parroquia",
        "Tipo Educación":        "tipo_educacion",
        "Nivel Educación":       "nivel_educacion",
        "Sostenimiento":         "sostenimiento",
        "Total_Docentes":        "total_docentes",
        "Total_Estudiantes":     "total_estudiantes",
        "Estudiantes_Femenino":  "estudiantes_femenino",
        "Estudiantes_Masculino": "estudiantes_masculino",
        "EstudiantesFemeninoTercerAñoBACH":            "bach3_femenino",
        "EstudiantesMasculinoTercerAñoBACH":           "bach3_masculino",
        "EstudiantesFemeninoPromovidosTercerAñoBACH":  "bach3_fem_promovidos",
        "EstudiantesMasculinoPromovidosTercerAñoBACH": "bach3_masc_promovidos",
        "EstudiantesFemeninoNoPromovidosTercerAñoBACH":  "bach3_fem_no_promovidos",
        "EstudiantesMasculinoNoPromovidosTercerAñoBACH": "bach3_masc_no_promovidos",
        "EstudiantesFemeninoAbandonoTercerAñoBACH":    "bach3_fem_abandono",
        "EstudiantesMasculinoAbandonoTercerAñoBACH":   "bach3_masc_abandono",
    })

    df = df.replace({"-": None, "": None})

    COLS_TEXT = ["ao_lectivo","AMIE","nombre_institucion","zona","provincia",
                 "cod_provincia","canton","cod_canton","parroquia",
                 "tipo_educacion","nivel_educacion","sostenimiento"]
    for col in [c for c in df.columns if c not in COLS_TEXT]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["provincia"] = df["provincia"].astype(str).str.strip().str.title()
    df["canton"]    = df["canton"].astype(str).str.strip().str.title()
    df["parroquia"] = df["parroquia"].astype(str).str.strip().str.title()
    df["cod_provincia"] = (df["cod_provincia"].astype(str)
                           .str.split(".").str[0].str.zfill(2).replace("nan", None))
    df["cod_canton"]    = (df["cod_canton"].astype(str)
                           .str.split(".").str[0].str.zfill(4).replace("nan", None))

    if "bach3_femenino" in df.columns and "bach3_masculino" in df.columns:
        df["bach3_total"] = df["bach3_femenino"].fillna(0) + df["bach3_masculino"].fillna(0)
        ambos_nan = df["bach3_femenino"].isna() & df["bach3_masculino"].isna()
        df.loc[ambos_nan, "bach3_total"] = None

    df = df.reset_index(drop=True)
    resumen(df, "silver_mineduc")

    print("\n  Niveles Educación:")
    print(df["nivel_educacion"].value_counts().to_string())

    if "bach3_total" in df.columns:
        top = df.groupby("provincia")["bach3_total"].sum().sort_values(ascending=False).head(5)
        print("\n  Top 5 provincias bachilleres 3ro BACH:")
        print(top.to_string())

    return df


def main():
    print("=" * 60)
    print("  transform/mineduc.py — Limpieza y carga MINEDUC")
    print("=" * 60)
    engine = get_engine()
    df = limpiar_mineduc()
    cargar_tabla(df, "silver_mineduc", engine)
    print("\n  Verificación:")
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM silver_mineduc")).scalar()
        print(f"    silver_mineduc: {n} filas")
    print("\n  ✅  MINEDUC completo.")

if __name__ == "__main__":
    main()