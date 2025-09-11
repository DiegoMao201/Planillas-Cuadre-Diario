import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json

# --- CONFIGURACIÓN Y CONEXIÓN A GOOGLE SHEETS ---

# Función para conectar con Google Sheets usando los secretos de Streamlit
@st.cache_resource(ttl=600) # Cache para no reconectar en cada rerun
def connect_to_gsheet():
    try:
        creds_json = dict(st.secrets["google_credentials"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        
        spreadsheet_name = st.secrets["google_sheets"]["spreadsheet_name"]
        sheet = client.open(spreadsheet_name)
        
        registros_sheet_name = st.secrets["google_sheets"]["registros_sheet_name"]
        config_sheet_name = st.secrets["google_sheets"]["config_sheet_name"]
        
        registros_ws = sheet.worksheet(registros_sheet_name)
        config_ws = sheet.worksheet(config_sheet_name)
        
        return registros_ws, config_ws
    except gspread.exceptions.WorksheetNotFound as e:
        st.error(f"Error: No se encontró la hoja de cálculo '{e.sheet_name}'.")
        st.warning(f"Asegúrate de que el nombre en Google Sheets coincida exactamente con el de tus secretos de Streamlit.")
        return None, None
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        st.warning("Asegúrate de haber configurado correctamente los secretos en Streamlit Cloud y compartido la hoja con el 'client_email'.")
        return None, None

# --- INICIALIZACIÓN Y MANEJO DE ESTADO ---

def initialize_session_state():
    # Inicializa el estado para los campos principales y las listas
    defaults = {
        'venta_total_dia': 0.0,
        'factura_inicial': "",
        'factura_final': "",
        'tarjetas': [],
        'consignaciones': [],
        'gastos': [],
        'efectivo': [],
        'new_card_val': 0.0 # Variable para limpiar el input de tarjetas
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def clear_session_state():
    # Guarda los valores de selección antes de limpiar
    tienda = st.session_state.get('tienda_seleccionada', None)
    fecha = st.session_state.get('fecha_seleccionada', datetime.now().date())
    
    # Limpia todo el estado
    for key in list(st.session_state.keys()):
        if not key.startswith('FormSubmitter'): # Evita borrar el estado interno de los botones
             del st.session_state[key]
    
    initialize_session_state()
    
    # Restaura la selección si existía
    if tienda:
        st.session_state.tienda_seleccionada = tienda
    if fecha:
        st.session_state.fecha_seleccionada = fecha


# --- INTERFAZ DE LA APLICACIÓN ---

st.set_page_config(layout="wide", page_title="Cuadres de Caja")
st.title("📄 Aplicación de Cuadres de Caja")

# Conectar a Google Sheets
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
                valor_tarjeta = st.session_state.new_card_val
                if valor_tarjeta > 0:
                    st.session_state.tarjetas.append(valor_tarjeta)
                    st.session_state.new_card_val = 0.0 # Resetea para limpiar el input
                    st.rerun()
            
            st.write("---")
            st.write("**Tarjetas Ingresadas:**")
            
            # --- Lógica de 4 columnas para editar y borrar ---
            num_tarjetas = len(st.session_state.tarjetas)
            if num_tarjetas > 0:
                card_cols = st.columns(4)
                for i in range(num_tarjetas):
                    col = card_cols[i % 4]
                    with col:
                        sub_col1, sub_col2 = st.columns([3, 1])
                        # Campo para editar el valor
                        nuevo_valor = sub_col1.number_input(
                            f"Valor {i+1}", 
                            value=float(st.session_state.tarjetas[i]), 
                            key=f"card_edit_{i}",
                            label_visibility="collapsed"
                        )
                        st.session_state.tarjetas[i] = nuevo_valor # Actualización en tiempo real
                        # Botón para eliminar
                        if sub_col2.button("🗑️", key=f"card_del_{i}", help="Eliminar esta tarjeta"):
                            st.session_state.tarjetas.pop(i)
                            st.rerun()
            else:
                st.info("Aún no se han agregado tarjetas.")

            subtotal_tarjetas = sum(st.session_state.tarjetas)
            st.metric("Subtotal Tarjetas", f"${subtotal_tarjetas:,.0f}")

        # --- Secciones de Consignaciones, Gastos y Efectivo (mejoradas también) ---
        # (Se podría aplicar el mismo patrón de edición y borrado si se desea)

        with st.expander("🏦 Consignaciones"):
            # (El código de consignaciones, gastos y efectivo se mantiene igual por ahora,
            # pero se puede mejorar con el patrón de edición/borrado como en las tarjetas)
            cc1, cc2, cc3 = st.columns(3)
            banco_consignacion = cc1.selectbox("Banco", options=bancos, key="banco_consignacion")
            valor_consignacion = cc2.number_input("Valor", min_value=0.0, step=1000.0, key="valor_consignacion")
            fecha_consignacion = cc3.date_input("Fecha Consignación", key="fecha_consignacion")
            if st.button("Agregar Consignación"):
                if valor_consignacion > 0:
                    st.session_state.consignaciones.append({
                        "banco": banco_consignacion, "valor": valor_consignacion, "fecha": fecha_consignacion.strftime("%Y-%m-%d")
                    })
            st.write("Consignaciones Ingresadas:")
            for item in st.session_state.consignaciones:
                st.write(f"- {item['banco']}: ${item['valor']:,.0f} (Fecha: {item['fecha']})")
            subtotal_consignaciones = sum(c['valor'] for c in st.session_state.consignaciones)
            st.metric("Subtotal Consignaciones", f"${subtotal_consignaciones:,.0f}")
            
        with st.expander("💸 Gastos"):
            gc1, gc2 = st.columns(2)
            desc_gasto = gc1.text_input("Descripción del Gasto", key="desc_gasto")
            valor_gasto = gc2.number_input("Valor del Gasto", min_value=0.0, step=100.0, key="valor_gasto")
            if st.button("Agregar Gasto"):
                if valor_gasto > 0 and desc_gasto:
                    st.session_state.gastos.append({"descripcion": desc_gasto, "valor": valor_gasto})
            st.write("Gastos Ingresados:")
            for item in st.session_state.gastos:
                st.write(f"- {item['descripcion']}: ${item['valor']:,.0f}")
            subtotal_gastos = sum(g['valor'] for g in st.session_state.gastos)
            st.metric("Subtotal Gastos", f"${subtotal_gastos:,.0f}")

        with st.expander("💵 Efectivo y Caja Menor"):
            ec1, ec2 = st.columns(2)
            tipo_movimiento = ec1.selectbox("Tipo de Movimiento", ["Efectivo", "Reintegro Caja Menor"], key="tipo_mov")
            valor_movimiento = ec2.number_input("Valor", min_value=0.0, step=1000.0, key="valor_mov")
            if st.button("Agregar Movimiento"):
                if valor_movimiento > 0:
                    st.session_state.efectivo.append({"tipo": tipo_movimiento, "valor": valor_movimiento})
            st.write("Movimientos Ingresados:")
            for item in st.session_state.efectivo:
                st.write(f"- {item['tipo']}: ${item['valor']:,.0f}")
            subtotal_efectivo = sum(e['valor'] for e in st.session_state.efectivo)
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
        v3.metric("Diferencia", f"${diferencia:,.0f}", delta_color=color_diferencia)

        if st.button("💾 Guardar Cuadre", type="primary", use_container_width=True):
            if diferencia != 0:
                st.error("No se puede guardar. El cuadre tiene una diferencia.")
            elif st.session_state.venta_total_dia == 0:
                st.warning("No se puede guardar un cuadre con venta total en cero.")
            else:
                id_registro = f"{tienda_seleccionada}-{fecha_seleccionada.strftime('%Y-%m-%d')}"
                nueva_fila = [
                    id_registro, tienda_seleccionada, fecha_seleccionada.strftime("%Y-%m-%d"),
                    st.session_state.factura_inicial, st.session_state.factura_final,
                    st.session_state.venta_total_dia, json.dumps(st.session_state.tarjetas),
                    json.dumps(st.session_state.consignaciones), json.dumps(st.session_state.gastos),
                    json.dumps(st.session_state.efectivo), datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ]
                try:
                    # Futuro: Añadir lógica para actualizar en lugar de solo agregar
                    registros_ws.append_row(nueva_fila)
                    st.success(f"¡Cuadre para {tienda_seleccionada} en la fecha {fecha_seleccionada} guardado exitosamente!")
                    clear_session_state()
                    st.rerun()
                except Exception as e:
                    st.error(f"Ocurrió un error al guardar los datos: {e}")
