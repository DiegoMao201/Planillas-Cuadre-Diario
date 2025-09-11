import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json
import pandas as pd
from PIL import Image
import re

# --- CONFIGURACIÓN DE LA PÁGINA DE STREAMLIT ---
st.set_page_config(layout="wide", page_title="Cuadre Diario de Caja")

# --- CONEXIÓN A GOOGLE SHEETS (SIN CAMBIOS) ---
@st.cache_resource(ttl=600)
def connect_to_gsheet():
    try:
        creds_json = dict(st.secrets["google_credentials"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        sheet = client.open(st.secrets["google_sheets"]["spreadsheet_name"])
        registros_ws = sheet.worksheet(st.secrets["google_sheets"]["registros_sheet_name"])
        config_ws = sheet.worksheet(st.secrets["google_sheets"]["config_sheet_name"])
        return registros_ws, config_ws
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        return None, None

# --- LÓGICA DE LA PÁGINA DE REPORTES ---

def get_account_mappings(config_ws):
    """Lee el mapeo de cuentas desde la hoja de configuración."""
    try:
        records = config_ws.get_all_records()
        mappings = {}
        for record in records:
            tipo = record.get("Tipo Movimiento")
            detalle = record.get("Bancos/Detalle")
            cuenta = record.get("Cuenta Contable")
            if tipo == "BANCO":
                mappings[detalle] = cuenta
            else:
                mappings[tipo] = cuenta
        return mappings
    except Exception as e:
        st.error(f"No se pudo leer el mapeo de cuentas de la hoja 'Configuracion'. Error: {e}")
        return {}

def generate_txt_file(registros_ws, config_ws, start_date, end_date):
    """Genera el contenido del archivo TXT a partir de los registros."""
    st.info("Generando archivo... Esto puede tardar unos segundos.")
    
    all_records = registros_ws.get_all_records()
    account_mappings = get_account_mappings(config_ws)
    
    # Filtrar registros por el rango de fechas seleccionado
    filtered_records = []
    for record in all_records:
        try:
            record_date = datetime.strptime(record['Fecha'], '%Y-%m-%d').date()
            if start_date <= record_date <= end_date:
                filtered_records.append(record)
        except (ValueError, TypeError):
            continue # Ignora filas con formato de fecha incorrecto

    if not filtered_records:
        st.warning("No se encontraron registros en el rango de fechas seleccionado.")
        return None

    # Ordenar por tienda y luego por fecha
    filtered_records.sort(key=lambda r: (r['Tienda'], r['Fecha']))

    txt_lines = []
    consecutivos_tienda = {} # Para generar consecutivos por tienda
    consecutivo_sistema = 2000 # Consecutivo simple para el sistema

    for record in filtered_records:
        tienda = record['Tienda']
        centro_costo = re.search(r'\d+', tienda)
        centro_costo = centro_costo.group(0) if centro_costo else '0'

        if tienda not in consecutivos_tienda:
            consecutivos_tienda[tienda] = 1001
        else:
            consecutivos_tienda[tienda] += 1
        
        fecha_cuadre = record['Fecha']
        total_debito_dia = 0

        # Procesar cada tipo de movimiento como una línea de débito
        movimientos = {
            'TARJETA': json.loads(record.get('Tarjetas', '[]')),
            'CONSIGNACION': json.loads(record.get('Consignaciones', '[]')),
            'GASTO': json.loads(record.get('Gastos', '[]')),
            'EFECTIVO': json.loads(record.get('Efectivo', '[]'))
        }

        # 1. LÍNEAS DE DÉBITO
        for tipo_mov, data_list in movimientos.items():
            for item in data_list:
                valor = float(item.get('Valor', 0))
                if valor == 0: continue
                total_debito_dia += valor

                cuenta = ""
                serie_tarjeta = tienda
                nit_tercero = "800224617"
                nombre_tercero = "FERREINOX SAS BIC"

                if tipo_mov == 'TARJETA':
                    cuenta = account_mappings.get('TARJETA', 'CUENTA_NO_ENCONTRADA')
                    serie_tarjeta = f"T{centro_costo}"
                elif tipo_mov == 'CONSIGNACION':
                    banco = item.get('Banco')
                    cuenta = account_mappings.get(banco, 'CUENTA_NO_ENCONTRADA')
                elif tipo_mov == 'GASTO':
                    cuenta = account_mappings.get('GASTO', 'CUENTA_NO_ENCONTRADA')
                    # Futuro: Aquí se podría leer un NIT específico del gasto
                elif tipo_mov == 'EFECTIVO':
                    cuenta = account_mappings.get('EFECTIVO', 'CUENTA_NO_ENCONTRADA')

                linea = [
                    fecha_cuadre,
                    str(consecutivos_tienda[tienda]),
                    str(cuenta),
                    "999", # Codigo por defecto
                    f"Ventas planillas contado ({tienda})",
                    serie_tarjeta,
                    str(consecutivo_sistema),
                    str(valor), # Débito
                    "0", # Crédito
                    centro_costo,
                    nit_tercero,
                    nombre_tercero,
                    "0" # Constante
                ]
                txt_lines.append("|".join(linea))
                consecutivo_sistema += 1
        
        # 2. LÍNEA DE CRÉDITO (TOTAL DE LA VENTA)
        if total_debito_dia > 0:
            cuenta_venta = account_mappings.get('VENTA', 'CUENTA_VENTA_NO_ENCONTRADA')
            linea_credito = [
                fecha_cuadre, str(consecutivos_tienda[tienda]), str(cuenta_venta), "999",
                f"Ventas planillas contado ({tienda})", tienda, str(consecutivo_sistema),
                "0", # Débito
                str(total_debito_dia), # Crédito
                centro_costo, "800224617", "FERREINOX SAS BIC", "0"
            ]
            txt_lines.append("|".join(linea_credito))
            consecutivo_sistema += 1

    return "\n".join(txt_lines)


def render_reports_page(registros_ws, config_ws):
    """Muestra la página de generación de reportes."""
    st.header("Generación de Archivo Plano para ERP", divider="rainbow")
    
    st.markdown("""
    Seleccione un rango de fechas para generar el archivo TXT que se subirá al sistema contable. 
    El sistema agrupará todos los movimientos de los cuadres de caja encontrados en ese período.
    """)
    
    today = datetime.now().date()
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Fecha de Inicio", today.replace(day=1))
    end_date = col2.date_input("Fecha de Fin", today)

    if start_date > end_date:
        st.error("Error: La fecha de inicio no puede ser posterior a la fecha de fin.")
        return

    if st.button("📊 Generar Archivo TXT", use_container_width=True, type="primary"):
        txt_content = generate_txt_file(registros_ws, config_ws, start_date, end_date)
        if txt_content:
            st.download_button(
                label="📥 Descargar Archivo .txt",
                data=txt_content.encode('utf-8'),
                file_name=f"contabilidad_{start_date}_a_{end_date}.txt",
                mime="text/plain",
                use_container_width=True
            )
            st.success("Archivo generado y listo para descargar.")

# --- LÓGICA DE LA PÁGINA DEL FORMULARIO DE CUADRE (EXISTENTE Y REFACTORIZADA) ---
# Se usan las mismas funciones de antes, pero se llamarán desde 'render_form_page'

def initialize_session_state():
    """Inicializa el estado de la sesión con valores por defecto si no existen."""
    defaults = {'page': 'Formulario', 'venta_total_dia': 0.0, 'factura_inicial': "", 'factura_final': "",
                'tarjetas': [], 'consignaciones': [], 'gastos': [], 'efectivo': [], 'form_cleared': False}
    for key, value in defaults.items():
        if key not in st.session_state: st.session_state[key] = value

def clear_form_state():
    tienda = st.session_state.get('tienda_seleccionada', None)
    fecha = st.session_state.get('fecha_seleccionada', datetime.now().date())
    for key in list(st.session_state.keys()):
        if key not in ['page']: del st.session_state[key]
    initialize_session_state()
    if tienda: st.session_state.tienda_seleccionada = tienda
    if fecha: st.session_state.fecha_seleccionada = fecha
    st.session_state.form_cleared = True

def format_currency(num): return f"${int(num):,}".replace(",", ".") if isinstance(num, (int, float)) else "$0"

def load_cuadre_data(registros_ws):
    tienda = st.session_state.tienda_seleccionada
    fecha = st.session_state.fecha_seleccionada
    id_registro = f"{tienda}-{fecha.strftime('%Y-%m-%d')}"
    try:
        cell = registros_ws.find(id_registro, in_column=1)
        if cell:
            row_data = registros_ws.row_values(cell.row)
            clear_form_state()
            st.session_state.factura_inicial = row_data[3] if len(row_data) > 3 else ""
            st.session_state.factura_final = row_data[4] if len(row_data) > 4 else ""
            st.session_state.venta_total_dia = float(row_data[5]) if len(row_data) > 5 and row_data[5] else 0.0
            st.session_state.tarjetas = json.loads(row_data[6]) if len(row_data) > 6 and row_data[6] else []
            st.session_state.consignaciones = json.loads(row_data[7]) if len(row_data) > 7 and row_data[7] else []
            st.session_state.gastos = json.loads(row_data[8]) if len(row_data) > 8 and row_data[8] else []
            st.session_state.efectivo = json.loads(row_data[9]) if len(row_data) > 9 and row_data[9] else []
            st.toast(f"✅ Cuadre para {tienda} el {fecha.strftime('%d/%m/%Y')} cargado.", icon="📄")
        else:
            st.warning(f"No se encontró un cuadre para {tienda} en la fecha {fecha.strftime('%d/%m/%Y')}.")
            clear_form_state()
    except Exception as e:
        st.error(f"Ocurrió un error al cargar los datos: {e}")
        clear_form_state()

# Las funciones display_* (display_main_header, display_general_info_section, etc.) se mantienen igual que en el código anterior.
# Se omiten aquí por brevedad, pero están en el bloque de código final.
def display_main_header(tiendas_list, registros_ws):
    st.header("1. Selección de Registro", anchor=False, divider="rainbow")
    c1, c2, c3, c4 = st.columns([2,2,1,1]);c1.selectbox("Tienda", options=tiendas_list, key="tienda_seleccionada");c2.date_input("Fecha", key="fecha_seleccionada");c3.button("🔍 Cargar Cuadre", on_click=load_cuadre_data, args=[registros_ws], use_container_width=True);c4.button("✨ Iniciar Nuevo", on_click=clear_form_state, use_container_width=True)
def display_general_info_section():
    with st.container(border=True):
        st.subheader("📋 Información General");c1,c2,c3=st.columns(3);st.session_state.factura_inicial=c1.text_input("Factura Inicial",value=st.session_state.factura_inicial);st.session_state.factura_final=c2.text_input("Factura Final",value=st.session_state.factura_final);st.session_state.venta_total_dia=c3.number_input("💰 Venta Total (Sistema)",min_value=0.0,step=1000.0,value=float(st.session_state.venta_total_dia),format="%.0f")
def display_payments_breakdown(bancos_list):
    with st.container(border=True):
        st.subheader("🧾 Desglose de Pagos");display_tarjetas_section();display_consignaciones_section(bancos_list);display_gastos_section();display_efectivo_section()
def display_tarjetas_section():
    with st.expander("💳 **Tarjetas**", expanded=True):
        with st.form("form_tarjetas",clear_on_submit=True):
            valor=st.number_input("Valor",min_value=1.0,step=1000.0,format="%.0f",label_visibility="collapsed");
            if st.form_submit_button("Agregar Tarjeta",use_container_width=True):
                if valor>0:st.session_state.tarjetas.append(valor);st.toast(f"Agregado: {format_currency(valor)}");st.rerun()
        if st.session_state.tarjetas:
            df=pd.DataFrame({'Valor':st.session_state.tarjetas});df['Eliminar']=False;edited_df=st.data_editor(df,key='editor_tarjetas',hide_index=True,use_container_width=True,column_config={"Valor":st.column_config.NumberColumn("Valor",format="$ %.0f"),"Eliminar":st.column_config.CheckboxColumn("Eliminar",width="small")});
            if edited_df['Eliminar'].any():st.session_state.tarjetas=[t for i,t in enumerate(st.session_state.tarjetas) if i not in edited_df[edited_df['Eliminar']].index];st.toast("Tarjeta(s) eliminada(s).");st.rerun()
            else:st.session_state.tarjetas=[float(v) for v in pd.to_numeric(edited_df['Valor'],errors='coerce').dropna().tolist()]
        st.metric("Subtotal Tarjetas",format_currency(sum(st.session_state.tarjetas)))
def display_dynamic_list_section(title, state_key, form_inputs, df_columns, bancos_list=None):
    with st.expander(f"**{title}**"):
        with st.form(f"form_{state_key}",clear_on_submit=True):
            cols=st.columns(len(form_inputs));data={}
            for i,(k,t,o) in enumerate(form_inputs):
                if t=="selectbox":data[k]=cols[i].selectbox(o['label'],options=bancos_list if k=="Banco" else o['options'])
                elif t=="number_input":data[k]=cols[i].number_input(o['label'],min_value=0.0,step=1000.0,format="%.0f")
                elif t=="date_input":data[k]=cols[i].date_input(o['label'],value=datetime.now().date())
                else:data[k]=cols[i].text_input(o['label'])
            if st.form_submit_button("Agregar"):
                if data.get("Valor",0)>0:
                    if 'Fecha' in data:data['Fecha']=data['Fecha'].strftime("%Y-%m-%d")
                    st.session_state[state_key].append(data);st.toast("Registro agregado.");st.rerun()
        if st.session_state[state_key]:
            df=pd.DataFrame(st.session_state[state_key]);df['Eliminar']=False;config={"Valor":st.column_config.NumberColumn("Valor",format="$ %.0f")};
            for col,c in df_columns.items():config[col]=st.column_config.SelectboxColumn(col,options=c['options'])
            edited_df=st.data_editor(df,key=f'editor_{state_key}',hide_index=True,use_container_width=True,column_config=config)
            if edited_df['Eliminar'].any():st.session_state[state_key]=[item for i,item in enumerate(st.session_state[state_key]) if i not in edited_df[edited_df['Eliminar']].index];st.toast("Registro(s) eliminado(s).");st.rerun()
            else:df_c=edited_df.drop(columns=['Eliminar']);df_c['Valor']=pd.to_numeric(df_c['Valor'],errors='coerce').fillna(0.0);df_c=df_c[df_c['Valor']>0];df_c['Valor']=df_c['Valor'].astype(float);st.session_state[state_key]=df_c.to_dict('records')
        st.metric(f"Subtotal {title.split('**')[0]}", format_currency(sum(item.get('Valor',0) for item in st.session_state[state_key])))
def display_consignaciones_section(bancos_list):display_dynamic_list_section("🏦 Consignaciones","consignaciones",[("Banco","selectbox",{"label":"Banco","options":bancos_list}),("Valor","number_input",{"label":"Valor"}),("Fecha","date_input",{"label":"Fecha"})],{"Banco":{"type":"selectbox","options":bancos_list}},bancos_list)
def display_gastos_section():display_dynamic_list_section("💸 Gastos","gastos",[("Descripción","text_input",{"label":"Descripción"}),("Valor","number_input",{"label":"Valor"})],{})
def display_efectivo_section():display_dynamic_list_section("💵 Efectivo y Caja Menor","efectivo",[("Tipo","selectbox",{"label":"Tipo Movimiento","options":["Efectivo Entregado","Reintegro Caja Menor"]}),("Valor","number_input",{"label":"Valor"})],{"Tipo":{"type":"selectbox","options":["Efectivo Entregado","Reintegro Caja Menor"]}})
def display_summary_and_save(registros_ws):
    st.header("3. Verificación y Guardado",anchor=False,divider="rainbow")
    with st.container(border=True):
        sub_t=sum(st.session_state.tarjetas);sub_c=sum(c.get('Valor',0) for c in st.session_state.consignaciones);sub_g=sum(g.get('Valor',0) for g in st.session_state.gastos);sub_e=sum(e.get('Valor',0) for e in st.session_state.efectivo);total_d=sub_t+sub_c+sub_g+sub_e;venta_t=st.session_state.venta_total_dia;diferencia=venta_t-total_d;
        v1,v2,v3=st.columns(3);v1.metric("💰 Venta Total (Sistema)",format_currency(venta_t));v2.metric("📊 Suma del Desglose",format_currency(total_d));
        if diferencia==0:v3.metric("✅ Diferencia (Cuadre OK)",format_currency(diferencia))
        else:v3.metric("❌ Diferencia (Revisar)",format_currency(diferencia),delta=format_currency(diferencia),delta_color="inverse")
        if st.button("💾 Guardar o Actualizar Cuadre",type="primary",use_container_width=True):
            if venta_t==0:st.warning("No se puede guardar un cuadre con la Venta Total en cero.");return
            fecha_str=st.session_state.fecha_seleccionada.strftime("%Y-%m-%d");id_r=f"{st.session_state.tienda_seleccionada}-{fecha_str}";
            fila=[id_r,st.session_state.tienda_seleccionada,fecha_str,st.session_state.factura_inicial,st.session_state.factura_final,venta_t,json.dumps(st.session_state.tarjetas),json.dumps(st.session_state.consignaciones),json.dumps(st.session_state.gastos),json.dumps(st.session_state.efectivo),diferencia,datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
            try:
                cell=registros_ws.find(id_r,in_column=1)
                if cell:registros_ws.update(f'A{cell.row}',[fila]);st.success(f"✅ Cuadre para {st.session_state.tienda_seleccionada} el {fecha_str} fue **actualizado**!")
                else:registros_ws.append_row(fila);st.success(f"✅ Cuadre para {st.session_state.tienda_seleccionada} el {fecha_str} fue **guardado**!")
                clear_form_state();st.rerun()
            except Exception as e:st.error(f"Error al guardar: {e}")

def render_form_page(registros_ws, config_ws, tiendas, bancos):
    """Muestra la página principal del formulario de cuadre."""
    display_main_header(tiendas, registros_ws)
    st.divider()
    st.header("2. Formulario de Cuadre", anchor=False, divider="rainbow")
    display_general_info_section()
    display_payments_breakdown(bancos)
    display_summary_and_save(registros_ws)

# --- FLUJO PRINCIPAL DE LA APLICACIÓN ---

def main():
    """Función principal que renderiza la aplicación y maneja la navegación."""
    initialize_session_state()
    
    try:
        logo = Image.open("LOGO FERREINOX SAS BIC 2024.PNG")
        c1, c2 = st.columns([1, 4])
        c1.image(logo, width=150)
        c2.title("CUADRE DIARIO DE CAJA")
    except FileNotFoundError:
        st.title("CUADRE DIARIO DE CAJA")

    registros_ws, config_ws = connect_to_gsheet()

    if registros_ws and config_ws:
        # Menú de navegación en la barra lateral
        with st.sidebar:
            st.header("Navegación")
            if st.button("📝 Formulario de Cuadre", use_container_width=True):
                st.session_state.page = "Formulario"
            if st.button("📈 Reportes TXT", use_container_width=True):
                st.session_state.page = "Reportes"
        
        # Cargar datos de configuración una vez
        try:
            tiendas = [t for t in config_ws.col_values(1)[1:] if t]
            bancos = [b for b in config_ws.col_values(2)[1:] if b]
        except Exception as e:
            st.error(f"Error al cargar datos de 'Configuracion': {e}")
            tiendas, bancos = [], []

        # Renderizar la página seleccionada
        if st.session_state.page == "Formulario":
            render_form_page(registros_ws, config_ws, tiendas, bancos)
        elif st.session_state.page == "Reportes":
            render_reports_page(registros_ws, config_ws)
    else:
        st.info("Esperando conexión con Google Sheets...")

if __name__ == "__main__":
    main()
