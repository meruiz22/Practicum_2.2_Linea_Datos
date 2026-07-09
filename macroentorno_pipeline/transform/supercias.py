"""
transform/supercias.py
======================
Semana 3 — Limpieza y carga fuentes Supercias.

Tablas Silver:
  - silver_supercias_ranking    (bi_ranking.csv  → 54 cols, ~1.67M filas, 2008-2025)
  - silver_supercias_directorio (bi_compania.csv → 6 cols, ~338k filas)

Uso:
  python transform/supercias.py
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL  = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/macroentorno_ec")

BASE          = os.path.expanduser("/home/mar/Documentos/Practicum 2.2/Practicum_2.2_Linea_Datos/macroentorno_pipeline")
BRONZE_SUPER  = os.path.join(BASE, "datos_crudos", "supercias")


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
        print(f"  Nulos (top 5): {dict(list(nulos.items())[:5])}")
    print(f"  Primeras 2 filas:\n{df.head(2).to_string(index=False)}")


def limpiar_ranking():
    """
    bi_ranking.csv | sep=, | 54 columnas | ~1.67M filas | años 2008-2025
    - Lectura en chunks de 100k para no saturar RAM
    - Se conservan todas las columnas (son indicadores financieros útiles para el dashboard)
    - ciiu_n1 y ciiu_n6 → string (preservar ceros a la izquierda)
    - Eliminar filas donde ingresos_ventas y activos son ambos NaN
    """
    archivo = os.path.join(BRONZE_SUPER, "bi_ranking.csv")
    print(f"\n[1] {os.path.basename(archivo)} (puede tardar ~30 seg) ...")
    chunks = []
    for chunk in pd.read_csv(archivo, low_memory=False, chunksize=100_000):
        chunk = chunk.dropna(subset=["ingresos_ventas", "activos"], how="all")
        chunks.append(chunk)
    df = pd.concat(chunks, ignore_index=True)
    print(f"  Leídas {len(df):,} filas con datos.")

    df["anio"]       = pd.to_numeric(df["anio"],       errors="coerce").astype("Int64")
    df["expediente"] = pd.to_numeric(df["expediente"], errors="coerce").astype("Int64")
    for col in ["ciiu_n1", "ciiu_n6"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper().replace("NAN", None)
    for col in ["ingresos_ventas","activos","patrimonio","utilidad_an_imp","n_empleados"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    resumen(df, "silver_supercias_ranking")
    print(f"  Años: {sorted(df['anio'].dropna().unique().tolist())}")
    return df


def limpiar_directorio():
    """
    bi_compania.csv | sep=, | 6 columnas: expediente, ruc, nombre, tipo, pro_codigo, provincia
    - ~338k empresas activas con EEFF presentados
    - pro_codigo → zfill(2) para coincidir con cod_provincia del BCE
    - RUC validado: 13 dígitos
    """
    archivo = os.path.join(BRONZE_SUPER, "bi_compania.csv")
    print(f"\n[2] {os.path.basename(archivo)}")
    df = pd.read_csv(archivo, low_memory=False)
    df["expediente"] = pd.to_numeric(df["expediente"], errors="coerce").astype("Int64")
    df["pro_codigo"] = df["pro_codigo"].astype(str).str.strip().str.zfill(2).replace("nan", None)
    df["nombre"]     = df["nombre"].astype(str).str.strip().str.title()
    df["provincia"]  = df["provincia"].astype(str).str.strip().str.title()
    df["tipo"]       = df["tipo"].astype(str).str.strip()
    df["ruc"]        = df["ruc"].astype(str).str.strip()
    n_inv = (~df["ruc"].str.match(r"^\d{13}$")).sum()
    if n_inv > 0:
        print(f"  ⚠️  {n_inv} filas con RUC inválido → eliminadas")
        df = df[df["ruc"].str.match(r"^\d{13}$")].copy()
    df = df.dropna(subset=["expediente"]).reset_index(drop=True)
    resumen(df, "silver_supercias_directorio")
    print(f"  Provincias únicas: {df['provincia'].nunique()}")
    return df


def main():
    print("=" * 60)
    print("  transform/supercias.py — Limpieza y carga Supercias")
    print("=" * 60)
    engine = get_engine()
    cargar_tabla(limpiar_ranking(),    "silver_supercias_ranking",    engine)
    cargar_tabla(limpiar_directorio(), "silver_supercias_directorio", engine)
    print("\n  Verificación:")
    with engine.connect() as conn:
        for t in ["silver_supercias_ranking", "silver_supercias_directorio"]:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"    {t}: {n} filas")
    print("\n  ✅  Supercias completo.")

if __name__ == "__main__":
    main()