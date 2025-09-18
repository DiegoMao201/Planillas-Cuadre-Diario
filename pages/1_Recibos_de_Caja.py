import streamlit as st
import pandas as pd
from io import BytesIO
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import json
from datetime import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Cash Receipts")
st.title("🧾 Cash Receipts Processing")
st.markdown("""
Upload the daily summary Excel file for cash receipts.
The system will display a summary table where you can assign the destination (bank or third party)
for each collected cash amount.
""")

# --- SECURE CONNECTION TO GOOGLE SHEETS ---
@st.cache_resource(ttl=600)
def connect_to_gsheet():
    """
    Establishes a connection to Google Sheets using credentials from st.secrets.
    Returns the worksheet objects for configuration, receipt records, and the global consecutive counter.
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
        global_consecutivo_ws = sheet.worksheet("GlobalConsecutivo")
        
        return config_ws, registros_recibos_ws, global_consecutivo_ws
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Fatal error: Google Sheets file named '{spreadsheet_name}' not found. Please check the name and access permissions.")
        return None, None, None
    except gspread.exceptions.WorksheetNotFound as e:
        st.error(f"Fatal error: One of the required worksheets was not found in the file. Detail: {e}")
        st.warning("Ensure that the worksheets named 'Configuracion', 'RegistrosRecibos', and 'GlobalConsecutivo' exist.")
        return None, None, None
    except Exception as e:
        st.error(f"Fatal error connecting to Google Sheets: {e}")
        st.warning("Please verify the credentials in Streamlit's secrets and the service account's permissions on the file.")
        return None, None, None

def get_app_config(config_ws):
    """
    Loads bank and third-party configuration from the 'Configuracion' worksheet.
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
        st.error(f"Error loading bank and third-party configuration: {e}")
        return [], [], {}

# --- FILE PROCESSING AND GENERATION LOGIC ---
def generate_txt_from_df(df, account_mappings, global_consecutive):
    """
    Generates the content of the TXT file for the ERP from the DataFrame.
    """
    txt_lines = []
    
    cuenta_recibo_caja = "11050501" # Contra-account for cash receipts
    
    for _, row in df.iterrows():
        try:
            fecha = pd.to_datetime(row['Fecha'], dayfirst=True).strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            fecha = row['Fecha']

        num_recibo = str(row['Recibo N°'])
        valor = float(row['Valor Efectivo'])
        destino = str(row['Destino'])
        
        if destino not in account_mappings:
            st.warning(f"Mapping for destination not found: {destino}. Skipping from TXT.")
            continue
        
        destino_info = account_mappings[destino]
        cuenta_destino = destino_info.get('cuenta')
        nit_tercero = destino_info.get('nit')
        nombre_tercero = destino_info.get('nombre')
        
        linea_debito = "|".join([
            fecha, str(global_consecutive), cuenta_destino, "8",
            f"Recibo de Caja {num_recibo} - {destino}", "Recibos", num_recibo,
            str(valor), "0", "0", nit_tercero, nombre_tercero, "0"
        ])
        txt_lines.append(linea_debito)

        linea_credito = "|".join([
            fecha, str(global_consecutive), cuenta_recibo_caja, "8", 
            f"Recibo de Caja {num_recibo} - Cliente {row['Cliente']}", "Recibos", num_recibo,
            "0", str(valor), "0", "0", "0", "0"
        ])
        txt_lines.append(linea_credito)

    return "\n".join(txt_lines)

def get_next_global_consecutive(global_consecutivo_ws):
    """
    Gets the next global consecutive number for the ERP document.
    """
    try:
        cell = global_consecutivo_ws.find('Ultimo_Consecutivo_Global')
        if cell:
            last_consecutive = int(global_consecutivo_ws.cell(cell.row, cell.col + 1).value)
            return last_consecutive + 1
        else:
            st.error("Label 'Ultimo_Consecutivo_Global' not found. Please check the 'GlobalConsecutivo' worksheet.")
            return None
    except Exception as e:
        st.error(f"Error getting global consecutive number: {e}")
        return None

def update_global_consecutive(global_consecutivo_ws, new_consecutive):
    """
    Updates the last used global consecutive number.
    """
    try:
        cell = global_consecutivo_ws.find('Ultimo_Consecutivo_Global')
        if cell:
            global_consecutivo_ws.update_cell(cell.row, cell.col + 1, new_consecutive)
    except Exception as e:
        st.error(f"Error updating global consecutive number: {e}")

# --- MAIN PAGE LOGIC ---
config_ws, registros_recibos_ws, global_consecutivo_ws = connect_to_gsheet()

if config_ws is None or registros_recibos_ws is None or global_consecutivo_ws is None:
    st.error("The application cannot continue due to a connection error with Google Sheets.")
