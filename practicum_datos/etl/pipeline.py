"""
etl/pipeline.py — Orquestador del pipeline E → T → L.

Ejecutar desde la RAÍZ del proyecto:
    python etl\pipeline.py
"""

import sys
import os
import time

# Agrega la raíz del proyecto al path para que config.py sea encontrado
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from etl.extract   import extraer_excel
from etl.transform import transformar
from etl.load      import cargar_tablas, verificar_carga


def run_pipeline() -> None:
    inicio = time.time()

    print("=" * 58)
    print("  PIPELINE AMIE — MINEDUC Ecuador")
    print("  Registro Histórico 2009-2024 · Prácticum 6to ciclo")
    print("=" * 58)

    print("\n[1/3] EXTRACCIÓN")
    df_raw = extraer_excel()

    print("\n[2/3] TRANSFORMACIÓN")
    tablas = transformar(df_raw)

    print("\n[3/3] CARGA EN PostgreSQL")
    cargar_tablas(tablas)
    verificar_carga()

    print("\n" + "=" * 58)
    print(f"  Pipeline completado en {time.time() - inicio:.1f} s")
    print("=" * 58)


if __name__ == "__main__":
    run_pipeline()