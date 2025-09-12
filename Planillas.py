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

# --- CONEXIÓN A GOOGLE SHEETS ---
@st.cache_resource(ttl=600)
def connect_to_gsheet():
    """Establece conexión segura con Google Sheets y las 3 hojas de trabajo."""
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
        st.error(f"Error al conectar con Google Sheets: {e}")
        return None, None, None

# --- LÓGICA DE REPORTES ---
def get_account_mappings(config_ws):
    """
    Lee el mapeo de cuentas desde la hoja 'Configuracion'.
    Ahora lee 'TERCERO' para obtener su cuenta, NIT y nombre.
    """
    try:
        records = config_ws.get_all_records()
        mappings = {}
        for record in records:
            tipo = record.get("Tipo Movimiento")
            detalle = record.get("Detalle")
            cuenta = record.get("Cuenta Contable")

            if cuenta:
                cuenta_str = str(cuenta)
                # Mapeo para BANCO y TERCERO se basa en el 'Detalle'
                if (tipo == "BANCO" or tipo == "TERCERO") and detalle:
                    mappings[str(detalle)] = {
                        'cuenta': cuenta_str,
                        'nit': str(record.get("NIT", "")),
                        'nombre': str(record.get("Nombre Tercero", ""))
                    }
                # Mapeo para GASTO, TARJETA, EFECTIVO se basa en el 'Detalle' también
                elif tipo in ["GASTO", "TARJETA", "EFECTIVO"] and detalle:
                     mappings[str(detalle)] = {'cuenta': cuenta_str}

        return mappings
    except Exception as e:
        st.error(f"No se pudo leer el mapeo de cuentas. Revisa la estructura de la hoja 'Configuracion'. Error: {e}")
        return {}


def generate_txt_file(registros_ws, config_ws, start_date, end_date):
    """Genera el contenido del archivo TXT con la lógica de Terceros en el concepto."""
    st.info("Generando archivo... Esto puede tardar unos segundos.")

    all_records = registros_ws.get_all_records()
    account_mappings = get_account_mappings(config_ws)

    if not account_mappings:
        st.error("No se pudo generar el reporte: Faltan las cuentas contables en 'Configuracion'.")
        return None

    # El formato de fecha en la hoja de cálculo es dd/mm/yyyy
    filtered_records = [
        r for r in all_records
        if start_date <= datetime.strptime(r.get('Fecha', '01/01/1900'), '%d/%m/%Y').date() <= end_date
    ]

    if not filtered_records:
        st.warning("No se encontraron registros en el rango de fechas seleccionado.")
        return None

    filtered_records.sort(key=lambda r: (r.get('Tienda', ''), r.get('Fecha', '')))

    txt_lines = []

    for record in filtered_records:
        consecutivo_del_registro = record.get('Consecutivo_Asignado', '0')
        if consecutivo_del_registro == '0' or not consecutivo_del_registro:
            st.warning(f"El registro de la tienda {record.get('Tienda')} del {record.get('Fecha')} no tiene un consecutivo asignado. Se usará '0'.")

        tienda_original = str(record.get('Tienda', ''))
        tienda_descripcion = re.sub(r'[\(\)]', '', tienda_original).strip()
        centro_costo = tienda_original

        fecha_cuadre = record['Fecha']
        total_debito_dia = 0

        movimientos = {
            'TARJETA': json.loads(record.get('Tarjetas', '[]')),
            'CONSIGNACION': json.loads(record.get('Consignaciones', '[]')),
            'GASTO': json.loads(record.get('Gastos', '[]')),
            'EFECTIVO': json.loads(record.get('Efectivo', '[]'))
        }

        for tipo_mov, data_list in movimientos.items():
            for item in data_list:
                valor = float(item.get('Valor', 0)) if isinstance(item, dict) else float(item)
                if valor == 0: continue
                total_debito_dia += valor

                cuenta = ""
                nit_tercero, nombre_tercero = "800224617", "FERREINOX SAS BIC"
                serie_documento = centro_costo
                descripcion = f"Ventas planillas contado {tienda_descripcion}"

                if tipo_mov == 'TARJETA':
                    cuenta = account_mappings.get('TARJETAS', {}).get('cuenta', 'ERR_TARJETA')
                    serie_documento = f"T{centro_costo}"
                elif tipo_mov == 'CONSIGNACION':
                    banco = item.get('Banco')
                    cuenta = account_mappings.get(banco, {}).get('cuenta', f'ERR_{banco}')
                elif tipo_mov == 'GASTO':
                    cuenta = account_mappings.get('GASTOS', {}).get('cuenta', 'ERR_GASTO')
                elif tipo_mov == 'EFECTIVO':
                    tipo_especifico = item.get('Tipo', 'Efectivo Entregado')
                    destino_tercero = item.get('Destino/Tercero')

                    if tipo_especifico == "Efectivo Entregado" and destino_tercero and destino_tercero != "N/A":
                        tercero_info = account_mappings.get(destino_tercero)
                        if tercero_info:
                            cuenta = tercero_info.get('cuenta', f'ERR_{destino_tercero}')
                            nit_tercero = tercero_info.get('nit', nit_tercero)
                            nombre_tercero = tercero_info.get('nombre', nombre_tercero)
                            descripcion = f"Ventas planillas contado {tienda_descripcion} {nombre_tercero}"
                        else:
                            cuenta = f'ERR_{destino_tercero}'
                    else:
                        cuenta = account_mappings.get(tipo_especifico, {}).get('cuenta', f'ERR_{tipo_especifico}')

                linea = "|".join([
                    fecha_cuadre, str(consecutivo_del_registro), str(cuenta), "8",
                    descripcion, serie_documento, str(consecutivo_del_registro),
                    str(valor), "0", centro_costo, nit_tercero, nombre_tercero, "0"
                ])
                txt_lines.append(linea)

        if total_debito_dia > 0:
            cuenta_venta = "11050501"
            descripcion_credito = f"Ventas planillas contado {tienda_descripcion}"
            linea_credito = "|".join([
                fecha_cuadre, str(consecutivo_del_registro), str(cuenta_venta), "8",
                descripcion_credito, centro_costo, str(consecutivo_del_registro),
                "0", str(total_debito_dia), centro_costo, "800224617", "FERREINOX SAS BIC", "0"
            ])
            txt_lines.append(linea_credito)

    return "\n".join(txt_lines)

