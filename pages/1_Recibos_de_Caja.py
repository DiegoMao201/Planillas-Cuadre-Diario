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
st.title("🧾 Procesamiento de Recibos de Caja v2.0")
# st.markdown permite escribir texto con formato (como negrilla, listas, etc.).
st.markdown("""
Sube el archivo de Excel, selecciona la **serie** correspondiente y el sistema generará una tabla resumen.
En la tabla podrás **agrupar recibos** y asignar el destino (banco o tercero) de cada valor recaudado.
""")

# --- CONEXIÓN SEGURA A GOOGLE SHEETS ---
# @st.cache_resource es un decorador de Streamlit que guarda en caché el resultado de la función.
# Esto evita tener que reconectarse a Google Sheets cada vez que la página se recarga, mejorando el rendimiento.
# ttl=600 significa que la caché se refrescará cada 600 segundos (10 minutos).
@st.cache_resource(ttl=600)
def connect_to_gsheet():
    """
    Establece una conexión con Google Sheets usando las credenciales guardadas en los "secrets" de Streamlit.
    Devuelve los objetos de las hojas de cálculo para configuración, registros y los consecutivos.
    """
    try:
        # Carga las credenciales desde los secretos de Streamlit. Es la forma segura de manejar claves.
        creds_json = dict(st.secrets["google_credentials"])
        # Define los permisos que la aplicación necesitará para acceder a Google Sheets y Google Drive.
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        # Crea las credenciales a partir del diccionario JSON y los permisos definidos.
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        # Autoriza al cliente de gspread para que pueda usar las credenciales.
        client = gspread.authorize(creds)
        
        # Nombre del archivo de Google Sheets que se va a abrir.
        spreadsheet_name = "Planillas_Ferreinox"
        sheet = client.open(spreadsheet_name)
        
        # Obtiene acceso a cada una de las hojas de trabajo (pestañas) necesarias dentro del archivo.
        config_ws = sheet.worksheet("Configuracion")
        registros_recibos_ws = sheet.worksheet("RegistrosRecibos")
        consecutivos_ws = sheet.worksheet("Consecutivos") # Cambiado de GlobalConsecutivo a Consecutivos
        
        # Devuelve las hojas de trabajo para que puedan ser usadas por otras funciones.
        return config_ws, registros_recibos_ws, consecutivos_ws
        
    # --- MANEJO DE ERRORES ESPECÍFICOS ---
    except gspread.exceptions.SpreadsheetNotFound:
        # Si el archivo principal no se encuentra.
        st.error(f"Error fatal: No se encontró el archivo de Google Sheets llamado '{spreadsheet_name}'. Revisa el nombre y los permisos de acceso.")
        return None, None, None
    except gspread.exceptions.WorksheetNotFound as e:
        # Si alguna de las pestañas necesarias no existe.
        st.error(f"Error fatal: No se encontró una de las hojas de trabajo requeridas en el archivo. Detalle: {e}")
        st.warning("Asegúrate de que existan las hojas llamadas 'Configuracion', 'RegistrosRecibos' y 'Consecutivos'.")
        return None, None, None
    except Exception as e:
        # Para cualquier otro error durante la conexión.
        st.error(f"Error fatal al conectar con Google Sheets: {e}")
        st.warning("Por favor, verifica las credenciales en los secrets de Streamlit y los permisos de la cuenta de servicio sobre el archivo.")
        return None, None, None

