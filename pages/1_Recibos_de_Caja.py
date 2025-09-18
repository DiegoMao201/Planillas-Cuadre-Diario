import streamlit as st
import pandas as pd
from io import BytesIO
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import json
from datetime import datetime

# --- PÁGINA: Recibos_de_Caja.py ---
# ==================================

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(layout="wide", page_title="Recibos de Caja")
st.title("🧾 Procesamiento de Recibos de Caja")
st.markdown("""
Sube el archivo Excel con el resumen diario de los recibos de caja.
El sistema mostrará una tabla resumida donde podrás asignar el destino (banco o tercero)
para cada monto de efectivo recaudado.
""")

# --- CONEXIÓN SEGURA A GOOGLE SHEETS ---
@st.cache_resource(ttl=600)
def connect_to_gsheet():
    """
    Establece conexión con Google Sheets usando las credenciales de st.secrets.
    Retorna los objetos de las hojas de configuración, registros de recibos y el consecutivo global.
    """
    try:
        creds_json = dict(st.secrets["google_credentials"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        spreadsheet_name = st.secrets["google_sheets"]["spreadsheet_name"]
        sheet = client.open(spreadsheet_name)
        
        # Obtenemos las hojas de trabajo
        config_ws = sheet.worksheet(st.secrets["google_sheets"]["config_sheet_name"])
        registros_recibos_ws = sheet.worksheet(st.secrets["google_sheets"]["registros_recibos_sheet_name"])
        global_consecutivo_ws = sheet.worksheet("GlobalConsecutivo")
        
        return config_ws, registros_recibos_ws, global_consecutivo_ws
    except Exception as e:
        st.error(f"Error fatal al conectar con Google Sheets: {e}")
        st.warning("Verifique las credenciales y los nombres de las hojas 'Configuracion', 'RegistrosRecibos' y 'GlobalConsecutivo' en los 'secrets' de Streamlit.")
        return None, None, None

def get_app_config(config_ws):
    """
    Carga la configuración de bancos y terceros desde la hoja 'Configuracion'.
    """
    if config_ws is None:
        return [], [], {}
    try:
        config_data = config_ws.get_all_records()
        bancos = sorted(list(set(str(d['Detalle']).strip() for d in config_data if d.get('Tipo Movimiento') == 'BANCO' and d.get('Detalle'))))
        terceros = sorted(list(set(str(d['Detalle']).strip() for d in config_data if d.get('Tipo Movimiento') == 'TERCERO' and d.get('Detalle'))))
        
        # Mapeo de cuentas para el archivo TXT
        account_mappings = {}
        for d in config_data:
            detalle = str(d.get('Detalle', '')).strip()
            if detalle and (d.get('Tipo Movimiento') in ['BANCO', 'TERCERO']):
                account_mappings[detalle] = {
                    'cuenta': str(d.get('Cuenta Contable', '')).strip(),
                    'nit': str(d.get('NIT', '')).strip(),
                    'nombre': str(d.get('Nombre Tercero', '')).strip(),
                }
        return bancos, terceros, account_mappings
    except Exception as e:
        st.error(f"Error al cargar la configuración de bancos y terceros: {e}")
        return [], [], {}

# --- LÓGICA DE PROCESAMIENTO Y GENERACIÓN DE ARCHIVOS ---
def generate_txt_from_df(df, account_mappings, global_consecutive):
    """
    Genera el contenido del archivo TXT para el ERP a partir del DataFrame.
    """
    txt_lines = []
    
    # Supongamos una cuenta de contrapartida para los recibos de caja, podría ser la cuenta 11050501
    cuenta_recibo_caja = "11050501" 
    
    for _, row in df.iterrows():
        # Aseguramos que la fecha se procese correctamente, venga como string o datetime
        try:
            fecha = pd.to_datetime(row['Fecha'], dayfirst=True).strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            fecha = row['Fecha'] # Si ya está en el formato correcto, la usamos tal cual

        num_recibo = str(row['Recibo N°'])
        valor = float(row['Valor Efectivo'])
        destino = str(row['Destino'])
        
        if destino not in account_mappings:
            st.warning(f"No se encontró mapeo para el destino: {destino}. Se omite del TXT.")
            continue
        
        destino_info = account_mappings[destino]
        cuenta_destino = destino_info.get('cuenta')
        nit_tercero = destino_info.get('nit')
        nombre_tercero = destino_info.get('nombre')
        
        # Línea de débito (movimiento hacia el banco/tercero)
        linea_debito = "|".join([
            fecha, str(global_consecutive), cuenta_destino, "8", # "8" es un tipo de documento de ejemplo
            f"Recibo de Caja {num_recibo} - {destino}", "Recibos", num_recibo,
            str(valor), "0", "0", nit_tercero, nombre_tercero, "0"
        ])
        txt_lines.append(linea_debito)

        # Línea de crédito (la contrapartida del recibo de caja)
        linea_credito = "|".join([
            fecha, str(global_consecutive), cuenta_recibo_caja, "8", 
            f"Recibo de Caja {num_recibo} - Cliente {row['Cliente']}", "Recibos", num_recibo,
            "0", str(valor), "0", "0", "0", "0"
        ])
        txt_lines.append(linea_credito)

    return "\n".join(txt_lines)

def get_next_global_consecutive(global_consecutivo_ws):
    """
    Obtiene el siguiente número consecutivo global para el documento del ERP,
    buscando la etiqueta 'Ultimo_Consecutivo_Global' y leyendo el valor.
    """
    try:
        # Busca la celda con la etiqueta 'Ultimo_Consecutivo_Global'
        cell = global_consecutivo_ws.find('Ultimo_Consecutivo_Global')
        if cell:
            # Lee el valor de la celda a la derecha de la etiqueta (misma fila, columna + 1)
            last_consecutive = int(global_consecutivo_ws.cell(cell.row, cell.col + 1).value)
            return last_consecutive + 1
        else:
            st.error("Etiqueta 'Ultimo_Consecutivo_Global' no encontrada. Verifique la hoja 'GlobalConsecutivo'.")
            return None
    except Exception as e:
        st.error(f"Error al obtener consecutivo global: {e}")
        return None

def update_global_consecutive(global_consecutivo_ws, new_consecutive):
    """
    Actualiza el último consecutivo global usado, buscando la etiqueta y actualizando el valor.
    """
    try:
        # Busca la celda con la etiqueta 'Ultimo_Consecutivo_Global'
        cell = global_consecutivo_ws.find('Ultimo_Consecutivo_Global')
        if cell:
            # Actualiza el valor de la celda a la derecha de la etiqueta
            global_consecutivo_ws.update_cell(cell.row, cell.col + 1, new_consecutive)
    except Exception as e:
        st.error(f"Error al actualizar el consecutivo global: {e}")

# --- LÓGICA PRINCIPAL DE LA PÁGINA ---
config_ws, registros_recibos_ws, global_consecutivo_ws = connect_to_gsheet()

if config_ws is None or registros_recibos_ws is None or global_consecutivo_ws is None:
    st.error("La aplicación no puede continuar debido a un error de conexión con Google Sheets.")
else:
    bancos, terceros, account_mappings = get_app_config(config_ws)
    opciones_destino = ["-- Seleccionar --"] + bancos + terceros

    if not opciones_destino or len(opciones_destino) == 1:
        st.error("No se pudieron cargar los destinos (bancos/terceros) desde la hoja 'Configuracion'. La página no puede funcionar.")
    else:
        uploaded_file = st.file_uploader(
            "📂 Sube tu archivo Excel de recibos de caja",
            type=['xlsx', 'xls']
        )

        if uploaded_file is not None:
            st.success("¡Archivo cargado exitosamente! Ahora puedes procesarlo.")
            
            try:
                # Leer el archivo Excel, indicando que el encabezado está en la fila 1 (índice 0)
                df = pd.read_excel(uploaded_file, header=0)

                # Usar .fillna(method='ffill') para propagar los valores
                df['NUMRECIBO'] = df['NUMRECIBO'].ffill()
                df['FECHA_RECIBO'] = df['FECHA_RECIBO'].ffill()
                df['NOMBRECLIENTE'] = df['NOMBRECLIENTE'].ffill()
                df['NIF20'] = df['NIF20'].ffill()
                
                # Limpiar los datos de filas con "SUBTOTALES", "TOTALES" o filas completamente vacías
                df_cleaned = df[~df.apply(lambda row: row.astype(str).str.contains('SUBTOTALES|TOTALES', case=False).any(), axis=1)].copy()
                df_cleaned.dropna(subset=['NUMRECIBO'], inplace=True)
                df_cleaned.dropna(how='all', inplace=True)

                # Función de limpieza y conversión de importe
                def clean_and_convert(value):
                    try:
                        # Limpia el valor: toma la primera parte si hay saltos de línea, quita símbolos y convierte a float
                        return float(str(value).split('\n')[0].replace('$', '').replace('.', '').replace(',', ''))
                    except (ValueError, IndexError):
                        return None
                
                # Aplicar la función de limpieza
                df_cleaned['IMPORTE_LIMPIO'] = df_cleaned['IMPORTE'].apply(clean_and_convert)
                df_cleaned.dropna(subset=['IMPORTE_LIMPIO'], inplace=True)

                # Agrupar los datos por NUMRECIBO para consolidar la información
                df_resumen = df_cleaned.groupby('NUMRECIBO').agg({
                    'FECHA_RECIBO': 'first',
                    'NOMBRECLIENTE': 'first',
                    'IMPORTE_LIMPIO': 'sum'
                }).reset_index()

                # Renombrar las columnas para una mejor visualización en la tabla
                df_resumen.rename(columns={
                    'FECHA_RECIBO': 'Fecha',
                    'NUMRECIBO': 'Recibo N°',
                    'NOMBRECLIENTE': 'Cliente',
                    'IMPORTE_LIMPIO': 'Valor Efectivo'
                }, inplace=True)
                
                # Formatear la fecha para mostrar solo la parte de la fecha
                if pd.api.types.is_datetime64_any_dtype(df_resumen['Fecha']):
                    df_resumen['Fecha'] = pd.to_datetime(df_resumen['Fecha']).dt.strftime('%d/%m/%Y')
                
                # Verificamos si la tabla tiene datos después de la limpieza
                if df_resumen.empty:
                    st.warning("El archivo no contiene recibos de efectivo válidos. Revisa el formato.")
                else:
                    # --- Sección de Totalización Visual ---
                    st.subheader("📊 Resumen del Día")
                    total_recibos = df_resumen['Valor Efectivo'].sum()
                    st.metric(label="💰 Total Efectivo Recaudado", value=f"${total_recibos:,.0f}".replace(",", "."))
                    st.divider()

                    st.subheader("Asigna el Destino del Efectivo")
                    st.info("Usa la columna 'Destino' para seleccionar a qué banco o tercero se envió el efectivo de cada recibo.")

                    df_resumen['Destino'] = "-- Seleccionar --"

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
                                format="$ %.0f",
                                disabled=True
                            ),
                            "Fecha": st.column_config.TextColumn(
                                "Fecha",
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
                        if edited_df['Destino'].isnull().any() or any(d == "-- Seleccionar --" for d in edited_df['Destino']):
                            st.warning("⚠️ Debes asignar un destino válido para TODOS los recibos de caja antes de procesar.")
                        else:
                            st.success("¡Asignaciones procesadas! Los datos están listos para ser usados.")
                            
                            # --- Guardar en Google Sheets y generar TXT ---
                            try:
                                # Obtener el consecutivo global para el documento del ERP
                                global_consecutive = get_next_global_consecutive(global_consecutivo_ws)
                                if global_consecutive is None:
                                    st.error("No se pudo obtener el consecutivo global. No se puede guardar.")
                                    st.stop() # <-- ESTA ES LA LÍNEA CORREGIDA

                                # Generar el archivo TXT
                                txt_content = generate_txt_from_df(edited_df, account_mappings, global_consecutive)

                                # Preparar los datos para guardar en la hoja de registros
                                registros_data = []
                                for _, row in edited_df.iterrows():
                                    registros_data.append([
                                        row['Fecha'],
                                        row['Recibo N°'],
                                        row['Cliente'],
                                        row['Valor Efectivo'],
                                        row['Destino'],
                                        global_consecutive,
                                        datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    ])
                                
                                registros_recibos_ws.append_rows(registros_data, value_input_option='USER_ENTERED')
                                update_global_consecutive(global_consecutivo_ws, global_consecutive)
                                st.success("✅ Datos guardados en Google Sheets.")

                                # Botón de descarga para el archivo TXT
                                st.download_button(
                                    label="⬇️ Descargar Archivo TXT para el ERP",
                                    data=txt_content.encode('utf-8'),
                                    file_name=f"recibos_caja_{datetime.now().strftime('%Y%m%d')}.txt",
                                    mime="text/plain"
                                )
                                st.info("El archivo TXT se ha generado y está listo para descargar.")

                            except Exception as e:
                                st.error(f"Error al guardar los datos o generar el archivo TXT: {e}")
                                st.warning("Verifique la conexión y la estructura de las hojas de Google Sheets.")

            except Exception as e:
                st.error(f"Ocurrió un error al leer o procesar el archivo Excel: {e}")
                st.warning("Asegúrate de que el archivo no esté corrupto y tenga el formato correcto.")
