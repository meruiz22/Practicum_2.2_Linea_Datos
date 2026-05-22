"""
etl/extract.py — Módulo de Extracción (E del ETL).
"""

import pandas as pd
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import EXCEL_PATH, SHEET_NAME

COLUMNAS_REQUERIDAS = [
    "Clave_primaria", "Periodo", "Zona", "Provincia", "Cod_Provincia",
    "Canton", "Cod_Canton", "Parroquia", "Cod_Parroquia",
    "Nombre_Institucion", "Codigo_Institucion", "Tipo_Educacion",
    "Sostenimiento", "Area", "Regimen_Escolar", "Modallidad", "Jornada",
    "Docentes_Femenino", "Docentes_Masculino", "Total_Docentes",
    "Estudiantes_Femenino", "Estudiantes_Masculino", "Total_Estudiantes",
    "Nivel_educativo",
]


def extraer_excel() -> pd.DataFrame:
    print(f"[EXTRACT] Leyendo: {EXCEL_PATH}")
    print("[EXTRACT] Esto puede tardar ~30 segundos...")

    if not os.path.exists(EXCEL_PATH):
        raise FileNotFoundError(
            f"\n[EXTRACT] No se encontró el archivo:\n  {EXCEL_PATH}\n"
            "Verifica que el Excel esté en la carpeta data/ del proyecto."
        )

    df = pd.read_excel(
        EXCEL_PATH,
        sheet_name=SHEET_NAME,
        dtype=object,
        engine="openpyxl",
    )

    print(f"[EXTRACT] Filas leídas  : {len(df):,}")
    print(f"[EXTRACT] Columnas      : {len(df.columns)}")
    _verificar_columnas(df)
    return df


def _verificar_columnas(df: pd.DataFrame) -> None:
    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        print(f"[EXTRACT] ADVERTENCIA — columnas no encontradas: {faltantes}")
    else:
        print("[EXTRACT] Todas las columnas requeridas presentes ✓")