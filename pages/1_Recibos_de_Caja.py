# Recibos_de_Caja.py

import streamlit as st
import pandas as pd
from io import BytesIO
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
            # 3. Leer el archivo Excel, indicando que el encabezado está en la fila 3 (índice 2)
            df = pd.read_excel(uploaded_file, header=2)

            # 4. Limpiar los datos: filtrar las filas que no tienen un número de recibo
            df_filtrado = df.dropna(subset=['NUMRECIBO'])

            # 5. Seleccionar y renombrar las columnas que necesitas
            # Basado en la estructura de tu imagen, se usan los nombres de la fila 3
            df_resumen = df_filtrado[['FECHA_RECIBO', 'NUMRECIBO', 'NOMBRELIENTE', 'IMPORTE']].copy()

            # Renombrar las columnas para una mejor visualización en la tabla
            df_resumen.rename(columns={
                'FECHA_RECIBO': 'Fecha',
                'NUMRECIBO': 'Recibo N°',
                'NOMBRELIENTE': 'Cliente',
                'IMPORTE': 'Valor Efectivo'
            }, inplace=True)
            
            # Limpiar la columna de importes, que en tu archivo tiene dos valores en una celda
            # Tomamos solo el primer valor (el de arriba)
            df_resumen['Valor Efectivo'] = df_resumen['Valor Efectivo'].apply(
                lambda x: str(x).split(' ')[0].replace(',', '').replace('.', '').replace('$', '')
            ).astype(float)
            
            # Verificamos si la tabla tiene datos después de la limpieza
            if df_resumen.empty:
                st.warning("El archivo no contiene recibos de efectivo válidos. Revisa el formato.")
            else:
                # 6. Usar st.data_editor para hacer la tabla interactiva
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
                            required=True
                        ),
                        "Valor Efectivo": st.column_config.NumberColumn(
                            "Valor Efectivo",
                            format="$ %d",
                            disabled=True
                        ),
                        "Fecha": st.column_config.DateColumn(
                            "Fecha",
                            format="DD/MM/YYYY",
                            disabled=True
                        ),
                        "Cliente": st.column_config.TextColumn(
                            "Cliente",
                            disabled=True
                        ),
                        "Recibo N°": st.column_config.TextColumn(
                            "Recibo N°",
                            disabled=True
                        ),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="editor_recibos"
                )

                st.divider()
                if st.button("✅ Procesar y Guardar Asignaciones", type="primary", use_container_width=True):
                    # Verificar si todos los destinos han sido seleccionados
                    if edited_df['Destino'].isnull().any() or any(d == "-- Seleccionar --" for d in edited_df['Destino']):
                        st.warning("⚠️ Debes asignar un destino válido para TODOS los recibos de caja antes de procesar.")
                    else:
                        st.success("¡Asignaciones procesadas! Los datos están listos para ser usados.")
                        
                        # --- FUTURA LÓGICA: GENERACIÓN DEL TXT ---
                        # Aquí es donde iría el código para generar el archivo TXT
                        # basado en la estructura que necesites.
                        
                        # Ejemplo de preparación del contenido para el TXT
                        txt_content = "Resumen de Recibos de Caja\n\n"
                        txt_content += edited_df.to_string(index=False)
                        
                        # Botón de descarga del archivo
                        # Asegúrate de que el formato final del TXT coincida con lo que necesitas.
                        st.download_button(
                            label="⬇️ Descargar Archivo de Resumen",
                            data=txt_content,
                            file_name="resumen_recibos.txt",
                            mime="text/plain"
                        )
                        st.info("El archivo TXT se ha generado y está listo para descargar.")


        except Exception as e:
            st.error(f"Ocurrió un error al leer o procesar el archivo Excel: {e}")
            st.warning("Asegúrate de que el archivo no esté corrupto y tenga el formato correcto.")