def render_reports_page(registros_ws, config_ws):
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

# --- LÓGICA DEL FORMULARIO ---
def initialize_session_state():
    defaults = {
        'page': 'Formulario', 'venta_total_dia': 0.0, 'factura_inicial': "", 'factura_final': "",
        'tarjetas': [], 'consignaciones': [], 'gastos': [], 'efectivo': [], 'form_cleared': False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def clear_form_state():
    tienda = st.session_state.get('tienda_seleccionada', None)
    fecha = st.session_state.get('fecha_seleccionada', datetime.now().date())
    for key in list(st.session_state.keys()):
        if key not in ['page', 'tienda_seleccionada', 'fecha_seleccionada']:
            del st.session_state[key]
    initialize_session_state()
    st.session_state.tienda_seleccionada = tienda
    st.session_state.fecha_seleccionada = fecha
    st.session_state.form_cleared = True

def format_currency(num):
    return f"${int(num):,}".replace(",", ".") if isinstance(num, (int, float)) else "$0"

def load_cuadre_data(registros_ws):
    """Carga los datos de un cuadre existente."""
    id_registro = f"{st.session_state.tienda_seleccionada}-{st.session_state.fecha_seleccionada.strftime('%d/%m/%Y')}"
    try:
        cell = registros_ws.find(id_registro, in_column=1)
        if cell:
            row_data = registros_ws.get(f'A{cell.row}:M{cell.row}')[0]
            clear_form_state()

            st.session_state.factura_inicial = row_data[4] if len(row_data) > 4 else ""
            st.session_state.factura_final = row_data[5] if len(row_data) > 5 else ""
            st.session_state.venta_total_dia = float(row_data[6]) if len(row_data) > 6 and row_data[6] else 0.0
            st.session_state.tarjetas = json.loads(row_data[7]) if len(row_data) > 7 and row_data[7] else []
            st.session_state.consignaciones = json.loads(row_data[8]) if len(row_data) > 8 and row_data[8] else []
            st.session_state.gastos = json.loads(row_data[9]) if len(row_data) > 9 and row_data[9] else []
            st.session_state.efectivo = json.loads(row_data[10]) if len(row_data) > 10 and row_data[10] else []
            st.toast("✅ Cuadre cargado.", icon="📄")
        else:
            st.warning("No se encontró cuadre para esta selección.")
            clear_form_state()
    except Exception as e:
        st.error(f"Error al cargar datos. Verifica la estructura de la hoja 'Registros'. Error: {e}")
        clear_form_state()

# --- FUNCIONES PARA MANEJAR CONSECUTIVOS ---
def get_next_consecutive(consecutivos_ws, tienda):
    """Obtiene el siguiente número consecutivo para una tienda."""
    try:
        cell = consecutivos_ws.find(tienda, in_column=1)
        if cell:
            last_consecutive = int(consecutivos_ws.cell(cell.row, 2).value)
            return last_consecutive + 1
        else:
            starting_consecutives = {
                '156 (PEREIRA)': 11509, '189 (DOSQUEBRADAS)': 11566, '157': 10990,
                '158': 11565, '238': 10924, '439': 11563
            }
            return starting_consecutives.get(tienda, 1000)
    except Exception as e:
        st.error(f"Error al obtener consecutivo: {e}")
        return None

def update_consecutive(consecutivos_ws, tienda, new_consecutive):
    """Actualiza o crea el registro del último consecutivo para una tienda."""
    try:
        cell = consecutivos_ws.find(tienda, in_column=1)
        if cell:
            consecutivos_ws.update_cell(cell.row, 2, new_consecutive)
        else:
            consecutivos_ws.append_row([tienda, new_consecutive])
    except Exception as e:
        st.error(f"Error al actualizar consecutivo: {e}")

# --- FUNCIÓN DE GUARDADO ---
def display_summary_and_save(registros_ws, consecutivos_ws):
    """Muestra el resumen y maneja la lógica de guardado/actualización."""
    st.header("3. Verificación y Guardado", anchor=False, divider="rainbow")
    with st.container(border=True):
        sub_t = sum(float(t.get('Valor', 0)) for t in st.session_state.tarjetas)
        sub_c = sum(float(c.get('Valor', 0)) for c in st.session_state.consignaciones)
        sub_g = sum(float(g.get('Valor', 0)) for g in st.session_state.gastos)
        sub_e = sum(float(e.get('Valor', 0)) for e in st.session_state.efectivo)
        total_d = sub_t + sub_c + sub_g + sub_e
        venta_t = float(st.session_state.get('venta_total_dia', 0.0))
        diferencia = venta_t - total_d

        v1, v2, v3 = st.columns(3)
        v1.metric("💰 Venta Total (Sistema)", format_currency(venta_t))
        v2.metric("📊 Suma del Desglose", format_currency(total_d))

        v3.metric(
            "✅ Diferencia" if diferencia == 0 else "❌ Diferencia",
            format_currency(diferencia),
            delta=format_currency(diferencia) if diferencia != 0 else None,
            delta_color="inverse" if diferencia != 0 else "off"
        )

        if st.button("💾 Guardar o Actualizar Cuadre", type="primary", use_container_width=True):
            tienda_seleccionada = st.session_state.get("tienda_seleccionada")
            if not tienda_seleccionada:
                st.warning("🛑 Por favor, seleccione una tienda antes de guardar.")
                return

            if venta_t == 0:
                st.warning("Venta Total no puede ser cero.")
                return

            fecha_str = st.session_state.fecha_seleccionada.strftime("%d/%m/%Y")
            id_r = f"{tienda_seleccionada}-{fecha_str}"

            try:
                cell = registros_ws.find(id_r, in_column=1)

                if cell:
                    consecutivo_asignado = registros_ws.cell(cell.row, 2).value
                    st.info(f"Actualizando registro. El consecutivo se mantendrá: {consecutivo_asignado}")
                else:
                    consecutivo_asignado = get_next_consecutive(consecutivos_ws, tienda_seleccionada)
                    if consecutivo_asignado is None: return
                    update_consecutive(consecutivos_ws, tienda_seleccionada, consecutivo_asignado)

                fila = [
                    id_r, consecutivo_asignado, tienda_seleccionada, fecha_str,
                    st.session_state.factura_inicial, st.session_state.factura_final, venta_t,
                    json.dumps(st.session_state.tarjetas), json.dumps(st.session_state.consignaciones),
                    json.dumps(st.session_state.gastos), json.dumps(st.session_state.efectivo),
                    diferencia, datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                ]

                if cell:
                    registros_ws.update(f'A{cell.row}', [fila])
                    st.success(f"✅ Cuadre para {tienda_seleccionada} el {fecha_str} fue **actualizado**!")
                else:
                    registros_ws.append_row(fila)
                    st.success(f"✅ Cuadre para {tienda_seleccionada} el {fecha_str} fue **guardado** con el consecutivo **{consecutivo_asignado}**!")

            except Exception as e:
                st.error(f"Error al guardar: {e}")

# --- FUNCIONES DE VISUALIZACIÓN ---
def display_main_header(tiendas_list, registros_ws):
    st.header("1. Selección de Registro", anchor=False, divider="rainbow")
    c1,c2,c3,c4 = st.columns([2,2,1,1])
    c1.selectbox("Tienda", options=tiendas_list, key="tienda_seleccionada", on_change=clear_form_state)
    c2.date_input("Fecha", key="fecha_seleccionada", on_change=clear_form_state, format="DD/MM/YYYY")
    c3.button("🔍 Cargar Cuadre", on_click=load_cuadre_data, args=[registros_ws], use_container_width=True)
    c4.button("✨ Iniciar Nuevo", on_click=clear_form_state, use_container_width=True)

def display_general_info_section():
    with st.container(border=True):
        st.subheader("📋 Información General")
        c1,c2,c3=st.columns(3)
        st.session_state.factura_inicial=c1.text_input("Factura Inicial", value=st.session_state.get('factura_inicial', ""))
        st.session_state.factura_final=c2.text_input("Factura Final", value=st.session_state.get('factura_final', ""))
        st.session_state.venta_total_dia=c3.number_input("💰 Venta Total (Sistema)",min_value=0.0,step=1000.0,value=float(st.session_state.get('venta_total_dia', 0.0)),format="%.0f")

def display_payments_breakdown(bancos_list, terceros_list):
    with st.container(border=True):
        st.subheader("🧾 Desglose de Pagos")
        display_tarjetas_section()
        display_consignaciones_section(bancos_list)
        display_gastos_section()
        display_efectivo_section(terceros_list)

def display_tarjetas_section():
    with st.expander("💳 **Tarjetas**", expanded=True):
        with st.form("form_tarjetas", clear_on_submit=True):
            valor = st.number_input("Valor", min_value=1.0, step=1000.0, format="%.0f", label_visibility="collapsed")
            if st.form_submit_button("Agregar Tarjeta", use_container_width=True):
                if valor > 0:
                    st.session_state.tarjetas.append({'Valor': valor})
                    st.toast(f"Agregado: {format_currency(valor)}")
                    st.rerun()
        if st.session_state.tarjetas:
            df_data = [item if isinstance(item, dict) else {'Valor': item} for item in st.session_state.tarjetas]
            df = pd.DataFrame(df_data)
            df['Eliminar'] = False

            edited_df = st.data_editor(
                df, key='editor_tarjetas', hide_index=True, use_container_width=True,
                column_config={"Valor": st.column_config.NumberColumn("Valor", format="$ %.0f"), "Eliminar": st.column_config.CheckboxColumn("Eliminar", width="small")}
            )

            if edited_df['Eliminar'].any():
                st.session_state.tarjetas = [t for i, t in enumerate(df_data) if i not in edited_df[edited_df['Eliminar']].index]
                st.toast("Tarjeta(s) eliminada(s).")
                st.rerun()
            else:
                cleaned_df = edited_df.drop(columns=['Eliminar'])
                cleaned_df['Valor'] = pd.to_numeric(cleaned_df['Valor'], errors='coerce').fillna(0)
                st.session_state.tarjetas = cleaned_df[['Valor']].to_dict('records')

        subtotal_tarjetas = sum(float(item.get('Valor', 0)) for item in st.session_state.tarjetas)
        st.metric("Subtotal Tarjetas", format_currency(subtotal_tarjetas))

def display_dynamic_list_section(title, key, form_inputs, options_map=None):
    if options_map is None: options_map = {}

    with st.expander(f"**{title}**", expanded=True):
        with st.form(f"form_{key}", clear_on_submit=True):
            cols = st.columns(len(form_inputs))
            data = {}
            for i, (k, t, o) in enumerate(form_inputs):
                if t == "selectbox":
                    options_list = options_map.get(k, o.get('options', []))
                    data[k] = cols[i].selectbox(o['label'], options=options_list, label_visibility="collapsed")
                elif t == "number_input":
                    data[k] = cols[i].number_input(o['label'], min_value=0.0, step=1000.0, format="%.0f", label_visibility="collapsed")
                elif t == "date_input":
                    data[k] = cols[i].date_input(o['label'], value=datetime.now().date(), label_visibility="collapsed", format="DD/MM/YYYY")
                else:
                    data[k] = cols[i].text_input(o['label'], label_visibility="collapsed")

            if st.form_submit_button(f"Agregar {title.split(' ')[1][:-1]}", use_container_width=True):
                if data.get("Valor", 0) > 0:
                    if 'Fecha' in data and isinstance(data['Fecha'], datetime.date):
                        data['Fecha'] = data['Fecha'].strftime("%d/%m/%Y")
                    st.session_state[key].append(data)
                    st.toast("Registro agregado.")
                    st.rerun()

        if st.session_state[key]:
            df = pd.DataFrame(st.session_state[key])
            df['Eliminar'] = False
            config = {
                "Valor": st.column_config.NumberColumn("Valor", format="$ %.0f"),
                "Eliminar": st.column_config.CheckboxColumn("Eliminar", width="small")
            }
            # CORRECCIÓN: Se configura dinámicamente el selectbox para el data_editor
            for col_name, options_list in options_map.items():
                if col_name in df.columns:
                    config[col_name] = st.column_config.SelectboxColumn(col_name, options=options_list, required=True)

            edited_df = st.data_editor(df, key=f'editor_{key}', hide_index=True, use_container_width=True, column_config=config)

            if edited_df['Eliminar'].any():
                st.session_state[key] = [item for i, item in enumerate(st.session_state[key]) if i not in edited_df[edited_df['Eliminar']].index]
                st.toast("Registro(s) eliminado(s).")
                st.rerun()
            else:
                df_c = edited_df.drop(columns=['Eliminar'])
                st.session_state[key] = df_c.to_dict('records')

        st.metric(f"Subtotal {title.split(' ')[1]}", format_currency(sum(float(item.get('Valor', 0)) for item in st.session_state[key])))

def display_consignaciones_section(bancos_list):
    display_dynamic_list_section(
        "🏦 Consignaciones", "consignaciones",
        [("Banco", "selectbox", {"label": "Banco"}),
         ("Valor", "number_input", {"label": "Valor"}),
         ("Fecha", "date_input", {"label": "Fecha"})],
        options_map={"Banco": bancos_list}
    )

def display_gastos_section():
    display_dynamic_list_section(
        "💸 Gastos", "gastos",
        [("Descripción", "text_input", {"label": "Descripción"}),
         ("Valor", "number_input", {"label": "Valor"})]
    )

def display_efectivo_section(terceros_list):
    terceros_con_na = ["N/A"] + terceros_list
    display_dynamic_list_section(
        "💵 Efectivo", "efectivo",
        [("Tipo", "selectbox", {"label": "Tipo Movimiento", "options": ["Efectivo Entregado", "Reintegro Caja Menor"]}),
         ("Destino/Tercero", "selectbox", {"label": "Destino/Tercero"}),
         ("Valor", "number_input", {"label": "Valor"})],
        options_map={
            "Tipo": ["Efectivo Entregado", "Reintegro Caja Menor"],
            "Destino/Tercero": terceros_con_na
        }
    )

def render_form_page(registros_ws, config_ws, consecutivos_ws, tiendas, bancos, terceros):
    display_main_header(tiendas, registros_ws)
    st.divider()
    st.header("2. Formulario de Cuadre", anchor=False, divider="rainbow")
    display_general_info_section()
    display_payments_breakdown(bancos, terceros)
    display_summary_and_save(registros_ws, consecutivos_ws)

# --- FLUJO PRINCIPAL ---
def main():
    initialize_session_state()

    try:
        c1, c2 = st.columns([1, 4])
        c1.image("LOGO FERREINOX SAS BIC 2024.PNG", width=150)
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

        try:
            config_data = config_ws.get_all_records()
            tiendas = sorted(list(set(str(d['Detalle']) for d in config_data if d.get('Tipo Movimiento') == 'TIENDA')))
            bancos = sorted(list(set(str(d['Detalle']) for d in config_data if d.get('Tipo Movimiento') == 'BANCO' and d.get('Detalle'))))
            terceros = sorted(list(set(str(d['Detalle']) for d in config_data if d.get('Tipo Movimiento') == 'TERCERO' and d.get('Detalle'))))

        except Exception as e:
            st.error(f"Error al cargar datos de 'Configuracion': {e}")
            tiendas, bancos, terceros = [], [], []

        if not tiendas and st.session_state.page == "Formulario":
            st.error("🚨 No se encontraron tiendas en la hoja de 'Configuracion'.")
            st.warning("Por favor, agregue al menos una tienda (Tipo Movimiento = TIENDA) para poder continuar.")
            return

        if st.session_state.page == "Formulario":
            render_form_page(registros_ws, config_ws, consecutivos_ws, tiendas, bancos, terceros)
        elif st.session_state.page == "Reportes":
            render_reports_page(registros_ws, config_ws)
    else:
        st.info("Esperando conexión con Google Sheets...")

if __name__ == "__main__":
    main()
