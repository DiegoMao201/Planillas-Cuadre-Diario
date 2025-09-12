# Planillas.py

import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json
import pandas as pd
import re

# --- 1. PAGE AND APP CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Cuadre Diario de Caja")

# --- 2. GOOGLE SHEETS CONNECTION ---
@st.cache_resource(ttl=600)
def connect_to_gsheet():
    """
    Establishes a secure connection to Google Sheets using credentials from st.secrets.
    Returns the worksheet objects for 'Registros', 'Configuracion', and 'Consecutivos'.
    """
    try:
        creds_json = dict(st.secrets["google_credentials"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        sheet = client.open(st.secrets["google_sheets"]["spreadsheet_name"])
        registros_ws = sheet.worksheet(st.secrets["google_sheets"]["registros_sheet_name"])
        config_ws = sheet.worksheet(st.secrets["google_sheets"]["config_sheet_name"])
        consecutivos_ws = sheet.worksheet("Consecutivos")
        return registros_ws, config_ws, consecutivos_ws
    except Exception as e:
        st.error(f"Error fatal al conectar con Google Sheets: {e}")
        st.warning("Verifique las credenciales y los nombres de las hojas en los 'secrets' de Streamlit.")
        return None, None, None

# --- 3. DATA LOADING AND PROCESSING LOGIC ---
def get_app_config(config_ws):
    """
    Reads the 'Configuracion' sheet to get lists of stores, banks, and third parties.
    This avoids reading the entire sheet multiple times.
    """
    try:
        config_data = config_ws.get_all_records()
        tiendas = sorted(list(set(str(d['Detalle']) for d in config_data if d.get('Tipo Movimiento') == 'TIENDA')))
        bancos = sorted(list(set(str(d['Detalle']) for d in config_data if d.get('Tipo Movimiento') == 'BANCO' and d.get('Detalle'))))
        terceros = sorted(list(set(str(d['Detalle']) for d in config_data if d.get('Tipo Movimiento') == 'TERCERO' and d.get('Detalle'))))
        return tiendas, bancos, terceros
    except Exception as e:
        st.error(f"Error al cargar la configuración de tiendas, bancos y terceros: {e}")
        return [], [], []

def get_account_mappings(config_ws):
    """
    Reads account mappings from the 'Configuracion' sheet.
    - For BANCO and TERCERO types, it captures the account, NIT, and name.
    - For other types (GASTO, TARJETA, EFECTIVO), it captures the default account.
    The mapping key is always the 'Detalle' column.
    """
    try:
        records = config_ws.get_all_records()
        mappings = {}
        for record in records:
            tipo = record.get("Tipo Movimiento")
            detalle = record.get("Detalle")
            cuenta = record.get("Cuenta Contable")

            if detalle and cuenta:
                detalle_str = str(detalle)
                cuenta_str = str(cuenta)
                if tipo in ["BANCO", "TERCERO"]:
                    mappings[detalle_str] = {
                        'cuenta': cuenta_str,
                        'nit': str(record.get("NIT", "")),
                        'nombre': str(record.get("Nombre Tercero", ""))
                    }
                elif tipo in ["GASTO", "TARJETA", "EFECTIVO"]:
                    mappings[detalle_str] = {'cuenta': cuenta_str}
        return mappings
    except Exception as e:
        st.error(f"Error al leer el mapeo de cuentas. Revisa la hoja 'Configuracion'. Error: {e}")
        return {}

def generate_txt_file(registros_ws, config_ws, start_date, end_date):
    """
    Generates the content for the TXT file for the selected date range.
    Includes enhanced logic for associating expenses (Gastos) with third parties.
    """
    st.info("Generando archivo... Esto puede tardar unos segundos.")
    
    all_records = registros_ws.get_all_records()
    account_mappings = get_account_mappings(config_ws)

    if not account_mappings:
        st.error("No se pudo generar el reporte: Faltan mapeos de cuentas en 'Configuracion'.")
        return None

    try:
        filtered_records = [
            r for r in all_records
            if start_date <= datetime.strptime(r.get('Fecha', '01/01/1900'), '%d/%m/%Y').date() <= end_date
        ]
    except ValueError as e:
        st.error(f"Error de formato de fecha en la hoja 'Registros'. Asegúrese que las fechas estén en formato DD/MM/YYYY. Error: {e}")
        return None

    if not filtered_records:
        st.warning("No se encontraron registros en el rango de fechas seleccionado.")
        return None

    filtered_records.sort(key=lambda r: (r.get('Tienda', ''), r.get('Fecha', '')))
    
    txt_lines = []
    
    for record in filtered_records:
        consecutivo = record.get('Consecutivo_Asignado', '0')
        tienda = str(record.get('Tienda', ''))
        fecha_cuadre = record['Fecha']
        centro_costo = tienda 
        tienda_descripcion = re.sub(r'[\(\)]', '', tienda).strip()

        total_debito_dia = 0
        movimientos = {
            'TARJETA': json.loads(record.get('Tarjetas', '[]')),
            'CONSIGNACION': json.loads(record.get('Consignaciones', '[]')),
            'GASTO': json.loads(record.get('Gastos', '[]')),
            'EFECTIVO': json.loads(record.get('Efectivo', '[]'))
        }

        for tipo_mov, data_list in movimientos.items():
            for item in data_list:
                valor = float(item.get('Valor', 0))
                if valor == 0: continue
                total_debito_dia += valor

                # Default values for each line
                cuenta = ""
                nit_tercero, nombre_tercero = "800224617", "FERREINOX SAS BIC" # Default company NIT
                serie_documento = centro_costo
                descripcion = f"Ventas planillas contado {tienda_descripcion}"
                
                if tipo_mov == 'TARJETA':
                    # Assumes a single entry in 'Configuracion' like: Tipo=TARJETA, Detalle=TARJETAS
                    cuenta = account_mappings.get('TARJETAS', {}).get('cuenta', 'ERR_TARJETA')
                    serie_documento = f"T{centro_costo}"

                elif tipo_mov == 'CONSIGNACION':
                    banco = item.get('Banco')
                    # Looks up the bank's account from its 'Detalle'
                    cuenta = account_mappings.get(banco, {}).get('cuenta', f'ERR_{banco}')

                elif tipo_mov == 'GASTO':
                    # Assumes a generic expense entry: Tipo=GASTO, Detalle=GASTOS
                    cuenta = account_mappings.get('GASTOS', {}).get('cuenta', 'ERR_GASTO')
                    gasto_tercero = item.get('Tercero')
                    
                    # If a third party is associated, use their info but keep the expense account
                    if gasto_tercero and gasto_tercero != "N/A":
                        tercero_info = account_mappings.get(gasto_tercero)
                        if tercero_info:
                            nit_tercero = tercero_info.get('nit', nit_tercero)
                            nombre_tercero = tercero_info.get('nombre', nombre_tercero)
                            descripcion = f"{item.get('Descripción', 'Gasto')} - {nombre_tercero}"
                        else:
                            descripcion = f"{item.get('Descripción', 'Gasto')} (Tercero {gasto_tercero} no encontrado)"
                    else:
                        descripcion = item.get('Descripción', 'Gasto Varios')


                elif tipo_mov == 'EFECTIVO':
                    tipo_especifico = item.get('Tipo', 'Efectivo Entregado')
                    destino_tercero = item.get('Destino/Tercero (Opcional)')

                    if tipo_especifico == "Efectivo Entregado" and destino_tercero and destino_tercero != "N/A":
                        tercero_info = account_mappings.get(destino_tercero)
                        if tercero_info:
                            # For cash deliveries, the account becomes the third party's account (e.g., a payable/receivable)
                            cuenta = tercero_info.get('cuenta', f'ERR_{destino_tercero}')
                            nit_tercero = tercero_info.get('nit', nit_tercero)
                            nombre_tercero = tercero_info.get('nombre', nombre_tercero)
                            descripcion = f"Entrega efectivo a {nombre_tercero} - {tienda_descripcion}"
                        else:
                            cuenta = f'ERR_{destino_tercero}'
                    else:
                        # For other cash types (like reimbursements), use the account mapped to its 'Detalle'
                        cuenta = account_mappings.get(tipo_especifico, {}).get('cuenta', f'ERR_{tipo_especifico}')

                linea = "|".join([
                    fecha_cuadre, str(consecutivo), str(cuenta), "8",
                    descripcion, serie_documento, str(consecutivo),
                    str(valor), "0", centro_costo, nit_tercero, nombre_tercero, "0"
                ])
                txt_lines.append(linea)

        # Add the balancing credit line for the day's total sales
        if total_debito_dia > 0:
            cuenta_venta = "11050501" # Default cash account for sales
            descripcion_credito = f"Ventas planillas contado {tienda_descripcion}"
            linea_credito = "|".join([
                fecha_cuadre, str(consecutivo), str(cuenta_venta), "8",
                descripcion_credito, centro_costo, str(consecutivo),
                "0", str(total_debito_dia), centro_costo, "800224617", "FERREINOX SAS BIC", "0"
            ])
            txt_lines.append(linea_credito)
            
    return "\n".join(txt_lines)

# --- 4. SESSION STATE MANAGEMENT ---
def initialize_session_state():
    """Initializes session state with default values if they don't exist."""
    defaults = {
        'page': 'Formulario', 'venta_total_dia': 0.0, 'factura_inicial': "", 'factura_final': "",
        'tarjetas': [], 'consignaciones': [], 'gastos': [], 'efectivo': [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def clear_form_state():
    """Resets the form fields to their default state, preserving selected store and date."""
    tienda = st.session_state.get('tienda_seleccionada', None)
    fecha = st.session_state.get('fecha_seleccionada', datetime.now().date())
    
    # Store keys to keep
    keys_to_keep = ['page', 'tienda_seleccionada', 'fecha_seleccionada']
    
    # Reset all other keys by re-initializing
    for key in list(st.session_state.keys()):
        if key not in keys_to_keep:
            del st.session_state[key]
            
    initialize_session_state()
    
    st.session_state.tienda_seleccionada = tienda
    st.session_state.fecha_seleccionada = fecha

# --- 5. UI COMPONENTS & FORM RENDERING ---
def format_currency(num):
    """Formats a number as Colombian currency."""
    return f"${int(num):,}".replace(",", ".") if isinstance(num, (int, float)) else "$0"

def load_cuadre_data(registros_ws):
    """Loads existing data from the 'Registros' sheet for the selected store and date."""
    if not st.session_state.get("tienda_seleccionada"):
        st.warning("Por favor, seleccione una tienda primero.")
        return

    id_registro = f"{st.session_state.tienda_seleccionada}-{st.session_state.fecha_seleccionada.strftime('%d/%m/%Y')}"
    try:
        cell = registros_ws.find(id_registro, in_column=1)
        if cell:
            row_data = registros_ws.row_values(cell.row)
            clear_form_state() # Clear previous state before loading new data

            st.session_state.factura_inicial = row_data[4] if len(row_data) > 4 else ""
            st.session_state.factura_final = row_data[5] if len(row_data) > 5 else ""
            st.session_state.venta_total_dia = float(row_data[6]) if len(row_data) > 6 and row_data[6] else 0.0
            st.session_state.tarjetas = json.loads(row_data[7]) if len(row_data) > 7 and row_data[7] else []
            st.session_state.consignaciones = json.loads(row_data[8]) if len(row_data) > 8 and row_data[8] else []
            st.session_state.gastos = json.loads(row_data[9]) if len(row_data) > 9 and row_data[9] else []
            st.session_state.efectivo = json.loads(row_data[10]) if len(row_data) > 10 and row_data[10] else []
            st.toast(f"✅ Cuadre para '{st.session_state.tienda_seleccionada}' cargado.", icon="📄")
        else:
            st.warning("No se encontró un cuadre para esta tienda y fecha. Puede crear uno nuevo.")
            clear_form_state()
    except Exception as e:
        st.error(f"Error al cargar datos. Verifique la hoja 'Registros'. Error: {e}")
        clear_form_state()

# --- Consecutive Number Management ---
def get_next_consecutive(consecutivos_ws, tienda):
    """Gets the next consecutive number for a given store from the 'Consecutivos' sheet."""
    try:
        cell = consecutivos_ws.find(tienda, in_column=1)
        if cell:
            last_consecutive = int(consecutivos_ws.cell(cell.row, 2).value)
            return last_consecutive + 1
        else:
            st.warning(f"No se encontró un consecutivo inicial para la tienda '{tienda}'. Se usará '1000' por defecto.")
            return 1000
    except Exception as e:
        st.error(f"Error al obtener consecutivo: {e}")
        return None

def update_consecutive(consecutivos_ws, tienda, new_consecutive):
    """Updates the last used consecutive number for a store in the 'Consecutivos' sheet."""
    try:
        cell = consecutivos_ws.find(tienda, in_column=1)
        if cell:
            consecutivos_ws.update_cell(cell.row, 2, new_consecutive)
        else:
            consecutivos_ws.append_row([tienda, new_consecutive])
    except Exception as e:
        st.error(f"Error al actualizar consecutivo: {e}")

# --- Dynamic UI Section Generator (Core of the form) ---
def display_dynamic_list_section(title, key, form_inputs, options_map=None):
    """
    A reusable function to create a form section for adding items to a list (e.g., expenses, deposits).
    Handles data entry, display in a table, and deletion.
    """
    if options_map is None: options_map = {}

    with st.expander(f"**{title}**", expanded=True):
        # --- Form for adding new items ---
        with st.form(f"form_{key}", clear_on_submit=True):
            cols = st.columns(len(form_inputs))
            data = {}
            for i, (input_key, input_type, options) in enumerate(form_inputs):
                label = options.get('label', input_key)
                if input_type == "selectbox":
                    data[input_key] = cols[i].selectbox(label, options=options_map.get(input_key, []), label_visibility="collapsed", placeholder=label)
                elif input_type == "number_input":
                    data[input_key] = cols[i].number_input(label, min_value=0.0, step=1000.0, format="%.0f", label_visibility="collapsed", placeholder=label)
                elif input_type == "date_input":
                    data[input_key] = cols[i].date_input(label, value=datetime.now().date(), label_visibility="collapsed", format="DD/MM/YYYY")
                else: # text_input
                    data[input_key] = cols[i].text_input(label, label_visibility="collapsed", placeholder=label)
            
            if st.form_submit_button(f"✚ Agregar {title.split(' ')[1]}", use_container_width=True):
                if data.get("Valor", 0) > 0:
                    # FIX: Proactively convert date objects to strings to ensure consistent data type.
                    if 'Fecha' in data and hasattr(data['Fecha'], 'strftime'):
                        data['Fecha'] = data['Fecha'].strftime("%d/%m/%Y")
                    
                    st.session_state[key].append(data)
                    st.toast(f"✅ {title.split(' ')[1]} agregado.")
                    st.rerun()
                else:
                    st.warning("El valor debe ser mayor a cero.")

        # --- Table for displaying and editing items ---
        if st.session_state[key]:
            df = pd.DataFrame(st.session_state[key])
            df['Eliminar'] = False
            
            column_config = {
                "Valor": st.column_config.NumberColumn("Valor", format="$ %.0f", required=True),
                "Eliminar": st.column_config.CheckboxColumn("Eliminar", width="small")
            }
            # Dynamically configure selectbox columns for the data editor
            for col_name, options_list in options_map.items():
                if col_name in df.columns:
                    column_config[col_name] = st.column_config.SelectboxColumn(col_name, options=options_list, required=True)

            edited_df = st.data_editor(df, key=f'editor_{key}', hide_index=True, use_container_width=True, column_config=column_config)

            if edited_df['Eliminar'].any():
                indices_to_remove = edited_df[edited_df['Eliminar']].index
                st.session_state[key] = [item for i, item in enumerate(st.session_state[key]) if i not in indices_to_remove]
                st.toast("🗑️ Registro(s) eliminado(s).")
                st.rerun()
            else:
                st.session_state[key] = edited_df.drop(columns=['Eliminar']).to_dict('records')

        subtotal = sum(float(item.get('Valor', 0)) for item in st.session_state[key])
        st.metric(f"Subtotal {title.split(' ')[1]}", format_currency(subtotal))

# --- Specific Form Sections ---
def display_tarjetas_section():
    # Tarjetas section is simpler, so it keeps its own custom logic without the dynamic function.
    with st.expander("💳 **Tarjetas**", expanded=True):
        with st.form("form_tarjetas", clear_on_submit=True):
            valor = st.number_input("Valor", min_value=1.0, step=1000.0, format="%.0f", label_visibility="collapsed", placeholder="Valor Tarjeta")
            if st.form_submit_button("✚ Agregar Tarjeta", use_container_width=True):
                if valor > 0:
                    st.session_state.tarjetas.append({'Valor': valor})
                    st.toast(f"Agregado: {format_currency(valor)}")
                    st.rerun()
        if st.session_state.tarjetas:
            df = pd.DataFrame(st.session_state.tarjetas)
            df['Eliminar'] = False
            edited_df = st.data_editor(
                df, key='editor_tarjetas', hide_index=True, use_container_width=True,
                column_config={"Valor": st.column_config.NumberColumn("Valor", format="$ %.0f"), "Eliminar": st.column_config.CheckboxColumn("Eliminar", width="small")}
            )
            if edited_df['Eliminar'].any():
                st.session_state.tarjetas = [t for i, t in enumerate(st.session_state.tarjetas) if i not in edited_df[edited_df['Eliminar']].index]
                st.toast("Tarjeta(s) eliminada(s).")
                st.rerun()
            else:
                st.session_state.tarjetas = edited_df.drop(columns=['Eliminar']).to_dict('records')
        
        st.metric("Subtotal Tarjetas", format_currency(sum(float(t.get('Valor', 0)) for t in st.session_state.tarjetas)))

def display_consignaciones_section(bancos_list):
    display_dynamic_list_section(
        "🏦 Consignaciones", "consignaciones",
        [("Banco", "selectbox", {"label": "Banco"}),
         ("Valor", "number_input", {"label": "Valor"}),
         ("Fecha", "date_input", {"label": "Fecha"})],
        options_map={"Banco": bancos_list}
    )

def display_gastos_section(terceros_list):
    # ENHANCEMENT: Added a dropdown to select the third party (provider) for the expense.
    terceros_con_na = ["N/A"] + terceros_list
    display_dynamic_list_section(
        "💸 Gastos", "gastos",
        [("Descripción", "text_input", {"label": "Descripción"}),
         ("Tercero", "selectbox", {"label": "Tercero (Proveedor)"}),
         ("Valor", "number_input", {"label": "Valor"})],
        options_map={"Tercero": terceros_con_na}
    )

def display_efectivo_section(terceros_list):
    terceros_con_na = ["N/A"] + terceros_list
    display_dynamic_list_section(
        "💵 Efectivo", "efectivo",
        [("Tipo", "selectbox", {"label": "Tipo Movimiento"}),
         ("Destino/Tercero (Opcional)", "selectbox", {"label": "Destino/Tercero"}),
         ("Valor", "number_input", {"label": "Valor"})],
        options_map={
            "Tipo": ["Efectivo Entregado", "Reintegro Caja Menor"],
            "Destino/Tercero (Opcional)": terceros_con_na
        }
    )

# --- Summary and Save Section ---
def display_summary_and_save(registros_ws, consecutivos_ws):
    st.header("3. Verificación y Guardado", anchor=False, divider="rainbow")
    with st.container(border=True):
        sub_t = sum(float(t.get('Valor', 0)) for t in st.session_state.tarjetas)
        sub_c = sum(float(c.get('Valor', 0)) for c in st.session_state.consignaciones)
        sub_g = sum(float(g.get('Valor', 0)) for g in st.session_state.gastos)
        sub_e = sum(float(e.get('Valor', 0)) for e in st.session_state.efectivo)
        total_desglose = sub_t + sub_c + sub_g + sub_e
        venta_total = float(st.session_state.get('venta_total_dia', 0.0))
        diferencia = venta_total - total_desglose

        v1, v2, v3 = st.columns(3)
        v1.metric("💰 Venta Total (Sistema)", format_currency(venta_total))
        v2.metric("📊 Suma del Desglose", format_currency(total_desglose))
        delta_color = "inverse" if diferencia != 0 else "off"
        v3.metric("Diferencia", format_currency(diferencia), delta=format_currency(diferencia), delta_color=delta_color)

        if st.button("💾 Guardar o Actualizar Cuadre", type="primary", use_container_width=True):
            tienda = st.session_state.get("tienda_seleccionada")
            if not tienda:
                st.warning("🛑 Por favor, seleccione una tienda antes de guardar.")
                return
            if venta_total <= 0:
                st.warning("⚠️ La Venta Total del día debe ser mayor a cero.")
                return

            fecha_str = st.session_state.fecha_seleccionada.strftime("%d/%m/%Y")
            id_registro = f"{tienda}-{fecha_str}"

            try:
                cell = registros_ws.find(id_registro, in_column=1)
                if cell:
                    consecutivo_asignado = registros_ws.cell(cell.row, 2).value
                    st.info(f"Actualizando registro existente. El consecutivo se mantendrá: {consecutivo_asignado}")
                else:
                    consecutivo_asignado = get_next_consecutive(consecutivos_ws, tienda)
                    if consecutivo_asignado is None: return
                    update_consecutive(consecutivos_ws, tienda, consecutivo_asignado)
                
                fila_datos = [
                    id_registro, consecutivo_asignado, tienda, fecha_str,
                    st.session_state.factura_inicial, st.session_state.factura_final, venta_total,
                    json.dumps(st.session_state.tarjetas), json.dumps(st.session_state.consignaciones),
                    json.dumps(st.session_state.gastos), json.dumps(st.session_state.efectivo),
                    diferencia, datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                ]

                if cell:
                    registros_ws.update(f'A{cell.row}', [fila_datos])
                    st.success(f"✅ Cuadre para {tienda} el {fecha_str} fue **actualizado**!")
                else:
                    registros_ws.append_row(fila_datos)
                    st.success(f"✅ Cuadre para {tienda} el {fecha_str} fue **guardado** con el consecutivo **{consecutivo_asignado}**!")
            except Exception as e:
                st.error(f"Error al guardar los datos en Google Sheets: {e}")

# --- 6. MAIN PAGE RENDERING FUNCTIONS ---
def render_form_page(worksheets, config):
    """Renders the main data entry form."""
    registros_ws, config_ws, consecutivos_ws = worksheets
    tiendas, bancos, terceros = config
    
    st.header("1. Selección de Registro", anchor=False, divider="rainbow")
    c1,c2,c3,c4 = st.columns([2,2,1,1])
    c1.selectbox("Tienda", options=tiendas, key="tienda_seleccionada", on_change=clear_form_state, placeholder="Seleccione una tienda...")
    c2.date_input("Fecha", key="fecha_seleccionada", on_change=clear_form_state, format="DD/MM/YYYY")
    with c3:
        st.write(" ")
        st.button("🔍 Cargar Cuadre", on_click=load_cuadre_data, args=[registros_ws], use_container_width=True)
    with c4:
        st.write(" ")
        st.button("✨ Iniciar Nuevo", on_click=clear_form_state, use_container_width=True)

    st.divider()
    st.header("2. Formulario de Cuadre", anchor=False, divider="rainbow")
    
    with st.container(border=True):
        st.subheader("📋 Información General")
        c1,c2,c3=st.columns(3)
        st.session_state.factura_inicial=c1.text_input("Factura Inicial", value=st.session_state.get('factura_inicial', ""))
        st.session_state.factura_final=c2.text_input("Factura Final", value=st.session_state.get('factura_final', ""))
        st.session_state.venta_total_dia=c3.number_input("💰 Venta Total (Sistema)",min_value=0.0,step=1000.0,value=float(st.session_state.get('venta_total_dia', 0.0)),format="%.0f")

    with st.container(border=True):
        st.subheader("🧾 Desglose de Pagos")
        display_tarjetas_section()
        display_consignaciones_section(bancos)
        display_gastos_section(terceros) # Pass the list of third parties
        display_efectivo_section(terceros)

    display_summary_and_save(registros_ws, consecutivos_ws)

def render_reports_page(registros_ws, config_ws):
    """Renders the page for generating TXT reports."""
    st.header("Generación de Archivo Plano para ERP", divider="rainbow")
    st.markdown("Seleccione un rango de fechas para generar el archivo TXT para el sistema contable.")

    today = datetime.now().date()
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Fecha de Inicio", today.replace(day=1))
    end_date = col2.date_input("Fecha de Fin", today)

    if start_date > end_date:
        st.error("Error: La fecha de inicio no puede ser posterior a la fecha de fin.")
        return

    if st.button("📊 Generar Archivo TXT", use_container_width=True, type="primary"):
        with st.spinner('Generando...'):
            txt_content = generate_txt_file(registros_ws, config_ws, start_date, end_date)
            if txt_content:
                st.download_button(
                    label="📥 Descargar Archivo .txt",
                    data=txt_content.encode('utf-8'),
                    file_name=f"contabilidad_{start_date.strftime('%Y%m%d')}_a_{end_date.strftime('%Y%m%d')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
                st.success("Archivo generado y listo para descargar.")

# --- 7. MAIN APPLICATION FLOW ---
def main():
    """Main function to run the Streamlit app."""
    initialize_session_state()

    try:
        c1, c2 = st.columns([1, 4])
        # To display a logo, ensure the image file is in the same directory as your script.
        # c1.image("LOGO FERREINOX SAS BIC 2024.PNG", width=150) 
        c2.title("CUADRE DIARIO DE CAJA")
    except Exception:
        st.title("CUADRE DIARIO DE CAJA")

    registros_ws, config_ws, consecutivos_ws = connect_to_gsheet()
    
    if all([registros_ws, config_ws, consecutivos_ws]):
        with st.sidebar:
            st.header("Navegación")
            if st.button("📝 Formulario de Cuadre", use_container_width=True, type="primary" if st.session_state.page=="Formulario" else "secondary"):
                st.session_state.page="Formulario"
                st.rerun()
            if st.button("📈 Reportes TXT", use_container_width=True, type="primary" if st.session_state.page=="Reportes" else "secondary"):
                st.session_state.page="Reportes"
                st.rerun()
        
        tiendas, bancos, terceros = get_app_config(config_ws)

        if not tiendas and st.session_state.page == "Formulario":
            st.error("🚨 No se encontraron tiendas en la hoja de 'Configuracion'.")
            st.warning("Por favor, agregue al menos una tienda (Tipo Movimiento = TIENDA) para poder continuar.")
            return

        if st.session_state.page == "Formulario":
            render_form_page((registros_ws, config_ws, consecutivos_ws), (tiendas, bancos, terceros))
        elif st.session_state.page == "Reportes":
            render_reports_page(registros_ws, config_ws)
    else:
        st.info("⏳ Esperando conexión con Google Sheets...")

if __name__ == "__main__":
    main()
