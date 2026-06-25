"""
transform/bce.py
================
Semana 2 — Limpieza y carga de todas las fuentes del Banco Central del Ecuador.

Tablas Silver que genera:
  - silver_pib_real          (retropolacion_1965_2024p.xlsx  → hoja 'PIB pc nominal')
  - silver_pib_nominal       (pib-per-cpita-nominal.csv)
  - silver_vab               (Boletin_retropolacion_regionales_2007_2024p_val.xlsx → hoja 'VAB provincial')
  - silver_petroleo_riesgo   (petroleo_wti.csv + petroleo_crudo_ecu.csv + riesgo_pais.csv)
  - silver_iee               (IEE_Nueva_Metodologia.xlsx)

Uso:
  python transform/bce.py
"""

import os
import re
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/macroentorno_ec")

BASE = r"C:\Users\marti\OneDrive\Documentos\Practicum 2.2\Practicum_2.2_Linea_Datos\macroentorno_pipeline"
BRONZE_BCE = os.path.join(BASE, "datos_crudos", "bce")


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
        print(f"  Nulos: {nulos.to_dict()}")
    print(f"  Primeras 3 filas:\n{df.head(3).to_string(index=False)}")


# ─────────────────────────────────────────
# 1. PIB real — silver_pib_real
# ─────────────────────────────────────────
def limpiar_pib_real():
    """
    Fuente: retropolacion_1965_2024p.xlsx | Hoja: 'PIB pc nominal'
    Decisiones:
    - header=9: primeros 9 renglones son metadatos del BCE.
    - Solo primeras 5 columnas (hay columnas vacías a la derecha).
    - 2024 viene como '2024 (p)' → limpiar con regex.
    - variacion_pct en 1965 = NaN → correcto, no eliminar.
    """
    archivo = os.path.join(BRONZE_BCE, "retropolacion_1965_2024p.xlsx")
    print(f"\n[1] Leyendo {os.path.basename(archivo)} ...")

    df = pd.read_excel(archivo, sheet_name="PIB pc nominal",
                       engine="openpyxl", header=9)
    df = df.iloc[:, :5].copy()
    df.columns = ["anio", "pib_musd", "poblacion", "pib_percapita", "variacion_pct"]

    mascara = df["anio"].astype(str).str.match(r"^\d{4}(\s*\(p\))?$", na=False)
    df = df[mascara].copy()
    df["anio"] = (df["anio"].astype(str)
                  .str.replace(r"\s*\(p\)", "", regex=True)
                  .astype(int))

    for col in ["pib_musd", "poblacion", "pib_percapita", "variacion_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("anio").reset_index(drop=True)
    resumen(df, "silver_pib_real")
    return df


# ─────────────────────────────────────────
# 2. PIB per cápita nominal — silver_pib_nominal
# ─────────────────────────────────────────
def limpiar_pib_nominal():
    """
    Fuente: pib-per-cpita-nominal.csv
    Decisiones:
    - sep=; | encoding=utf-8-sig | decimal coma europea
    - Fecha anual → columna 'fecha' DATE + 'anio' INTEGER
    - Serie 2000-2025 (26 registros)
    """
    archivo = os.path.join(BRONZE_BCE, "pib-per-cpita-nominal.csv")
    print(f"\n[2] Leyendo {os.path.basename(archivo)} ...")

    df = pd.read_csv(archivo, sep=";", encoding="utf-8-sig")
    df.columns = ["fecha", "pib_percapita_nominal_usd"]
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["anio"] = df["fecha"].dt.year
    df["pib_percapita_nominal_usd"] = (
        df["pib_percapita_nominal_usd"]
        .astype(str).str.replace(",", ".", regex=False)
    )
    df["pib_percapita_nominal_usd"] = pd.to_numeric(
        df["pib_percapita_nominal_usd"], errors="coerce"
    )
    df = df.dropna(subset=["fecha", "pib_percapita_nominal_usd"])
    df = df[["fecha", "anio", "pib_percapita_nominal_usd"]].sort_values("anio").reset_index(drop=True)
    resumen(df, "silver_pib_nominal")
    return df


# ─────────────────────────────────────────
# 3. VAB provincial — silver_vab
# ─────────────────────────────────────────
def limpiar_vab():
    """
    Fuente: Boletin_retropolacion_regionales_2007_2024p_val.xlsx | Hoja: 'VAB provincial'
    Decisiones:
    - Estructura wide: COD. | Provincia | 2007 | ... | 2024 (p)
    - header=8 → fila 9 del Excel tiene los encabezados reales
    - melt() → formato long: anio | cod_provincia | provincia | vab_miles_usd
    - '2024 (p)' → limpiar a 2024 entero
    - 28 provincias × 18 años = 504 filas
    """
    archivo = os.path.join(BRONZE_BCE, "Boletin_retropolacion_regionales_2007_2024p_val.xlsx")
    print(f"\n[3] Leyendo {os.path.basename(archivo)} ...")

    df = pd.read_excel(archivo, sheet_name="VAB provincial",
                       engine="openpyxl", header=8)
    df = df.rename(columns={"COD.": "cod_provincia", "Provincia": "provincia"})
    df = df.dropna(subset=["cod_provincia"])
    df = df[df["cod_provincia"].astype(str).str.match(r"^\d+$")]
    df["provincia"] = df["provincia"].astype(str).str.strip().str.title()
    df["cod_provincia"] = df["cod_provincia"].astype(str).str.zfill(2)

    cols_anio = [c for c in df.columns if c not in ["cod_provincia", "provincia"]]
    df_long = df.melt(id_vars=["cod_provincia", "provincia"],
                      value_vars=cols_anio,
                      var_name="anio_raw", value_name="vab_miles_usd")

    df_long["anio"] = (
        df_long["anio_raw"].astype(str)
        .str.replace(r"\s*\(p\)", "", regex=True)
        .str.extract(r"(\d{4})")[0]
        .astype(int)
    )
    df_long["vab_miles_usd"] = pd.to_numeric(df_long["vab_miles_usd"], errors="coerce")
    df_long = df_long.dropna(subset=["vab_miles_usd"])
    df_long = df_long[["anio", "cod_provincia", "provincia", "vab_miles_usd"]] \
        .sort_values(["anio", "cod_provincia"]).reset_index(drop=True)

    resumen(df_long, "silver_vab")
    return df_long


# ─────────────────────────────────────────
# 4. Petróleo y Riesgo País — silver_petroleo_riesgo
# ─────────────────────────────────────────
def limpiar_petroleo_riesgo():
    """
    Fuentes:
      - petroleo_wti.csv       → diario, desde 2015-01-02 (3.803 filas)
      - petroleo_crudo_ecu.csv → mensual, desde 2000-01-01 (315 filas)
      - riesgo_pais.csv        → diario, desde 2004-07-29 (7.303 filas)
    Decisiones:
    - sep=; | encoding=utf-8-sig | decimal coma europea
    - Merge outer por fecha → NULLs documentados y esperados
    - riesgo_pais_pb < 0 → NaN (imposible)
    - Se eliminan fechas futuras
    """
    def leer_csv(nombre, col):
        ruta = os.path.join(BRONZE_BCE, nombre)
        print(f"    Leyendo {nombre} ...")
        df = pd.read_csv(ruta, sep=";", encoding="utf-8-sig")
        df.columns = ["fecha", col]
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df[col] = df[col].astype(str).str.replace(",", ".", regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["fecha", col])
        df = df[df["fecha"] <= pd.Timestamp.today()]
        return df

    print(f"\n[4] Leyendo archivos de petróleo y riesgo país ...")
    df_wti    = leer_csv("petroleo_wti.csv",       "precio_petroleo_wti")
    df_ecu    = leer_csv("petroleo_crudo_ecu.csv", "precio_crudo_ecu")
    df_riesgo = leer_csv("riesgo_pais.csv",        "riesgo_pais_pb")

    df_riesgo.loc[df_riesgo["riesgo_pais_pb"] < 0, "riesgo_pais_pb"] = None

    df = df_wti.merge(df_ecu,    on="fecha", how="outer")
    df = df.merge(df_riesgo,     on="fecha", how="outer")
    df = df.sort_values("fecha").reset_index(drop=True)

    resumen(df, "silver_petroleo_riesgo")
    print(f"  Rango: {df['fecha'].min().date()} → {df['fecha'].max().date()}")
    return df


# ─────────────────────────────────────────
# 5. IEE — silver_iee
# ─────────────────────────────────────────
def limpiar_iee():
    """
    Fuente: IEE_Nueva_Metodologia.xlsx | Hoja: 'IEE'
    Decisiones:
    - header=7: fila 8 del Excel tiene encabezados (Fecha, IEE Global, Comercio, ...)
    - Serie mensual 2010-02-01 → 2026-04-01 (196 registros)
    - Última fila es nota al pie → eliminar filas sin fecha válida
    - Valores fuera de [0, 200] → NaN
    """
    archivo = os.path.join(BRONZE_BCE, "IEE_Nueva_Metodologia.xlsx")
    print(f"\n[5] Leyendo {os.path.basename(archivo)} ...")

    df = pd.read_excel(archivo, header=7, engine="openpyxl")
    df.columns = ["fecha", "iee_global", "iee_comercio",
                  "iee_construccion", "iee_manufactura", "iee_servicios"]
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"])

    for col in ["iee_global", "iee_comercio", "iee_construccion",
                "iee_manufactura", "iee_servicios"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        n = ((df[col] < 0) | (df[col] > 200)).sum()
        if n > 0:
            print(f"  ⚠️  {col}: {n} valores fuera de [0,200] → NaN")
            df.loc[(df[col] < 0) | (df[col] > 200), col] = None

    df = df.drop_duplicates(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)
    resumen(df, "silver_iee")
    return df


# ─────────────────────────────────────────
# Orquestador
# ─────────────────────────────────────────
def main():
    print("=" * 60)
    print("  transform/bce.py — Limpieza y carga fuentes BCE")
    print("=" * 60)

    engine = get_engine()

    df_pib_real = limpiar_pib_real()
    df_pib_nom  = limpiar_pib_nominal()
    df_vab      = limpiar_vab()
    df_petroleo = limpiar_petroleo_riesgo()
    df_iee      = limpiar_iee()

    print("\n" + "=" * 60)
    print("  Cargando tablas Silver en PostgreSQL ...")
    print("=" * 60)

    cargar_tabla(df_pib_real, "silver_pib_real",        engine)
    cargar_tabla(df_pib_nom,  "silver_pib_nominal",     engine)
    cargar_tabla(df_vab,      "silver_vab",             engine)
    cargar_tabla(df_petroleo, "silver_petroleo_riesgo", engine)
    cargar_tabla(df_iee,      "silver_iee",             engine)

    print("\n" + "=" * 60)
    print("  Verificación de conteos:")
    with engine.connect() as conn:
        for t in ["silver_pib_real", "silver_pib_nominal", "silver_vab",
                  "silver_petroleo_riesgo", "silver_iee"]:
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                print(f"    {t}: {n} filas")
            except Exception as e:
                print(f"    {t}: ⚠️  {e}")

    print("\n  ✅  Todas las tablas BCE cargadas correctamente.")
    print("=" * 60)


if __name__ == "__main__":
    main()
