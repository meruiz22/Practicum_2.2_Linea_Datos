"""
etl/load.py — Módulo de Carga (L del ETL).

Usa DB_CONFIG de config.py para conectarse a PostgreSQL con psycopg2.
Orden de carga respeta FK:
  1. dim_ubicacion   (sin FK)
  2. dim_institucion (FK → dim_ubicacion)
  3. fact_matricula  (FK → dim_institucion)
"""

import sys
import os
import psycopg2
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DB_CONFIG

ORDEN_CARGA = ["dim_ubicacion", "dim_institucion", "fact_matricula"]


def _get_engine():
    """Construye el engine de SQLAlchemy a partir de DB_CONFIG."""
    c = DB_CONFIG
    url = (
        f"postgresql+psycopg2://{c['user']}:{c['password']}"
        f"@{c['host']}:{c['port']}/{c['database']}"
    )
    return create_engine(url)


def cargar_tablas(tablas: dict) -> None:
    """
    Recibe el dict de transform.transformar() y carga cada tabla en PostgreSQL.

    Parámetros
    ----------
    tablas : dict  →  {'dim_ubicacion': df, 'dim_institucion': df, 'fact_matricula': df}
    """
    print(f"[LOAD] Conectando a: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    engine = _get_engine()

    with engine.begin() as conn:
        for nombre in ORDEN_CARGA:
            df = tablas[nombre]
            df.to_sql(nombre, con=conn, if_exists="replace", index=False)
            print(f"[LOAD] '{nombre}' cargada: {len(df):,} filas ✓")

    _aplicar_restricciones(engine)
    print("[LOAD] Carga completada.")


def _aplicar_restricciones(engine) -> None:
    """Aplica PK y FK de forma idempotente."""
    ddl = [
        "DO $$ BEGIN ALTER TABLE dim_ubicacion ADD PRIMARY KEY (id_ubicacion); EXCEPTION WHEN others THEN NULL; END $$",
        "DO $$ BEGIN ALTER TABLE dim_institucion ADD PRIMARY KEY (cod_amie); EXCEPTION WHEN others THEN NULL; END $$",
        "DO $$ BEGIN ALTER TABLE dim_institucion ADD CONSTRAINT fk_inst_ubicacion FOREIGN KEY (id_ubicacion) REFERENCES dim_ubicacion(id_ubicacion); EXCEPTION WHEN others THEN NULL; END $$",
        "DO $$ BEGIN ALTER TABLE fact_matricula ADD PRIMARY KEY (cod_amie, anio_lectivo); EXCEPTION WHEN others THEN NULL; END $$",
        "DO $$ BEGIN ALTER TABLE fact_matricula ADD CONSTRAINT fk_fact_inst FOREIGN KEY (cod_amie) REFERENCES dim_institucion(cod_amie); EXCEPTION WHEN others THEN NULL; END $$",
    ]
    with engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))
    print("[LOAD] Restricciones PK/FK aplicadas ✓")


def verificar_carga() -> None:
    """Imprime el conteo de filas de cada tabla en PostgreSQL."""
    engine = _get_engine()
    print("\n[LOAD] Verificación:")
    with engine.connect() as conn:
        for tabla in ORDEN_CARGA:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
            print(f"  {tabla}: {n:,} filas")