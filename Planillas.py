import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json
import pandas as pd

# --- CONFIGURACIÓN Y CONEXIÓN A GOOGLE SHEETS ---

@st.cache_resource(ttl=600)
def connect_to_gsheet():
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
        st.error(f"Error: No se encontró la hoja de cálculo '{e.worksheet_name}'. Revisa los nombres en tus secretos de Streamlit.")
        return None, None
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        st.warning("Asegúrate de haber configurado los secretos y compartido la hoja con el 'client_email'.")
        return None, None

# --- HELPERS Y MANEJO DE ESTADO ---

def format_number(num):
    """Formatea un número a un string con separador de miles de punto."""
    try:
        return f"${int(num):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"

def initialize_session_state():
    defaults = {
        'venta_total_dia': 0.0, 'factura_inicial': "", 'factura_final': "",
        'tarjetas': [], 'consignaciones': [], 'gastos': [], 'efectivo': [],
        'new_card_val': 0.0
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def clear_session_state():
    tienda = st.session_state.get('tienda_seleccionada', None)
    fecha = st.session_state.get('fecha_seleccionada', datetime.now().date())
    
    for key in list(st.session_state.keys()):
        if not key.startswith('FormSubmitter'):
             del st.session_state[key]
    
    initialize_session_state()
    
    if tienda: st.session_state.tienda_seleccionada = tienda
    if fecha: st.session_state.fecha_seleccionada = fecha

# --- INTERFAZ DE LA APLICACIÓN ---

st.set_page_config(layout="wide", page_title="Cuadres de Caja")
st.title("📄 Aplicación de Cuadres de Caja")

registros_ws, config_ws = connect_to_gsheet()

if registros_ws and config_ws:
    try:
        tiendas = config_ws.col_values(1)[1:] 
        bancos = config_ws.col_values(2)[1:]
    except Exception as e:
        st.error(f"No se pudieron cargar Tiendas/Bancos. Revisa la hoja 'Configuracion'. Error: {e}")
        tiendas, bancos = [], []

    initialize_session_state()

    st.header("1. Selección de Registro")
    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    tienda_seleccionada = col1.selectbox("Tienda", options=tiendas, key="tienda_seleccionada")
    fecha_seleccionada = col2.date_input("Fecha", key="fecha_seleccionada")
    col3.button("Cargar Cuadre", on_click=lambda: st.info("Funcionalidad de Cargar en desarrollo."), use_container_width=True)
    
    if col4.button("Iniciar Cuadre Nuevo", use_container_width=True):
        clear_session_state()
        st.success("Formulario limpiado. Listo para un nuevo cuadre.")
        st.rerun()

    st.divider()
    st.header("2. Formulario de Cuadre")

    with st.container(border=True):
        st.subheader("Información General")
        c1, c2, c3 = st.columns(3)
        st.session_state.factura_inicial = c1.text_input("Factura Inicial", value=st.session_state.factura_inicial)
        st.session_state.factura_final = c2.text_input("Factura Final", value=st.session_state.factura_final)
        st.session_state.venta_total_dia = c3.number_input(
            "💰 Venta Total del Día", min_value=0.0, step=1000.0, value=st.session_state.venta_total_dia, format="%d"
        )

    with st.container(border=True):
        st.subheader("Desglose de Pagos")

        # --- SECCIONES REFACTORIZADAS CON TABLAS Y FORMATO ---
        
        with st.expander("💳 Tarjetas (Crédito / Débito)", expanded=True):
            input_col, btn_col = st.columns([2, 1])
            input_col.number_input("Valor Nueva Tarjeta", min_value=0.0, step=1000.0, key="new_card_val", label_visibility="collapsed", format="%d")
            if btn_col.button("Agregar Tarjeta"):
                if st.session_state.new_card_val > 0:
                    st.session_state.tarjetas.append(st.session_state.new_card_val)
                    st.session_state.new_card_val = 0.0
                    st.rerun()
            
            if st.session_state.tarjetas:
                df_tarjetas = pd.DataFrame({'Valor': st.session_state.tarjetas})
                df_tarjetas['Eliminar'] = False
                edited_df = st.data_editor(
                    df_tarjetas, key='editor_tarjetas', hide_index=True, use_container_width=True,
                    column_config={
                        "Valor": st.column_config.NumberColumn("Valor", format="$ %d"),
                        "Eliminar": st.column_config.CheckboxColumn("Eliminar")
                    }
                )
                st.session_state.tarjetas = [float(v) for v in edited_df['Valor']]
                if edited_df['Eliminar'].any():
                    indices_a_eliminar = edited_df[edited_df['Eliminar']].index
                    st.session_state.tarjetas = [t for i, t in enumerate(st.session_state.tarjetas) if i not in indices_a_eliminar]
                    st.rerun()

            subtotal_tarjetas = sum(st.session_state.tarjetas)
            st.metric("Subtotal Tarjetas", format_number(subtotal_tarjetas))

        with st.expander("🏦 Consignaciones"):
            form_cols = st.columns([2, 2, 2, 1])
            banco_consignacion = form_cols[0].selectbox("Banco", options=bancos, key="banco_consignacion_new")
            valor_consignacion = form_cols[1].number_input("Valor", min_value=0.0, step=1000.0, key="valor_consignacion_new", format="%d")
            fecha_consignacion = form_cols[2].date_input("Fecha", key="fecha_consignacion_new")
            if form_cols[3].button("Agregar", key="btn_add_consignacion"):
                if valor_consignacion > 0:
                    st.session_state.consignaciones.append({"Banco": banco_consignacion, "Valor": valor_consignacion, "Fecha": fecha_consignacion.strftime("%Y-%m-%d")})
                    st.rerun()
            
            if st.session_state.consignaciones:
                df_cons = pd.DataFrame(st.session_state.consignaciones)
                df_cons['Eliminar'] = False
                edited_df_cons = st.data_editor(
                    df_cons, key='editor_consignaciones', hide_index=True, use_container_width=True,
                    column_config={"Valor": st.column_config.NumberColumn("Valor", format="$ %d")}
                )
                if edited_df_cons['Eliminar'].any():
                    indices = edited_df_cons[edited_df_cons['Eliminar']].index
                    st.session_state.consignaciones = [c for i, c in enumerate(st.session_state.consignaciones) if i not in indices]
                    st.rerun()
                else:
                    st.session_state.consignaciones = edited_df_cons.drop(columns=['Eliminar']).to_dict('records')

            subtotal_consignaciones = sum(c.get('Valor', 0) for c in st.session_state.consignaciones)
            st.metric("Subtotal Consignaciones", format_number(subtotal_consignaciones))
            
        with st.expander("💸 Gastos"):
            form_cols_gastos = st.columns([3, 2, 1])
            desc_gasto = form_cols_gastos[0].text_input("Descripción", key="desc_gasto_new")
            valor_gasto = form_cols_gastos[1].number_input("Valor", min_value=0.0, step=100.0, key="valor_gasto_new", format="%d")
            if form_cols_gastos[2].button("Agregar", key="btn_add_gasto"):
                if valor_gasto > 0 and desc_gasto:
                    st.session_state.gastos.append({"Descripción": desc_gasto, "Valor": valor_gasto})
                    st.rerun()

            if st.session_state.gastos:
                df_gastos = pd.DataFrame(st.session_state.gastos)
                df_gastos['Eliminar'] = False
                edited_df_gastos = st.data_editor(
                    df_gastos, key='editor_gastos', hide_index=True, use_container_width=True,
                    column_config={"Valor": st.column_config.NumberColumn("Valor", format="$ %d")}
                )
                if edited_df_gastos['Eliminar'].any():
                    indices = edited_df_gastos[edited_df_gastos['Eliminar']].index
                    st.session_state.gastos = [g for i, g in enumerate(st.session_state.gastos) if i not in indices]
                    st.rerun()
                else:
                    st.session_state.gastos = edited_df_gastos.drop(columns=['Eliminar']).to_dict('records')

            subtotal_gastos = sum(g.get('Valor', 0) for g in st.session_state.gastos)
            st.metric("Subtotal Gastos", format_number(subtotal_gastos))

        with st.expander("💵 Efectivo y Caja Menor"):
            form_cols_efectivo = st.columns([3, 2, 1])
            tipo_movimiento = form_cols_efectivo[0].selectbox("Tipo Movimiento", ["Efectivo", "Reintegro Caja Menor"], key="tipo_mov_new")
            valor_movimiento = form_cols_efectivo[1].number_input("Valor", min_value=0.0, step=1000.0, key="valor_mov_new", format="%d")
            if form_cols_efectivo[2].button("Agregar", key="btn_add_efectivo"):
                if valor_movimiento > 0:
                    st.session_state.efectivo.append({"Tipo": tipo_movimiento, "Valor": valor_movimiento})
                    st.rerun()

            if st.session_state.efectivo:
                df_efectivo = pd.DataFrame(st.session_state.efectivo)
                df_efectivo['Eliminar'] = False
                edited_df_efectivo = st.data_editor(
                    df_efectivo, key='editor_efectivo', hide_index=True, use_container_width=True,
                    column_config={"Valor": st.column_config.NumberColumn("Valor", format="$ %d")}
                )
                if edited_df_efectivo['Eliminar'].any():
                    indices = edited_df_efectivo[edited_df_efectivo['Eliminar']].index
                    st.session_state.efectivo = [e for i, e in enumerate(st.session_state.efectivo) if i not in indices]
                    st.rerun()
                else:
                    st.session_state.efectivo = edited_df_efectivo.drop(columns=['Eliminar']).to_dict('records')

            subtotal_efectivo = sum(e.get('Valor', 0) for e in st.session_state.efectivo)
            st.metric("Subtotal Efectivo y Caja Menor", format_number(subtotal_efectivo))

    st.divider()

    st.header("3. Verificación y Guardado")
    with st.container(border=True):
        total_desglose = subtotal_tarjetas + subtotal_consignaciones + subtotal_gastos + subtotal_efectivo
        diferencia = st.session_state.venta_total_dia - total_desglose

        v1, v2, v3 = st.columns(3)
        v1.metric("Venta Total Ingresada", format_number(st.session_state.venta_total_dia))
        v2.metric("Suma del Desglose", format_number(total_desglose))
        
        label_diferencia = "✅ Diferencia" if diferencia == 0 else "❌ Diferencia"
        v3.metric(label_diferencia, format_number(diferencia))

        if st.button("💾 Guardar Cuadre", type="primary", use_container_width=True):
            if st.session_state.venta_total_dia == 0:
                st.warning("No se puede guardar un cuadre con venta total en cero.")
            else:
                if diferencia != 0:
                    st.toast(f"Atención: El cuadre se guardará con una diferencia de {format_number(diferencia)}.", icon='⚠️')
                
                id_registro = f"{tienda_seleccionada}-{fecha_seleccionada.strftime('%Y-%m-%d')}"
                nueva_fila = [
                    id_registro, tienda_seleccionada, fecha_seleccionada.strftime("%Y-%m-%d"),
                    st.session_state.factura_inicial, st.session_state.factura_final,
                    st.session_state.venta_total_dia, json.dumps(st.session_state.tarjetas),
                    json.dumps(st.session_state.consignaciones), json.dumps(st.session_state.gastos),
                    json.dumps(st.session_state.efectivo), diferencia, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ]
                try:
                    # Futuro: Añadir lógica para actualizar si ya existe
                    registros_ws.append_row(nueva_fila)
                    st.success(f"¡Cuadre para {tienda_seleccionada} el {fecha_seleccionada} guardado exitosamente!")
                    clear_session_state()
                    st.rerun()
                except Exception as e:
                    st.error(f"Ocurrió un error al guardar los datos: {e}")
