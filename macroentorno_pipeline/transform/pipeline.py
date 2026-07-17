"""
transform/pipeline.py
=====================
Lee tab_consolidado, expande los DATOS_JSON a las tablas analíticas.
"""

import os
import json
import argparse
import pandas as pd
from datetime import datetime, date
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://marti:marti2024@localhost:5432/macroentorno_ec"
)

def get_engine():
    return create_engine(DATABASE_URL)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ─────────────────────────────────────────────────────────────
# Utilidades — reciben conn para usar la misma transacción
# ─────────────────────────────────────────────────────────────

def upsert_dim_tiempo(conn, fecha: date) -> int:
    """Inserta en dim_tiempo si no existe. Usa la misma conn/transacción."""
    result = conn.execute(text("""
        INSERT INTO dim_tiempo (fecha, anio, mes, trimestre)
        VALUES (:fecha, :anio, :mes, :trim)
        ON CONFLICT (fecha) DO NOTHING
        RETURNING id_tiempo
    """), {
        "fecha": fecha,
        "anio":  fecha.year,
        "mes":   fecha.month,
        "trim":  (fecha.month - 1) // 3 + 1
    })
    row = result.fetchone()
    if row:
        return row[0]
    r2 = conn.execute(
        text("SELECT id_tiempo FROM dim_tiempo WHERE fecha = :f"),
        {"f": fecha}
    )
    return r2.fetchone()[0]


def upsert_dim_geografia(conn, provincia: str, cod_prov: str,
                          canton: str = None, cod_canton: str = None) -> int:
    """Inserta en dim_geografia si no existe. Usa la misma conn/transacción."""
    result = conn.execute(text("""
        INSERT INTO dim_geografia (provincia, cod_provincia, canton, cod_canton)
        VALUES (:prov, :cprov, :cant, :ccant)
        ON CONFLICT (cod_provincia, COALESCE(cod_canton, '0000')) DO NOTHING
        RETURNING id_geo
    """), {
        "prov":  provincia.title() if provincia else "SIN DATO",
        "cprov": str(cod_prov).zfill(2),
        "cant":  canton.title() if canton else None,
        "ccant": str(cod_canton).zfill(4) if cod_canton else None
    })
    row = result.fetchone()
    if row:
        return row[0]
    r2 = conn.execute(text("""
        SELECT id_geo FROM dim_geografia
        WHERE cod_provincia = :cp
          AND COALESCE(cod_canton, '0000') = :cc
    """), {
        "cp": str(cod_prov).zfill(2),
        "cc": str(cod_canton).zfill(4) if cod_canton else "0000"
    })
    return r2.fetchone()[0]


def leer_consolidado(engine, indicador=None, solo_nuevos=False):
    filtro_est = "AND estado = 'COMPLETO'" if solo_nuevos else ""
    with engine.connect() as conn:
        if indicador:
            sql = f"""
                SELECT id, indicador, fecha_extraccion, datos_json, dato_clave
                FROM tab_consolidado
                WHERE indicador = '{indicador}'
                {filtro_est}
                ORDER BY indicador, dato_clave
            """
        else:
            sql = f"""
                SELECT id, indicador, fecha_extraccion, datos_json, dato_clave
                FROM tab_consolidado
                WHERE 1=1 {filtro_est}
                ORDER BY indicador, dato_clave
            """
        return pd.read_sql(sql, conn)


# ─────────────────────────────────────────────────────────────
# Procesadores — cada uno abre UNA sola conexión para todo
# ─────────────────────────────────────────────────────────────

