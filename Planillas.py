import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json
import pandas as pd
from PIL import Image

# --- CONFIGURACIÓN DE LA PÁGINA DE STREAMLIT ---
# Se establece una configuración inicial para la página, como el layout y el título.
st.set_page_config(layout="wide", page_title="Cuadre Diario de Caja")

# --- CONEXIÓN SEGURA Y CACHEADADA A GOOGLE SHEETS ---

@st.cache_resource(ttl=600)
def connect_to_gsheet():
    """
    Establece una conexión segura con Google Sheets usando las credenciales de Streamlit Secrets.
    La conexión se mantiene en caché para evitar reconexiones innecesarias.
    Retorna los objetos de las hojas de cálculo 'Registros' y 'Configuracion'.
    """
    try:
        creds_json = dict(st.secrets["google_credentials"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        
        spreadsheet_name = st.secrets["google_sheets"]["spreadsheet_name"]
        sheet = client.open(spreadsheet_name)
        
        registros_ws = sheet.worksheet(st.secrets["google_sheets"]["registros_sheet_name"])
        config_ws = sheet.worksheet(st.secrets["google_sheets"]["config_sheet_name"])
        
        return registros_ws, config_ws
    except gspread.exceptions.WorksheetNotFound as e:
        st.error(f"Error Crítico: No se encontró la hoja de cálculo '{e.worksheet_name}'. Revisa los nombres en tus secretos de Streamlit.")
        return None, None
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        st.warning("Asegúrate de haber configurado los secretos ('secrets.toml') y compartido la hoja de cálculo con el 'client_email' de tus credenciales.")
        return None, None

# --- FUNCIONES DE LÓGICA Y MANEJO DE ESTADO ---

def format_currency(num):
    """Formatea un número como una cadena de moneda en formato colombiano."""
    try:
        return f"${int(num):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"

def initialize_session_state():
    """Inicializa el estado de la sesión con valores por defecto si no existen."""
    defaults = {
        'venta_total_dia': 0.0, 'factura_inicial': "", 'factura_final': "",
        'tarjetas': [], 'consignaciones': [], 'gastos': [], 'efectivo': [],
        'form_cleared': False
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def clear_form_state():
    """Limpia el estado del formulario, preservando la tienda y fecha seleccionadas."""
    tienda = st.session_state.get('tienda_seleccionada', None)
    fecha = st.session_state.get('fecha_seleccionada', datetime.now().date())
    
    for key in list(st.session_state.keys()):
        if not key.startswith('FormSubmitter'):
            del st.session_state[key]
    
    initialize_session_state()
    
    if tienda: st.session_state.tienda_seleccionada = tienda
    if fecha: st.session_state.fecha_seleccionada = fecha
    st.session_state.form_cleared = True

def load_cuadre_data(registros_ws):
    """
    Busca y carga los datos de un cuadre existente desde Google Sheets al estado de la sesión.
    """
    tienda = st.session_state.tienda_seleccionada
    fecha = st.session_state.fecha_seleccionada
    id_registro = f"{tienda}-{fecha.strftime('%Y-%m-%d')}"
    
    try:
        cell = registros_ws.find(id_registro, in_column=1)
        if cell:
            row_data = registros_ws.row_values(cell.row)
            
            # Limpia el formulario antes de cargar nuevos datos
            clear_form_state()
            
            # Carga los datos en el estado de la sesión con manejo de errores
            st.session_state.factura_inicial = row_data[3] if len(row_data) > 3 else ""
            st.session_state.factura_final = row_data[4] if len(row_data) > 4 else ""
            st.session_state.venta_total_dia = float(row_data[5]) if len(row_data) > 5 and row_data[5] else 0.0
            
            # Carga de listas JSON con validación
            st.session_state.tarjetas = json.loads(row_data[6]) if len(row_data) > 6 and row_data[6] else []
            st.session_state.consignaciones = json.loads(row_data[7]) if len(row_data) > 7 and row_data[7] else []
            st.session_state.gastos = json.loads(row_data[8]) if len(row_data) > 8 and row_data[8] else []
            st.session_state.efectivo = json.loads(row_data[9]) if len(row_data) > 9 and row_data[9] else []

            st.toast(f"✅ Cuadre para {tienda} el {fecha.strftime('%d/%m/%Y')} cargado exitosamente.", icon="📄")
        else:
            st.warning(f"No se encontró un cuadre para {tienda} en la fecha {fecha.strftime('%d/%m/%Y')}. Puede crear uno nuevo.")
            clear_form_state() # Limpia si no se encuentra para evitar confusión

    except Exception as e:
        st.error(f"Ocurrió un error al cargar los datos: {e}")
        clear_form_state()

# --- FUNCIONES DE RENDERIZADO DE LA INTERFAZ ---

def display_main_header(tiendas_list, registros_ws):
    """Muestra el encabezado principal para la selección de tienda, fecha y acciones."""
    st.header("1. Selección de Registro", anchor=False, divider="rainbow")
    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    
    col1.selectbox("Tienda", options=tiendas_list, key="tienda_seleccionada")
    col2.date_input("Fecha", key="fecha_seleccionada")
    
    # El botón ahora llama a la función de carga
    col3.button("🔍 Cargar Cuadre", on_click=load_cuadre_data, args=[registros_ws], use_container_width=True, help="Busca y carga un cuadre existente para la tienda y fecha seleccionadas.")
    col4.button("✨ Iniciar Nuevo", on_click=clear_form_state, use_container_width=True, help="Limpia todos los campos del formulario para un nuevo registro.")

    if st.session_state.get('form_cleared', False):
        st.toast("🧹 Formulario limpiado. ¡Listo para un nuevo cuadre!", icon="✅")
        st.session_state.form_cleared = False

def display_general_info_section():
    """Muestra los campos de información general del cuadre."""
    with st.container(border=True):
        st.subheader("📋 Información General")
        c1, c2, c3 = st.columns(3)
        st.session_state.factura_inicial = c1.text_input("Factura Inicial", value=st.session_state.factura_inicial)
        st.session_state.factura_final = c2.text_input("Factura Final", value=st.session_state.factura_final)
        
        st.session_state.venta_total_dia = c3.number_input(
            "💰 Venta Total del Día (Sistema)",
            min_value=0.0, step=1000.0,
            value=float(st.session_state.venta_total_dia),
            format="%.0f"
        )

def display_payments_breakdown(bancos_list):
    """Contenedor principal para el desglose de pagos."""
    with st.container(border=True):
        st.subheader("🧾 Desglose de Pagos")
        display_tarjetas_section()
        display_consignaciones_section(bancos_list)
        display_gastos_section()
        display_efectivo_section()

def display_tarjetas_section():
    """Muestra la sección para agregar y listar pagos con tarjeta."""
    with st.expander("💳 **Tarjetas (Crédito / Débito)**", expanded=True):
        with st.form("form_tarjetas", clear_on_submit=True):
            valor_tarjeta = st.number_input(
                "Valor Nueva Tarjeta", min_value=1.0, step=1000.0, format="%.0f", label_visibility="collapsed"
            )
            if st.form_submit_button("Agregar Tarjeta", use_container_width=True):
                if valor_tarjeta > 0:
                    st.session_state.tarjetas.append(valor_tarjeta)
                    st.toast(f"Tarjeta de {format_currency(valor_tarjeta)} agregada.", icon="💳")
                    st.rerun()

        if st.session_state.tarjetas:
            df_tarjetas = pd.DataFrame({'Valor': st.session_state.tarjetas})
            df_tarjetas['Eliminar'] = False
            
            edited_df = st.data_editor(
                df_tarjetas, key='editor_tarjetas', hide_index=True, use_container_width=True,
                column_config={
                    "Valor": st.column_config.NumberColumn("Valor", format="$ %.0f"),
                    "Eliminar": st.column_config.CheckboxColumn("Eliminar", width="small")
                }
            )
            
            if edited_df['Eliminar'].any():
                indices_a_eliminar = edited_df[edited_df['Eliminar']].index
                st.session_state.tarjetas = [t for i, t in enumerate(st.session_state.tarjetas) if i not in indices_a_eliminar]
                st.toast("Tarjeta(s) eliminada(s).", icon="🗑️")
                st.rerun()
            else:
                cleaned_valores = pd.to_numeric(edited_df['Valor'], errors='coerce').dropna().tolist()
                st.session_state.tarjetas = [float(v) for v in cleaned_valores]

        subtotal_tarjetas = sum(st.session_state.tarjetas)
        st.metric("Subtotal Tarjetas", format_currency(subtotal_tarjetas))

def display_dynamic_list_section(title, state_key, form_inputs, df_columns, bancos_list=None):
    """Función genérica para mostrar secciones con listas dinámicas."""
    with st.expander(title, expanded=False):
        with st.form(f"form_{state_key}", clear_on_submit=True):
            form_cols = st.columns(len(form_inputs))
            new_item_data = {}
            for i, (key, type, options) in enumerate(form_inputs):
                if type == "selectbox":
                    new_item_data[key] = form_cols[i].selectbox(options['label'], options=bancos_list if key=="Banco" else options['options'])
                elif type == "number_input":
                    new_item_data[key] = form_cols[i].number_input(
                        options['label'], min_value=0.0, step=1000.0, format="%.0f"
                    )
                elif type == "date_input":
                    new_item_data[key] = form_cols[i].date_input(options['label'], value=datetime.now().date())
                elif type == "text_input":
                    new_item_data[key] = form_cols[i].text_input(options['label'])
            
            if st.form_submit_button("Agregar", use_container_width=True):
                if new_item_data.get("Valor", 0) > 0:
                    if 'Fecha' in new_item_data:
                        new_item_data['Fecha'] = new_item_data['Fecha'].strftime("%Y-%m-%d")
                    st.session_state[state_key].append(new_item_data)
                    st.toast("Registro agregado.", icon="✨")
                    st.rerun()

        if st.session_state[state_key]:
            df = pd.DataFrame(st.session_state[state_key])
            df['Eliminar'] = False
            
            column_config = {"Valor": st.column_config.NumberColumn("Valor", format="$ %.0f")}
            for col, config in df_columns.items():
                if config['type'] == 'selectbox':
                    column_config[col] = st.column_config.SelectboxColumn(col, options=config['options'])

            edited_df = st.data_editor(df, key=f'editor_{state_key}', hide_index=True, use_container_width=True, column_config=column_config)
            
            if edited_df['Eliminar'].any():
                indices = edited_df[edited_df['Eliminar']].index
                st.session_state[state_key] = [item for i, item in enumerate(st.session_state[state_key]) if i not in indices]
                st.toast("Registro(s) eliminado(s).", icon="🗑️")
                st.rerun()
            else:
                df_cleaned = edited_df.drop(columns=['Eliminar'])
                df_cleaned['Valor'] = pd.to_numeric(df_cleaned['Valor'], errors='coerce').fillna(0.0)
                df_cleaned = df_cleaned[df_cleaned['Valor'] > 0]
                df_cleaned['Valor'] = df_cleaned['Valor'].astype(float)
                st.session_state[state_key] = df_cleaned.to_dict('records')

        subtotal = sum(item.get('Valor', 0) for item in st.session_state[state_key])
        st.metric(f"Subtotal {title.split('**')[1]}", format_currency(subtotal))

def display_consignaciones_section(bancos_list):
    display_dynamic_list_section(
        title="🏦 **Consignaciones**", state_key="consignaciones",
        form_inputs=[("Banco", "selectbox", {"label": "Banco", "options": bancos_list}), ("Valor", "number_input", {"label": "Valor"}), ("Fecha", "date_input", {"label": "Fecha"})],
        df_columns={"Banco": {"type": "selectbox", "options": bancos_list}}, bancos_list=bancos_list
    )

def display_gastos_section():
    display_dynamic_list_section(
        title="💸 **Gastos**", state_key="gastos",
        form_inputs=[("Descripción", "text_input", {"label": "Descripción"}), ("Valor", "number_input", {"label": "Valor"})],
        df_columns={}
    )

def display_efectivo_section():
    opciones_efectivo = ["Efectivo Entregado", "Reintegro Caja Menor"]
    display_dynamic_list_section(
        title="💵 **Efectivo y Caja Menor**", state_key="efectivo",
        form_inputs=[("Tipo", "selectbox", {"label": "Tipo Movimiento", "options": opciones_efectivo}), ("Valor", "number_input", {"label": "Valor"})],
        df_columns={"Tipo": {"type": "selectbox", "options": opciones_efectivo}}
    )

def display_summary_and_save(registros_ws):
    """Muestra el resumen final, calcula la diferencia y contiene el botón de guardar."""
    st.header("3. Verificación y Guardado", anchor=False, divider="rainbow")
    with st.container(border=True):
        subtotal_tarjetas = sum(st.session_state.tarjetas)
        subtotal_consignaciones = sum(c.get('Valor', 0) for c in st.session_state.consignaciones)
        subtotal_gastos = sum(g.get('Valor', 0) for g in st.session_state.gastos)
        subtotal_efectivo = sum(e.get('Valor', 0) for e in st.session_state.efectivo)
        
        total_desglose = subtotal_tarjetas + subtotal_consignaciones + subtotal_gastos + subtotal_efectivo
        venta_total = st.session_state.venta_total_dia
        diferencia = venta_total - total_desglose

        v1, v2, v3 = st.columns(3)
        v1.metric("💰 Venta Total (Sistema)", format_currency(venta_total))
        v2.metric("📊 Suma del Desglose", format_currency(total_desglose))
        
        if diferencia == 0:
            v3.metric("✅ Diferencia (Cuadre OK)", format_currency(diferencia))
        else:
            v3.metric("❌ Diferencia (Revisar)", format_currency(diferencia), delta=format_currency(diferencia), delta_color="inverse")

        if st.button("💾 Guardar o Actualizar Cuadre", type="primary", use_container_width=True):
            if venta_total == 0:
                st.warning("No se puede guardar un cuadre con la Venta Total en cero.")
                return

            if diferencia != 0:
                st.toast(f"Atención: El cuadre se guardará con una diferencia de {format_currency(diferencia)}.", icon='⚠️')

            fecha_str = st.session_state.fecha_seleccionada.strftime("%Y-%m-%d")
            id_registro = f"{st.session_state.tienda_seleccionada}-{fecha_str}"
            
            nueva_fila = [
                id_registro, st.session_state.tienda_seleccionada, fecha_str,
                st.session_state.factura_inicial, st.session_state.factura_final,
                venta_total, json.dumps(st.session_state.tarjetas),
                json.dumps(st.session_state.consignaciones), json.dumps(st.session_state.gastos),
                json.dumps(st.session_state.efectivo), diferencia, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            try:
                cell = registros_ws.find(id_registro, in_column=1)
                
                if cell:
                    registros_ws.update(f'A{cell.row}', [nueva_fila])
                    st.success(f"✅ ¡Cuadre para {st.session_state.tienda_seleccionada} el {fecha_str} fue **actualizado** exitosamente!")
                else:
                    registros_ws.append_row(nueva_fila)
                    st.success(f"✅ ¡Cuadre para {st.session_state.tienda_seleccionada} el {fecha_str} fue **guardado** exitosamente!")
                
                clear_form_state()
                st.rerun()

            except Exception as e:
                st.error(f"Ocurrió un error al guardar los datos en Google Sheets: {e}")

# --- FLUJO PRINCIPAL DE LA APLICACIÓN ---

def main():
    """Función principal que ejecuta la aplicación Streamlit."""

    # --- NUEVA SECCIÓN DE TÍTULO Y LOGO ---
    try:
        logo = Image.open("LOGO FERREINOX SAS BIC 2024.PNG")
        c1, c2 = st.columns([1, 4])
        c1.image(logo, width=150)
        c2.title("CUADRE DIARIO DE CAJA")
    except FileNotFoundError:
        st.title("CUADRE DIARIO DE CAJA")
        st.warning("No se encontró el archivo del logo 'LOGO FERREINOX SAS BIC 2024.PNG'. Asegúrate de que esté en la carpeta raíz.")
    
    registros_ws, config_ws = connect_to_gsheet()

    if registros_ws and config_ws:
        try:
            tiendas = config_ws.col_values(1)[1:] 
            bancos = config_ws.col_values(2)[1:]
            tiendas = [t for t in tiendas if t]
            bancos = [b for b in bancos if b]
        except Exception as e:
            st.error(f"No se pudieron cargar los datos de 'Configuracion'. Revisa la hoja. Error: {e}")
            tiendas, bancos = ["Error al cargar"], ["Error al cargar"]

        initialize_session_state()
        
        display_main_header(tiendas, registros_ws)
        st.divider()
        st.header("2. Formulario de Cuadre", anchor=False, divider="rainbow")
        
        display_general_info_section()
        display_payments_breakdown(bancos)
        display_summary_and_save(registros_ws)
    else:
        st.info("Esperando la conexión con Google Sheets. Si el error persiste, revisa las credenciales.")

if __name__ == "__main__":
    main()
