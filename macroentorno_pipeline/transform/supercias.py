"""
transform/supercias.py
======================
Semana 3 — Limpieza y carga fuentes Supercias (SCVS).

Tablas Silver que genera:
  - silver_supercias_ranking    (bi_ranking.csv)
  - silver_supercias_directorio (bi_compania.csv)

Estructura confirmada:
  bi_ranking.csv  → sep=, | 54 columnas | 1.673.303 filas | años 2008–2025
  bi_compania.csv → sep=, |  6 columnas | 338.402 filas

Uso:
  python transform/supercias.py
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/macroentorno_ec")

BASE = r"C:\Users\marti\OneDrive\Documentos\Practicum 2.2\Practicum_2.2_Linea_Datos\macroentorno_pipeline"
BRONZE_SUPER = os.path.join(BASE, "datos_crudos", "supercias")


def get_engine():
    return create_engine(DATABASE_URL)


def cargar_tabla(df, tabla, engine):
    df.to_sql(tabla, engine, if_exists="replace", index=False,
              chunksize=10_000, method="multi")
    print(f"  ✅ {tabla}: {len(df)} filas cargadas.")


def resumen(df, nombre):
    print(f"\n{'─'*55}")
    print(f"  {nombre}  |  shape={df.shape}")
    nulos = df.isnull().sum()
    nulos = nulos[nulos > 0]
    if not nulos.empty:
        print(f"  Nulos (top 5): {dict(list(nulos.items())[:5])}")
    print(f"  Primeras 2 filas:\n{df.head(2).to_string(index=False)}")


# ─────────────────────────────────────────
# 1. Ranking — silver_supercias_ranking
# ─────────────────────────────────────────
def limpiar_ranking():
    """
    Fuente: bi_ranking.csv
    Columnas clave para el proyecto:
      anio, expediente, ingresos_ventas, activos, patrimonio,
      n_empleados, ciiu_n1, ciiu_n6, cod_segmento
    Decisiones:
    - Archivo de 356 MB → leer en chunks de 100k filas para no saturar memoria
    - Se conservan TODAS las columnas (54) para tener datos completos en la BD
    - Se eliminan filas donde ingresos_ventas y activos son ambos NaN
    - anio como INTEGER — ya viene limpio (2008–2025)
    - ciiu_n1 y ciiu_n6 se convierten a string con zfill para preservar ceros
    - Se hace join con bi_compania para agregar provincia y nombre (ver abajo)
    """
    archivo = os.path.join(BRONZE_SUPER, "bi_ranking.csv")
    print(f"\n[1] Leyendo {os.path.basename(archivo)} (puede tardar ~30 seg) ...")

    chunks = []
    for chunk in pd.read_csv(archivo, low_memory=False, chunksize=100_000):
        # Eliminar filas completamente vacías en los indicadores clave
        chunk = chunk.dropna(subset=["ingresos_ventas", "activos"], how="all")
        chunks.append(chunk)

    df = pd.concat(chunks, ignore_index=True)
    print(f"  Leídas {len(df):,} filas con datos.")

    # Limpiar tipos
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
    df["expediente"] = pd.to_numeric(df["expediente"], errors="coerce").astype("Int64")

    # CIIU como string
    for col in ["ciiu_n1", "ciiu_n6"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper().replace("NAN", None)

    # Financieros como numeric
    cols_num = ["ingresos_ventas", "activos", "patrimonio", "utilidad_an_imp",
                "n_empleados", "ingresos_totales", "utilidad_ejercicio"]
    for col in cols_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    resumen(df, "silver_supercias_ranking")
    print(f"  Años: {sorted(df['anio'].dropna().unique().tolist())}")
    return df


# ─────────────────────────────────────────
# 2. Directorio — silver_supercias_directorio
# ─────────────────────────────────────────
def limpiar_directorio():
    """
    Fuente: bi_compania.csv
    Columnas: expediente, ruc, nombre, tipo, pro_codigo, provincia
    Decisiones:
    - 338.402 filas — carga completa sin chunks
    - Solo compañías activas según el reto → el archivo ya viene filtrado
      (Supercias publica solo activas con EEFF presentados)
    - nombre y provincia a title case para consistencia
    - pro_codigo como string con zfill(2) para que coincida con cod_provincia del BCE
    - Se eliminan filas sin RUC válido (13 dígitos)
    """
    archivo = os.path.join(BRONZE_SUPER, "bi_compania.csv")
    print(f"\n[2] Leyendo {os.path.basename(archivo)} ...")

    df = pd.read_csv(archivo, low_memory=False)
    # Columnas: expediente, ruc, nombre, tipo, pro_codigo, provincia

    df["expediente"] = pd.to_numeric(df["expediente"], errors="coerce").astype("Int64")
    df["pro_codigo"] = df["pro_codigo"].astype(str).str.strip().str.zfill(2).replace("nan", None)
    df["nombre"]     = df["nombre"].astype(str).str.strip().str.title()
    df["provincia"]  = df["provincia"].astype(str).str.strip().str.title()
    df["tipo"]       = df["tipo"].astype(str).str.strip()
    df["ruc"]        = df["ruc"].astype(str).str.strip()

    # Filtrar RUC inválidos (deben ser 13 dígitos)
    mascara_ruc = df["ruc"].str.match(r"^\d{13}$")
    n_invalidos = (~mascara_ruc).sum()
    if n_invalidos > 0:
        print(f"  ⚠️  {n_invalidos} filas con RUC inválido → eliminadas")
        df = df[mascara_ruc].copy()

    df = df.dropna(subset=["expediente"]).reset_index(drop=True)

    resumen(df, "silver_supercias_directorio")
    print(f"  Provincias únicas: {df['provincia'].nunique()}")
    return df


# ─────────────────────────────────────────
# Orquestador
# ─────────────────────────────────────────
def main():
    print("=" * 60)
    print("  transform/supercias.py — Limpieza y carga Supercias")
    print("=" * 60)

    engine = get_engine()

    df_ranking    = limpiar_ranking()
    df_directorio = limpiar_directorio()

    print("\n" + "=" * 60)
    print("  Cargando tablas Silver en PostgreSQL ...")
    print("=" * 60)

    cargar_tabla(df_ranking,    "silver_supercias_ranking",    engine)
    cargar_tabla(df_directorio, "silver_supercias_directorio", engine)

    print("\n" + "=" * 60)
    print("  Verificación de conteos:")
    with engine.connect() as conn:
        for t in ["silver_supercias_ranking", "silver_supercias_directorio"]:
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                print(f"    {t}: {n} filas")
            except Exception as e:
                print(f"    {t}: ⚠️  {e}")

    print("\n  ✅  Fuentes Supercias procesadas.")
    print("=" * 60)


if __name__ == "__main__":
    main()
