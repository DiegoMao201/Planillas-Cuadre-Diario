import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import json

# --- CONFIGURACIÓN Y CONEXIÓN A GOOGLE SHEETS ---

# Función para conectar con Google Sheets usando los secretos de Streamlit
def connect_to_gsheet():
    try:
        # Carga las credenciales desde los secretos de Streamlit
        creds_json = {
            "type": st.secrets["google_credentials"]["type"],
            "project_id": st.secrets["google_credentials"]["project_id"],
            "private_key_id": st.secrets["google_credentials"]["private_key_id"],
            "private_key": st.secrets["google_credentials"]["private_key"],
            "client_email": st.secrets["google_credentials"]["client_email"],
            "client_id": st.secrets["google_credentials"]["client_id"],
            "auth_uri": st.secrets["google_credentials"]["auth_uri"],
            "token_uri": st.secrets["google_credentials"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["google_credentials"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["google_credentials"]["client_x509_cert_url"]
        }
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        
        # Abre la hoja de cálculo y las hojas de trabajo
        spreadsheet_name = st.secrets["google_sheets"]["spreadsheet_name"]
        registros_sheet_name = st.secrets["google_sheets"]["registros_sheet_name"]
        config_sheet_name = st.secrets["google_sheets"]["config_sheet_name"]
        
        sheet = client.open(spreadsheet_name)
        registros_ws = sheet.worksheet(registros_sheet_name)
        config_ws = sheet.worksheet(config_sheet_name)
        
        return registros_ws, config_ws
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        st.warning("Asegúrate de haber configurado correctamente los secretos en Streamlit Cloud.")
        return None, None

# --- INICIALIZACIÓN Y MANEJO DE ESTADO ---

# Inicializa el estado de la sesión para el formulario si no existe
def initialize_session_state():
    if 'venta_total_dia' not in st.session_state:
        st.session_state.venta_total_dia = 0.0
    if 'factura_inicial' not in st.session_state:
        st.session_state.factura_inicial = ""
    if 'factura_final' not in st.session_state:
        st.session_state.factura_final = ""
    if 'tarjetas' not in st.session_state:
        st.session_state.tarjetas = []
    if 'consignaciones' not in st.session_state:
        st.session_state.consignaciones = []
    if 'gastos' not in st.session_state:
        st.session_state.gastos = []
    if 'efectivo' not in st.session_state:
        st.session_state.efectivo = []

# Limpia el estado de la sesión para un nuevo cuadre
def clear_session_state():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    initialize_session_state()

# --- INTERFAZ DE LA APLICACIÓN ---

st.set_page_config(layout="wide")
st.title("📄 Aplicación de Cuadres de Caja")

# Conectar a Google Sheets
registros_ws, config_ws = connect_to_gsheet()

if registros_ws and config_ws:
    # Cargar listas de configuración desde la hoja 'Configuracion'
    try:
        tiendas = config_ws.col_values(1)[1:] # Asume que las tiendas están en la columna A
        bancos = config_ws.col_values(2)[1:]  # Asume que los bancos están en la columna B
    except Exception as e:
        st.error(f"No se pudieron cargar los datos de configuración (Tiendas/Bancos). Revisa la hoja 'Configuracion'. Error: {e}")
        tiendas = ["Error al cargar"]
        bancos = ["Error al cargar"]

    # Inicializar el estado de la sesión
    initialize_session_state()

    st.header("1. Selección de Registro")
    col1, col2 = st.columns(2)
    with col1:
        tienda_seleccionada = st.selectbox("Tienda", options=tiendas)
    with col2:
        fecha_seleccionada = st.date_input("Fecha")

    if st.button("Cargar Cuadre"):
        # Lógica para cargar datos (se implementará)
        st.info("Funcionalidad de Cargar en desarrollo.")

    if st.button("Iniciar Cuadre Nuevo"):
        clear_session_state()
        st.success("Formulario limpiado. Listo para un nuevo cuadre.")

    st.divider()

    # --- FORMULARIO DE INGRESO ---
    st.header("2. Formulario de Cuadre")

    with st.container(border=True):
        st.subheader("Información General")
        c1, c2, c3 = st.columns(3)
        st.session_state.factura_inicial = c1.text_input("Factura Inicial", value=st.session_state.factura_inicial)
        st.session_state.factura_final = c2.text_input("Factura Final", value=st.session_state.factura_final)
        st.session_state.venta_total_dia = c3.number_input(
            "💰 Venta Total del Día", 
            min_value=0.0, 
            step=1000.0, 
            value=st.session_state.venta_total_dia
        )

    with st.container(border=True):
        st.subheader("Desglose de Pagos")

        # Tarjetas
        with st.expander("💳 Tarjetas (Crédito / Débito)"):
            valor_tarjeta = st.number_input("Valor Nueva Tarjeta", min_value=0.0, step=1000.0, key="new_card_val")
            if st.button("Agregar Tarjeta"):
                if valor_tarjeta > 0:
                    st.session_state.tarjetas.append(valor_tarjeta)
            
            st.write("Tarjetas Ingresadas:")
            for i, valor in enumerate(st.session_state.tarjetas):
                st.write(f"- ${valor:,.2f}")
            subtotal_tarjetas = sum(st.session_state.tarjetas)
            st.metric("Subtotal Tarjetas", f"${subtotal_tarjetas:,.2f}")

        # Consignaciones
        with st.expander("🏦 Consignaciones"):
            cc1, cc2, cc3 = st.columns(3)
            banco_consignacion = cc1.selectbox("Banco", options=bancos, key="banco_consignacion")
            valor_consignacion = cc2.number_input("Valor", min_value=0.0, step=1000.0, key="valor_consignacion")
            fecha_consignacion = cc3.date_input("Fecha Consignación", key="fecha_consignacion")
            if st.button("Agregar Consignación"):
                if valor_consignacion > 0:
                    st.session_state.consignaciones.append({
                        "banco": banco_consignacion,
                        "valor": valor_consignacion,
                        "fecha": fecha_consignacion.strftime("%Y-%m-%d")
                    })
            
            st.write("Consignaciones Ingresadas:")
            for item in st.session_state.consignaciones:
                st.write(f"- {item['banco']}: ${item['valor']:,.2f} (Fecha: {item['fecha']})")
            subtotal_consignaciones = sum(c['valor'] for c in st.session_state.consignaciones)
            st.metric("Subtotal Consignaciones", f"${subtotal_consignaciones:,.2f}")
            
        # Gastos
        with st.expander("💸 Gastos"):
            gc1, gc2 = st.columns(2)
            desc_gasto = gc1.text_input("Descripción del Gasto", key="desc_gasto")
            valor_gasto = gc2.number_input("Valor del Gasto", min_value=0.0, step=100.0, key="valor_gasto")
            if st.button("Agregar Gasto"):
                if valor_gasto > 0 and desc_gasto:
                    st.session_state.gastos.append({"descripcion": desc_gasto, "valor": valor_gasto})
            
            st.write("Gastos Ingresados:")
            for item in st.session_state.gastos:
                st.write(f"- {item['descripcion']}: ${item['valor']:,.2f}")
            subtotal_gastos = sum(g['valor'] for g in st.session_state.gastos)
            st.metric("Subtotal Gastos", f"${subtotal_gastos:,.2f}")

        # Efectivo y Caja Menor
        with st.expander("💵 Efectivo y Caja Menor"):
            ec1, ec2 = st.columns(2)
            tipo_movimiento = ec1.selectbox("Tipo de Movimiento", ["Efectivo", "Reintegro Caja Menor"], key="tipo_mov")
            valor_movimiento = ec2.number_input("Valor", min_value=0.0, step=1000.0, key="valor_mov")
            if st.button("Agregar Movimiento"):
                if valor_movimiento > 0:
                    st.session_state.efectivo.append({"tipo": tipo_movimiento, "valor": valor_movimiento})

            st.write("Movimientos Ingresados:")
            for item in st.session_state.efectivo:
                st.write(f"- {item['tipo']}: ${item['valor']:,.2f}")
            subtotal_efectivo = sum(e['valor'] for e in st.session_state.efectivo)
            st.metric("Subtotal Efectivo y Caja Menor", f"${subtotal_efectivo:,.2f}")

    st.divider()

    # --- VERIFICACIÓN Y GUARDADO ---
    st.header("3. Verificación y Guardado")

    with st.container(border=True):
        total_desglose = subtotal_tarjetas + subtotal_consignaciones + subtotal_gastos + subtotal_efectivo
        diferencia = st.session_state.venta_total_dia - total_desglose

        v1, v2, v3 = st.columns(3)
        v1.metric("Venta Total Ingresada", f"${st.session_state.venta_total_dia:,.2f}")
        v2.metric("Suma del Desglose", f"${total_desglose:,.2f}")
        
        if diferencia == 0:
            v3.metric("✅ Diferencia", f"${diferencia:,.2f}")
        else:
            v3.metric("❌ Diferencia", f"${diferencia:,.2f}")

        if st.button("💾 Guardar Cuadre", type="primary", use_container_width=True):
            if diferencia != 0:
                st.error("No se puede guardar. El cuadre tiene una diferencia.")
            else:
                # Preparar datos para guardar
                id_registro = f"{tienda_seleccionada}-{fecha_seleccionada.strftime('%Y-%m-%d')}"
                nueva_fila = [
                    id_registro,
                    tienda_seleccionada,
                    fecha_seleccionada.strftime("%Y-%m-%d"),
                    st.session_state.factura_inicial,
                    st.session_state.factura_final,
                    st.session_state.venta_total_dia,
                    json.dumps(st.session_state.tarjetas), # Convertir listas a texto JSON
                    json.dumps(st.session_state.consignaciones),
                    json.dumps(st.session_state.gastos),
                    json.dumps(st.session_state.efectivo),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ]
                
                try:
                    # Lógica para guardar (aquí se podría añadir la lógica para actualizar si ya existe)
                    registros_ws.append_row(nueva_fila)
                    st.success(f"¡Cuadre para {tienda_seleccionada} en la fecha {fecha_seleccionada} guardado exitosamente!")
                    # Limpiar el formulario después de guardar
                    clear_session_state()
                except Exception as e:
                    st.error(f"Ocurrió un error al guardar los datos: {e}")
