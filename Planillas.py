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

# --- INICIALIZACIÓN Y MANEJO DE ESTADO ---

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
    col1, col2 = st.columns(2)
    tienda_seleccionada = col1.selectbox("Tienda", options=tiendas, key="tienda_seleccionada")
    fecha_seleccionada = col2.date_input("Fecha", key="fecha_seleccionada")

    if st.button("Cargar Cuadre"):
        st.info("Funcionalidad de Cargar en desarrollo.")

    if st.button("Iniciar Cuadre Nuevo"):
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
            "💰 Venta Total del Día", min_value=0.0, step=1000.0, value=st.session_state.venta_total_dia
        )

    with st.container(border=True):
        st.subheader("Desglose de Pagos")

        with st.expander("💳 Tarjetas (Crédito / Débito)", expanded=True):
            input_col, btn_col = st.columns([3, 1])
            input_col.number_input("Valor Nueva Tarjeta", min_value=0.0, step=1000.0, key="new_card_val", label_visibility="collapsed")
            if btn_col.button("Agregar Tarjeta"):
                if st.session_state.new_card_val > 0:
                    st.session_state.tarjetas.append(st.session_state.new_card_val)
                    st.session_state.new_card_val = 0.0
                    st.rerun()
            
            st.write("---")
            if st.session_state.tarjetas:
                df_tarjetas = pd.DataFrame({'Valor': st.session_state.tarjetas})
                df_tarjetas['Eliminar'] = [False] * len(df_tarjetas)
                
                edited_df = st.data_editor(df_tarjetas, key='editor_tarjetas', hide_index=True)
                
                st.session_state.tarjetas = [float(v) for v in edited_df['Valor']]
                
                if edited_df['Eliminar'].any():
                    indices_a_eliminar = edited_df[edited_df['Eliminar']].index
                    st.session_state.tarjetas = [t for i, t in enumerate(st.session_state.tarjetas) if i not in indices_a_eliminar]
                    st.rerun()
            else:
                st.info("Aún no se han agregado tarjetas.")

            subtotal_tarjetas = sum(st.session_state.tarjetas)
            st.metric("Subtotal Tarjetas", f"${subtotal_tarjetas:,.0f}")

        with st.expander("🏦 Consignaciones"):
            cc1, cc2, cc3, cc4 = st.columns([2, 2, 2, 1])
            banco_consignacion = cc1.selectbox("Banco", options=bancos, key="banco_consignacion_new")
            valor_consignacion = cc2.number_input("Valor", min_value=0.0, step=1000.0, key="valor_consignacion_new")
            fecha_consignacion = cc3.date_input("Fecha Consignación", key="fecha_consignacion_new")
            if cc4.button("Agregar", key="btn_add_consignacion"):
                if valor_consignacion > 0:
                    st.session_state.consignaciones.append({
                        "Banco": banco_consignacion, "Valor": valor_consignacion, "Fecha": fecha_consignacion.strftime("%Y-%m-%d")
                    })
                    st.rerun()
            
            if st.session_state.consignaciones:
                df_consignaciones = pd.DataFrame(st.session_state.consignaciones)
                df_consignaciones['Eliminar'] = False
                edited_df_cons = st.data_editor(df_consignaciones, key='editor_consignaciones', hide_index=True)
                
                if edited_df_cons['Eliminar'].any():
                    indices_a_eliminar = edited_df_cons[edited_df_cons['Eliminar']].index
                    st.session_state.consignaciones = [c for i, c in enumerate(st.session_state.consignaciones) if i not in indices_a_eliminar]
                    st.rerun()
                else:
                    st.session_state.consignaciones = edited_df_cons.drop(columns=['Eliminar']).to_dict('records')

            subtotal_consignaciones = sum(c['Valor'] for c in st.session_state.consignaciones)
            st.metric("Subtotal Consignaciones", f"${subtotal_consignaciones:,.0f}")
            
        with st.expander("💸 Gastos"):
            gc1, gc2, gc3 = st.columns([3, 2, 1])
            desc_gasto = gc1.text_input("Descripción", key="desc_gasto_new")
            valor_gasto = gc2.number_input("Valor", min_value=0.0, step=100.0, key="valor_gasto_new")
            if gc3.button("Agregar", key="btn_add_gasto"):
                if valor_gasto > 0 and desc_gasto:
                    st.session_state.gastos.append({"Descripción": desc_gasto, "Valor": valor_gasto})
                    st.rerun()

            if st.session_state.gastos:
                df_gastos = pd.DataFrame(st.session_state.gastos)
                df_gastos['Eliminar'] = False
                edited_df_gastos = st.data_editor(df_gastos, key='editor_gastos', hide_index=True)

                if edited_df_gastos['Eliminar'].any():
                    indices_a_eliminar = edited_df_gastos[edited_df_gastos['Eliminar']].index
                    st.session_state.gastos = [g for i, g in enumerate(st.session_state.gastos) if i not in indices_a_eliminar]
                    st.rerun()
                else:
                    st.session_state.gastos = edited_df_gastos.drop(columns=['Eliminar']).to_dict('records')

            subtotal_gastos = sum(g['Valor'] for g in st.session_state.gastos)
            st.metric("Subtotal Gastos", f"${subtotal_gastos:,.0f}")

        with st.expander("💵 Efectivo y Caja Menor"):
            ec1, ec2, ec3 = st.columns([3, 2, 1])
            tipo_movimiento = ec1.selectbox("Tipo Movimiento", ["Efectivo", "Reintegro Caja Menor"], key="tipo_mov_new")
            valor_movimiento = ec2.number_input("Valor", min_value=0.0, step=1000.0, key="valor_mov_new")
            if ec3.button("Agregar", key="btn_add_efectivo"):
                if valor_movimiento > 0:
                    st.session_state.efectivo.append({"Tipo": tipo_movimiento, "Valor": valor_movimiento})
                    st.rerun()

            if st.session_state.efectivo:
                df_efectivo = pd.DataFrame(st.session_state.efectivo)
                df_efectivo['Eliminar'] = False
                edited_df_efectivo = st.data_editor(df_efectivo, key='editor_efectivo', hide_index=True)

                if edited_df_efectivo['Eliminar'].any():
                    indices_a_eliminar = edited_df_efectivo[edited_df_efectivo['Eliminar']].index
                    st.session_state.efectivo = [e for i, e in enumerate(st.session_state.efectivo) if i not in indices_a_eliminar]
                    st.rerun()
                else:
                    st.session_state.efectivo = edited_df_efectivo.drop(columns=['Eliminar']).to_dict('records')

            subtotal_efectivo = sum(e['Valor'] for e in st.session_state.efectivo)
            st.metric("Subtotal Efectivo y Caja Menor", f"${subtotal_efectivo:,.0f}")

    st.divider()

    st.header("3. Verificación y Guardado")
    with st.container(border=True):
        total_desglose = subtotal_tarjetas + subtotal_consignaciones + subtotal_gastos + subtotal_efectivo
        diferencia = st.session_state.venta_total_dia - total_desglose

        v1, v2, v3 = st.columns(3)
        v1.metric("Venta Total Ingresada", f"${st.session_state.venta_total_dia:,.0f}")
        v2.metric("Suma del Desglose", f"${total_desglose:,.0f}")
        
        color_diferencia = "normal" if diferencia == 0 else "inverse"
        label_diferencia = "✅ Diferencia" if diferencia == 0 else "❌ Diferencia"
        v3.metric(label_diferencia, f"${diferencia:,.0f}", delta_color=color_diferencia)

        if st.button("💾 Guardar Cuadre", type="primary", use_container_width=True):
            if st.session_state.venta_total_dia == 0:
                st.warning("No se puede guardar un cuadre con venta total en cero.")
            else:
                if diferencia != 0:
                    st.warning(f"Atención: El cuadre se guardará con una diferencia de ${diferencia:,.0f}.")
                
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
