# -*- coding: utf-8 -*-

# --- IMPORTACIÓN DE LIBRERÍAS NECESARIAS ---
import streamlit as st  # Para crear la aplicación web interactiva.
import pandas as pd  # Para la manipulación y análisis de datos (especialmente con DataFrames).
from io import BytesIO  # Para manejar datos en memoria, como el archivo subido.
from oauth2client.service_account import ServiceAccountCredentials  # Para la autenticación con la API de Google.
import gspread  # Para interactuar con Google Sheets (leer y escribir datos).
import json  # Para trabajar con datos en formato JSON (usado en las credenciales).
from datetime import datetime  # Para obtener la fecha y hora actual.

# --- CONFIGURACIÓN DE LA PÁGINA DE STREAMLIT ---
# st.set_page_config establece las propiedades de la página, como el layout y el título que aparece en la pestaña del navegador.
st.set_page_config(layout="wide", page_title="Recibos de Caja")

# --- TÍTULOS Y DESCRIPCIÓN DE LA APLICACIÓN ---
# st.title muestra un título principal en la aplicación.
st.title("🧾 Procesamiento de Recibos de Caja v3.0")
# st.markdown permite escribir texto con formato (como negrilla, listas, etc.).
st.markdown("""
Sube el archivo de Excel, selecciona la **serie** correspondiente y el sistema generará una tabla resumen.
En la tabla podrás **agrupar recibos** y asignar el destino (banco o tercero) de cada valor recaudado.
""")