def procesar_petroleo_riesgo(engine, df_tc):
    log("Procesando petroleo_riesgo ...")
    df = df_tc[df_tc["indicador"].isin(["PRECIO_PETROLEO_WTI","RIESGO_PAIS"])].copy()
    if df.empty:
        log("  Sin datos."); return

    insertados = 0
    with engine.begin() as conn:  # begin() = autocommit al salir del with
        for _, row in df.iterrows():
            datos = row["datos_json"] if isinstance(row["datos_json"], dict) \
                    else json.loads(row["datos_json"])
            fecha = pd.to_datetime(datos.get("fecha_fiscal")).date()
            valor = float(datos.get("valor", 0) or 0)
            id_t  = upsert_dim_tiempo(conn, fecha)

            if row["indicador"] == "PRECIO_PETROLEO_WTI":
                conn.execute(text("""
                    INSERT INTO petroleo_riesgo (id_tiempo, precio_wti, fecha_extraccion)
                    VALUES (:id_t, :val, :fext)
                    ON CONFLICT (id_tiempo) DO UPDATE SET
                        precio_wti = EXCLUDED.precio_wti,
                        fecha_extraccion = EXCLUDED.fecha_extraccion
                """), {"id_t": id_t, "val": valor, "fext": row["fecha_extraccion"]})
            else:
                conn.execute(text("""
                    INSERT INTO petroleo_riesgo (id_tiempo, riesgo_pais_pb, fecha_extraccion)
                    VALUES (:id_t, :val, :fext)
                    ON CONFLICT (id_tiempo) DO UPDATE SET
                        riesgo_pais_pb = EXCLUDED.riesgo_pais_pb,
                        fecha_extraccion = EXCLUDED.fecha_extraccion
                """), {"id_t": id_t, "val": int(valor), "fext": row["fecha_extraccion"]})
            insertados += 1

    log(f"  ✅ petroleo_riesgo: {insertados} filas.")


def procesar_iee(engine, df_tc):
    log("Procesando iee ...")
    df = df_tc[df_tc["indicador"]=="BCE_IEE_GLOBAL"].copy()
    if df.empty:
        log("  Sin datos."); return

    insertados = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            datos = row["datos_json"] if isinstance(row["datos_json"], dict) \
                    else json.loads(row["datos_json"])
            periodo = datos.get("periodo_fiscal") or datos.get("fecha_publicacion")
            fecha = pd.to_datetime(periodo).date()
            m = datos.get("metricas", {})
            id_t = upsert_dim_tiempo(conn, fecha)
            conn.execute(text("""
                INSERT INTO iee (id_tiempo, iee_global, iee_comercio,
                    iee_construccion, iee_manufactura, iee_servicios, fecha_extraccion)
                VALUES (:id_t,:glob,:com,:con,:man,:ser,:fext)
                ON CONFLICT (id_tiempo) DO UPDATE SET
                    iee_global=EXCLUDED.iee_global,
                    iee_comercio=EXCLUDED.iee_comercio,
                    iee_construccion=EXCLUDED.iee_construccion,
                    iee_manufactura=EXCLUDED.iee_manufactura,
                    iee_servicios=EXCLUDED.iee_servicios,
                    fecha_extraccion=EXCLUDED.fecha_extraccion
            """), {
                "id_t": id_t, "glob": m.get("iee_global"),
                "com": m.get("comercio"), "con": m.get("construccion"),
                "man": m.get("manufactura"), "ser": m.get("servicios"),
                "fext": row["fecha_extraccion"]
            })
            insertados += 1
    log(f"  ✅ iee: {insertados} filas.")


def procesar_pib(engine, df_tc):
    log("Procesando pib_real y pib_nominal ...")
    df = df_tc[df_tc["indicador"].isin(
        ["PIB_REAL_PER_CAPITA","PIB_NOMINAL_PER_CAPITA"])].copy()
    if df.empty:
        log("  Sin datos."); return

    insertados = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            datos = row["datos_json"] if isinstance(row["datos_json"], dict) \
                    else json.loads(row["datos_json"])
            anio = int(datos.get("anio_fiscal", datos.get("anio", 2000)))
            fecha = date(anio, 1, 1)
            id_t = upsert_dim_tiempo(conn, fecha)

            if row["indicador"] == "PIB_REAL_PER_CAPITA":
                conn.execute(text("""
                    INSERT INTO pib_real
                        (id_tiempo, pib_musd, poblacion, pib_percapita,
                         variacion_pct, fecha_extraccion)
                    VALUES (:id_t,:pib,:pob,:pc,:var,:fext)
                    ON CONFLICT (id_tiempo) DO UPDATE SET
                        pib_musd=EXCLUDED.pib_musd,
                        poblacion=EXCLUDED.poblacion,
                        pib_percapita=EXCLUDED.pib_percapita,
                        variacion_pct=EXCLUDED.variacion_pct,
                        fecha_extraccion=EXCLUDED.fecha_extraccion
                """), {
                    "id_t": id_t,
                    "pib": datos.get("pib_real_millones"),
                    "pob": datos.get("poblacion_total"),
                    "pc":  datos.get("pib_pc_real_usd"),
                    "var": datos.get("tasa_variacion_anual"),
                    "fext": row["fecha_extraccion"]
                })
            else:
                conn.execute(text("""
                    INSERT INTO pib_nominal
                        (id_tiempo, pib_percapita_nominal_usd, fecha_extraccion)
                    VALUES (:id_t,:val,:fext)
                    ON CONFLICT (id_tiempo) DO UPDATE SET
                        pib_percapita_nominal_usd=EXCLUDED.pib_percapita_nominal_usd,
                        fecha_extraccion=EXCLUDED.fecha_extraccion
                """), {
                    "id_t": id_t,
                    "val":  datos.get("pib_pc_nominal_usd"),
                    "fext": row["fecha_extraccion"]
                })
            insertados += 1
    log(f"  ✅ pib_real / pib_nominal: {insertados} filas.")


