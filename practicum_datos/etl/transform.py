"""
etl/transform.py — Módulo de Transformación (T del ETL).

Dataset: Excel histórico AMIE 2009-2024.

Pasos en orden:
  1. Renombrar columnas (estandarizar, corregir typo "Modallidad").
  2. Limpiar campo Periodo  →  "2009-2010 Inicio" → "2009-2010".
  3. Convertir columnas numéricas; nulos → 0.
  4. Eliminar duplicados por (cod_amie, anio_lectivo).
  5. Validar consistencia total_estudiantes == f + m.
  6. Construir dim_ubicacion, dim_institucion y fact_matricula.
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ------------------------------------------------------------------
# Diccionario de renombrado
# ------------------------------------------------------------------
RENAME = {
    "Clave_primaria":          "clave_primaria",
    "Periodo":                 "anio_lectivo_raw",
    "Zona":                    "zona",
    "Provincia":               "provincia",
    "Cod_Provincia":           "cod_provincia",
    "Canton":                  "canton",
    "Cod_Canton":              "cod_canton",
    "Parroquia":               "parroquia",
    "Cod_Parroquia":           "cod_parroquia",
    "Nombre_Institucion":      "nombre_institucion",
    "Codigo_Institucion":      "cod_amie",
    "Tipo_Educacion":          "tipo_educacion",
    "Sostenimiento":           "sostenimiento",
    "Area":                    "area",
    "Regimen_Escolar":         "regimen_escolar",
    "Modallidad":              "modalidad",        # corrige doble 'l'
    "Jornada":                 "jornada",
    "Docentes_Femenino":       "docentes_f",
    "Docentes_Masculino":      "docentes_m",
    "Total_Docentes":          "total_docentes",
    "Estudiantes_Femenino":    "estudiantes_f",
    "Estudiantes_Masculino":   "estudiantes_m",
    "Total_Estudiantes":       "total_estudiantes",
    "Nivel_educativo":         "nivel_educacion",
}

COLUMNAS_NUMERICAS = [
    "total_docentes", "total_estudiantes",
    "estudiantes_f",  "estudiantes_m",
    "docentes_f",     "docentes_m",
]


# ------------------------------------------------------------------
# Función principal
# ------------------------------------------------------------------
def transformar(df_raw: pd.DataFrame) -> dict:
    """
    Aplica todas las transformaciones y devuelve las tres tablas.

    Retorna
    -------
    dict con claves: 'dim_ubicacion', 'dim_institucion', 'fact_matricula'
    """
    print("[TRANSFORM] Iniciando transformaciones...")

    df = _renombrar(df_raw)
    df = _limpiar_periodo(df)
    df = _convertir_numericos(df)
    df = _eliminar_duplicados(df)
    df = _validar_consistencia(df)

    dim_ub   = _construir_dim_ubicacion(df)
    dim_inst = _construir_dim_institucion(df, dim_ub)
    fact     = _construir_fact_matricula(df)

    print("\n[TRANSFORM] ✓ Completado.")
    print(f"  dim_ubicacion  : {len(dim_ub):,} filas")
    print(f"  dim_institucion: {len(dim_inst):,} filas")
    print(f"  fact_matricula : {len(fact):,} filas")

    return {
        "dim_ubicacion":   dim_ub,
        "dim_institucion": dim_inst,
        "fact_matricula":  fact,
    }


# ------------------------------------------------------------------
# Paso 1 — Renombrado
# ------------------------------------------------------------------
def _renombrar(df: pd.DataFrame) -> pd.DataFrame:
    rename_ok = {k: v for k, v in RENAME.items() if k in df.columns}
    df = df.rename(columns=rename_ok)
    print(f"[TRANSFORM] Columnas renombradas: {len(rename_ok)}")
    return df


# ------------------------------------------------------------------
# Paso 2 — Limpiar campo período
#   "2009-2010 Inicio" → "2009-2010"
# ------------------------------------------------------------------
def _limpiar_periodo(df: pd.DataFrame) -> pd.DataFrame:
    if "anio_lectivo_raw" not in df.columns:
        return df
    df["anio_lectivo"] = (
        df["anio_lectivo_raw"]
        .astype(str)
        .str.replace(r"\s+Inicio$", "", regex=True)
        .str.strip()
    )
    df = df.drop(columns=["anio_lectivo_raw"])
    periodos = sorted(df["anio_lectivo"].unique())
    print(f"[TRANSFORM] Períodos: {periodos[0]} … {periodos[-1]}  ({len(periodos)} en total)")
    return df


# ------------------------------------------------------------------
# Paso 3 — Tipos numéricos
# ------------------------------------------------------------------
def _convertir_numericos(df: pd.DataFrame) -> pd.DataFrame:
    for col in COLUMNAS_NUMERICAS:
        if col in df.columns:
            nulos = df[col].isna().sum()
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            if nulos > 0:
                print(f"[TRANSFORM] '{col}': {nulos:,} nulos → 0")
    return df


# ------------------------------------------------------------------
# Paso 4 — Duplicados
# ------------------------------------------------------------------
def _eliminar_duplicados(df: pd.DataFrame) -> pd.DataFrame:
    antes = len(df)
    df = df.drop_duplicates(subset=["cod_amie", "anio_lectivo"], keep="first")
    n = antes - len(df)
    print(f"[TRANSFORM] Duplicados eliminados: {n:,}")
    return df


# ------------------------------------------------------------------
# Paso 5 — Validación de consistencia de género
# ------------------------------------------------------------------
def _validar_consistencia(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["total_estudiantes", "estudiantes_f", "estudiantes_m"]
    if not all(c in df.columns for c in cols):
        return df
    incons = (df["total_estudiantes"] != df["estudiantes_f"] + df["estudiantes_m"])
    df["inconsistente_genero"] = incons.astype(int)
    n   = incons.sum()
    pct = 100 * n / len(df)
    print(f"[TRANSFORM] Registros inconsistentes (total ≠ f+m): {n:,} ({pct:.1f}%)")
    print("[TRANSFORM] Decisión: se conservan con flag inconsistente_genero=1")
    return df


# ------------------------------------------------------------------
# Paso 6a — dim_ubicacion
# ------------------------------------------------------------------
def _construir_dim_ubicacion(df: pd.DataFrame) -> pd.DataFrame:
    """
    Combinaciones únicas de campos geográficos.
    Genera id_ubicacion incremental como clave primaria.
    """
    cols = ["provincia","cod_provincia","canton","cod_canton",
            "parroquia","cod_parroquia","zona","regimen_escolar"]
    cols_ok = [c for c in cols if c in df.columns]
    dim = df[cols_ok].drop_duplicates().reset_index(drop=True)
    dim.insert(0, "id_ubicacion", range(1, len(dim) + 1))
    return dim


# ------------------------------------------------------------------
# Paso 6b — dim_institucion
# ------------------------------------------------------------------
def _construir_dim_institucion(df: pd.DataFrame, dim_ub: pd.DataFrame) -> pd.DataFrame:
    """
    Características estables de cada institución.
    Merge con dim_ubicacion para obtener id_ubicacion (FK).
    Se conserva la fila del año más reciente por cod_amie.
    """
    cols_inst = ["cod_amie","nombre_institucion","tipo_educacion",
                 "sostenimiento","modalidad","jornada","area","nivel_educacion"]
    cols_geo  = [c for c in dim_ub.columns if c != "id_ubicacion"]

    cols_inst_ok = [c for c in cols_inst if c in df.columns]
    cols_geo_ok  = [c for c in cols_geo  if c in df.columns]

    df_inst = (
        df.sort_values("anio_lectivo", ascending=False)
          [cols_inst_ok + cols_geo_ok]
          .drop_duplicates(subset=["cod_amie"])
    )

    df_inst = df_inst.merge(
        dim_ub[cols_geo_ok + ["id_ubicacion"]],
        on=cols_geo_ok,
        how="left",
    ).drop(columns=cols_geo_ok)

    return df_inst.reset_index(drop=True)


# ------------------------------------------------------------------
# Paso 6c — fact_matricula
# ------------------------------------------------------------------
def _construir_fact_matricula(df: pd.DataFrame) -> pd.DataFrame:
    """
    Una fila por (cod_amie, anio_lectivo).
    Calcula ratio_est_docente; NULL si total_docentes == 0.
    """
    cols = ["cod_amie","anio_lectivo","total_estudiantes","estudiantes_f",
            "estudiantes_m","total_docentes","docentes_f","docentes_m"]
    if "inconsistente_genero" in df.columns:
        cols.append("inconsistente_genero")

    fact = df[[c for c in cols if c in df.columns]].copy()

    fact["ratio_est_docente"] = np.where(
        fact["total_docentes"] == 0,
        np.nan,
        (fact["total_estudiantes"] / fact["total_docentes"]).round(2)
    )

    return fact.reset_index(drop=True)