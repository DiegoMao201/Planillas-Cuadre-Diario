# -*- coding: utf-8 -*-

# --- IMPORTACIÓN DE LIBRERÍAS NECESARIAS ---
import streamlit as st
import pandas as pd
from io import BytesIO
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import json
from datetime import datetime

# --- CONFIGURACIÓN DE LA PÁGINA DE STREAMLIT ---
st.set_page_config(layout="wide", page_title="Recibos de Caja")

# --- TÍTULOS Y DESCRIPCIÓN DE LA APLICACIÓN ---
st.title("🧾 Procesamiento de Recibos de Caja v4.0 (con Edición)")
st.markdown("""
Esta herramienta permite dos flujos de trabajo:
1.  **Cargar un nuevo archivo de Excel** para procesar y guardar un nuevo grupo de recibos.
2.  **Buscar y cargar un grupo existente** para editarlo y volver a guardarlo.
""")

# --- CONEXIÓN SEGURA A GOOGLE SHEETS ---
@st.cache_resource(ttl=600)
def connect_to_gsheet():
    """
    Establece una conexión con Google Sheets usando las credenciales de Streamlit.
    Devuelve los objetos de las hojas de cálculo necesarias.
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
        global_consecutivo_ws = sheet.worksheet("GlobalConsecutivo")
        
        return config_ws, registros_recibos_ws, consecutivos_ws, global_consecutivo_ws
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Error fatal: No se encontró el archivo de Google Sheets llamado '{spreadsheet_name}'. Revisa el nombre y los permisos.")
        return None, None, None, None
    except gspread.exceptions.WorksheetNotFound as e:
        st.error(f"Error fatal: No se encontró una de las hojas de trabajo requeridas. Detalle: {e}")
        st.warning("Asegúrate de que existan las hojas 'Configuracion', 'RegistrosRecibos', 'Consecutivos' y 'GlobalConsecutivo'.")
        return None, None, None, None
    except Exception as e:
        st.error(f"Error fatal al conectar con Google Sheets: {e}")
        st.warning("Verifica las credenciales en los secrets de Streamlit y los permisos de la cuenta de servicio.")
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

# --- LÓGICA DE PROCESAMIENTO Y GENERACIÓN DE ARCHIVOS ---
def generate_txt_content(df, account_mappings, series_consecutive, global_consecutive, series):
    """
    Genera el contenido del archivo TXT para el ERP, con la nueva estructura y un crédito único.
    """
    txt_lines = []
    cuenta_recibo_caja = "11050501"
    tipo_documento = "12"
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

            linea_debito = "|".join([
                fecha, str(global_consecutive), cuenta_destino, tipo_documento,
                f"Recibo de Caja {num_recibo} - {row['Cliente']}",
                str(series_numeric), str(series_consecutive),
                str(valor), "0", "0", nit_tercero, nombre_tercero, "0"
            ])
            txt_lines.append(linea_debito)

    # --- 2. PROCESAR REGISTROS AGRUPADOS (AGRUPACIÓN > 1) ---
    df_agrupado = df[df['Agrupación'] > 1]
    if not df_agrupado.empty:
        grouped = df_agrupado.groupby(['Agrupación', 'Destino']).agg(
            Valor_Total=('Valor Efectivo', 'sum'),
            Fecha_Primera=('Fecha', 'first'),
            Recibos_Incluidos=('Recibo N°', lambda x: ','.join(x.astype(str).str.split('.').str[0])),
            Clientes_Grupo=('Cliente', lambda x: ', '.join(x.unique()))
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

                linea_debito = "|".join([
                    fecha, str(global_consecutive), cuenta_destino, tipo_documento,
                    f"Consolidado Recibos {recibos} - {clientes_grupo}",
                    str(series_numeric), str(series_consecutive),
                    str(valor_total), "0", "0", nit_tercero, nombre_tercero, "0"
                ])
                txt_lines.append(linea_debito)

    # --- 3. GENERAR LÍNEA DE CRÉDITO ÚNICA Y CONSOLIDADA ---
    if not df.empty and txt_lines:
        total_valor = df['Valor Efectivo'].sum()
        primera_fecha = pd.to_datetime(df['Fecha'].iloc[0], dayfirst=True).strftime('%d/%m/%Y')
        
        min_recibo = int(df['Recibo N°'].min())
        max_recibo = int(df['Recibo N°'].max())
        comentario_credito = f"Consolidado Recibos del {min_recibo} al {max_recibo}"

        linea_credito_unica = "|".join([
            primera_fecha, str(global_consecutive), cuenta_recibo_caja, tipo_documento,
            comentario_credito,
            str(series_numeric), str(series_consecutive),
            "0", str(total_valor), "0", "0", "0", "0"
        ])
        txt_lines.append(linea_credito_unica)

    return "\n".join(txt_lines)

# --- FUNCIONES PARA MANEJAR CONSECUTIVOS ---
def get_next_series_consecutive(consecutivos_ws, series_name):
    """Obtiene el siguiente número consecutivo para una serie específica."""
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
    """Actualiza el último número consecutivo utilizado para una serie."""
    try:
        label_to_find = f'Ultimo_Consecutivo_{series_name}'
        cell = consecutivos_ws.find(label_to_find)
        if cell:
            consecutivos_ws.update_cell(cell.row, cell.col + 1, new_consecutive)
    except Exception as e:
        st.error(f"Error actualizando el consecutivo para la serie {series_name}: {e}")

def get_next_global_consecutive(global_consecutivo_ws):
    """Obtiene el siguiente número consecutivo global."""
    try:
        last_consecutive = int(global_consecutivo_ws.acell('B1').value)
        return last_consecutive + 1
    except Exception as e:
        st.error(f"Error obteniendo el consecutivo global: {e}")
        return None

def update_global_consecutive(global_consecutivo_ws, new_consecutive):
    """Actualiza el último número consecutivo global."""
    try:
        global_consecutivo_ws.update_acell('B1', new_consecutive)
    except Exception as e:
        st.error(f"Error actualizando el consecutivo global: {e}")

# --- NUEVA FUNCIÓN PARA BORRAR REGISTROS ANTES DE ACTUALIZAR ---
def delete_existing_records(ws, global_consecutive_to_delete):
    """
    Encuentra y borra todas las filas en la hoja que coincidan con un consecutivo global.
    """
    try:
        st.info(f"Buscando registros antiguos con el consecutivo global {global_consecutive_to_delete} para eliminarlos...")
        all_records = ws.get_all_records()
        df_records = pd.DataFrame(all_records)
        
        if 'Consecutivo Global' not in df_records.columns:
            st.error("La hoja 'RegistrosRecibos' no tiene la columna 'Consecutivo Global'. No se puede actualizar.")
            return

        # Convertir a string para una comparación segura
        df_records['Consecutivo Global'] = df_records['Consecutivo Global'].astype(str)
        global_consecutive_to_delete = str(global_consecutive_to_delete)

        # Encontrar los índices de las filas a borrar (los índices en gspread son 1-based y la cabecera es la fila 1)
        rows_to_delete_indices = df_records[df_records['Consecutivo Global'] == global_consecutive_to_delete].index.tolist()
        
        # Los índices del DataFrame son 0-based, necesitamos sumar 2 para obtener el número de fila real en la hoja
        # (1 por la cabecera, 1 porque gspread es 1-based)
        gspread_rows_to_delete = sorted([i + 2 for i in rows_to_delete_indices], reverse=True)

        if not gspread_rows_to_delete:
            st.warning("No se encontraron registros antiguos que coincidieran. Se procederá a guardar como si fueran nuevos.")
            return

        # Borrar filas desde la última hasta la primera para evitar problemas con la reindexación
        for row_index in gspread_rows_to_delete:
            ws.delete_rows(row_index)
        
        st.success(f"Se eliminaron {len(gspread_rows_to_delete)} registros antiguos con éxito.")

    except Exception as e:
        st.error(f"Error crítico al intentar borrar registros antiguos: {e}")
        # Detener la ejecución si no se pueden borrar los registros para evitar duplicados
        st.stop()


# --- LÓGICA PRINCIPAL DE LA PÁGINA ---
config_ws, registros_recibos_ws, consecutivos_ws, global_consecutivo_ws = connect_to_gsheet()

if config_ws is None or registros_recibos_ws is None or consecutivos_ws is None or global_consecutivo_ws is None:
    st.error("La aplicación no puede continuar debido a un error de conexión con Google Sheets.")
else:
    bancos, terceros, account_mappings = get_app_config(config_ws)
    opciones_destino = ["-- Seleccionar --"] + bancos + terceros
    opciones_agrupacion = list(range(1, 11))
    series_disponibles = ["189U", "157U", "156U"]
    
    # Inicializar el modo de la aplicación en el estado de la sesión
    if 'mode' not in st.session_state:
        st.session_state.mode = 'new' # Puede ser 'new' o 'edit'
        st.session_state.editing_info = {}
        st.session_state.found_groups = []

    st.subheader("1. Elige una opción")

    # Botones para seleccionar el modo de trabajo
    col_mode_1, col_mode_2, col_mode_3 = st.columns([1,1,2])
    with col_mode_1:
        if st.button("🆕 Procesar Nuevo Archivo", use_container_width=True, type="primary" if st.session_state.mode == 'new' else "secondary"):
            # Limpiar estado al cambiar de modo
            for key in list(st.session_state.keys()):
                if key not in ['mode', 'google_credentials']:
                    del st.session_state[key]
            st.session_state.mode = 'new'
            st.rerun()

    with col_mode_2:
        if st.button("✏️ Editar Grupo Existente", use_container_width=True, type="primary" if st.session_state.mode == 'edit' else "secondary"):
            for key in list(st.session_state.keys()):
                if key not in ['mode', 'google_credentials']:
                     del st.session_state[key]
            st.session_state.mode = 'edit'
            st.rerun()
            
    st.divider()

    # --- MODO EDICIÓN: BUSCAR Y CARGAR GRUPO ---
    if st.session_state.mode == 'edit':
        st.header("✏️ Editar Grupo de Recibos")
        st.info("Busca un grupo de recibos que ya hayas procesado para cargarlo y modificarlo.")
        
        with st.expander("Buscar Grupo de Recibos", expanded=True):
            search_col1, search_col2 = st.columns(2)
            with search_col1:
                search_date = st.date_input("Fecha de los recibos:", datetime.now())
                search_date_str = search_date.strftime('%d/%m/%Y')
            with search_col2:
                search_serie = st.selectbox("Serie de los recibos:", options=series_disponibles, key="search_serie")
            
            if st.button("Buscar Grupos", use_container_width=True):
                try:
                    all_records_df = pd.DataFrame(registros_recibos_ws.get_all_records())
                    if not all_records_df.empty:
                        # Filtrar por fecha y serie
                        filtered_df = all_records_df[
                            (all_records_df['Fecha'] == search_date_str) & 
                            (all_records_df['Serie'] == search_serie)
                        ]
                        
                        if not filtered_df.empty:
                            # Agrupar para mostrar al usuario
                            st.session_state.found_groups = filtered_df.groupby('Consecutivo Global').agg(
                                Recibos=('Recibo N°', lambda x: f"{x.min()}-{x.max()}"),
                                Total=('Valor Efectivo', lambda x: pd.to_numeric(x).sum())
                            ).reset_index()
                            st.session_state.full_search_results = all_records_df # Guardar resultados completos
                        else:
                            st.session_state.found_groups = []
                            st.warning("No se encontraron grupos para esa fecha y serie.")
                    else:
                        st.warning("No hay registros en la hoja 'RegistrosRecibos' para buscar.")
                except Exception as e:
                    st.error(f"Error al buscar registros: {e}")

            if 'found_groups' in st.session_state and not st.session_state.found_groups.empty:
                st.markdown("---")
                st.subheader("Grupos Encontrados")
                
                # Crear opciones para el selectbox
                group_options = {
                    f"Global {row['Consecutivo Global']} (Recibos {row['Recibos']}, Total ${row['Total']:,.2f})": row['Consecutivo Global']
                    for index, row in st.session_state.found_groups.iterrows()
                }
                
                selected_group_display = st.selectbox(
                    "Selecciona el grupo que deseas cargar:",
                    options=list(group_options.keys())
                )

                if st.button("Cargar Grupo Seleccionado", use_container_width=True, type="primary"):
                    global_consecutive_to_load = group_options[selected_group_display]
                    
                    # Filtrar los datos completos del grupo seleccionado
                    group_data_df = st.session_state.full_search_results[
                        st.session_state.full_search_results['Consecutivo Global'].astype(str) == str(global_consecutive_to_load)
                    ].copy()

                    # Preparar el DataFrame para el editor
                    group_data_df.rename(columns={
                        'Recibo N°': 'Recibo N°', 'Valor Efectivo': 'Valor Efectivo'
                    }, inplace=True)
                    
                    # Asegurar tipos de datos correctos
                    group_data_df['Valor Efectivo'] = pd.to_numeric(group_data_df['Valor Efectivo'])
                    group_data_df['Agrupación'] = pd.to_numeric(group_data_df['Agrupación'])
                    
                    df_to_edit = group_data_df[['Fecha', 'Recibo N°', 'Cliente', 'Valor Efectivo', 'Agrupación', 'Destino']]
                    
                    st.session_state.df_procesado = df_to_edit
                    st.session_state.editing_info = {
                        'global_consecutive': global_consecutive_to_load,
                        'series_consecutive': group_data_df['Consecutivo Serie'].iloc[0],
                        'serie': group_data_df['Serie'].iloc[0]
                    }
                    st.success(f"Grupo con Consecutivo Global {global_consecutive_to_load} cargado. Ahora puedes editarlo en la tabla de abajo.")
                    st.rerun()

    # --- MODO NUEVO: CARGAR ARCHIVO EXCEL ---
    elif st.session_state.mode == 'new':
        st.header("🆕 Procesar Nuevo Grupo de Recibos")
        
        st.subheader("A. Selecciona la Serie del Documento")
        serie_seleccionada = st.selectbox(
            "Elige la serie que corresponde a los recibos de este archivo:",
            options=series_disponibles, index=0, help="Esta serie se usará en el archivo TXT final."
        )
        st.divider()

        st.subheader("B. Carga el Archivo de Excel")
        uploaded_file = st.file_uploader(
            "📂 Sube tu archivo de Excel de recibos de caja",
            type=['xlsx', 'xls']
        )

        if uploaded_file is not None:
            if 'df_procesado' not in st.session_state or st.session_state.get('uploaded_file_name') != uploaded_file.name:
                try:
                    df = pd.read_excel(uploaded_file, header=0)
                    required_columns = ['FECHA_RECIBO', 'NUMRECIBO', 'NOMBRECLIENTE', 'IMPORTE']
                    missing_columns = [col for col in required_columns if col not in df.columns]
                    if missing_columns:
                        st.error(f"Error: Faltan las siguientes columnas en el Excel: {', '.join(missing_columns)}")
                        st.stop()

                    if 'NUMRECIBO' in df.columns:
                        df['NUMRECIBO'] = df['NUMRECIBO'].ffill()
                    df_cleaned = df.dropna(subset=['FECHA_RECIBO', 'NOMBRECLIENTE']).copy()
                    
                    def clean_and_convert(value):
                        if isinstance(value, (int, float)): return float(value)
                        try:
                            str_value = str(value).replace('$', '').strip().replace('.', '').replace(',', '.')
                            return float(str_value)
                        except (ValueError, TypeError): return None
                    
                    df_cleaned['IMPORTE_LIMPIO'] = df_cleaned['IMPORTE'].apply(clean_and_convert)
                    df_cleaned.dropna(subset=['IMPORTE_LIMPIO'], inplace=True)

                    df_resumen = df_cleaned.groupby('NUMRECIBO').agg({
                        'FECHA_RECIBO': 'first', 'NOMBRECLIENTE': 'first', 'IMPORTE_LIMPIO': 'sum'
                    }).reset_index()

                    df_resumen.rename(columns={
                        'FECHA_RECIBO': 'Fecha', 'NUMRECIBO': 'Recibo N°',
                        'NOMBRECLIENTE': 'Cliente', 'IMPORTE_LIMPIO': 'Valor Efectivo'
                    }, inplace=True)
                    
                    if pd.api.types.is_datetime64_any_dtype(df_resumen['Fecha']):
                        df_resumen['Fecha'] = pd.to_datetime(df_resumen['Fecha']).dt.strftime('%d/%m/%Y')
                    
                    df_resumen['Agrupación'] = 1
                    df_resumen['Destino'] = "-- Seleccionar --"
                    
                    df_resumen = df_resumen[['Fecha', 'Recibo N°', 'Cliente', 'Valor Efectivo', 'Agrupación', 'Destino']]
                    
                    st.session_state.df_procesado = df_resumen.copy()
                    st.session_state.uploaded_file_name = uploaded_file.name
                    st.session_state.editing_info = {'serie': serie_seleccionada} # Guardar la serie para el nuevo registro
                    st.success("¡Archivo procesado! Ahora puedes asignar destinos y grupos en la tabla de abajo.")

                except Exception as e:
                    st.error(f"Ocurrió un error al leer o procesar el archivo de Excel: {e}")

    # --- TABLA DE EDICIÓN Y PROCESAMIENTO (COMÚN PARA AMBOS MODOS) ---
    if 'df_procesado' in st.session_state and not st.session_state.df_procesado.empty:
        st.divider()
        st.header("2. Asigna Agrupación y Destinos")
        
        total_recibos = st.session_state.df_procesado['Valor Efectivo'].sum()
        st.metric(label="💰 Total Efectivo del Grupo", value=f"${total_recibos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

        with st.expander("Herramientas de asignación masiva"):
            col1, col2 = st.columns(2)
            with col1:
                destino_masivo = st.selectbox("Asignar destino a todos:", options=opciones_destino, key="sel_destino_masivo")
                if st.button("Aplicar Destino", use_container_width=True):
                    if destino_masivo != "-- Seleccionar --":
                        st.session_state.df_procesado['Destino'] = destino_masivo
                        st.rerun()
            with col2:
                agrupacion_masiva = st.selectbox("Asignar grupo a todos:", options=opciones_agrupacion, key="sel_agrupacion_masiva")
                if st.button("Aplicar Grupo", use_container_width=True):
                    st.session_state.df_procesado['Agrupación'] = agrupacion_masiva
                    st.rerun()

        st.info("Puedes editar cada fila individualmente en la tabla a continuación.")
        edited_df = st.data_editor(
            st.session_state.df_procesado,
            column_config={
                "Agrupación": st.column_config.SelectboxColumn("Agrupación", help="Grupo 1 es individual. Grupos >1 se sumarán.", options=opciones_agrupacion, required=True),
                "Destino": st.column_config.SelectboxColumn("Destino del Efectivo", help="Selecciona el banco o tercero.", options=opciones_destino, required=True),
                "Valor Efectivo": st.column_config.NumberColumn("Valor Efectivo", format="$ %.2f", disabled=True),
                "Fecha": st.column_config.TextColumn("Fecha", disabled=True),
                "Cliente": st.column_config.TextColumn("Cliente", disabled=True),
                "Recibo N°": st.column_config.TextColumn("Recibo N°", disabled=True),
            },
            hide_index=True, use_container_width=True, key="editor_recibos"
        )
        
        st.divider()
        st.header("3. Finalizar Proceso")
        
        if st.button("💾 Procesar y Guardar Cambios", type="primary", use_container_width=True):
            if edited_df['Destino'].isnull().any() or any(d == "-- Seleccionar --" for d in edited_df['Destino']):
                st.warning("⚠️ Debes asignar un destino válido para TODOS los recibos antes de procesar.")
            else:
                try:
                    # Determinar si se están creando o editando registros
                    if st.session_state.mode == 'new':
                        st.info("Procesando como un NUEVO grupo...")
                        # Obtener nuevos consecutivos
                        global_consecutive = get_next_global_consecutive(global_consecutivo_ws)
                        serie_seleccionada = st.session_state.editing_info['serie']
                        series_consecutive = get_next_series_consecutive(consecutivos_ws, serie_seleccionada)
                        
                        if global_consecutive is None or series_consecutive is None:
                            st.error("No se pudieron obtener los consecutivos. Revisa la configuración en Google Sheets.")
                            st.stop()
                    
                    elif st.session_state.mode == 'edit':
                        st.info("Procesando como una EDICIÓN de grupo existente...")
                        # Reutilizar consecutivos existentes
                        global_consecutive = st.session_state.editing_info['global_consecutive']
                        series_consecutive = st.session_state.editing_info['series_consecutive']
                        serie_seleccionada = st.session_state.editing_info['serie']
                        
                        # PASO CLAVE: Borrar los registros antiguos antes de guardar los nuevos
                        delete_existing_records(registros_recibos_ws, global_consecutive)

                    # Generar el contenido del archivo TXT
                    txt_content = generate_txt_content(edited_df, account_mappings, series_consecutive, global_consecutive, serie_seleccionada)

                    # Preparar los datos para guardar en Google Sheets
                    registros_data = []
                    for _, row in edited_df.iterrows():
                        registros_data.append([
                            row['Fecha'], row['Recibo N°'], row['Cliente'], row['Valor Efectivo'],
                            row['Destino'], serie_seleccionada, series_consecutive,
                            global_consecutive, row['Agrupación'], datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        ])
                    
                    # Guardar los datos (nuevos o actualizados)
                    registros_recibos_ws.append_rows(registros_data, value_input_option='USER_ENTERED')
                    
                    # Actualizar los contadores solo si es un registro nuevo
                    if st.session_state.mode == 'new':
                        update_series_consecutive(consecutivos_ws, serie_seleccionada, series_consecutive)
                        update_global_consecutive(global_consecutivo_ws, global_consecutive)
                    
                    st.success("✅ ¡Éxito! Los datos han sido guardados en Google Sheets.")

                    # Ofrecer la descarga del archivo TXT
                    st.download_button(
                        label="⬇️ Descargar Archivo TXT para el ERP",
                        data=txt_content.encode('utf-8'),
                        file_name=f"recibos_{serie_seleccionada}_{global_consecutive}_{datetime.now().strftime('%Y%m%d')}.txt",
                        mime="text/plain"
                    )
                    st.info("El archivo TXT ha sido generado y está listo para descargar.")

                    # Limpiar estado para la siguiente operación
                    for key in list(st.session_state.keys()):
                        if key not in ['mode', 'google_credentials']:
                            del st.session_state[key]
                    st.session_state.mode = 'new' # Volver al modo por defecto
                    # st.rerun() # Opcional: recargar la página para un estado completamente limpio

                except Exception as e:
                    st.error(f"Error al guardar los datos o generar el archivo TXT: {e}")