def procesar_enemdu(engine, df_tc):
    log("Procesando enemdu ...")
    df = df_tc[df_tc["indicador"]=="INEC_ENEMDU_POBLACIONES"].copy()
    if df.empty:
        log("  Sin datos."); return

    insertados = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            datos = row["datos_json"] if isinstance(row["datos_json"], dict) \
                    else json.loads(row["datos_json"])
            anio = int(datos.get("anio_fiscal", 2000))
            mes  = int(datos.get("mes_fiscal", 1))
            fecha = date(anio, mes, 1)
            id_t = upsert_dim_tiempo(conn, fecha)
            m = datos.get("metricas", {})
            conn.execute(text("""
                INSERT INTO enemdu
                    (id_tiempo, periodo_original, nombre_indicador,
                     nacional_total, area_urbana, area_rural,
                     sexo_hombre, sexo_mujer, fecha_extraccion)
                VALUES (:id_t,:per,:nom,:nat,:urb,:rur,:hom,:muj,:fext)
                ON CONFLICT (id_tiempo, nombre_indicador) DO UPDATE SET
                    nacional_total=EXCLUDED.nacional_total,
                    area_urbana=EXCLUDED.area_urbana,
                    area_rural=EXCLUDED.area_rural,
                    fecha_extraccion=EXCLUDED.fecha_extraccion
            """), {
                "id_t": id_t, "per": datos.get("periodo_original"),
                "nom": datos.get("nombre_indicador"),
                "nat": m.get("nacional_total"), "urb": m.get("area_urbana"),
                "rur": m.get("area_rural"), "hom": m.get("sexo_hombre"),
                "muj": m.get("sexo_mujer"), "fext": row["fecha_extraccion"]
            })
            insertados += 1
    log(f"  ✅ enemdu: {insertados} filas.")


def procesar_vab(engine, df_tc):
    log("Procesando vab_cantonal ...")
    df = df_tc[df_tc["indicador"]=="VAB_CANTONAL_CIIU"].copy()
    if df.empty:
        log("  Sin datos."); return

    insertados = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            datos = row["datos_json"] if isinstance(row["datos_json"], dict) \
                    else json.loads(row["datos_json"])
            anio = datos.get("anio")
            id_t = upsert_dim_tiempo(conn, date(int(anio), 1, 1)) if anio else None
            id_geo = upsert_dim_geografia(
                conn,
                provincia=datos.get("provincia","SIN DATO"),
                cod_prov=datos.get("codigo_provincia","00"),
                canton=datos.get("canton"),
                cod_canton=datos.get("codigo_canton")
            )
            for sector, valor in datos.get("sectores", {}).items():
                conn.execute(text("""
                    INSERT INTO vab_cantonal
                        (id_tiempo, id_geo, sector, vab_miles_usd, fecha_extraccion)
                    VALUES (:id_t,:id_geo,:sec,:val,:fext)
                    ON CONFLICT (id_tiempo, id_geo, sector) DO UPDATE SET
                        vab_miles_usd=EXCLUDED.vab_miles_usd,
                        fecha_extraccion=EXCLUDED.fecha_extraccion
                """), {
                    "id_t": id_t, "id_geo": id_geo, "sec": sector,
                    "val": valor, "fext": row["fecha_extraccion"]
                })
                insertados += 1
    log(f"  ✅ vab_cantonal: {insertados} filas.")


