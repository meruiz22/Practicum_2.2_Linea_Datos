from dotenv import load_dotenv
import os

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST"),
    "port":     os.getenv("DB_PORT"),
    "database": os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

# Ruta del archivo Excel
EXCEL_PATH = r"C:\Users\marti\OneDrive\Documentos\Practicum 2.2\Practicum_2.2_Linea_Datos\practicum_datos\data\registro-administrativo-historico_2009-2024-inicio.xlsx"
SHEET_NAME    = "VERDADEDRO"
ANIO_RECIENTE = "2022-2023"