def get_app_config(config_ws):
    """
    Carga la configuración de bancos y terceros desde la hoja de trabajo 'Configuracion'.
    """
    # Si la hoja de configuración no se pudo cargar, devuelve listas y diccionarios vacíos.
    if config_ws is None:
        return [], [], {}
    try:
        # Lee todos los registros de la hoja y los convierte en una lista de diccionarios.
        config_data = config_ws.get_all_records()
        # Filtra y crea una lista de bancos, eliminando duplicados y espacios en blanco.
        bancos = sorted(list(set(str(d['Detalle']).strip() for d in config_data if d.get('Tipo Movimiento') == 'BANCO' and d.get('Detalle'))))
        # Filtra y crea una lista de terceros, de la misma manera.
        terceros = sorted(list(set(str(d['Detalle']).strip() for d in config_data if d.get('Tipo Movimiento') == 'TERCERO' and d.get('Detalle'))))
        
        # Crea un diccionario para mapear cada destino (banco/tercero) con su información contable (cuenta, NIT, nombre).
        account_mappings = {}
        for d in config_data:
            detalle = str(d.get('Detalle', '')).strip()
            # Si el detalle existe y es de tipo BANCO o TERCERO, lo añade al diccionario.
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
def generate_txt_content(df, account_mappings, consecutive, series):
    """
    Genera el contenido del archivo TXT para el ERP a partir del DataFrame procesado,
    manejando registros individuales y agrupados.
    """
    txt_lines = []
    cuenta_recibo_caja = "11050501"
    tipo_documento = "12" # CAMBIO: Se actualiza el tipo de documento de 8 a 12

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

            # Línea DÉBITO (Banco/Tercero)
            linea_debito = "|".join([
                fecha, str(series), cuenta_destino, tipo_documento,
                f"Recibo de Caja {num_recibo} - {destino}", "Recibos", str(consecutive),
                str(valor), "0", "0", nit_tercero, nombre_tercero, "0"
            ])
            txt_lines.append(linea_debito)

            # Línea CRÉDITO (Caja)
            linea_credito = "|".join([
                fecha, str(series), cuenta_recibo_caja, tipo_documento,
                f"Recibo de Caja {num_recibo} - Cliente {row['Cliente']}", "Recibos", str(consecutive),
                "0", str(valor), "0", "0", "0", "0"
            ])
            txt_lines.append(linea_credito)

    # --- 2. PROCESAR REGISTROS AGRUPADOS (AGRUPACIÓN > 1) ---
    df_agrupado = df[df['Agrupación'] > 1]
    if not df_agrupado.empty:
        # Agrupa por el número de agrupación y el destino, sumando los valores.
        grouped = df_agrupado.groupby(['Agrupación', 'Destino']).agg(
            Valor_Total=('Valor Efectivo', 'sum'),
            Fecha_Primera=('Fecha', 'first'),
            Recibos_Incluidos=('Recibo N°', lambda x: ','.join(x.astype(str).str.split('.').str[0]))
        ).reset_index()

        for _, group_row in grouped.iterrows():
            destino = group_row['Destino']
            valor_total = group_row['Valor_Total']
            fecha = pd.to_datetime(group_row['Fecha_Primera'], dayfirst=True).strftime('%d/%m/%Y')
            recibos = group_row['Recibos_Incluidos']

            if destino in account_mappings:
                destino_info = account_mappings[destino]
                cuenta_destino = destino_info['cuenta']
                nit_tercero = destino_info['nit']
                nombre_tercero = destino_info['nombre']

                # Línea DÉBITO para el grupo
                linea_debito = "|".join([
                    fecha, str(series), cuenta_destino, tipo_documento,
                    f"Consolidado Recibos {recibos} - {destino}", "Recibos", str(consecutive),
                    str(valor_total), "0", "0", nit_tercero, nombre_tercero, "0"
                ])
                txt_lines.append(linea_debito)

                # Línea CRÉDITO para el grupo
                linea_credito = "|".join([
                    fecha, str(series), cuenta_recibo_caja, tipo_documento,
                    f"Consolidado Recibos {recibos}", "Recibos", str(consecutive),
                    "0", str(valor_total), "0", "0", "0", "0"
                ])
                txt_lines.append(linea_credito)

    return "\n".join(txt_lines)

# --- NUEVAS FUNCIONES PARA MANEJAR CONSECUTIVOS POR SERIE ---
def get_next_consecutive(consecutivos_ws, series_name):
    """
    Obtiene el siguiente número consecutivo para una serie específica.
    """
    try:
        # Busca la celda que contiene la etiqueta de la serie.
        label_to_find = f'Ultimo_Consecutivo_{series_name}'
        cell = consecutivos_ws.find(label_to_find)
        if cell:
            # Lee el valor de la celda de al lado (a la derecha).
            last_consecutive = int(consecutivos_ws.cell(cell.row, cell.col + 1).value)
            return last_consecutive + 1
        else:
            st.error(f"No se encontró la etiqueta '{label_to_find}'. Revisa la hoja 'Consecutivos'.")
            return None
    except Exception as e:
        st.error(f"Error obteniendo el consecutivo para la serie {series_name}: {e}")
        return None

