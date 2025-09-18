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
st.title("🧾 Procesamiento de Recibos de Caja")
# st.markdown permite escribir texto con formato (como negrilla, listas, etc.).
st.markdown("""
Sube el archivo de Excel con el resumen diario de los recibos de caja.
El sistema mostrará una tabla resumen donde podrás asignar el destino (banco o tercero)
de cada valor en efectivo recaudado.
""")

# --- CONEXIÓN SEGURA A GOOGLE SHEETS ---
# @st.cache_resource es un decorador de Streamlit que guarda en caché el resultado de la función.
# Esto evita tener que reconectarse a Google Sheets cada vez que la página se recarga, mejorando el rendimiento.
# ttl=600 significa que la caché se refrescará cada 600 segundos (10 minutos).
@st.cache_resource(ttl=600)
def connect_to_gsheet():
    """
    Establece una conexión con Google Sheets usando las credenciales guardadas en los "secrets" de Streamlit.
    Devuelve los objetos de las hojas de cálculo para configuración, registros y el consecutivo global.
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
        global_consecutivo_ws = sheet.worksheet("GlobalConsecutivo")
        
        # Devuelve las hojas de trabajo para que puedan ser usadas por otras funciones.
        return config_ws, registros_recibos_ws, global_consecutivo_ws
        
    # --- MANEJO DE ERRORES ESPECÍFICOS ---
    except gspread.exceptions.SpreadsheetNotFound:
        # Si el archivo principal no se encuentra.
        st.error(f"Error fatal: No se encontró el archivo de Google Sheets llamado '{spreadsheet_name}'. Revisa el nombre y los permisos de acceso.")
        return None, None, None
    except gspread.exceptions.WorksheetNotFound as e:
        # Si alguna de las pestañas necesarias no existe.
        st.error(f"Error fatal: No se encontró una de las hojas de trabajo requeridas en el archivo. Detalle: {e}")
        st.warning("Asegúrate de que existan las hojas llamadas 'Configuracion', 'RegistrosRecibos' y 'GlobalConsecutivo'.")
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
def generate_txt_from_df(df, account_mappings, global_consecutive):
    """
    Genera el contenido del archivo TXT para el ERP a partir del DataFrame procesado.
    """
    txt_lines = []
    
    # Define la cuenta contable de contrapartida para los recibos de caja.
    cuenta_recibo_caja = "11050501" 
    
    # Itera sobre cada fila del DataFrame que contiene los datos editados por el usuario.
    for _, row in df.iterrows():
        try:
            # Convierte la fecha a formato DD/MM/YYYY. Se asume que el día viene primero.
            fecha = pd.to_datetime(row['Fecha'], dayfirst=True).strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            # Si la fecha ya está en el formato correcto, la usa directamente.
            fecha = row['Fecha']

        # Obtiene los demás datos de la fila.
        num_recibo = str(row['Recibo N°'])
        valor = float(row['Valor Efectivo'])
        destino = str(row['Destino'])
        
        # Verifica si el destino seleccionado tiene una configuración contable.
        if destino not in account_mappings:
            st.warning(f"No se encontró mapeo para el destino: {destino}. Se omitirá del TXT.")
            continue # Salta a la siguiente fila.
        
        # Obtiene la información contable del destino.
        destino_info = account_mappings[destino]
        cuenta_destino = destino_info.get('cuenta')
        nit_tercero = destino_info.get('nit')
        nombre_tercero = destino_info.get('nombre')
        
        # Crea la línea del DÉBITO para el archivo TXT, uniendo los campos con '|'.
        # Esta línea registra la entrada del dinero al banco o tercero.
        linea_debito = "|".join([
            fecha, str(global_consecutive), cuenta_destino, "8",
            f"Recibo de Caja {num_recibo} - {destino}", "Recibos", num_recibo,
            str(valor), "0", "0", nit_tercero, nombre_tercero, "0"
        ])
        txt_lines.append(linea_debito)

        # Crea la línea del CRÉDITO para el archivo TXT.
        # Esta línea registra la salida del dinero de la caja general.
        linea_credito = "|".join([
            fecha, str(global_consecutive), cuenta_recibo_caja, "8", 
            f"Recibo de Caja {num_recibo} - Cliente {row['Cliente']}", "Recibos", num_recibo,
            "0", str(valor), "0", "0", "0", "0"
        ])
        txt_lines.append(linea_credito)

    # Une todas las líneas generadas con un salto de línea para formar el contenido del archivo.
    return "\n".join(txt_lines)

def get_next_global_consecutive(global_consecutivo_ws):
    """
    Obtiene el siguiente número consecutivo global para el documento del ERP.
    """
    try:
        # Busca la celda que contiene el texto 'Ultimo_Consecutivo_Global'.
        cell = global_consecutivo_ws.find('Ultimo_Consecutivo_Global')
        if cell:
            # Si la encuentra, lee el valor de la celda de al lado (a la derecha).
            last_consecutive = int(global_consecutivo_ws.cell(cell.row, cell.col + 1).value)
            # Devuelve el siguiente número.
            return last_consecutive + 1
        else:
            st.error("No se encontró la etiqueta 'Ultimo_Consecutivo_Global'. Revisa la hoja 'GlobalConsecutivo'.")
            return None
    except Exception as e:
        st.error(f"Error obteniendo el consecutivo global: {e}")
        return None

def update_global_consecutive(global_consecutivo_ws, new_consecutive):
    """
    Actualiza el último número consecutivo global utilizado en la hoja de Google Sheets.
    """
    try:
        # Busca la celda que contiene el texto 'Ultimo_Consecutivo_Global'.
        cell = global_consecutivo_ws.find('Ultimo_Consecutivo_Global')
        if cell:
            # Actualiza la celda de al lado con el nuevo número consecutivo.
            global_consecutivo_ws.update_cell(cell.row, cell.col + 1, new_consecutive)
    except Exception as e:
        st.error(f"Error actualizando el consecutivo global: {e}")

# --- LÓGICA PRINCIPAL DE LA PÁGINA ---
# Llama a la función de conexión para obtener acceso a las hojas de trabajo.
config_ws, registros_recibos_ws, global_consecutivo_ws = connect_to_gsheet()

# Si la conexión falla, muestra un error y detiene la ejecución.
if config_ws is None or registros_recibos_ws is None or global_consecutivo_ws is None:
    st.error("La aplicación no puede continuar debido a un error de conexión con Google Sheets.")
else:
    # Si la conexión es exitosa, carga la configuración de la aplicación.
    bancos, terceros, account_mappings = get_app_config(config_ws)
    # Crea la lista de opciones para el selector de destino.
    opciones_destino = ["-- Seleccionar --"] + bancos + terceros

    # Si no se cargaron destinos, muestra un error.
    if not opciones_destino or len(opciones_destino) == 1:
        st.error("No se pudieron cargar los destinos (bancos/terceros) desde la hoja 'Configuracion'. La página no puede funcionar.")
    else:
        # Muestra el componente para subir archivos.
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

                # --- NUEVA VALIDACIÓN DE COLUMNAS ---
                # Define las columnas que son absolutamente necesarias para que el script funcione.
                required_columns = ['FECHA_RECIBO', 'NUMRECIBO', 'NOMBRECLIENTE', 'IMPORTE']
                # Verifica si todas las columnas requeridas existen en el archivo subido.
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                # Si faltan columnas, muestra un error detallado y detiene la ejecución.
                if missing_columns:
                    st.error(f"Error en el formato del archivo. Faltan las siguientes columnas: {', '.join(missing_columns)}")
                    st.warning("Por favor, asegúrate de que el archivo de Excel contenga estas columnas con los nombres exactos.")
                    st.stop() # Detiene la ejecución del script para evitar más errores.

                # --- LÓGICA DE LIMPIEZA DE DATOS ---
                
                # PASO 1: Identificar y eliminar filas de subtotales/totales.
                # Se asume que una fila de transacción válida DEBE tener una fecha.
                # Las filas de subtotales o totales generalmente no tienen fecha, así que se eliminan.
                df_cleaned = df.dropna(subset=['FECHA_RECIBO']).copy()

                # PASO 2: Rellenar hacia abajo la información de identificación.
                # Esto propaga el número de recibo, fecha y cliente a todas las líneas de detalle asociadas.
                id_cols = ['NUMRECIBO', 'FECHA_RECIBO', 'NOMBRECLIENTE', 'NIF20']
                for col in id_cols:
                    if col in df_cleaned.columns:
                        df_cleaned[col] = df_cleaned[col].ffill()

                # PASO 3: Función para limpiar y convertir valores de moneda.
                # Maneja formatos como "$ 1.234,56", eliminando símbolos y convirtiéndolos a un número (float).
                def clean_and_convert(value):
                    try:
                        str_value = str(value).strip()
                        # 1. Quitar el símbolo de moneda '$'
                        str_value = str_value.replace('$', '')
                        # 2. Quitar el separador de miles '.'
                        str_value = str_value.replace('.', '')
                        # 3. Reemplazar el separador decimal ',' por un punto '.'
                        str_value = str_value.replace(',', '.')
                        # Convertir a float (número con decimales)
                        return float(str_value)
                    except (ValueError, IndexError):
                        # Si la conversión falla, devuelve None
                        return None
                
                # Aplica la función de limpieza a la columna 'IMPORTE'.
                df_cleaned['IMPORTE_LIMPIO'] = df_cleaned['IMPORTE'].apply(clean_and_convert)
                # Elimina cualquier fila donde la conversión de moneda haya fallado.
                df_cleaned.dropna(subset=['IMPORTE_LIMPIO'], inplace=True)

                # --- FIN DE LA LÓGICA DE LIMPIEZA ---

                # Agrupa por número de recibo y suma los montos limpios para obtener el total por recibo.
                df_resumen = df_cleaned.groupby('NUMRECIBO').agg({
                    'FECHA_RECIBO': 'first', # Toma el primer valor (todos deberían ser iguales).
                    'NOMBRECLIENTE': 'first',
                    'IMPORTE_LIMPIO': 'sum' # Suma todos los importes del mismo recibo.
                }).reset_index()

                # Renombra las columnas para que sean más amigables en la interfaz de usuario.
                df_resumen.rename(columns={
                    'FECHA_RECIBO': 'Fecha',
                    'NUMRECIBO': 'Recibo N°',
                    'NOMBRECLIENTE': 'Cliente',
                    'IMPORTE_LIMPIO': 'Valor Efectivo'
                }, inplace=True)
                
                # Asegura que la columna de fecha tenga el formato DD/MM/YYYY.
                if pd.api.types.is_datetime64_any_dtype(df_resumen['Fecha']):
                    df_resumen['Fecha'] = pd.to_datetime(df_resumen['Fecha']).dt.strftime('%d/%m/%Y')
                
                # Si después de la limpieza el DataFrame está vacío, muestra una advertencia.
                if df_resumen.empty:
                    st.warning("El archivo no contiene recibos de caja válidos después de la limpieza. Por favor, revisa el formato y los datos.")
                else:
                    # Muestra un resumen del total recaudado.
                    st.subheader("📊 Resumen del Día")
                    total_recibos = df_resumen['Valor Efectivo'].sum()
                    # Formatea el total como moneda colombiana (puntos para miles, coma para decimales).
                    st.metric(label="💰 Total Efectivo Recaudado", value=f"${total_recibos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    st.divider() # Dibuja una línea divisoria.

                    st.subheader("Asignar Destino del Efectivo")
                    st.info("Usa la columna 'Destino' para seleccionar a qué banco o tercero se entregó el efectivo de cada recibo.")

                    # Añade la columna 'Destino' con un valor por defecto.
                    df_resumen['Destino'] = "-- Seleccionar --"

                    # Muestra una tabla editable (data_editor) para que el usuario asigne los destinos.
                    edited_df = st.data_editor(
                        df_resumen,
                        column_config={
                            "Destino": st.column_config.SelectboxColumn(
                                "Destino del Efectivo",
                                help="Selecciona el banco o tercero donde se consignó/entregó el efectivo.",
                                options=opciones_destino,
                                required=True # Hace que la selección sea obligatoria.
                            ),
                            "Valor Efectivo": st.column_config.NumberColumn("Valor Efectivo", format="$ %.2f", disabled=True),
                            "Fecha": st.column_config.TextColumn("Fecha", disabled=True),
                            "Cliente": st.column_config.TextColumn("Cliente", disabled=True),
                            "Recibo N°": st.column_config.TextColumn("Recibo N°", disabled=True),
                        },
                        hide_index=True, # Oculta el índice del DataFrame.
                        use_container_width=True, # Hace que la tabla ocupe todo el ancho disponible.
                        key="editor_recibos" # Una clave única para este componente.
                    )

                    st.divider()
                    # Muestra el botón principal para procesar los datos.
                    if st.button("✅ Procesar y Guardar Asignaciones", type="primary", use_container_width=True):
                        # Verifica si todos los recibos tienen un destino asignado.
                        if edited_df['Destino'].isnull().any() or any(d == "-- Seleccionar --" for d in edited_df['Destino']):
                            st.warning("⚠️ Debes asignar un destino válido para TODOS los recibos de caja antes de procesar.")
                        else:
                            st.success("¡Asignaciones procesadas! Los datos están listos para ser guardados.")
                            
                            try:
                                # Obtiene el siguiente consecutivo global para este lote de registros.
                                global_consecutive = get_next_global_consecutive(global_consecutivo_ws)
                                if global_consecutive is None:
                                    # Si no se puede obtener el consecutivo, detiene el proceso.
                                    st.error("No se pudo obtener el consecutivo global. No se puede guardar.")
                                    st.stop()

                                # Genera el contenido del archivo TXT.
                                txt_content = generate_txt_from_df(edited_df, account_mappings, global_consecutive)

                                # Prepara los datos para ser guardados en la hoja de registros de Google Sheets.
                                registros_data = []
                                for _, row in edited_df.iterrows():
                                    registros_data.append([
                                        row['Fecha'],
                                        row['Recibo N°'],
                                        row['Cliente'],
                                        row['Valor Efectivo'],
                                        row['Destino'],
                                        global_consecutive,
                                        datetime.now().strftime("%d/%m/%Y %H:%M:%S") # Añade marca de tiempo del procesamiento.
                                    ])
                                
                                # Añade las nuevas filas a la hoja de Google Sheets.
                                registros_recibos_ws.append_rows(registros_data, value_input_option='USER_ENTERED')
                                # Actualiza el contador del consecutivo global.
                                update_global_consecutive(global_consecutivo_ws, global_consecutive)
                                st.success("✅ Datos guardados en Google Sheets.")

                                # Muestra el botón de descarga para el archivo TXT.
                                st.download_button(
                                    label="⬇️ Descargar Archivo TXT para el ERP",
                                    data=txt_content.encode('utf-8'), # Codifica el contenido a UTF-8.
                                    file_name=f"recibos_caja_{datetime.now().strftime('%Y%m%d')}.txt",
                                    mime="text/plain"
                                )
                                st.info("El archivo TXT ha sido generado y está listo para descargar.")

                            except Exception as e:
                                st.error(f"Error al guardar los datos o generar el archivo TXT: {e}")
                                st.warning("Por favor, revisa la conexión y la estructura de las hojas de Google Sheets.")

            except Exception as e:
                st.error(f"Ocurrió un error al leer o procesar el archivo de Excel: {e}")
                st.warning("Asegúrate de que el archivo no esté corrupto y tenga el formato esperado.")
