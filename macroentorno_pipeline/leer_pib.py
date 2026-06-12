import pandas as pd

df = pd.read_excel(
    r"C:\Users\marti\OneDrive\Documentos\Practicum 2.2\Practicum_2.2_Linea_Datos\macroentorno_pipeline\datos_crudos\bce\retropolacion_1965_2024p.xlsx",
    sheet_name="PIB pc nominal",
    engine="openpyxl",
    header=9
)

df = df.iloc[:, :5].copy()
df.columns = ["anio", "pib_musd", "poblacion", "pib_percapita", "variacion_pct"]

print(df.shape)
print(df.head(10))
print(df.tail(10))
print(df[df["anio"].astype(str).str.contains("p", na=False)])