def procesar_matriz_empleo(engine, df_tc):
    log("Procesando matriz_empleo ...")
    df = df_tc[df_tc["indicador"].isin(
        ["MATRIZ_EMPLEO_VAB","MATRIZ_EMPLEO_TOTAL"])].copy()
    if df.empty:
        log("  Sin datos."); return

    import re as _re
    insertados = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            datos = row["datos_json"] if isinstance(row["datos_json"], dict) \
                    else json.loads(row["datos_json"])
            # Limpiar año: '2024P' → 2024
            anio_raw = str(datos.get("anio", 2000))
            anio = int(_re.sub(r"[^0-9]", "", anio_raw) or 2000)
            id_t = upsert_dim_tiempo(conn, date(anio, 1, 1))
            tipo = "VAB" if row["indicador"]=="MATRIZ_EMPLEO_VAB" else "EMPLEO_TOTAL"
            conn.execute(text("""
                INSERT INTO matriz_empleo
                    (id_tiempo, codigo_cie, seccion, industria,
                     valor, unidad, tipo, fecha_extraccion)
                VALUES (:id_t,:cie,:sec,:ind,:val,:uni,:tipo,:fext)
                ON CONFLICT (id_tiempo, codigo_cie, tipo) DO UPDATE SET
                    valor=EXCLUDED.valor,
                    fecha_extraccion=EXCLUDED.fecha_extraccion
            """), {
                "id_t": id_t, "cie": datos.get("codigo_cie"),
                "sec": datos.get("seccion"), "ind": datos.get("industria"),
                "val": datos.get("valor"), "uni": datos.get("unidad"),
                "tipo": tipo, "fext": row["fecha_extraccion"]
            })
            insertados += 1
    log(f"  ✅ matriz_empleo: {insertados} filas.")


def procesar_censo(engine, df_tc):
    log("Procesando censo_actividad y censo_ocupacion ...")
    df = df_tc[df_tc["indicador"].isin(
        ["CENSO_RAMA_ACTIVIDAD","CENSO_GRUPO_OCUPACION"])].copy()
    if df.empty:
        log("  Sin datos."); return

    insertados = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            datos = row["datos_json"] if isinstance(row["datos_json"], dict) \
                    else json.loads(row["datos_json"])
            id_geo = upsert_dim_geografia(
                conn,
                provincia=datos.get("provincia","SIN DATO"),
                cod_prov=datos.get("codigo_provincia","00")
                         if datos.get("codigo_provincia") else "00",
                canton=datos.get("canton")
            )
            if row["indicador"] == "CENSO_RAMA_ACTIVIDAD":
                for rama, personas in datos.get("ramas_actividad", {}).items():
                    conn.execute(text("""
                        INSERT INTO censo_actividad
                            (id_geo, anio_censo, sexo, rango_edad,
                             rama_actividad, personas_ocupadas, fecha_extraccion)
                        VALUES (:ig,2022,:sx,:ed,:rama,:per,:fext)
                        ON CONFLICT (id_geo, sexo, rango_edad, rama_actividad)
                        DO UPDATE SET
                            personas_ocupadas=EXCLUDED.personas_ocupadas,
                            fecha_extraccion=EXCLUDED.fecha_extraccion
                    """), {
                        "ig": id_geo, "sx": datos.get("sexo"),
                        "ed": datos.get("rango_edad"), "rama": rama,
                        "per": personas, "fext": row["fecha_extraccion"]
                    })
                    insertados += 1
            else:
                for grupo, personas in datos.get("grupos_ocupacion", {}).items():
                    conn.execute(text("""
                        INSERT INTO censo_ocupacion
                            (id_geo, anio_censo, sexo, rango_edad,
                             grupo_ocupacion, personas, fecha_extraccion)
                        VALUES (:ig,2022,:sx,:ed,:gr,:per,:fext)
                        ON CONFLICT (id_geo, sexo, rango_edad, grupo_ocupacion)
                        DO UPDATE SET
                            personas=EXCLUDED.personas,
                            fecha_extraccion=EXCLUDED.fecha_extraccion
                    """), {
                        "ig": id_geo, "sx": datos.get("sexo"),
                        "ed": datos.get("rango_edad"), "gr": grupo,
                        "per": personas, "fext": row["fecha_extraccion"]
                    })
                    insertados += 1
    log(f"  ✅ censo_actividad / censo_ocupacion: {insertados} filas.")