# --- CONEXIÓN SEGURA A GOOGLE SHEETS ---
# @st.cache_resource es un decorador de Streamlit que guarda en caché el resultado de la función.
@st.cache_resource(ttl=600)
def connect_to_gsheet():
    """
    Establece una conexión con Google Sheets usando las credenciales guardadas en los "secrets" de Streamlit.
    Devuelve los objetos de las hojas de cálculo para configuración, registros, consecutivos de serie y el consecutivo global.
    """
    try:
        creds_json = dict(st.secrets["google_credentials"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        
        spreadsheet_name = "Planillas_Ferreinox"
        sheet = client.open(spreadsheet_name)
        
        config_ws = sheet.worksheet("Configuracion")
        registros_recibos_ws = sheet.worksheet("RegistrosRecibos")
        consecutivos_ws = sheet.worksheet("Consecutivos")
        # MODIFICADO: Se añade la hoja para el consecutivo global.
        global_consecutivo_ws = sheet.worksheet("GlobalConsecutivo") 
        
        return config_ws, registros_recibos_ws, consecutivos_ws, global_consecutivo_ws
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Error fatal: No se encontró el archivo de Google Sheets llamado '{spreadsheet_name}'. Revisa el nombre y los permisos de acceso.")
        return None, None, None, None
    except gspread.exceptions.WorksheetNotFound as e:
        st.error(f"Error fatal: No se encontró una de las hojas de trabajo requeridas en el archivo. Detalle: {e}")
        st.warning("Asegúrate de que existan las hojas llamadas 'Configuracion', 'RegistrosRecibos', 'Consecutivos' y 'GlobalConsecutivo'.")
        return None, None, None, None
    except Exception as e:
        st.error(f"Error fatal al conectar con Google Sheets: {e}")
        st.warning("Por favor, verifica las credenciales en los secrets de Streamlit y los permisos de la cuenta de servicio sobre el archivo.")
        return None, None, None, None

def get_app_config(config_ws):
    """
    Carga la configuración de bancos y terceros desde la hoja de trabajo 'Configuracion'.
    """
    if config_ws is None:
        return [], [], {}
    try:
        config_data = config_ws.get_all_records()
        bancos = sorted(list(set(str(d['Detalle']).strip() for d in config_data if d.get('Tipo Movimiento') == 'BANCO' and d.get('Detalle'))))
        terceros = sorted(list(set(str(d['Detalle']).strip() for d in config_data if d.get('Tipo Movimiento') == 'TERCERO' and d.get('Detalle'))))
        
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

# --- LÓGICA DE PROCESAMIENTO Y GENERACIÓN DE ARCHIVOS (MODIFICADA)---
def generate_txt_content(df, account_mappings, series_consecutive, global_consecutive, series):
    """
    Genera el contenido del archivo TXT para el ERP, con la nueva estructura y un crédito único.
    """
    txt_lines = []
    cuenta_recibo_caja = "11050501"
    tipo_documento = "12"
    # NUEVO: Extrae solo la parte numérica de la serie para usarla en la columna 6.
    series_numeric = ''.join(filter(str.isdigit, series))

    # --- 1. PROCESAR REGISTROS INDIVIDUALES (AGRUPACIÓN 1) ---
    df_individual = df[df['Agrupación'] == 1]
    for _, row in df_individual.iterrows():
        fecha = pd.to_datetime(row['Fecha'], dayfirst=True).strftime('%d/%m/%Y')
        num_recibo = str(int(row['Recibo N°']))
        valor = float(row['Valor Efectivo'])
        destino = str(row['Destino'])
        
        if destino in account_mappings:
            destino_info = account_mappings[destino]
            cuenta_destino = destino_info['cuenta']
            nit_tercero = destino_info['nit']
            nombre_tercero = destino_info['nombre']

            # Línea DÉBITO (MODIFICADA)
            linea_debito = "|".join([
                fecha, str(global_consecutive), cuenta_destino, tipo_documento,
                f"Recibo de Caja {num_recibo} - {row['Cliente']}", # Comentario ahora muestra el cliente
                str(series_numeric), str(series_consecutive),      # Columna 6 es la serie numérica
                str(valor), "0", "0", nit_tercero, nombre_tercero, "0"
            ])
            txt_lines.append(linea_debito)

    # --- 2. PROCESAR REGISTROS AGRUPADOS (AGRUPACIÓN > 1) ---
    df_agrupado = df[df['Agrupación'] > 1]
    if not df_agrupado.empty:
        # La agrupación ahora también extrae los nombres de los clientes para el comentario.
        grouped = df_agrupado.groupby(['Agrupación', 'Destino']).agg(
            Valor_Total=('Valor Efectivo', 'sum'),
            Fecha_Primera=('Fecha', 'first'),
            Recibos_Incluidos=('Recibo N°', lambda x: ','.join(x.astype(str).str.split('.').str[0])),
            Clientes_Grupo=('Cliente', lambda x: ', '.join(x.unique())) # NUEVO: Obtiene clientes del grupo
        ).reset_index()

        for _, group_row in grouped.iterrows():
            destino = group_row['Destino']
            valor_total = group_row['Valor_Total']
            fecha = pd.to_datetime(group_row['Fecha_Primera'], dayfirst=True).strftime('%d/%m/%Y')
            recibos = group_row['Recibos_Incluidos']
            clientes_grupo = group_row['Clientes_Grupo']

            if destino in account_mappings:
                destino_info = account_mappings[destino]
                cuenta_destino = destino_info['cuenta']
                nit_tercero = destino_info['nit']
                nombre_tercero = destino_info['nombre']

                # Línea DÉBITO para el grupo (MODIFICADA)
                linea_debito = "|".join([
                    fecha, str(global_consecutive), cuenta_destino, tipo_documento,
                    f"Consolidado Recibos {recibos} - {clientes_grupo}", # Comentario ahora muestra clientes
                    str(series_numeric), str(series_consecutive),         # Columna 6 es la serie numérica
                    str(valor_total), "0", "0", nit_tercero, nombre_tercero, "0"
                ])
                txt_lines.append(linea_debito)

    # --- 3. NUEVO: GENERAR LÍNEA DE CRÉDITO ÚNICA Y CONSOLIDADA ---
    if not df.empty and txt_lines: # Solo se añade si se generaron líneas de débito.
        total_valor = df['Valor Efectivo'].sum()
        clientes = ", ".join(df['Cliente'].unique())
        primera_fecha = pd.to_datetime(df['Fecha'].iloc[0], dayfirst=True).strftime('%d/%m/%Y')

        linea_credito_unica = "|".join([
            primera_fecha, str(global_consecutive), cuenta_recibo_caja, tipo_documento,
            f"Consolidado Clientes: {clientes}", # Comentario con todos los clientes
            str(series_numeric), str(series_consecutive),
            "0", str(total_valor), "0", "0", "0", "0"
        ])
        txt_lines.append(linea_credito_unica)

    return "\n".join(txt_lines)

def get_next_series_consecutive(consecutivos_ws, series_name):
    """
    Obtiene el siguiente número consecutivo para una serie específica.
    """
    try:
        label_to_find = f'Ultimo_Consecutivo_{series_name}'
        cell = consecutivos_ws.find(label_to_find)
        if cell:
            last_consecutive = int(consecutivos_ws.cell(cell.row, cell.col + 1).value)
            return last_consecutive + 1
        else:
            st.error(f"No se encontró la etiqueta '{label_to_find}'. Revisa la hoja 'Consecutivos'.")
            return None
    except Exception as e:
        st.error(f"Error obteniendo el consecutivo para la serie {series_name}: {e}")
        return None

def update_series_consecutive(consecutivos_ws, series_name, new_consecutive):
    """
    Actualiza el último número consecutivo utilizado para una serie en Google Sheets.
    """
    try:
        label_to_find = f'Ultimo_Consecutivo_{series_name}'
        cell = consecutivos_ws.find(label_to_find)
        if cell:
            consecutivos_ws.update_cell(cell.row, cell.col + 1, new_consecutive)
    except Exception as e:
        st.error(f"Error actualizando el consecutivo para la serie {series_name}: {e}")

# --- NUEVAS FUNCIONES PARA MANEJAR CONSECUTIVO GLOBAL ---
def get_next_global_consecutive(global_consecutivo_ws):
    """
    Obtiene el siguiente número consecutivo global desde la celda B1.
    """
    try:
        last_consecutive = int(global_consecutivo_ws.acell('B1').value)
        return last_consecutive + 1
    except Exception as e:
        st.error(f"Error obteniendo el consecutivo global: {e}")
        st.warning("Asegúrate de que la hoja 'GlobalConsecutivo' exista y la celda B1 contenga un número.")
        return None

def update_global_consecutive(global_consecutivo_ws, new_consecutive):
    """
    Actualiza el último número consecutivo global en la celda B1.
    """
    try:
        global_consecutivo_ws.update('B1', new_consecutive)
    except Exception as e:
        st.error(f"Error actualizando el consecutivo global: {e}")

# --- LÓGICA PRINCIPAL DE LA PÁGINA ---
config_ws, registros_recibos_ws, consecutivos_ws, global_consecutivo_ws = connect_to_gsheet()

if config_ws is None or registros_recibos_ws is None or consecutivos_ws is None or global_consecutivo_ws is None:
    st.error("La aplicación no puede continuar debido a un error de conexión con Google Sheets.")
else:
    bancos, terceros, account_mappings = get_app_config(config_ws)
    opciones_destino = ["-- Seleccionar --"] + bancos + terceros
    opciones_agrupacion = list(range(1, 11))

    if not opciones_destino or len(opciones_destino) == 1:
        st.error("No se pudieron cargar los destinos (bancos/terceros) desde la hoja 'Configuracion'. La página no puede funcionar.")
    else:
        st.subheader("1. Selecciona la Serie del Documento")
        series_disponibles = ["189U", "157U", "156U"]
        serie_seleccionada = st.selectbox(
            "Elige la serie que corresponde a los recibos de este archivo:",
            options=series_disponibles,
            index=0,
            help="Esta serie se usará en el archivo TXT final."
        )
        st.divider()

        st.subheader("2. Carga el Archivo de Excel")
        uploaded_file = st.file_uploader(
            "📂 Sube tu archivo de Excel de recibos de caja",
            type=['xlsx', 'xls']
        )

        if uploaded_file is not None:
            st.success("¡Archivo subido con éxito! Ahora puedes procesarlo.")
            
            try:
                df = pd.read_excel(uploaded_file, header=0)

                required_columns = ['FECHA_RECIBO', 'NUMRECIBO', 'NOMBRECLIENTE', 'IMPORTE']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    st.error(f"Error en el formato del archivo. Faltan las siguientes columnas: {', '.join(missing_columns)}")
                    st.warning("Por favor, asegúrate de que el archivo de Excel contenga estas columnas con los nombres exactos.")
                    st.stop()

                if 'NUMRECIBO' in df.columns:
                    df['NUMRECIBO'] = df['NUMRECIBO'].ffill()
                df_cleaned = df.dropna(subset=['FECHA_RECIBO', 'NOMBRECLIENTE']).copy()
                
                def clean_and_convert(value):
                    if isinstance(value, (int, float)):
                        return float(value)
                    try:
                        str_value = str(value).replace('$', '').strip()
                        if ',' in str_value:
                            str_value = str_value.replace('.', '')
                            str_value = str_value.replace(',', '.')
                        return float(str_value)
                    except (ValueError, TypeError):
                        return None
                
                df_cleaned['IMPORTE_LIMPIO'] = df_cleaned['IMPORTE'].apply(clean_and_convert)
                df_cleaned.dropna(subset=['IMPORTE_LIMPIO'], inplace=True)

                df_resumen = df_cleaned.groupby('NUMRECIBO').agg({
                    'FECHA_RECIBO': 'first',
                    'NOMBRECLIENTE': 'first',
                    'IMPORTE_LIMPIO': 'sum'
                }).reset_index()

                df_resumen.rename(columns={
                    'FECHA_RECIBO': 'Fecha',
                    'NUMRECIBO': 'Recibo N°',
                    'NOMBRECLIENTE': 'Cliente',
                    'IMPORTE_LIMPIO': 'Valor Efectivo'
                }, inplace=True)
                
                if pd.api.types.is_datetime64_any_dtype(df_resumen['Fecha']):
                    df_resumen['Fecha'] = pd.to_datetime(df_resumen['Fecha']).dt.strftime('%d/%m/%Y')
                
                df_resumen['Agrupación'] = 1
                df_resumen['Destino'] = "-- Seleccionar --"
                
                df_resumen = df_resumen[['Fecha', 'Recibo N°', 'Cliente', 'Valor Efectivo', 'Agrupación', 'Destino']]

                if 'df_procesado' not in st.session_state or st.session_state.get('uploaded_file_name') != uploaded_file.name:
                    st.session_state.df_procesado = df_resumen.copy()
                    st.session_state.uploaded_file_name = uploaded_file.name

                if df_resumen.empty:
                    st.warning("El archivo no contiene recibos de caja válidos después de la limpieza.")
                else:
                    st.subheader("3. Asigna Agrupación y Destinos")
                    total_recibos = st.session_state.df_procesado['Valor Efectivo'].sum()
                    st.metric(label="💰 Total Efectivo Recaudado", value=f"${total_recibos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    st.divider()

                    st.info("Usa estas herramientas para asignar valores a todos los recibos de forma masiva.")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        destino_masivo = st.selectbox(
                            "Asignar destino a todos:",
                            options=opciones_destino, key="sel_destino_masivo"
                        )
                        if st.button("Aplicar Destino", use_container_width=True):
                            if destino_masivo != "-- Seleccionar --":
                                st.session_state.df_procesado['Destino'] = destino_masivo
                                st.rerun()
                            else:
                                st.warning("Selecciona un destino válido.")
                    
                    with col2:
                        agrupacion_masiva = st.selectbox(
                            "Asignar grupo a todos:",
                            options=opciones_agrupacion, key="sel_agrupacion_masiva"
                        )
                        if st.button("Aplicar Grupo", use_container_width=True):
                            st.session_state.df_procesado['Agrupación'] = agrupacion_masiva
                            st.rerun()

                    st.divider()

                    st.markdown("Ahora, puedes editar cada fila individualmente si es necesario.")
                    edited_df = st.data_editor(
                        st.session_state.df_procesado,
                        column_config={
                            "Agrupación": st.column_config.SelectboxColumn("Agrupación", help="Grupo 1 es individual. Grupos 2-10 se sumarán.", options=opciones_agrupacion, required=True),
                            "Destino": st.column_config.SelectboxColumn("Destino del Efectivo", help="Selecciona el banco o tercero.", options=opciones_destino, required=True),
                            "Valor Efectivo": st.column_config.NumberColumn("Valor Efectivo", format="$ %.2f", disabled=True),
                            "Fecha": st.column_config.TextColumn("Fecha", disabled=True),
                            "Cliente": st.column_config.TextColumn("Cliente", disabled=True),
                            "Recibo N°": st.column_config.TextColumn("Recibo N°", disabled=True),
                        },
                        hide_index=True, use_container_width=True, key="editor_recibos"
                    )

                    st.divider()
                    st.subheader("4. Finalizar Proceso")
                    if st.button("✅ Procesar y Guardar Asignaciones", type="primary", use_container_width=True):
                        if edited_df['Destino'].isnull().any() or any(d == "-- Seleccionar --" for d in edited_df['Destino']):
                            st.warning("⚠️ Debes asignar un destino válido para TODOS los recibos de caja antes de procesar.")
                        else:
                            st.success("¡Asignaciones validadas! Generando archivos y guardando...")
                            
                            try:
                                # --- LÓGICA DE CONSECUTIVOS MODIFICADA ---
                                global_consecutive = get_next_global_consecutive(global_consecutivo_ws)
                                series_consecutive = get_next_series_consecutive(consecutivos_ws, serie_seleccionada)
                                
                                if global_consecutive is None or series_consecutive is None:
                                    st.error("No se pudieron obtener los consecutivos. Revisa los mensajes de error y la configuración en Google Sheets.")
                                    st.stop()

                                txt_content = generate_txt_content(edited_df, account_mappings, series_consecutive, global_consecutive, serie_seleccionada)

                                registros_data = []
                                for _, row in edited_df.iterrows():
                                    registros_data.append([
                                        row['Fecha'], row['Recibo N°'], row['Cliente'], row['Valor Efectivo'],
                                        row['Destino'], serie_seleccionada, series_consecutive,
                                        global_consecutive, # NUEVO: Se guarda el consecutivo global
                                        row['Agrupación'], datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    ])
                                
                                registros_recibos_ws.append_rows(registros_data, value_input_option='USER_ENTERED')
                                # Se actualizan ambos consecutivos
                                update_series_consecutive(consecutivos_ws, serie_seleccionada, series_consecutive)
                                update_global_consecutive(global_consecutivo_ws, global_consecutive)
                                
                                st.success("✅ Datos guardados en Google Sheets.")

                                st.download_button(
                                    label="⬇️ Descargar Archivo TXT para el ERP",
                                    data=txt_content.encode('utf-8'),
                                    file_name=f"recibos_{serie_seleccionada}_{global_consecutive}_{datetime.now().strftime('%Y%m%d')}.txt",
                                    mime="text/plain"
                                )
                                st.info("El archivo TXT ha sido generado y está listo para descargar.")

                            except Exception as e:
                                st.error(f"Error al guardar los datos o generar el archivo TXT: {e}")

            except Exception as e:
                st.error(f"Ocurrió un error al leer o procesar el archivo de Excel: {e}")