else:
    bancos, terceros, account_mappings = get_app_config(config_ws)
    opciones_destino = ["-- Select --"] + bancos + terceros

    if not opciones_destino or len(opciones_destino) == 1:
        st.error("Could not load destinations (banks/third parties) from the 'Configuracion' worksheet. The page cannot function.")
    else:
        uploaded_file = st.file_uploader(
            "📂 Upload your cash receipts Excel file",
            type=['xlsx', 'xls']
        )

        if uploaded_file is not None:
            st.success("File uploaded successfully! You can now process it.")
            
            try:
                df = pd.read_excel(uploaded_file, header=0)

                # --- NEW, ROBUST DATA CLEANING LOGIC ---
                # This block correctly handles subtotals and totals.

                # STEP 1: Identify and remove subtotal/total rows.
                # We assume that any valid transaction row MUST have a date.
                # Subtotal rows in the provided example do not have a date.
                # This reliably filters them out before any other processing.
                # NOTE: Replace 'FECHA_RECIBO' with the actual name of your date column if it's different.
                df_cleaned = df.dropna(subset=['FECHA_RECIBO']).copy()

                # STEP 2: Forward fill the identifying information.
                # Now that only transaction rows are left, we can safely propagate
                # the receipt number and client name to all related lines.
                id_cols = ['NUMRECIBO', 'FECHA_RECIBO', 'NOMBRECLIENTE', 'NIF20']
                for col in id_cols:
                    if col in df_cleaned.columns:
                        df_cleaned[col] = df_cleaned[col].ffill()

                # STEP 3: Function to correctly clean and convert currency values.
                # This handles formats like "$ 1.234,56" by removing symbols and
                # converting it to a machine-readable float (1234.56).
                def clean_and_convert(value):
                    try:
                        str_value = str(value).split('\n')[0].strip()
                        # 1. Remove currency symbol
                        str_value = str_value.replace('$', '')
                        # 2. Remove thousands separator (.)
                        str_value = str_value.replace('.', '')
                        # 3. Replace decimal separator (,) with a period (.)
                        str_value = str_value.replace(',', '.')
                        # Convert to float
                        return float(str_value)
                    except (ValueError, IndexError):
                        # If conversion fails, return None
                        return None
                
                # Apply the cleaning function and drop any rows where conversion failed
                df_cleaned['IMPORTE_LIMPIO'] = df_cleaned['IMPORTE'].apply(clean_and_convert)
                df_cleaned.dropna(subset=['IMPORTE_LIMPIO'], inplace=True)

                # --- END OF CORRECTED LOGIC ---

                # Group by receipt number and sum the cleaned amounts
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
                
                if df_resumen.empty:
                    st.warning("The file does not contain valid cash receipts. Please check the format.")
                else:
                    st.subheader("📊 Daily Summary")
                    total_recibos = df_resumen['Valor Efectivo'].sum()
                    # Correct formatting for Colombian currency display
                    st.metric(label="💰 Total Cash Collected", value=f"${total_recibos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    st.divider()

                    st.subheader("Assign Cash Destination")
                    st.info("Use the 'Destino' column to select which bank or third party received the cash for each receipt.")

                    df_resumen['Destino'] = "-- Select --"

                    edited_df = st.data_editor(
                        df_resumen,
                        column_config={
                            "Destino": st.column_config.SelectboxColumn(
                                "Cash Destination",
                                help="Select the bank or third party where the cash was deposited/delivered.",
                                options=opciones_destino,
                                required=True
                            ),
                            "Valor Efectivo": st.column_config.NumberColumn("Cash Value", format="$ %.2f", disabled=True),
                            "Fecha": st.column_config.TextColumn("Date", disabled=True),
                            "Cliente": st.column_config.TextColumn("Client", disabled=True),
                            "Recibo N°": st.column_config.TextColumn("Receipt No.", disabled=True),
                        },
                        hide_index=True,
                        use_container_width=True,
                        key="editor_recibos"
                    )

                    st.divider()
                    if st.button("✅ Process and Save Assignments", type="primary", use_container_width=True):
                        if edited_df['Destino'].isnull().any() or any(d == "-- Select --" for d in edited_df['Destino']):
                            st.warning("⚠️ You must assign a valid destination for ALL cash receipts before processing.")
                        else:
                            st.success("Assignments processed! The data is ready to be used.")
                            
                            try:
                                global_consecutive = get_next_global_consecutive(global_consecutivo_ws)
                                if global_consecutive is None:
                                    st.error("Could not get the global consecutive number. Cannot save.")
                                    st.stop()

                                txt_content = generate_txt_from_df(edited_df, account_mappings, global_consecutive)

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
                                st.success("✅ Data saved to Google Sheets.")

                                st.download_button(
                                    label="⬇️ Download TXT File for ERP",
                                    data=txt_content.encode('utf-8'),
                                    file_name=f"recibos_caja_{datetime.now().strftime('%Y%m%d')}.txt",
                                    mime="text/plain"
                                )
                                st.info("The TXT file has been generated and is ready for download.")

                            except Exception as e:
                                st.error(f"Error saving data or generating the TXT file: {e}")
                                st.warning("Please check the connection and structure of the Google Sheets worksheets.")

            except Exception as e:
                st.error(f"An error occurred while reading or processing the Excel file: {e}")
                st.warning("Make sure the file is not corrupt and has the correct format.")