def procesar_mineduc(engine, df_tc):
    log("Procesando mineduc_amie ...")
    df = df_tc[df_tc["indicador"]=="MINEDUC_AMIE_COSTA"].copy()
    if df.empty:
        log("  Sin datos."); return

    insertados = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            datos = row["datos_json"] if isinstance(row["datos_json"], dict) \
                    else json.loads(row["datos_json"])
            inst = datos.get("institucion", {})
            # Resumen de estudiantes
            est_res  = datos.get("estudiantes_resumen", {})
            # Detalle por año
            est_det  = datos.get("estudiantes_detallado", {})
            bach3    = est_det.get("bachillerato_3er_ano", {})
            bach3_h  = bach3.get("h", 0) or 0
            bach3_m  = bach3.get("m", 0) or 0
            bach3_t  = bach3_h + bach3_m

            id_geo = upsert_dim_geografia(
                conn,
                provincia=inst.get("provincia", "SIN DATO"),
                cod_prov=str(inst.get("cod_provincia", "00")).zfill(2),
                canton=inst.get("canton"),
                cod_canton=str(inst.get("cod_canton","0000")).zfill(4)
                           if inst.get("cod_canton") else None
            )
            conn.execute(text("""
                INSERT INTO mineduc_amie
                    (id_geo, periodo_lectivo, anio_base, amie,
                     nombre_institucion, zona, parroquia, nivel_educacion,
                     sostenimiento, total_estudiantes,
                     bach3_total, bach3_femenino, bach3_masculino,
                     fecha_extraccion)
                VALUES (:ig,:per,:anio,:amie,:nom,:zona,:parr,:niv,
                        :sos,:tot,:b3t,:b3f,:b3m,:fext)
                ON CONFLICT (amie, periodo_lectivo) DO UPDATE SET
                    total_estudiantes=EXCLUDED.total_estudiantes,
                    bach3_total=EXCLUDED.bach3_total,
                    bach3_femenino=EXCLUDED.bach3_femenino,
                    bach3_masculino=EXCLUDED.bach3_masculino,
                    fecha_extraccion=EXCLUDED.fecha_extraccion
            """), {
                "ig":   id_geo,
                "per":  datos.get("periodo_lectivo"),
                "anio": datos.get("anio_base"),
                "amie": inst.get("amie"),
                "nom":  inst.get("nombre"),
                "zona": inst.get("zona"),
                "parr": inst.get("parroquia"),
                "niv":  inst.get("nivel_educacion"),
                "sos":  inst.get("sostenimiento"),
                "tot":  est_res.get("total_estudiantes"),
                "b3t":  bach3_t if bach3_t > 0 else None,
                "b3f":  bach3_m if bach3_m > 0 else None,
                "b3m":  bach3_h if bach3_h > 0 else None,
                "fext": row["fecha_extraccion"]
            })
            insertados += 1
    log(f"  ✅ mineduc_amie: {insertados} filas.")


