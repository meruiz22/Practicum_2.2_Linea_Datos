"""
transform/cargar_rpa.py
=======================
Convierte el SQL exportado de Oracle (TAB_CONSOLIDADO)
a PostgreSQL e inserta los datos en tab_consolidado.

Problemas Oracle que resuelve:
  1. to_date('09/07/26','DD/MM/RR')   → '2026-07-09'
  2. JSON con comillas externas Oracle → JSONB limpio
     '\"{\\\"key\\\":\\\"val\\\"}\"'  → '{"key":"val"}'
  3. ID como NUMBER                   → BIGINT (se omite, es SERIAL)
  4. Columnas entre comillas dobles   → minúsculas sin comillas

"""

import re
import os
import json
import argparse
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://marti:marti2024@localhost:5432/macroentorno_ec"
)


def convertir_fecha(match):
    """
    to_date('09/07/26','DD/MM/RR') → '2026-07-09'
    Formato RR Oracle: 00-49 = 2000-2049, 50-99 = 1950-1999
    """
    fecha_str = match.group(1).strip("'")
    partes = fecha_str.split("/")
    if len(partes) == 3:
        dia, mes, anio_corto = partes
        anio = int("20" + anio_corto) if int(anio_corto) <= 49 \
               else int("19" + anio_corto)
        return f"'{anio}-{mes}-{dia}'"
    return match.group(0)


def limpiar_json_oracle(json_raw: str) -> str:
    """
    El JSON de Oracle viene como: '\"{\\\"key\\\":\\\"val\\\"}\"'
    Necesita convertirse a JSON válido para PostgreSQL JSONB.
    
    Pasos:
      1. Quitar comillas externas del string Oracle
      2. Des-escapar backslashes internos
      3. Validar que es JSON antes de retornar
    """
    # Quitar comilla simple de inicio y fin del valor SQL
    # El valor completo en el INSERT es: '\"{...}\"'
    # Dentro de Python ya llegamos sin las comillas simples externas
    
    # Paso 1: si empieza y termina con " → es el wrapper Oracle
    limpio = json_raw.strip()
    if limpio.startswith('\\"') or limpio.startswith('"'):
        # Quitar comilla doble externa
        if limpio.startswith('\\"') and limpio.endswith('\\"'):
            limpio = limpio[2:-2]
        elif limpio.startswith('"') and limpio.endswith('"'):
            limpio = limpio[1:-1]
    
    # Paso 2: des-escapar \" → "
    limpio = limpio.replace('\\"', '"')
    
    # Paso 3: validar JSON
    try:
        parsed = json.loads(limpio)
        return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        # Si no es JSON válido, retornar None para usar NULL
        return None


