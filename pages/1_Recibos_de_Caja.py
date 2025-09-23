# -*- coding: utf-8 -*-

# --- IMPORTACIÓN DE LIBRERÍAS NECESARIAS ---
import streamlit as st
import pandas as pd
from io import BytesIO
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from datetime import datetime
from itertools import groupby
from operator import itemgetter
import time

# Importaciones para la generación y estilo del Excel
import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter

# --- CONFIGURACIÓN DE LA PÁGINA DE STREAMLIT ---
st.set_page_config(layout="wide", page_title="Recibos de Caja")

# --- TÍTULOS Y DESCRIPCIÓN DE LA APLICACIÓN ---
st.title("🧾 Procesamiento de Recibos de Caja v5.2 (Corrección de Sintaxis y Columnas)")
st.markdown("""
Esta herramienta ahora permite tres flujos de trabajo:
1.  **Descargar reportes antiguos**: Busca cualquier grupo ya procesado por un rango de fechas y serie para descargar sus archivos.
2.  **Cargar un nuevo archivo de Excel**: Procesa y guarda un nuevo grupo de recibos, generando un reporte detallado.
3.  **Buscar y editar un grupo existente**: Carga un grupo para editarlo y volver a guardarlo.
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
    Usa el DataFrame con el detalle de movimientos.
    """
    txt_lines = []
    cuenta_recibo_caja = "11050501"
    tipo_documento = "12"
    series_numeric = ''.join(filter(str.isdigit, series))

    # --- 1. PROCESAR REGISTROS INDIVIDUALES (AGRUPACIÓN 1) ---
    # Para el TXT, se necesita agrupar por recibo para generar una sola línea por recibo individual
    df_individual = df[df['Agrupación'] == 1].copy()
    if not df_individual.empty:
        individual_grouped = df_individual.groupby('Recibo N°').agg(
            Valor_Total=('Valor Efectivo', 'sum'),
            Fecha=('Fecha', 'first'),
            Cliente=('Cliente', 'first'),
            Destino=('Destino', 'first')
        ).reset_index()

        for _, row in individual_grouped.iterrows():
            fecha = pd.to_datetime(row['Fecha'], dayfirst=True).strftime('%d/%m/%Y')
            num_recibo = str(int(row['Recibo N°']))
            valor = float(row['Valor_Total'])
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
        # Aquí se agrupan los movimientos para generar una sola línea por consignación en el TXT
        grouped = df_agrupado.groupby(['Agrupación', 'Destino']).agg(
            Valor_Total=('Valor Efectivo', 'sum'),
            Fecha_Primera=('Fecha', 'first'),
            Recibos_Incluidos=('Recibo N°', lambda x: ','.join(sorted(list(set(x.astype(str).str.split('.').str[0]))))),
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

# --- FUNCIÓN PARA GENERAR REPORTE EXCEL PROFESIONAL ---
def generate_excel_report(df):
    """
    Genera un archivo Excel profesional y estilizado.
    - Muestra el detalle completo de cada movimiento.
    - Ordena por Agrupación y luego por Recibo N°.
    - Añade subtotales para cada recibo individual (Agrupación = 1).
    - Añade subtotales para cada grupo de consignación (Agrupación > 1).
    - Incluye la nueva columna 'Serie-Número'.
    """
    output = BytesIO()
    
    # Asegurar que las columnas numéricas sean del tipo correcto para ordenar
    df['Recibo N°'] = pd.to_numeric(df['Recibo N°'], errors='coerce')
    df['Agrupación'] = pd.to_numeric(df['Agrupación'], errors='coerce')
    df.dropna(subset=['Recibo N°', 'Agrupación'], inplace=True)
    
    # Reordenar las columnas para una presentación lógica en Excel, incluyendo la nueva columna
    preferred_order = ['Fecha', 'Recibo N°', 'Serie-Número', 'Cliente', 'Valor Efectivo', 'Agrupación', 'Destino']
    # Incluir cualquier otra columna que pueda venir del excel original
    excel_columns = preferred_order + [col for col in df.columns if col not in preferred_order]
    df = df[excel_columns]

    # 1. Separar data en individuales y grupos de consignación
    df_individual = df[df['Agrupación'] == 1].copy()
    df_grouped = df[df['Agrupación'] > 1].copy()

    # Ordenar cada sub-dataframe
    df_individual.sort_values(by=['Recibo N°'], inplace=True)
    df_grouped.sort_values(by=['Agrupación', 'Recibo N°'], inplace=True)

    report_data = []

    # 2. Procesar recibos individuales con subtotal por número de recibo
    if not df_individual.empty:
        for recibo_num, group in df_individual.groupby('Recibo N°', sort=False):
            # Agregar todas las filas (movimientos) de este recibo
            for _, row in group.iterrows():
                report_data.append(row[excel_columns].tolist())
            
            # Agregar la fila de subtotal para este recibo (lógica dinámica)
            subtotal = group['Valor Efectivo'].sum()
            subtotal_row = [''] * len(excel_columns)
            cliente_col_idx = excel_columns.index('Cliente')
            valor_col_idx = excel_columns.index('Valor Efectivo')
            subtotal_row[cliente_col_idx] = f'Subtotal Recibo N° {int(recibo_num)}'
            subtotal_row[valor_col_idx] = subtotal
            report_data.append(subtotal_row)

    # 3. Procesar consignaciones agrupadas con subtotal por grupo
    if not df_grouped.empty:
        for agrupacion_id, group in df_grouped.groupby('Agrupación', sort=False):
            # Agregar todas las filas de este grupo de consignación
            for _, row in group.iterrows():
                report_data.append(row[excel_columns].tolist())
            
            # Agregar la fila de subtotal para este grupo (lógica dinámica)
            subtotal = group['Valor Efectivo'].sum()
            subtotal_row = [''] * len(excel_columns)
            cliente_col_idx = excel_columns.index('Cliente')
            valor_col_idx = excel_columns.index('Valor Efectivo')
            subtotal_row[cliente_col_idx] = f'Subtotal Consignación Grupo {int(agrupacion_id)}'
            subtotal_row[valor_col_idx] = subtotal
            report_data.append(subtotal_row)
    
    # Crear el DataFrame final para el reporte
    if not report_data:
        report_df = pd.DataFrame(columns=excel_columns)
    else:
        report_df = pd.DataFrame(report_data, columns=excel_columns)
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        report_df.to_excel(writer, index=False, sheet_name='Recibos de Caja')
        workbook = writer.book
        worksheet = writer.sheets['Recibos de Caja']

        # --- Definición de Estilos ---
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        subtotal_font = Font(bold=True)
        subtotal_fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
        total_font = Font(bold=True, size=12)
        total_fill = PatternFill(start_color="C0C0C0", end_color="C0C0C0", fill_type="solid")
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        currency_format = '$ #,##0.00'

        # Aplicar estilo al encabezado
        for cell in worksheet["1:1"]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')

        # Aplicar estilo a las filas de datos y subtotales
        for row_idx, row in enumerate(worksheet.iter_rows(min_row=2, max_row=worksheet.max_row), start=2):
            # Identificar si es una fila de subtotal por el texto en la columna Cliente
            cliente_col_idx_check = excel_columns.index('Cliente')
            is_subtotal_row = str(row[cliente_col_idx_check].value).startswith('Subtotal')
            
            for cell in row:
                cell.border = thin_border
                if is_subtotal_row:
                    cell.font = subtotal_font
                    cell.fill = subtotal_fill
            
            # Formatear la columna de Valor Efectivo como moneda
            valor_cell_index = excel_columns.index('Valor Efectivo') + 1
            valor_cell_letter = get_column_letter(valor_cell_index)
            valor_cell = worksheet[f'{valor_cell_letter}{row_idx}']
            if isinstance(valor_cell.value, (int, float)):
                valor_cell.number_format = currency_format

            # Alinear columnas específicas
            for col_name, align in [('Recibo N°', 'center'), ('Valor Efectivo', 'right'), ('Agrupación', 'center'), ('Serie-Número', 'center')]:
                if col_name in excel_columns:
                    col_idx = excel_columns.index(col_name) + 1
                    col_letter = get_column_letter(col_idx)
                    worksheet[f'{col_letter}{row_idx}'].alignment = Alignment(horizontal=align)
            
        # --- Añadir Fila de Total General ---
        grand_total = df['Valor Efectivo'].sum()
        total_row_idx = worksheet.max_row + 1
        
        # Colocar el total general en las columnas correctas
        cliente_col_idx = excel_columns.index('Cliente') + 1
        valor_col_idx = excel_columns.index('Valor Efectivo') + 1
        
        worksheet.cell(row=total_row_idx, column=cliente_col_idx, value='TOTAL GENERAL')
        worksheet.cell(row=total_row_idx, column=valor_col_idx, value=grand_total)
        
        total_range = f'A{total_row_idx}:{get_column_letter(worksheet.max_column)}{total_row_idx}'
        for row in worksheet[total_range]:
            for cell in row:
                cell.font = total_font
                cell.fill = total_fill
                cell.border = thin_border
        
        total_valor_cell = worksheet.cell(row=total_row_idx, column=valor_col_idx)
        total_valor_cell.number_format = currency_format
        total_valor_cell.alignment = Alignment(horizontal='right')

        # --- Ajustar el ancho de las columnas ---
        for col_idx, column in enumerate(worksheet.columns, 1):
            max_length = 0
            column_letter = get_column_letter(col_idx)
            
            # Considerar el largo del encabezado
            if worksheet[f'{column_letter}1'].value:
                max_length = len(str(worksheet[f'{column_letter}1'].value))

            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            # Añadir un poco de espacio extra
            adjusted_width = (max_length + 2)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    return output.getvalue()


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

# --- FUNCIÓN PARA BORRAR REGISTROS ---
def delete_existing_records(ws, global_consecutive_to_delete):
    """
    Encuentra y borra todas las filas que coincidan con un consecutivo global
    utilizando una solicitud por lotes (batch) para evitar errores de cuota.
    """
    try:
        st.info(f"Buscando registros antiguos con el consecutivo global {global_consecutive_to_delete} para eliminarlos...")
        all_records = ws.get_all_records()
        if not all_records:
            st.warning("No hay registros en la hoja para buscar. Se procederá a guardar como si fueran nuevos.")
            return

        df_records = pd.DataFrame(all_records)
        
        if 'Consecutivo Global' not in df_records.columns:
            st.error("La hoja 'RegistrosRecibos' no tiene la columna 'Consecutivo Global'. No se puede actualizar.")
            st.stop()
            return

        df_records['Consecutivo Global'] = df_records['Consecutivo Global'].astype(str)
        global_consecutive_to_delete = str(global_consecutive_to_delete)

        rows_to_delete_indices = df_records[df_records['Consecutivo Global'] == global_consecutive_to_delete].index.tolist()
        
        # El índice de gspread es 1-based y la cabecera es la fila 1, por lo que los datos empiezan en la fila 2.
        gspread_rows_to_delete = sorted([i + 2 for i in rows_to_delete_indices])

        if not gspread_rows_to_delete:
            st.warning("No se encontraron registros antiguos que coincidieran. Se procederá a guardar como si fueran nuevos.")
            return

        # Agrupar índices consecutivos para eliminar en rangos
        requests = []
        for k, g in groupby(enumerate(gspread_rows_to_delete), lambda i_x: i_x[0] - i_x[1]):
            group = list(map(itemgetter(1), g))
            start_index = group[0] - 1 # El startIndex es 0-based
            end_index = group[-1]
            
            requests.append({
                "deleteDimension": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "ROWS",
                        "startIndex": start_index,
                        "endIndex": end_index
                    }
                }
            })
        
        if requests:
            # Es más seguro eliminar desde el final hacia el principio para no alterar los índices de las siguientes operaciones.
            requests.reverse()
            ws.spreadsheet.batch_update({"requests": requests})
            st.success(f"Se eliminaron {len(gspread_rows_to_delete)} registros antiguos en una sola operación por lotes.")

    except Exception as e:
        st.error(f"Error crítico al intentar borrar registros antiguos: {e}")
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
    
    if 'mode' not in st.session_state:
        st.session_state.mode = 'new'
        st.session_state.editing_info = {}
        st.session_state.found_groups = []

    # --- SECCIÓN DE DESCARGA DE REPORTES ANTERIORES ---
    st.divider()
    with st.expander("📥 Descargar Reportes Anteriores", expanded=False):
        st.info("Busca un grupo por un rango de fechas y serie para generar y descargar sus archivos al instante.")
        
        dl_col1, dl_col2, dl_col3 = st.columns(3)
        with dl_col1:
            start_date = st.date_input("Fecha de inicio:", datetime.now(), key="dl_start_date")
        with dl_col2:
            end_date = st.date_input("Fecha de fin:", datetime.now(), key="dl_end_date")
        with dl_col3:
            download_serie = st.selectbox("Serie a buscar:", options=series_disponibles, key="dl_serie")
        
        if st.button("Buscar Grupos para Descargar", use_container_width=True):
            if end_date < start_date:
                st.error("Error: La fecha de fin no puede ser anterior a la fecha de inicio.")
            else:
                try:
                    with st.spinner("Buscando registros en Google Sheets..."):
                        all_values = registros_recibos_ws.get_all_values()
                        if len(all_values) > 1:
                            headers = all_values[0]
                            data = all_values[1:]
                            all_records_df = pd.DataFrame(data, columns=headers)
                            
                            # Eliminar columnas vacías si existen
                            if '' in all_records_df.columns:
                                all_records_df = all_records_df.drop(columns=[''])
                            
                            all_records_df['Fecha_dt'] = pd.to_datetime(all_records_df['Fecha'], format='%d/%m/%Y', errors='coerce')
                            all_records_df.dropna(subset=['Fecha_dt'], inplace=True)

                            start_date_dt = pd.to_datetime(start_date)
                            end_date_dt = pd.to_datetime(end_date)
                            
                            filtered_df = all_records_df[
                                (all_records_df['Fecha_dt'] >= start_date_dt) &
                                (all_records_df['Fecha_dt'] <= end_date_dt) &
                                (all_records_df['Serie'] == download_serie)
                            ].copy()

                            if not filtered_df.empty:
                                filtered_df['Valor Efectivo'] = pd.to_numeric(filtered_df['Valor Efectivo'], errors='coerce')
                                filtered_df['Recibo N°'] = pd.to_numeric(filtered_df['Recibo N°'], errors='coerce')
                                filtered_df.dropna(subset=['Valor Efectivo', 'Recibo N°'], inplace=True)
                                
                                st.session_state.downloadable_groups_df = filtered_df.groupby('Consecutivo Global').agg(
                                    Recibos=('Recibo N°', lambda x: f"{int(x.min())}-{int(x.max())}"),
                                    Total=('Valor Efectivo', 'sum')
                                ).reset_index()
                                
                                st.session_state.full_download_data = filtered_df
                            else:
                                st.warning("No se encontraron grupos para el rango de fechas y serie seleccionados.")
                                st.session_state.downloadable_groups_df = pd.DataFrame()
                        else:
                            st.warning("No hay registros guardados para buscar.")
                except Exception as e:
                    st.error(f"Ocurrió un error al buscar los registros: {e}")

    if 'downloadable_groups_df' in st.session_state and not st.session_state.downloadable_groups_df.empty:
        group_options = {
            f"Global {row['Consecutivo Global']} (Recibos {row['Recibos']}, Total ${row['Total']:,.2f})": row['Consecutivo Global']
            for _, row in st.session_state.downloadable_groups_df.iterrows()
        }
        
        selected_group_display = st.selectbox(
            "Selecciona un grupo para preparar su descarga:",
            options=["-- Elige un grupo --"] + list(group_options.keys())
        )

        if selected_group_display != "-- Elige un grupo --":
            global_consecutive_to_download = group_options[selected_group_display]
            
            df_for_download = st.session_state.full_download_data[
                st.session_state.full_download_data['Consecutivo Global'].astype(str) == str(global_consecutive_to_download)
            ].copy()

            # Asegurar tipos de datos correctos para las funciones de generación
            df_for_download['Valor Efectivo'] = pd.to_numeric(df_for_download['Valor Efectivo'])
            df_for_download['Agrupación'] = pd.to_numeric(df_for_download['Agrupación'])
            df_for_download['Recibo N°'] = pd.to_numeric(df_for_download['Recibo N°'])
            
            series_consecutive_dl = df_for_download['Consecutivo Serie'].iloc[0]
            serie_dl = df_for_download['Serie'].iloc[0]

            # --- NUEVO: Crear la columna unificada si los datos existen en los registros antiguos
            if 'Serie' in df_for_download.columns and 'Número' in df_for_download.columns:
                 df_for_download['Serie-Número'] = df_for_download['Serie'].astype(str) + "-" + df_for_download['Número'].astype(str)
            else:
                 df_for_download['Serie-Número'] = "N/A" # Placeholder si los datos antiguos no tienen esta info

            txt_content_dl = generate_txt_content(df_for_download, account_mappings, series_consecutive_dl, global_consecutive_to_download, serie_dl)
            excel_file_dl = generate_excel_report(df_for_download)

            st.success(f"Archivos para el grupo Global {global_consecutive_to_download} listos para descargar.")
            
            dl_btn_col1, dl_btn_col2 = st.columns(2)
            with dl_btn_col1:
                st.download_button(
                    label="⬇️ Descargar Archivo TXT para el ERP",
                    data=txt_content_dl.encode('utf-8'),
                    file_name=f"recibos_{serie_dl}_{global_consecutive_to_download}_{datetime.now().strftime('%Y%m%d')}.txt",
                    mime="text/plain", use_container_width=True, key=f"dl_txt_{global_consecutive_to_download}"
                )
            with dl_btn_col2:
                st.download_button(
                    label="📄 Descargar Reporte en Excel",
                    data=excel_file_dl,
                    file_name=f"Reporte_Recibos_{serie_dl}_{global_consecutive_to_download}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key=f"dl_xls_{global_consecutive_to_download}"
                )
    st.divider()

    # --- SECCIÓN PRINCIPAL DE PROCESAMIENTO ---
    st.header("Flujo de Trabajo: Procesar o Editar")
    st.subheader("1. Elige una opción")

    col_mode_1, col_mode_2, col_mode_3 = st.columns([1,1,2])
    with col_mode_1:
        if st.button("🆕 Procesar Nuevo Archivo", use_container_width=True, type="primary" if st.session_state.mode == 'new' else "secondary"):
            # Limpiar estado de sesión para un nuevo ciclo
            keys_to_keep = ['mode', 'google_credentials']
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep:
                    del st.session_state[key]
            st.session_state.mode = 'new'
            st.rerun()

    with col_mode_2:
        if st.button("✏️ Editar Grupo Existente", use_container_width=True, type="primary" if st.session_state.mode == 'edit' else "secondary"):
            keys_to_keep = ['mode', 'google_credentials']
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep:
                    del st.session_state[key]
            st.session_state.mode = 'edit'
            st.rerun()
            
    # --- MODO EDICIÓN: BUSCAR Y CARGAR GRUPO ---
    if st.session_state.mode == 'edit':
        st.subheader("2. Buscar y Cargar Grupo para Edición")
        st.info("Busca un grupo de recibos que ya hayas procesado para cargarlo y modificarlo.")
        
        with st.container(border=True):
            search_col1, search_col2 = st.columns(2)
            with search_col1:
                search_date = st.date_input("Fecha de los recibos:", datetime.now())
                search_date_str = search_date.strftime('%d/%m/%Y')
            with search_col2:
                search_serie = st.selectbox("Serie de los recibos:", options=series_disponibles, key="search_serie")
            
            if st.button("Buscar Grupos para Editar", use_container_width=True):
                try:
                    with st.spinner("Buscando, por favor espera..."):
                        all_values = registros_recibos_ws.get_all_values()
                        
                        if len(all_values) < 2:
                            all_records_df = pd.DataFrame()
                        else:
                            headers = all_values[0]
                            data = all_values[1:]
                            all_records_df = pd.DataFrame(data, columns=headers)
                            
                            if '' in all_records_df.columns:
                                all_records_df = all_records_df.drop(columns=[''])
                            
                            required_search_cols = ['Fecha', 'Serie', 'Consecutivo Global', 'Recibo N°', 'Valor Efectivo']
                            for col in required_search_cols:
                                if col not in all_records_df.columns:
                                    st.error(f"Error crítico: La columna esperada '{col}' no se encontró en la hoja 'RegistrosRecibos'. Por favor, verifica la cabecera en Google Sheets.")
                                    st.stop()

                        if not all_records_df.empty:
                            filtered_df = all_records_df[
                                (all_records_df['Fecha'] == search_date_str) & 
                                (all_records_df['Serie'] == search_serie)
                            ]
                            
                            if not filtered_df.empty:
                                st.session_state.found_groups = filtered_df.groupby('Consecutivo Global').agg(
                                    Recibos=('Recibo N°', lambda x: f"{pd.to_numeric(x).min()}-{pd.to_numeric(x).max()}"),
                                    Total=('Valor Efectivo', lambda x: pd.to_numeric(x).sum())
                                ).reset_index()
                                st.session_state.full_search_results = all_records_df
                            else:
                                st.session_state.found_groups = pd.DataFrame()
                                st.warning("No se encontraron grupos para esa fecha y serie.")
                        else:
                            st.warning("No hay registros en la hoja 'RegistrosRecibos' para buscar.")
                except Exception as e:
                    st.error(f"Error al buscar registros: {e}")

            if 'found_groups' in st.session_state and not st.session_state.found_groups.empty:
                st.markdown("---")
                st.subheader("Grupos Encontrados")
                
                group_options = {
                    f"Global {row['Consecutivo Global']} (Recibos {row['Recibos']}, Total ${row['Total']:,.2f})": row['Consecutivo Global']
                    for index, row in st.session_state.found_groups.iterrows()
                }
                
                selected_group_display = st.selectbox(
                    "Selecciona el grupo que deseas cargar para editar:",
                    options=list(group_options.keys())
                )

                if st.button("Cargar Grupo Seleccionado", use_container_width=True, type="primary"):
                    global_consecutive_to_load = group_options[selected_group_display]
                    
                    group_data_df = st.session_state.full_search_results[
                        st.session_state.full_search_results['Consecutivo Global'].astype(str) == str(global_consecutive_to_load)
                    ].copy()

                    # Asegurar tipos de datos correctos
                    group_data_df['Valor Efectivo'] = pd.to_numeric(group_data_df['Valor Efectivo'])
                    group_data_df['Agrupación'] = pd.to_numeric(group_data_df['Agrupación'])
                    
                    # Guardar el detalle completo y crear un resumen para la UI
                    st.session_state.df_full_detail = group_data_df.copy()

                    df_summary_edit = group_data_df.groupby('Recibo N°').agg(
                        Fecha=('Fecha', 'first'),
                        Cliente=('Cliente', 'first'),
                        Valor_Efectivo_Total=('Valor Efectivo', 'sum'),
                        Agrupación=('Agrupación', 'first'),
                        Destino=('Destino', 'first')
                    ).reset_index()

                    df_summary_edit.rename(columns={'Valor_Efectivo_Total': 'Valor Efectivo'}, inplace=True)
                    st.session_state.df_for_display = df_summary_edit[['Fecha', 'Recibo N°', 'Cliente', 'Valor Efectivo', 'Agrupación', 'Destino']]
                    
                    st.session_state.editing_info = {
                        'global_consecutive': global_consecutive_to_load,
                        'series_consecutive': group_data_df['Consecutivo Serie'].iloc[0],
                        'serie': group_data_df['Serie'].iloc[0]
                    }
                    st.success(f"Grupo con Consecutivo Global {global_consecutive_to_load} cargado. Ahora puedes editarlo en la tabla de abajo.")
                    st.rerun()

    # --- MODO NUEVO: CARGAR ARCHIVO EXCEL ---
    elif st.session_state.mode == 'new':
        st.subheader("2. Cargar Nuevo Archivo")
        
        with st.container(border=True):
            st.markdown("##### A. Selecciona la Serie del Documento")
            serie_seleccionada = st.selectbox(
                "Elige la serie que corresponde a los recibos de este archivo:",
                options=series_disponibles, index=0, help="Esta serie se usará en el archivo TXT final."
            )
            
            st.markdown("##### B. Carga el Archivo de Excel")
            uploaded_file = st.file_uploader(
                "📂 Sube tu archivo de Excel de recibos de caja (con el detalle de movimientos)",
                type=['xlsx', 'xls']
            )

        if uploaded_file is not None:
            # Lógica para procesar el archivo solo una vez
            if 'df_for_display' not in st.session_state or st.session_state.get('uploaded_file_name') != uploaded_file.name:
                with st.spinner("Procesando archivo de Excel..."):
                    try:
                        # 1. Cargar el archivo Excel.
                        df = pd.read_excel(uploaded_file, header=0)

                        # 2. <<<--- MODIFICACIÓN CLAVE: Eliminar la última fila (total) antes de cualquier procesamiento.
                        df = df.iloc[:-1]

                        # 3. Estandarizar nombres de columnas para mayor flexibilidad.
                        # Se eliminan acentos, espacios y se convierte a mayúsculas.
                        df.columns = df.columns.str.strip().str.upper().str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8')
                        
                        # 4. Mapear posibles nombres de columnas a un estándar interno.
                        #    Se separa NUMRECIBO de NUMERO para evitar conflictos.
                        column_mapping = {
                            'NUMRECIBO': ['NUMRECIBO', 'RECIBO', 'NUMERO RECIBO', 'N RECIBO'],
                            'NOMBRECLIENTE': ['NOMBRECLIENTE', 'CLIENTE', 'NOMBRE CLIENTE'],
                            'FECHA_RECIBO': ['FECHA_RECIBO', 'FECHA RECIBO', 'FECHA'],
                            'IMPORTE': ['IMPORTE', 'VALOR', 'TOTAL'],
                            'NUMERO': ['NUMERO'], # Para la columna 'Número' de la factura
                            'SERIE': ['SERIE']   # Para la columna 'Serie' de la factura
                        }
                        
                        found_columns = {}
                        for standard_name, possible_names in column_mapping.items():
                            for name in possible_names:
                                if name in df.columns:
                                    found_columns[name] = standard_name
                                    break
                        
                        df.rename(columns=found_columns, inplace=True)

                        # 5. Verificar que las columnas clave existan después del mapeo.
                        required_columns = ['FECHA_RECIBO', 'NUMRECIBO', 'NOMBRECLIENTE', 'IMPORTE', 'NUMERO', 'SERIE']
                        missing_columns = [col for col in required_columns if col not in df.columns]
                        if missing_columns:
                            st.error(f"Error Crítico: No se pudieron encontrar las siguientes columnas requeridas: {', '.join(missing_columns)}")
                            st.stop()
                        
                        # 6. Eliminar filas que no tengan un importe válido para limpiar el dataset.
                        df_cleaned = df.dropna(subset=['IMPORTE']).copy()

                        # 7. Rellenar datos en caso de que el reporte use celdas combinadas.
                        for col in ['NUMRECIBO', 'FECHA_RECIBO', 'NOMBRECLIENTE']:
                            df_cleaned[col] = df_cleaned[col].ffill()

                        # 8. Limpiar y convertir la columna de importe a formato numérico.
                        def clean_and_convert(value):
                            if isinstance(value, (int, float)): return float(value)
                            try:
                                str_value = str(value).replace('$', '').strip().replace('.', '').replace(',', '.')
                                return float(str_value)
                            except (ValueError, TypeError): return None
                        
                        df_cleaned['IMPORTE_LIMPIO'] = df_cleaned['IMPORTE'].apply(clean_and_convert)
                        df_cleaned.dropna(subset=['IMPORTE_LIMPIO'], inplace=True)

                        if df_cleaned.empty:
                            st.warning("Advertencia: No se encontraron datos válidos en el archivo.")
                            st.stop()

                        # 9. Renombrar columnas para uso interno y formatear fecha.
                        df_full_detail = df_cleaned.rename(columns={
                            'FECHA_RECIBO': 'Fecha', 'NUMRECIBO': 'Recibo N°',
                            'NOMBRECLIENTE': 'Cliente', 'IMPORTE_LIMPIO': 'Valor Efectivo'
                        })
                        
                        if pd.api.types.is_datetime64_any_dtype(df_full_detail['Fecha']):
                            df_full_detail['Fecha'] = pd.to_datetime(df_full_detail['Fecha']).dt.strftime('%d/%m/%Y')
                        
                        st.session_state.df_full_detail = df_full_detail.copy()

                        # 10. Agrupar por recibo para la vista de edición en la UI.
                        df_summary = df_full_detail.groupby('Recibo N°').agg(
                            Fecha=('Fecha', 'first'),
                            Cliente=('Cliente', 'first'),
                            Valor_Efectivo_Total=('Valor Efectivo', 'sum')
                        ).reset_index()
                        df_summary.rename(columns={'Valor_Efectivo_Total': 'Valor Efectivo'}, inplace=True)
                        
                        df_summary['Agrupación'] = 1
                        df_summary['Destino'] = "-- Seleccionar --"
                        
                        st.session_state.df_for_display = df_summary[['Fecha', 'Recibo N°', 'Cliente', 'Valor Efectivo', 'Agrupación', 'Destino']]
                        st.session_state.uploaded_file_name = uploaded_file.name
                        st.session_state.editing_info = {'serie': serie_seleccionada}
                        st.success("¡Archivo procesado! Ahora puedes asignar destinos y grupos.")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Ocurrió un error al leer o procesar el archivo de Excel: {e}")
                        if 'df_for_display' in st.session_state:
                            del st.session_state.df_for_display
                        if 'uploaded_file_name' in st.session_state:
                            del st.session_state.uploaded_file_name


    # --- TABLA DE EDICIÓN Y PROCESAMIENTO (COMÚN PARA AMBOS MODOS) ---
    if 'df_for_display' in st.session_state and not st.session_state.df_for_display.empty:
        st.divider()
        st.header("3. Asigna Agrupación y Destinos")
        
        # El total se calcula del dataframe de detalle para asegurar precisión
        total_recibos = st.session_state.df_full_detail['Valor Efectivo'].sum()
        st.metric(label="💰 Total Efectivo del Grupo", value=f"${total_recibos:,.2f}")

        with st.expander("Herramientas de asignación masiva"):
            col1, col2 = st.columns(2)
            with col1:
                destino_masivo = st.selectbox("Asignar destino a todos:", options=opciones_destino, key="sel_destino_masivo")
                if st.button("Aplicar Destino", use_container_width=True):
                    if destino_masivo != "-- Seleccionar --":
                        st.session_state.df_for_display['Destino'] = destino_masivo
                        st.rerun()
            with col2:
                agrupacion_masiva = st.selectbox("Asignar grupo a todos:", options=opciones_agrupacion, key="sel_agrupacion_masiva")
                if st.button("Aplicar Grupo", use_container_width=True):
                    st.session_state.df_for_display['Agrupación'] = agrupacion_masiva
                    st.rerun()

        st.info("Edita la agrupación y el destino para cada recibo. El detalle completo se usará para el reporte final.")
        
        edited_summary_df = st.data_editor(
            st.session_state.df_for_display,
            column_config={
                "Agrupación": st.column_config.SelectboxColumn("Agrupación", help="Grupo 1 es individual. Grupos >1 se sumarán.", options=opciones_agrupacion, required=True),
                "Destino": st.column_config.SelectboxColumn("Destino del Efectivo", help="Selecciona el banco o tercero.", options=opciones_destino, required=True),
                "Valor Efectivo": st.column_config.NumberColumn("Valor Total Recibo", format="$ %.2f", disabled=True),
                "Fecha": st.column_config.TextColumn("Fecha", disabled=True),
                "Cliente": st.column_config.TextColumn("Cliente", disabled=True),
                "Recibo N°": st.column_config.NumberColumn("Recibo N°", disabled=True),
            },
            hide_index=True, use_container_width=True, key="editor_recibos",
            column_order=['Fecha', 'Recibo N°', 'Cliente', 'Valor Efectivo', 'Agrupación', 'Destino']
        )
        
        st.divider()
        st.header("4. Finalizar Proceso")
        
        if st.button("💾 Procesar y Guardar Cambios", type="primary", use_container_width=True):
            if edited_summary_df['Destino'].isnull().any() or any(d == "-- Seleccionar --" for d in edited_summary_df['Destino']):
                st.warning("⚠️ Debes asignar un destino válido para TODOS los recibos antes de procesar.")
            else:
                with st.spinner("Guardando datos y generando archivos..."):
                    try:
                        if st.session_state.mode == 'new':
                            st.info("Procesando como un NUEVO grupo...")
                            global_consecutive = get_next_global_consecutive(global_consecutivo_ws)
                            serie_seleccionada = st.session_state.editing_info['serie']
                            series_consecutive = get_next_series_consecutive(consecutivos_ws, serie_seleccionada)
                            
                            if global_consecutive is None or series_consecutive is None:
                                st.error("No se pudieron obtener los consecutivos. Revisa la configuración en Google Sheets.")
                                st.stop()
                        
                        elif st.session_state.mode == 'edit':
                            st.info("Procesando como una EDICIÓN de grupo existente...")
                            global_consecutive = st.session_state.editing_info['global_consecutive']
                            series_consecutive = st.session_state.editing_info['series_consecutive']
                            serie_seleccionada = st.session_state.editing_info['serie']
                            
                            delete_existing_records(registros_recibos_ws, global_consecutive)

                        # --- Combinar decisiones de la UI con los datos de detalle ---
                        df_full_detail = st.session_state.df_full_detail.copy()
                        
                        # Eliminar columnas viejas de Agrupación/Destino si existen en el df de detalle para evitar conflictos
                        if 'Agrupación' in df_full_detail.columns:
                            df_full_detail = df_full_detail.drop(columns=['Agrupación'])
                        if 'Destino' in df_full_detail.columns:
                            df_full_detail = df_full_detail.drop(columns=['Destino'])
                        
                        final_detailed_df = pd.merge(
                            df_full_detail,
                            edited_summary_df[['Recibo N°', 'Agrupación', 'Destino']],
                            on='Recibo N°',
                            how='left'
                        )

                        # <<<--- NUEVO: Crear la columna unificada 'Serie-Número' para los reportes
                        # Se asegura de que ambas columnas sean string antes de unirlas.
                        final_detailed_df['Serie-Número'] = final_detailed_df['SERIE'].astype(str) + "-" + final_detailed_df['NUMERO'].astype(str)

                        # Usar el DataFrame detallado y actualizado para todas las operaciones finales
                        txt_content = generate_txt_content(final_detailed_df, account_mappings, series_consecutive, global_consecutive, serie_seleccionada)
                        excel_file = generate_excel_report(final_detailed_df)

                        # Preparar datos para guardar en Google Sheets
                        registros_data_df = final_detailed_df.copy()
                        registros_data_df['Serie'] = serie_seleccionada
                        registros_data_df['Consecutivo Serie'] = series_consecutive
                        registros_data_df['Consecutivo Global'] = global_consecutive
                        registros_data_df['Timestamp'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                        # Alinear con las cabeceras de Google Sheets
                        gsheet_headers = registros_recibos_ws.row_values(1)
                        registros_to_append = pd.DataFrame(columns=gsheet_headers)

                        for col in gsheet_headers:
                            if col in registros_data_df.columns:
                                registros_to_append[col] = registros_data_df[col]
                            else:
                                registros_to_append[col] = ''
                        
                        # Reordenar y convertir a lista de listas
                        registros_to_append = registros_to_append[gsheet_headers]
                        registros_data = registros_to_append.fillna('').values.tolist()
                        
                        registros_recibos_ws.append_rows(registros_data, value_input_option='USER_ENTERED')
                        
                        # Actualizar consecutivos solo si es un nuevo registro
                        if st.session_state.mode == 'new':
                            update_series_consecutive(consecutivos_ws, serie_seleccionada, series_consecutive)
                            update_global_consecutive(global_consecutivo_ws, global_consecutive)
                        
                        st.success("✅ ¡Éxito! Los datos han sido guardados en Google Sheets.")

                        st.subheader("5. Descargar Archivos")
                        dl_col1, dl_col2 = st.columns(2)
                        with dl_col1:
                            st.download_button(
                                label="⬇️ Descargar Archivo TXT para el ERP",
                                data=txt_content.encode('utf-8'),
                                file_name=f"recibos_{serie_seleccionada}_{global_consecutive}_{datetime.now().strftime('%Y%m%d')}.txt",
                                mime="text/plain", use_container_width=True
                            )
                        with dl_col2:
                            st.download_button(
                                label="📄 Descargar Reporte Detallado en Excel",
                                data=excel_file,
                                file_name=f"Reporte_Recibos_{serie_seleccionada}_{global_consecutive}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True
                            )

                        # Limpiar el estado de la sesión para el próximo uso
                        keys_to_clear = [k for k in st.session_state.keys() if k not in ['mode', 'google_credentials']]
                        for key in keys_to_clear:
                            del st.session_state[key]
                        
                        st.info("El proceso ha finalizado. La página se recargará para iniciar un nuevo ciclo.")
                        time.sleep(5) # Dar tiempo al usuario para ver el mensaje
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error al guardar los datos o generar los archivos: {e}")