def procesar_supercias(engine, df_tc):
    log("Procesando supercias_directorio ...")
    df = df_tc[df_tc["indicador"]=="SUPERCIAS_DIRECTORIO"].copy()
    if df.empty:
        log("  Sin datos."); return

    insertados = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            datos = row["datos_json"] if isinstance(row["datos_json"], dict) \
                    else json.loads(row["datos_json"])
            emp = datos.get("empresa_metadata", {})
            ubi = datos.get("ubicacion", {})
            fin = datos.get("financiero_ciiu", {})
            id_geo = upsert_dim_geografia(
                conn,
                provincia=ubi.get("provincia","SIN DATO"),
                cod_prov=str(ubi.get("cod_provincia","00")).zfill(2)
                         if ubi.get("cod_provincia") else "00",
                canton=ubi.get("canton")
            )
            conn.execute(text("""
                INSERT INTO supercias_directorio
                    (id_geo, periodo_reporte, expediente, ruc, nombre,
                     situacion_legal, tipo_compania, ciiu_nivel1, ciiu_nivel6,
                     capital_suscrito, ultimo_balance_anio, fecha_extraccion)
                VALUES (:ig,:per,:exp,:ruc,:nom,:sl,:tc,:c1,:c6,:cap,:ub,:fext)
                ON CONFLICT (expediente, periodo_reporte) DO UPDATE SET
                    situacion_legal=EXCLUDED.situacion_legal,
                    fecha_extraccion=EXCLUDED.fecha_extraccion
            """), {
                "ig": id_geo, "per": datos.get("periodo_reporte"),
                "exp": int(emp.get("expediente", 0)),
                "ruc": emp.get("ruc"),
                "nom": emp.get("nombre","").title() if emp.get("nombre") else None,
                "sl":  emp.get("situacion_legal"),
                "tc":  emp.get("tipo_compania"),
                "c1":  fin.get("ciiu_nivel1"), "c6": fin.get("ciiu_nivel6"),
                "cap": fin.get("capital_suscrito"),
                "ub":  int(str(fin["ultimo_balance_anio"]).strip())
                       if fin.get("ultimo_balance_anio") and
                          str(fin.get("ultimo_balance_anio","")).strip().isdigit()
                       else None,
                "fext":row["fecha_extraccion"]
            })
            insertados += 1
    log(f"  ✅ supercias_directorio: {insertados} filas.")


# ─────────────────────────────────────────────────────────────
# Orquestador
# ─────────────────────────────────────────────────────────────

PROCESADORES = {
    "PRECIO_PETROLEO_WTI":     procesar_petroleo_riesgo,
    "RIESGO_PAIS":             procesar_petroleo_riesgo,
    "BCE_IEE_GLOBAL":          procesar_iee,
    "PIB_REAL_PER_CAPITA":     procesar_pib,
    "PIB_NOMINAL_PER_CAPITA":  procesar_pib,
    "INEC_ENEMDU_POBLACIONES": procesar_enemdu,
    "VAB_CANTONAL_CIIU":       procesar_vab,
    "MATRIZ_EMPLEO_VAB":       procesar_matriz_empleo,
    "MATRIZ_EMPLEO_TOTAL":     procesar_matriz_empleo,
    "CENSO_RAMA_ACTIVIDAD":    procesar_censo,
    "CENSO_GRUPO_OCUPACION":   procesar_censo,
    "MINEDUC_AMIE_COSTA":      procesar_mineduc,
    "SUPERCIAS_DIRECTORIO":    procesar_supercias,
}


def main():
    parser = argparse.ArgumentParser(description="Pipeline macroentorno")
    parser.add_argument("--indicador", help="Procesar solo este indicador")
    parser.add_argument("--solo-nuevos", action="store_true")
    args = parser.parse_args()

    engine = get_engine()
    log("=" * 55)
    log("  pipeline.py — Expansión JSON → tablas analíticas")
    log("=" * 55)

    df_tc = leer_consolidado(engine, args.indicador,
                              getattr(args, "solo_nuevos", False))
    log(f"  Registros leídos de tab_consolidado: {len(df_tc)}")

    if df_tc.empty:
        log("  Sin registros para procesar."); return

    ejecutados = set()
    for indicador, procesador in PROCESADORES.items():
        if args.indicador and indicador != args.indicador:
            continue
        if procesador.__name__ not in ejecutados:
            df_ind = df_tc[df_tc["indicador"].isin([
                k for k, v in PROCESADORES.items()
                if v.__name__ == procesador.__name__
            ])]
            if not df_ind.empty:
                procesador(engine, df_ind)
            ejecutados.add(procesador.__name__)

    log("\n  Conteos finales:")
    tablas = ["dim_tiempo","dim_geografia","pib_real","pib_nominal",
              "petroleo_riesgo","iee","enemdu","vab_cantonal","matriz_empleo",
              "censo_actividad","censo_ocupacion","mineduc_amie",
              "supercias_directorio"]
    with engine.connect() as conn:
        for t in tablas:
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                log(f"    {t}: {n:,} filas")
            except Exception as e:
                log(f"    {t}: ⚠️  {e}")

    log("\n  ✅  Pipeline completado.")


if __name__ == "__main__":
    main()