def extraer_valores(linea: str):
    """
    Extrae los valores del INSERT Oracle y retorna un dict
    listo para insertar en PostgreSQL con parámetros.
    
    INSERT into TAB_CONSOLIDADO (ID,INDICADOR,FECHA_EXTRACCION,ESTADO,
    NECESITA_RESPALDO,DETALLE_ERROR,DATOS_JSON,DATO_CLAVE,HASH_CONTENIDO)
    values ('88','PRECIO_PETROLEO_WTI',to_date(...),'COMPLETO','0',
            null,'"{...}"','2015-05-01','abc123');
    """
    # Convertir to_date primero
    linea = re.sub(
        r"to_date\('([^']+)',\s*'[^']+'\)",
        convertir_fecha,
        linea,
        flags=re.IGNORECASE
    )

    # Extraer el bloque values(...)
    m = re.search(r"values\s*\((.+)\)\s*;?\s*$", linea, re.IGNORECASE | re.DOTALL)
    if not m:
        return None

    values_str = m.group(1).strip()

    # Parsear los 9 campos en orden:
    # ID, INDICADOR, FECHA_EXTRACCION, ESTADO, NECESITA_RESPALDO,
    # DETALLE_ERROR, DATOS_JSON, DATO_CLAVE, HASH_CONTENIDO
    #
    # El JSON interno puede contener comas → no se puede hacer split simple
    # Usamos una máquina de estados simple

    campos = []
    i = 0
    campo_actual = ""
    en_string = False
    profundidad_json = 0

    while i < len(values_str):
        c = values_str[i]

        if not en_string and c == "'":
            en_string = True
            campo_actual += c
        elif en_string and c == "'" and i + 1 < len(values_str) and values_str[i+1] == "'":
            # Comilla escapada ''
            campo_actual += "''"
            i += 2
            continue
        elif en_string and c == "'":
            en_string = False
            campo_actual += c
        elif not en_string and c == ",":
            campos.append(campo_actual.strip())
            campo_actual = ""
            i += 1
            continue
        else:
            campo_actual += c
        i += 1

    if campo_actual.strip():
        campos.append(campo_actual.strip())

    if len(campos) < 9:
        return None

    def limpiar_str(v):
        """Quita comillas simples externas del valor SQL."""
        v = v.strip()
        if v.lower() == "null":
            return None
        if v.startswith("'") and v.endswith("'"):
            return v[1:-1]
        return v

    try:
        # id         = campos[0]  → ignorar, es SERIAL en PostgreSQL
        indicador        = limpiar_str(campos[1])
        fecha_extraccion = limpiar_str(campos[2])   # ya convertida de to_date
        estado           = limpiar_str(campos[3])
        necesita         = limpiar_str(campos[4])
        detalle_error    = limpiar_str(campos[5])
        datos_json_raw   = limpiar_str(campos[6])
        dato_clave       = limpiar_str(campos[7])
        hash_contenido   = limpiar_str(campos[8])

        # Limpiar JSON Oracle
        datos_json = limpiar_json_oracle(datos_json_raw) if datos_json_raw else None
        if datos_json is None:
            return None  # JSON inválido → descartar

        # Convertir fecha string → objeto date
        fecha_obj = None
        if fecha_extraccion:
            try:
                from datetime import datetime as dt
                fecha_obj = dt.strptime(fecha_extraccion, "%Y-%m-%d").date()
            except Exception:
                fecha_obj = None

        # Convertir JSON string → dict (psycopg2 lo serializa como JSONB)
        import json as _json
        datos_json_obj = None
        if datos_json:
            try:
                datos_json_obj = _json.loads(datos_json)
            except Exception:
                datos_json_obj = None

        if datos_json_obj is None:
            return None  # Sin JSON válido no insertamos

        return {
            "indicador":        indicador,
            "fecha_extraccion": fecha_obj,
            "estado":           estado or "COMPLETO",
            "necesita":         int(necesita) if necesita else 0,
            "detalle_error":    detalle_error,
            "datos_json":       _json.dumps(datos_json_obj, ensure_ascii=False),
            "dato_clave":       dato_clave,
            "hash_contenido":   hash_contenido or ""
        }
    except Exception:
        return None


INSERT_SQL = text("""
    INSERT INTO tab_consolidado
        (indicador, fecha_extraccion, estado, necesita_respaldo,
         detalle_error, datos_json, dato_clave, hash_contenido)
    VALUES
        (:indicador, :fecha_extraccion, :estado, :necesita,
         :detalle_error, :datos_json, :dato_clave, :hash_contenido)
    ON CONFLICT (indicador, dato_clave) DO UPDATE SET
        datos_json       = EXCLUDED.datos_json,
        fecha_extraccion = EXCLUDED.fecha_extraccion,
        hash_contenido   = EXCLUDED.hash_contenido
    WHERE tab_consolidado.hash_contenido <> EXCLUDED.hash_contenido
""")


