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
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/macroentorno_ec")

BASE        = os.path.expanduser("/home/mar/Documentos/Practicum 2.2/Practicum_2.2_Linea_Datos/macroentorno_pipeline")
BRONZE_BCE  = os.path.join(BASE, "datos_crudos", "bce")


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
        print(f"  Nulos: {nulos.to_dict()}")
    print(f"  Primeras 3 filas:\n{df.head(3).to_string(index=False)}")


def limpiar_pib_real():
    """
    retropolacion_1965_2024p.xlsx | Hoja: PIB pc nominal | header=9
    - Solo primeras 5 columnas
    - 2024 (p) → limpiar a entero
    - variacion_pct 1965 = NaN → correcto, no eliminar
    """
    archivo = os.path.join(BRONZE_BCE, "retropolacion_1965_2024p.xlsx")
    print(f"\n[1] {os.path.basename(archivo)}")
    df = pd.read_excel(archivo, sheet_name="PIB pc nominal", engine="openpyxl", header=9)
    df = df.iloc[:, :5].copy()
    df.columns = ["anio", "pib_musd", "poblacion", "pib_percapita", "variacion_pct"]
    df = df[df["anio"].astype(str).str.match(r"^\d{4}(\s*\(p\))?$", na=False)].copy()
    df["anio"] = df["anio"].astype(str).str.replace(r"\s*\(p\)", "", regex=True).astype(int)
    for col in ["pib_musd", "poblacion", "pib_percapita", "variacion_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("anio").reset_index(drop=True)
    resumen(df, "silver_pib_real")
    return df


def limpiar_pib_nominal():
    """
    pib-per-cpita-nominal.csv | sep=; | encoding=utf-8-sig | decimal coma
    - Fecha anual → DATE + anio INTEGER
    - Serie 2000-2025 (26 registros)
    """
    archivo = os.path.join(BRONZE_BCE, "pib-per-cpita-nominal.csv")
    print(f"\n[2] {os.path.basename(archivo)}")
    df = pd.read_csv(archivo, sep=";", encoding="utf-8-sig")
    df.columns = ["fecha", "pib_percapita_nominal_usd"]
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["anio"]  = df["fecha"].dt.year
    df["pib_percapita_nominal_usd"] = (
        df["pib_percapita_nominal_usd"].astype(str).str.replace(",", ".", regex=False)
    )
    df["pib_percapita_nominal_usd"] = pd.to_numeric(df["pib_percapita_nominal_usd"], errors="coerce")
    df = df.dropna(subset=["fecha", "pib_percapita_nominal_usd"])
    df = df[["fecha", "anio", "pib_percapita_nominal_usd"]].sort_values("anio").reset_index(drop=True)
    resumen(df, "silver_pib_nominal")
    return df


def limpiar_vab():
    """
    Boletin_retropolacion_regionales_2007_2024p_val.xlsx | Hoja: VAB provincial | header=8
    - Estructura wide → melt a long
    - 28 provincias × 18 años = 504 filas
    - 2024 (p) → limpiar a entero
    """
    archivo = os.path.join(BRONZE_BCE, "Boletin_retropolacion_regionales_2007_2024p_val.xlsx")
    print(f"\n[3] {os.path.basename(archivo)}")
    df = pd.read_excel(archivo, sheet_name="VAB provincial", engine="openpyxl", header=8)
    df = df.rename(columns={"COD.": "cod_provincia", "Provincia": "provincia"})
    df = df.dropna(subset=["cod_provincia"])
    df = df[df["cod_provincia"].astype(str).str.match(r"^\d+$")]
    df["provincia"]    = df["provincia"].astype(str).str.strip().str.title()
    df["cod_provincia"]= df["cod_provincia"].astype(str).str.zfill(2)
    cols_anio = [c for c in df.columns if c not in ["cod_provincia", "provincia"]]
    df_long = df.melt(id_vars=["cod_provincia", "provincia"],
                      value_vars=cols_anio, var_name="anio_raw", value_name="vab_miles_usd")
    df_long["anio"] = (
        df_long["anio_raw"].astype(str)
        .str.replace(r"\s*\(p\)", "", regex=True)
        .str.extract(r"(\d{4})")[0].astype(int)
    )
    df_long["vab_miles_usd"] = pd.to_numeric(df_long["vab_miles_usd"], errors="coerce")
    df_long = df_long.dropna(subset=["vab_miles_usd"])
    df_long = df_long[["anio", "cod_provincia", "provincia", "vab_miles_usd"]] \
        .sort_values(["anio", "cod_provincia"]).reset_index(drop=True)
    resumen(df_long, "silver_vab")
    return df_long


def limpiar_petroleo_riesgo():
    """
    3 CSVs | sep=; | encoding=utf-8-sig | decimal coma europea
      petroleo_wti.csv       → diario  2015-01-02 → 2026-06-24
      petroleo_crudo_ecu.csv → mensual 2000-01-01 → 2026-04-01
      riesgo_pais.csv        → diario  2004-07-29 → 2026-06-24
    Merge outer → NULLs esperados y documentados
    """
    def leer_csv(nombre, col):
        ruta = os.path.join(BRONZE_BCE, nombre)
        print(f"    Leyendo {nombre} ...")
        df = pd.read_csv(ruta, sep=";", encoding="utf-8-sig")
        df.columns = ["fecha", col]
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df[col] = df[col].astype(str).str.replace(",", ".", regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["fecha", col])

    print(f"\n[4] Petróleo y riesgo país (3 archivos)")
    df_wti    = leer_csv("petroleo_wti.csv",       "precio_petroleo_wti")
    df_ecu    = leer_csv("petroleo_crudo_ecu.csv", "precio_crudo_ecu")
    df_riesgo = leer_csv("riesgo_pais.csv",        "riesgo_pais_pb")
    df_riesgo.loc[df_riesgo["riesgo_pais_pb"] < 0, "riesgo_pais_pb"] = None
    df = df_wti.merge(df_ecu, on="fecha", how="outer")
    df = df.merge(df_riesgo, on="fecha", how="outer")
    df = df[df["fecha"] <= pd.Timestamp.today()].sort_values("fecha").reset_index(drop=True)
    resumen(df, "silver_petroleo_riesgo")
    return df


def limpiar_iee():
    """
    IEE_Nueva_Metodologia.xlsx | header=7
    - 196 registros mensuales 2010-02-01 → 2026-04-01
    - Última fila es nota al pie → dropna por fecha
    """
    archivo = os.path.join(BRONZE_BCE, "IEE_Nueva_Metodologia.xlsx")
    print(f"\n[5] {os.path.basename(archivo)}")
    df = pd.read_excel(archivo, header=7, engine="openpyxl")
    df.columns = ["fecha", "iee_global", "iee_comercio",
                  "iee_construccion", "iee_manufactura", "iee_servicios"]
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"])
    for col in ["iee_global", "iee_comercio", "iee_construccion",
                "iee_manufactura", "iee_servicios"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[(df[col] < 0) | (df[col] > 200), col] = None
    df = df.drop_duplicates(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)
    resumen(df, "silver_iee")
    return df


def main():
    print("=" * 60)
    print("  transform/bce.py — Limpieza y carga fuentes BCE")
    print("=" * 60)
    engine = get_engine()
    cargar_tabla(limpiar_pib_real(),          "silver_pib_real",        engine)
    cargar_tabla(limpiar_pib_nominal(),       "silver_pib_nominal",     engine)
    cargar_tabla(limpiar_vab(),               "silver_vab",             engine)
    cargar_tabla(limpiar_petroleo_riesgo(),   "silver_petroleo_riesgo", engine)
    cargar_tabla(limpiar_iee(),               "silver_iee",             engine)
    print("\n  Verificación:")
    with engine.connect() as conn:
        for t in ["silver_pib_real","silver_pib_nominal","silver_vab",
                  "silver_petroleo_riesgo","silver_iee"]:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"    {t}: {n} filas")
    print("\n  ✅  BCE completo.")

if __name__ == "__main__":
    main()
    