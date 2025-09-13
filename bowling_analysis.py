# Cargar las bibliotecas necesarias
import pandas as pd
import os

# Leer las hojas de Excel
excel_file = "C:\\Users\\USER\\OneDrive - Sevasa\\Boliche\\2025\\XII TORNEO EMPRESARIAL\\Torneo XII Empresarial 2025.xlsx"

# Leer la hoja JUGADORES1
jugadores1_df = pd.read_excel(excel_file, sheet_name="JUGADORES1")

# Leer la hoja EQUIPOS DETALLE
equipos_detalle_df = pd.read_excel(excel_file, sheet_name="EQUIPOS DETALLE")

# Seleccionar y renombrar columnas en equipos_detalle_df
equipos_detalle_df = equipos_detalle_df[['EQUIPO', 'JORNADAS', 'LINEA', 'PUNTOS', 'FORFIT']].copy()
equipos_detalle_df = equipos_detalle_df.rename(columns={'JORNADAS': 'JORNADA', 'PUNTOS': 'PTOS_GAN'})

# Hacer el merge usando EQUIPO, LINEA y JORNADA como claves
merged_df = jugadores1_df.merge(equipos_detalle_df, on=['EQUIPO', 'LINEA', 'JORNADA'], how='inner')

# Mostrar los primeros registros para verificar
print("Primeros registros del merge:")
print(merged_df.head())

# Exportar el DataFrame merged a Excel
merged_df.to_excel("Bowling.xlsx", index=False, engine='openpyxl')

# Calcular estadísticas por jugador y equipo
x = merged_df[['JUGADOR', 'PTOS_GAN', 'EQUIPO']].groupby(['JUGADOR', 'EQUIPO']).agg({
    'PTOS_GAN': ['sum', 'count']  # sum para total de puntos, count para número de juegos
}).reset_index()

# Aplanar las columnas multi-nivel
x.columns = ['JUGADOR', 'EQUIPO', 'Total_Puntos', 'Juegos']

# Ordenar por Total_Puntos descendente
x = x.sort_values('Total_Puntos', ascending=False).reset_index(drop=True)

print("\nEstadísticas por jugador:")
print(x)

# Exportar el DataFrame merged a Excel
merged_df.to_excel("JuegosMerge2025.xlsx", index=False, engine='openpyxl')

# Exportar también las estadísticas por jugador a Excel
x.to_excel("Estadisticas_Jugadores.xlsx", index=False, engine='openpyxl')

print("\nArchivos Excel exportados exitosamente en la carpeta actual:")
print("- Bowling.xlsx")
print("- JuegosMerge2025.xlsx")
print("- Estadisticas_Jugadores.xlsx")
