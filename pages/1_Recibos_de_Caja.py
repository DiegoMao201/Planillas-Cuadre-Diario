# pages/1_Recibos_de_Caja.py

import streamlit as st
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import gspread

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(layout="wide", page_title="Recibos de Caja")
st.title("🧾 Procesamiento de Recibos de Caja")
st.markdown("""
Sube el archivo Excel con el resumen diario de los recibos de caja. 
El sistema mostrará una tabla resumida donde podrás asignar el destino (banco o tercero) 
para cada monto de efectivo recaudado.
""")

# --- CONEXIÓN SEGURA A GOOGLE SHEETS (Función Reutilizada) ---
# Copiamos las funciones de conexión aquí para que esta página sea independiente
# y pueda acceder a la configuración de bancos y terceros.
@st.cache_resource(ttl=600)
def connect_to_gsheet():
    """
    Establece conexión con Google Sheets usando las credenciales de st.secrets.
    Retorna el objeto de la hoja de configuración.
    """
    try:
        creds_json = dict(st.secrets["google_credentials"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        sheet = client.open(st.secrets["google_sheets"]["spreadsheet_name"])
        config_ws = sheet.worksheet(st.secrets["google_sheets"]["config_sheet_name"])
        return config_ws
    except Exception as e:
        st.error(f"Error fatal al conectar con Google Sheets: {e}")
        st.warning("Verifique las credenciales y el nombre de la hoja 'Configuracion' en los 'secrets' de Streamlit.")
        return None

def get_app_config(config_ws):
    """
    Carga la configuración de bancos y terceros desde la hoja 'Configuracion'.
    """
    if config_ws is None:
        return [], []
    try:
        config_data = config_ws.get_all_records()
        bancos = sorted(list(set(str(d['Detalle']).strip() for d in config_data if d.get('Tipo Movimiento') == 'BANCO' and d.get('Detalle'))))
        terceros = sorted(list(set(str(d['Detalle']).strip() for d in config_data if d.get('Tipo Movimiento') == 'TERCERO' and d.get('Detalle'))))
        return bancos, terceros
    except Exception as e:
        st.error(f"Error al cargar la configuración de bancos y terceros: {e}")
        return [], []

# --- LÓGICA PRINCIPAL DE LA PÁGINA ---

# 1. Conectar a Google Sheets y obtener las listas de destinos
config_ws = connect_to_gsheet()
bancos, terceros = get_app_config(config_ws)
opciones_destino = ["-- Seleccionar --"] + bancos + terceros

if not opciones_destino or len(opciones_destino) == 1:
    st.error("No se pudieron cargar los destinos (bancos/terceros) desde la hoja 'Configuracion'. La página no puede funcionar.")
else:
    # 2. Componente para subir el archivo Excel
    uploaded_file = st.file_uploader(
        "📂 Sube tu archivo Excel de recibos de caja",
        type=['xlsx', 'xls']
    )

    if uploaded_file is not None:
        st.success("¡Archivo cargado exitosamente! Ahora puedes procesarlo.")
        
        try:
            # 3. Leer el archivo Excel en un DataFrame de Pandas
            df = pd.read_excel(uploaded_file)

            # **IMPORTANTE**: Aquí debes definir qué columnas de tu Excel quieres mostrar.
            # Cambia estas cadenas por los nombres EXACTOS de las columnas en tu archivo.
            columnas_a_mostrar = [
                "FECHA",         # Ejemplo: La columna con la fecha del recibo
                "CLIENTE",       # Ejemplo: La columna con el nombre del cliente
                "RECIBO N°",     # Ejemplo: La columna con el número del recibo
                "VALOR EFECTIVO" # Ejemplo: La columna con el monto en efectivo
            ]
            
            # Verificar si las columnas necesarias existen en el archivo subido
            columnas_faltantes = [col for col in columnas_a_mostrar if col not in df.columns]
            if columnas_faltantes:
                st.error(f"El archivo Excel no contiene las siguientes columnas requeridas: **{', '.join(columnas_faltantes)}**. Por favor, revisa el archivo.")
            else:
                # 4. Crear la tabla resumida
                df_resumen = df[columnas_a_mostrar].copy()
                
                # 5. Usar st.data_editor para hacer la tabla interactiva
                st.subheader("Asigna el Destino del Efectivo")
                st.info("Usa la columna 'Destino' para seleccionar a qué banco o tercero se envió el efectivo de cada recibo.")

                # Se añade la columna 'Destino' para que el usuario pueda editarla
                df_resumen['Destino'] = None

                edited_df = st.data_editor(
                    df_resumen,
                    column_config={
                        "Destino": st.column_config.SelectboxColumn(
                            "Destino del Efectivo",
                            help="Selecciona el banco o tercero donde se consignó/entregó el efectivo.",
                            options=opciones_destino,
                            required=True # Obliga al usuario a seleccionar una opción
                        ),
                        "VALOR EFECTIVO": st.column_config.NumberColumn(
                            "Valor Efectivo",
                            format="$ %d",
                            disabled=True # El valor no se puede editar
                        ),
                        "FECHA": st.column_config.DateColumn(
                            "Fecha",
                            format="DD/MM/YYYY",
                            disabled=True
                        ),
                        "CLIENTE": st.column_config.TextColumn(
                            "Cliente",
                            disabled=True
                        ),
                         "RECIBO N°": st.column_config.TextColumn(
                            "Recibo N°",
                            disabled=True
                        ),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="editor_recibos"
                )

                # 6. Botón para procesar la información
                st.divider()
                if st.button("✅ Procesar y Guardar Asignaciones", type="primary", use_container_width=True):
                    # Verificar si todos los destinos han sido seleccionados
                    if edited_df['Destino'].isnull().any() or any(d == "-- Seleccionar --" for d in edited_df['Destino']):
                        st.warning("⚠️ Debes asignar un destino válido para TODOS los recibos de caja antes de procesar.")
                    else:
                        # --- Lógica Futura ---
                        # Aquí es donde, en el siguiente paso, agregaríamos el código para:
                        # 1. Agrupar los montos por cada destino (ej. sumar todo lo que va para BANCOLOMBIA).
                        # 2. Formatear estos datos.
                        # 3. Guardarlos en una nueva hoja de Google Sheets o integrarlos con tu cuadre diario.
                        
                        st.success("¡Asignaciones procesadas!")
                        st.dataframe(edited_df) # Muestra el resultado final
                        st.info("En un futuro, esta información se guardará automáticamente.")

        except Exception as e:
            st.error(f"Ocurrió un error al leer o procesar el archivo Excel: {e}")
            st.warning("Asegúrate de que el archivo no esté corrupto y tenga el formato correcto.")