def update_consecutive(consecutivos_ws, series_name, new_consecutive):
    """
    Actualiza el último número consecutivo utilizado para una serie en Google Sheets.
    """
    try:
        # Busca la celda que contiene la etiqueta de la serie.
        label_to_find = f'Ultimo_Consecutivo_{series_name}'
        cell = consecutivos_ws.find(label_to_find)
        if cell:
            # Actualiza la celda de al lado con el nuevo número consecutivo.
            consecutivos_ws.update_cell(cell.row, cell.col + 1, new_consecutive)
    except Exception as e:
        st.error(f"Error actualizando el consecutivo para la serie {series_name}: {e}")

# --- LÓGICA PRINCIPAL DE LA PÁGINA ---
# Llama a la función de conexión para obtener acceso a las hojas de trabajo.
config_ws, registros_recibos_ws, consecutivos_ws = connect_to_gsheet()

# Si la conexión falla, muestra un error y detiene la ejecución.
if config_ws is None or registros_recibos_ws is None or consecutivos_ws is None:
    st.error("La aplicación no puede continuar debido a un error de conexión con Google Sheets.")
else:
    # Si la conexión es exitosa, carga la configuración de la aplicación.
    bancos, terceros, account_mappings = get_app_config(config_ws)
    opciones_destino = ["-- Seleccionar --"] + bancos + terceros
    opciones_agrupacion = list(range(1, 11)) # Opciones de 1 a 10 para agrupar

    # Si no se cargaron destinos, muestra un error.
    if not opciones_destino or len(opciones_destino) == 1:
        st.error("No se pudieron cargar los destinos (bancos/terceros) desde la hoja 'Configuracion'. La página no puede funcionar.")
    else:
        # --- NUEVO: SELECTOR DE SERIE ---
        st.subheader("1. Selecciona la Serie del Documento")
        # Lista de series disponibles para el usuario
        series_disponibles = ["189U", "157U", "156U"]
        serie_seleccionada = st.selectbox(
            "Elige la serie que corresponde a los recibos de este archivo:",
            options=series_disponibles,
            index=0,
            help="Esta serie se usará en el archivo TXT final."
        )
        st.divider()

        # Muestra el componente para subir archivos.
        st.subheader("2. Carga el Archivo de Excel")
        uploaded_file = st.file_uploader(
            "📂 Sube tu archivo de Excel de recibos de caja",
            type=['xlsx', 'xls'] # Acepta solo archivos de tipo Excel.
        )

        # Si un archivo ha sido subido...
        if uploaded_file is not None:
            st.success("¡Archivo subido con éxito! Ahora puedes procesarlo.")
            
            try:
                # Lee el archivo Excel y lo carga en un DataFrame de pandas.
                df = pd.read_excel(uploaded_file, header=0)

                # --- VALIDACIÓN DE COLUMNAS ---
                required_columns = ['FECHA_RECIBO', 'NUMRECIBO', 'NOMBRECLIENTE', 'IMPORTE']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    st.error(f"Error en el formato del archivo. Faltan las siguientes columnas: {', '.join(missing_columns)}")
                    st.warning("Por favor, asegúrate de que el archivo de Excel contenga estas columnas con los nombres exactos.")
                    st.stop()

                # --- LÓGICA DE LIMPIEZA DE DATOS ---
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
                
                # --- NUEVO: AÑADIR COLUMNA DE AGRUPACIÓN ---
                df_resumen['Agrupación'] = 1 # Por defecto, todos son individuales (grupo 1)
                df_resumen['Destino'] = "-- Seleccionar --"
                
                # Reordenar columnas para mejor visualización
                df_resumen = df_resumen[['Fecha', 'Recibo N°', 'Cliente', 'Valor Efectivo', 'Agrupación', 'Destino']]


                # --- INICIALIZACIÓN DEL ESTADO DE LA SESIÓN ---
                if 'df_procesado' not in st.session_state or st.session_state.get('uploaded_file_name') != uploaded_file.name:
                    st.session_state.df_procesado = df_resumen.copy()
                    st.session_state.uploaded_file_name = uploaded_file.name

                if df_resumen.empty:
                    st.warning("El archivo no contiene recibos de caja válidos después de la limpieza. Por favor, revisa el formato y los datos.")
                else:
                    st.subheader("3. Asigna Agrupación y Destinos")
                    total_recibos = st.session_state.df_procesado['Valor Efectivo'].sum()
                    st.metric(label="💰 Total Efectivo Recaudado", value=f"${total_recibos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    st.divider()

                    # --- HERRAMIENTA DE ASIGNACIÓN RÁPIDA (MODIFICADA) ---
                    st.info("Usa estas herramientas para asignar valores a todos los recibos de forma masiva.")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        # Asignación masiva de DESTINO
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
                        # Asignación masiva de AGRUPACIÓN
                        agrupacion_masiva = st.selectbox(
                            "Asignar grupo a todos:",
                            options=opciones_agrupacion, key="sel_agrupacion_masiva"
                        )
                        if st.button("Aplicar Grupo", use_container_width=True):
                            st.session_state.df_procesado['Agrupación'] = agrupacion_masiva
                            st.rerun()

                    st.divider()

                    # --- TABLA EDITABLE (MODIFICADA) ---
                    st.markdown("Ahora, puedes editar cada fila individualmente si es necesario.")
                    edited_df = st.data_editor(
                        st.session_state.df_procesado,
                        column_config={
                            "Agrupación": st.column_config.SelectboxColumn(
                                "Agrupación",
                                help="Grupo 1 es individual. Grupos 2-10 se sumarán en el TXT.",
                                options=opciones_agrupacion,
                                required=True
                            ),
                            "Destino": st.column_config.SelectboxColumn(
                                "Destino del Efectivo",
                                help="Selecciona el banco o tercero.",
                                options=opciones_destino,
                                required=True
                            ),
                            "Valor Efectivo": st.column_config.NumberColumn("Valor Efectivo", format="$ %.2f", disabled=True),
                            "Fecha": st.column_config.TextColumn("Fecha", disabled=True),
                            "Cliente": st.column_config.TextColumn("Cliente", disabled=True),
                            "Recibo N°": st.column_config.TextColumn("Recibo N°", disabled=True),
                        },
                        hide_index=True,
                        use_container_width=True,
                        key="editor_recibos"
                    )

                    st.divider()
                    st.subheader("4. Finalizar Proceso")
                    if st.button("✅ Procesar y Guardar Asignaciones", type="primary", use_container_width=True):
                        if edited_df['Destino'].isnull().any() or any(d == "-- Seleccionar --" for d in edited_df['Destino']):
                            st.warning("⚠️ Debes asignar un destino válido para TODOS los recibos de caja antes de procesar.")
                        else:
                            st.success("¡Asignaciones validadas! Generando archivos y guardando...")
                            
                            try:
                                # Obtener el consecutivo para la serie seleccionada
                                consecutive = get_next_consecutive(consecutivos_ws, serie_seleccionada)
                                if consecutive is None:
                                    st.error("No se pudo obtener el consecutivo. No se puede guardar.")
                                    st.stop()

                                # Generar el contenido del archivo TXT
                                txt_content = generate_txt_content(edited_df, account_mappings, consecutive, serie_seleccionada)

                                # Preparar datos para guardar en Google Sheets
                                registros_data = []
                                for _, row in edited_df.iterrows():
                                    registros_data.append([
                                        row['Fecha'],
                                        row['Recibo N°'],
                                        row['Cliente'],
                                        row['Valor Efectivo'],
                                        row['Destino'],
                                        serie_seleccionada, # Guardar la serie
                                        consecutive, # Guardar el consecutivo
                                        row['Agrupación'], # Guardar el grupo asignado
                                        datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    ])
                                
                                # Guardar en Google Sheets y actualizar consecutivo
                                registros_recibos_ws.append_rows(registros_data, value_input_option='USER_ENTERED')
                                update_consecutive(consecutivos_ws, serie_seleccionada, consecutive)
                                st.success("✅ Datos guardados en Google Sheets.")

                                # Botón de descarga para el archivo TXT
                                st.download_button(
                                    label="⬇️ Descargar Archivo TXT para el ERP",
                                    data=txt_content.encode('utf-8'),
                                    file_name=f"recibos_{serie_seleccionada}_{consecutive}_{datetime.now().strftime('%Y%m%d')}.txt",
                                    mime="text/plain"
                                )
                                st.info("El archivo TXT ha sido generado y está listo para descargar.")

                            except Exception as e:
                                st.error(f"Error al guardar los datos o generar el archivo TXT: {e}")
                                st.warning("Por favor, revisa la conexión y la estructura de las hojas de Google Sheets.")

            except Exception as e:
                st.error(f"Ocurrió un error al leer o procesar el archivo de Excel: {e}")
                st.warning("Asegúrate de que el archivo no esté corrupto y tenga el formato esperado.")
