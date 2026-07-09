"""
transform/inec.py
=================
Semana 3 — Limpieza y carga fuentes INEC.

Tablas Silver:
  - silver_enemdu  (202605_Tabulados_Mercado_Laboral_EXCEL.XLSX → hoja '2. Tasas')
  - silver_censo   (CPV_2022_Población_Cantón.csv — ajustar COLS_MAPA)

Uso:
  python transform/inec.py
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/macroentorno_ec")

BASE        = os.path.expanduser("/home/mar/Documentos/Practicum 2.2/Practicum_2.2_Linea_Datos/macroentorno_pipeline")
BRONZE_INEC = os.path.join(BASE, "datos_crudos", "inec")


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
        print(f"  Nulos: {dict(list(nulos.items())[:5])}")
    print(f"  Primeras 3 filas:\n{df.head(3).to_string(index=False)}")


def limpiar_enemdu():
    """
    202605_Tabulados_Mercado_Laboral_EXCEL.XLSX | Hoja: '2. Tasas'
    Estructura: Encuesta | Periodo | Indicadores | Nacional | Urbana | Rural | Hombre | Mujer
    - Fila 1: encabezados principales, Fila 2: sub-encabezados → datos desde fila 3
    - Periodo 'dic-07' → fecha real 2007-12-01
    - Formato long: una fila por (fecha, indicador) con Nacional/Urbana/Rural
    """
    archivo = os.path.join(BRONZE_INEC, "202605_Tabulados_Mercado_Laboral_EXCEL.XLSX")
    print(f"\n[1] {os.path.basename(archivo)}")
    df = pd.read_excel(archivo, sheet_name="2. Tasas", header=None, engine="openpyxl")
    df = df.iloc[2:].copy()
    df.columns = ["encuesta", "periodo", "indicador",
                  "total_nacional", "total_urbana", "total_rural",
                  "total_hombre", "total_mujer"]
    df = df.reset_index(drop=True)
    df = df.dropna(subset=["indicador"])
    df = df[df["indicador"].astype(str).str.strip().isin(["", "nan"]) == False]

    meses = {"ene":"01","feb":"02","mar":"03","abr":"04","may":"05","jun":"06",
             "jul":"07","ago":"08","sep":"09","oct":"10","nov":"11","dic":"12"}

    def parsear_periodo(p):
        p = str(p).strip().lower()
        for m, n in meses.items():
            if p.startswith(m):
                y = p.split("-")[-1]
                anio = int("20"+y) if int(y) <= 30 else int("19"+y)
                return pd.Timestamp(f"{anio}-{n}-01")
        return pd.NaT

    df["fecha"] = df["periodo"].apply(parsear_periodo)
    df["anio"]  = df["fecha"].dt.year
    for col in ["total_nacional","total_urbana","total_rural","total_hombre","total_mujer"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["indicador"] = df["indicador"].astype(str).str.strip()
    df = df[["fecha","anio","encuesta","periodo","indicador",
             "total_nacional","total_urbana","total_rural"]] \
        .sort_values(["fecha","indicador"]).reset_index(drop=True)
    resumen(df, "silver_enemdu")
    print(f"  Indicadores únicos: {df['indicador'].nunique()}")
    print(f"  Rango: {df['fecha'].min().date()} → {df['fecha'].max().date()}")
    return df


def limpiar_censo():
    """
    CPV_2022_Población_Cantón.csv
    IMPORTANTE: ajusta COLS_MAPA con los nombres reales de columnas del archivo.
    Para ver columnas disponibles ejecuta primero:
        head -1 ~/macroentorno_pipeline/datos_crudos/inec/CPV_2022_Población_Cantón.csv
    """
    archivo = os.path.join(BRONZE_INEC, "CPV_2022_Población_Cantón.csv")
    print(f"\n[2] {os.path.basename(archivo)}")

    df_head = pd.read_csv(archivo, nrows=2, low_memory=False)
    print(f"  Columnas disponibles: {df_head.columns.tolist()[:15]} ...")

    # ── AJUSTAR CON NOMBRES REALES ──────────────────────────────────────
    COLS_MAPA = {
        "provincia": "provincia",
        "canton":    "canton",
        "ciiu":      "rama_actividad",
        "sexo":      "sexo",
        "personas":  "total_personas",
    }
    # ────────────────────────────────────────────────────────────────────

    cols_ok = [v for v in COLS_MAPA.values() if v in df_head.columns]
    if not cols_ok:
        print("  ⚠️  Ninguna columna del mapa encontrada.")
        print("  Actualiza COLS_MAPA y vuelve a ejecutar.")
        return pd.DataFrame()

    df = pd.read_csv(archivo, usecols=cols_ok, low_memory=False)
    df = df.rename(columns={v: k for k, v in COLS_MAPA.items() if v in df.columns})
    for col in ["provincia", "canton", "ciiu"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()
    if "personas" in df.columns:
        df["personas"] = pd.to_numeric(df["personas"], errors="coerce")
    df["anio_censo"] = 2022
    df = df.dropna(how="all").reset_index(drop=True)
    resumen(df, "silver_censo")
    return df


def main():
    print("=" * 60)
    print("  transform/inec.py — Limpieza y carga fuentes INEC")
    print("=" * 60)
    engine = get_engine()
    df_enemdu = limpiar_enemdu()
    df_censo  = limpiar_censo()
    cargar_tabla(df_enemdu, "silver_enemdu", engine)
    if not df_censo.empty:
        cargar_tabla(df_censo, "silver_censo", engine)
    print("\n  Verificación:")
    with engine.connect() as conn:
        for t in ["silver_enemdu", "silver_censo"]:
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                print(f"    {t}: {n} filas")
            except Exception as e:
                print(f"    {t}: ⚠️  {e}")
    print("\n  ✅  INEC completo.")

if __name__ == "__main__":
    main()