def cargar_archivo(archivo: str, engine, verbose: bool = False):
    print(f"\n{'='*60}")
    print(f"  Cargando: {os.path.basename(archivo)}")
    print(f"{'='*60}")

    if not os.path.exists(archivo):
        print(f"  ❌ Archivo no encontrado: {archivo}")
        return

    # Contar inserts
    with open(archivo, "r", encoding="utf-8", errors="replace") as f:
        total_lineas = sum(
            1 for l in f
            if l.strip().lower().startswith("insert into tab_consolidado")
        )
    print(f"  Total INSERT a procesar: {total_lineas:,}")

    total = insertados = omitidos = errores = 0
    inicio = datetime.now()

    with open(archivo, "r", encoding="utf-8", errors="replace") as f:
        batch = []
        for linea in f:
            linea = linea.replace("\r\n", "\n").replace("\r", "")

            if not linea.strip().lower().startswith("insert into tab_consolidado"):
                continue

            valores = extraer_valores(linea)
            if valores is None:
                errores += 1
                if verbose:
                    print(f"  ⚠️  No se pudo parsear: {linea[:100]}")
                continue

            batch.append(valores)
            total += 1

            if len(batch) >= 500:
                with engine.connect() as conn:
                    for v in batch:
                        try:
                            result = conn.execute(INSERT_SQL, v)
                            if result.rowcount > 0:
                                insertados += 1
                            else:
                                omitidos += 1
                        except Exception as e:
                            errores += 1
                            if verbose:
                                print(f"  ⚠️  Error: {e}")
                                print(f"      Valores: {v}")
                    conn.commit()
                batch = []

                procesados = insertados + omitidos + errores
                if procesados % 10000 < 500:
                    elapsed = (datetime.now() - inicio).seconds
                    print(
                        f"  Procesados: {procesados:,} | "
                        f"Insertados: {insertados:,} | "
                        f"Omitidos: {omitidos:,} | "
                        f"Errores: {errores:,} | "
                        f"Tiempo: {elapsed}s"
                    )

        # Último lote
        if batch:
            with engine.connect() as conn:
                for v in batch:
                    try:
                        result = conn.execute(INSERT_SQL, v)
                        if result.rowcount > 0:
                            insertados += 1
                        else:
                            omitidos += 1
                    except Exception as e:
                        errores += 1
                        if verbose:
                            print(f"  ⚠️  Error: {e}")
                conn.commit()

    elapsed = (datetime.now() - inicio).seconds
    print(f"\n  ✅ Completado en {elapsed}s")
    print(f"     Insertados / actualizados : {insertados:,}")
    print(f"     Sin cambios (omitidos)    : {omitidos:,}")
    print(f"     Con error de parseo       : {errores:,}")


def verificar_carga(engine):
    print(f"\n{'='*60}")
    print("  Verificación tab_consolidado:")
    print(f"{'='*60}")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                indicador,
                COUNT(*)                                            AS total_filas,
                SUM(CASE WHEN estado='COMPLETO'   THEN 1 ELSE 0 END) AS completos,
                SUM(CASE WHEN estado='INCOMPLETO' THEN 1 ELSE 0 END) AS con_error,
                MAX(fecha_extraccion)                               AS ultima_extraccion
            FROM tab_consolidado
            GROUP BY indicador
            ORDER BY indicador
        """))
        print(f"\n  {'INDICADOR':<32} {'FILAS':>8} {'OK':>8} {'ERR':>6}  ULTIMA EXTRACCION")
        print(f"  {'-'*32} {'-'*8} {'-'*8} {'-'*6}  {'-'*20}")
        for row in result:
            print(
                f"  {str(row[0]):<32} {row[1]:>8,} "
                f"{row[2]:>8,} {row[3]:>6}  {row[4]}"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Carga SQL Oracle TAB_CONSOLIDADO a PostgreSQL"
    )
    parser.add_argument("--archivo", required=True,
                        help="Ruta al archivo SQL de Oracle")
    parser.add_argument("--verbose", action="store_true",
                        help="Mostrar errores detallados")
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)

    # Limpiar tabla primero si viene del archivo principal
    nombre = os.path.basename(args.archivo)
    if "supercias" not in nombre.lower():
        print("  ℹ️  Cargando archivo principal — se respeta ON CONFLICT.")

    cargar_archivo(args.archivo, engine, args.verbose)
    verificar_carga(engine)


if __name__ == "__main__":
    main()