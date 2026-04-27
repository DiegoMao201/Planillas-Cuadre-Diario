from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from app_shared import (
    append_vehicle_inspection_record,
    current_colombia_datetime,
    find_employee_by_cedula,
    format_colombia_timestamp,
    generate_inspection_id,
    get_last_vehicle_inspection_record,
    get_vehicle_inspection_worksheets,
    get_vehicle_profile_by_cedula,
    initialize_access_state,
    inject_shared_css,
    render_brand_header,
    render_sidebar,
    upsert_vehicle_profile,
    upload_request_attachment,
)


st.set_page_config(layout="wide", page_title="Inspeccion preoperacional vehiculos")

SEDES = ["SEDE DOSQUEBRADAS", "SEDE CERRITOS", "SEDE OLAYA"]
RESPONSABLES = [
    "HUGO NELSON ZAPATA",
    "DIEGO MAURICIO GARCIA RENGIFO",
    "CARLOS ANDRES VELEZ CARDONA",
    "ROBERT OLARTE TAMAYO",
    "JOSE ANDRES JORDAN MORENO",
    "MANUEL ALEJANDRO CHACON VILLA",
    "VICTOR MANUEL MUÑOZ",
    "Otros",
]
IDENTIFICATION_TYPES = [
    "Cédula de ciudadania",
    "Pasaporte",
    "Permiso Temporal",
    "Cédula de Extranjeria",
]
CARGO_OPTIONS = ["CONDUCTOR", "LIDER COMERCIAL", "VENDEDOR EXTERNO", "Otros"]
YES_NO_OPTIONS = ["Sí", "No"]
YES_NO_OPTIONS_PLAIN = ["Si", "No"]
CHECK_STATUS_OPTIONS = ["Bueno", "Malo", "Regular", "N/A"]
PLATE_STATUS_OPTIONS = ["Bueno", "Malo", "Regular"]
PLATE_FIELDS = [
    ("visible", "Visible"),
    ("pintura", "Estado de la pintura"),
    ("legible", "Legible"),
]
VEHICLE_CHECK_ITEMS = [
    ("cabina", "Cabina, cojineria y cerradura"),
    ("plumillas", "Plumillas, manijas, vidrios y espejos (sin rompimiento, ajustados)"),
    ("carroceria", "Carroceria y estructura general"),
    ("cinturones", "Estado de cinturones (sin rompimiento y funcionamiento correcto al realizar la prueba)"),
    ("fugas_motor", "El motor presenta fugas de aceite"),
    ("aceite_hidraulico", "Nivel de aceite hidraulico y motor"),
    ("nivel_agua", "Nivel de agua"),
    ("liquido_frenos", "Liquido de frenos y/o presion"),
    ("freno_parqueo", "Freno de parqueo"),
    ("fugas_transmision", "Fugas de aceite en la transmision"),
    ("llantas", "Estado llantas (sin perforaciones, huevos o deformidades)"),
    ("luces_reversa", "Luces de reversa"),
    ("pernos", "Esparragos y/o tuercas completas, pernos completos"),
    ("inflado_llantas", "Inflado de llantas"),
    ("llanta_repuesto", "Estado de la llanta de repuesto"),
    ("bateria", "Estado de bateria (ajustada y sin sulfatacion)"),
    ("rines", "Rines (sin fisuras). Pernos completos y ajustados"),
    ("labrado", "Profundidad de labrado de las llantas (mayor a 1,6 mm)"),
    ("bornes", "Estados de bornes, terminales y cables de bateria"),
    ("direccionales", "Luces direccionales traseras y delanteras"),
    ("luces_delanteras", "Luces delanteras (media y alta)"),
    ("luces_traseras", "Luces traseras (stop - freno - reversa - parqueo)"),
    ("luces_reserva", "Luces de reserva"),
    ("tablero", "Funcionamiento del tablero (temperatura, freno parqueo, revoluciones, velocimetro)"),
    ("pito", "Funcionamiento del pito o bocina"),
    ("kit_carreteras", "Kit de carreteras"),
    ("caja_herramientas", "Caja de herramienta con herramientas basicas"),
    ("extintor", "Extintor (revision presion, estado)"),
    ("botiquin", "Botiquin primeros auxilios"),
    ("linterna", "Linterna"),
    ("kit_quimicos", "Si se transportan productos quimicos se cuenta con kit de derrames, tarjetas de emergencia y rombos"),
]
CHECK_HEADER_BY_KEY = {
    "cabina": "Estado_Cabina_Cojineria_Cerradura",
    "plumillas": "Estado_Plumillas_Manijas_Vidrios_Espejos",
    "carroceria": "Estado_Carroceria_Estructura",
    "cinturones": "Estado_Cinturones",
    "fugas_motor": "Estado_Fugas_Aceite_Motor",
    "aceite_hidraulico": "Estado_Nivel_Aceite_Hidraulico_Motor",
    "nivel_agua": "Estado_Nivel_Agua",
    "liquido_frenos": "Estado_Liquido_Frenos_Presion",
    "freno_parqueo": "Estado_Freno_Parqueo",
    "fugas_transmision": "Estado_Fugas_Transmision",
    "llantas": "Estado_Llantas",
    "luces_reversa": "Estado_Luces_Reversa",
    "pernos": "Estado_Esparragos_Tuercas_Pernos",
    "inflado_llantas": "Estado_Inflado_Llantas",
    "llanta_repuesto": "Estado_Llanta_Repuesto",
    "bateria": "Estado_Bateria",
    "rines": "Estado_Rines",
    "labrado": "Estado_Profundidad_Labrado",
    "bornes": "Estado_Bornes_Terminales_Cables_Bateria",
    "direccionales": "Estado_Luces_Direccionales",
    "luces_delanteras": "Estado_Luces_Delanteras",
    "luces_traseras": "Estado_Luces_Traseras",
    "luces_reserva": "Estado_Luces_Reserva",
    "tablero": "Estado_Tablero",
    "pito": "Estado_Pito_Bocina",
    "kit_carreteras": "Estado_Kit_Carreteras",
    "caja_herramientas": "Estado_Caja_Herramientas",
    "extintor": "Estado_Extintor",
    "botiquin": "Estado_Botiquin",
    "linterna": "Estado_Linterna",
    "kit_quimicos": "Estado_Kit_Quimicos",
}


def inject_page_css() -> None:
    st.markdown(
        """
        <style>
        .vehicle-shell {
            border: 1px solid rgba(11, 57, 84, 0.12);
            border-radius: 22px;
            padding: 1.1rem;
            background:
                radial-gradient(circle at top left, rgba(24, 112, 160, 0.14), transparent 32%),
                linear-gradient(180deg, #ffffff 0%, #f5f9fc 100%);
            box-shadow: 0 16px 40px rgba(11, 57, 84, 0.07);
        }
        .vehicle-title {
            font-weight: 800;
            color: #0b3954;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }
        .vehicle-note {
            border-left: 4px solid #1870a0;
            background: #f0f7fb;
            padding: 0.8rem 0.95rem;
            border-radius: 10px;
            color: #274257;
            margin: 0.7rem 0 1rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def employee_summary_card(employee: dict[str, str]) -> None:
    st.markdown(
        f"""
        <div class="ferreinox-card">
            <span class="ferreinox-badge">Conductor validado</span>
            <div class="ferreinox-grid">
                <div class="ferreinox-field"><label>Nombre</label><span>{employee.get('nombre_completo', '')}</span></div>
                <div class="ferreinox-field"><label>Cedula</label><span>{employee.get('cedula', '')}</span></div>
                <div class="ferreinox-field"><label>N. Empleado</label><span>{employee.get('numero_empleado', '')}</span></div>
                <div class="ferreinox-field"><label>Cargo</label><span>{employee.get('cargo', '')}</span></div>
                <div class="ferreinox-field"><label>Sede</label><span>{employee.get('sede', '')}</span></div>
                <div class="ferreinox-field"><label>Correo</label><span>{employee.get('correo', '')}</span></div>
                <div class="ferreinox-field"><label>Telefono</label><span>{employee.get('telefono', '')}</span></div>
                <div class="ferreinox-field"><label>Ingreso</label><span>{employee.get('fecha_ingreso', '')}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def initialize_form_state() -> None:
    colombia_now = current_colombia_datetime()
    defaults = {
        "vehicle_cedula": "",
        "vehicle_sede": SEDES[0],
        "vehicle_fecha_inspeccion": colombia_now.date(),
        "vehicle_responsable": RESPONSABLES[0],
        "vehicle_responsable_otro": "",
        "vehicle_tipo_identificacion": IDENTIFICATION_TYPES[0],
        "vehicle_numero_identificacion": "",
        "vehicle_nombre_conductor": "",
        "vehicle_numero_documento_conductor": "",
        "vehicle_cargo": CARGO_OPTIONS[0],
        "vehicle_cargo_otro": "",
        "vehicle_placa": "",
        "vehicle_placa_visible": "Bueno",
        "vehicle_placa_pintura": "Bueno",
        "vehicle_placa_legible": "Bueno",
        "vehicle_licencia": "Sí",
        "vehicle_medicamentos": "No",
        "vehicle_descanso": "Si",
        "vehicle_alcohol": "No",
        "vehicle_tarjeta_propiedad": "Sí",
        "vehicle_soat_vigente": "Sí",
        "vehicle_soat_vencimiento": colombia_now.date(),
        "vehicle_tecnomecanica_vigente": "Sí",
        "vehicle_tecnomecanica_vencimiento": colombia_now.date(),
        "vehicle_extintor_vigente": "Si",
        "vehicle_extintor_vencimiento": colombia_now.date(),
        "vehicle_kilometraje": "",
        "vehicle_cambio_aceite": colombia_now.date(),
        "vehicle_mantenimiento_preventivo": colombia_now.date(),
        "vehicle_fallas": "",
        "vehicle_tratamiento_datos": "Sí",
        "vehicle_profile_loaded": "",
        "vehicle_employee_loaded": "",
        "vehicle_history_message": "",
        "vehicle_reset_after_submit": False,
        "vehicle_submit_success": "",
        "vehicle_submit_warning": "",
    }
    for item_key, _ in VEHICLE_CHECK_ITEMS:
        defaults[f"vehicle_check_{item_key}"] = "Bueno"
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _safe_date(value: str, fallback: date) -> date:
    if not value:
        return fallback
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return fallback


def sync_employee_defaults(employee: dict[str, str] | None) -> None:
    if not employee:
        return

    lookup = employee.get("cedula_lookup") or employee.get("cedula", "")
    if st.session_state.get("vehicle_employee_loaded") == lookup:
        return

    st.session_state["vehicle_employee_loaded"] = lookup
    st.session_state["vehicle_cedula"] = employee.get("cedula", st.session_state.get("vehicle_cedula", ""))
    st.session_state["vehicle_numero_identificacion"] = employee.get("cedula", "")
    st.session_state["vehicle_nombre_conductor"] = employee.get("nombre_completo", "")
    st.session_state["vehicle_numero_documento_conductor"] = employee.get("cedula", "")

    employee_cargo = employee.get("cargo", "").upper().strip()
    if employee_cargo in CARGO_OPTIONS:
        st.session_state["vehicle_cargo"] = employee_cargo
        st.session_state["vehicle_cargo_otro"] = ""
    elif employee_cargo:
        st.session_state["vehicle_cargo"] = "Otros"
        st.session_state["vehicle_cargo_otro"] = employee.get("cargo", "")

    employee_sede = employee.get("sede", "").upper().strip()
    if employee_sede in SEDES:
        st.session_state["vehicle_sede"] = employee_sede


def sync_profile_defaults(profile: dict[str, str] | None) -> None:
    if not profile:
        return

    signature = "|".join(
        [
            profile.get("Cedula", ""),
            profile.get("Placa_Vehiculo", ""),
            profile.get("Fecha_Vencimiento_SOAT", ""),
            profile.get("Fecha_Vencimiento_Tecnomecanica", ""),
            profile.get("Fecha_Vencimiento_Extintor", ""),
        ]
    )
    if st.session_state.get("vehicle_profile_loaded") == signature:
        return

    st.session_state["vehicle_profile_loaded"] = signature
    for state_key, record_key in {
        "vehicle_tipo_identificacion": "Tipo_Identificacion",
        "vehicle_numero_identificacion": "Numero_Identificacion",
        "vehicle_nombre_conductor": "Nombre_Conductor",
        "vehicle_numero_documento_conductor": "Numero_Documento_Conductor",
        "vehicle_placa": "Placa_Vehiculo",
    }.items():
        value = profile.get(record_key, "")
        if value:
            st.session_state[state_key] = value

    cargo_value = profile.get("Cargo_Conductor", "")
    if cargo_value in CARGO_OPTIONS:
        st.session_state["vehicle_cargo"] = cargo_value
        st.session_state["vehicle_cargo_otro"] = ""
    elif cargo_value:
        st.session_state["vehicle_cargo"] = "Otros"
        st.session_state["vehicle_cargo_otro"] = cargo_value

    if profile.get("Sede") in SEDES:
        st.session_state["vehicle_sede"] = profile["Sede"]

    st.session_state["vehicle_soat_vencimiento"] = _safe_date(
        profile.get("Fecha_Vencimiento_SOAT", ""),
        st.session_state["vehicle_soat_vencimiento"],
    )
    st.session_state["vehicle_tecnomecanica_vencimiento"] = _safe_date(
        profile.get("Fecha_Vencimiento_Tecnomecanica", ""),
        st.session_state["vehicle_tecnomecanica_vencimiento"],
    )
    st.session_state["vehicle_extintor_vencimiento"] = _safe_date(
        profile.get("Fecha_Vencimiento_Extintor", ""),
        st.session_state["vehicle_extintor_vencimiento"],
    )
    st.session_state["vehicle_cambio_aceite"] = _safe_date(
        profile.get("Fecha_Ultimo_Cambio_Aceite", ""),
        st.session_state["vehicle_cambio_aceite"],
    )
    st.session_state["vehicle_mantenimiento_preventivo"] = _safe_date(
        profile.get("Fecha_Ultimo_Mantenimiento_Preventivo", ""),
        st.session_state["vehicle_mantenimiento_preventivo"],
    )


def apply_history_record(record: dict[str, str]) -> None:
    base_mapping = {
        "vehicle_responsable": "Responsable_Inspeccion",
        "vehicle_responsable_otro": "Responsable_Inspeccion_Otro",
        "vehicle_tipo_identificacion": "Tipo_Identificacion",
        "vehicle_numero_identificacion": "Numero_Identificacion",
        "vehicle_nombre_conductor": "Nombre_Conductor",
        "vehicle_numero_documento_conductor": "Numero_Documento_Conductor",
        "vehicle_placa": "Placa_Vehiculo",
        "vehicle_licencia": "Licencia_Vigente",
        "vehicle_medicamentos": "Medicamentos_Somnolencia",
        "vehicle_descanso": "Descanso_Minimo_6_Horas",
        "vehicle_alcohol": "Alcohol_O_Sustancias",
        "vehicle_tarjeta_propiedad": "Tarjeta_Propiedad",
        "vehicle_soat_vigente": "SOAT_Vigente",
        "vehicle_tecnomecanica_vigente": "Certificado_Tecnomecanica",
        "vehicle_extintor_vigente": "Extintor_Vigente",
        "vehicle_kilometraje": "Kilometraje_Actual",
        "vehicle_fallas": "Fallas_Plan_Accion",
        "vehicle_tratamiento_datos": "Tratamiento_Datos",
    }
    for state_key, record_key in base_mapping.items():
        value = record.get(record_key, "")
        if value:
            st.session_state[state_key] = value

    if record.get("Sede") in SEDES:
        st.session_state["vehicle_sede"] = record["Sede"]

    cargo_value = record.get("Cargo_Conductor", "")
    if cargo_value in CARGO_OPTIONS:
        st.session_state["vehicle_cargo"] = cargo_value
        st.session_state["vehicle_cargo_otro"] = ""
    elif cargo_value:
        st.session_state["vehicle_cargo"] = "Otros"
        st.session_state["vehicle_cargo_otro"] = cargo_value

    st.session_state["vehicle_placa_visible"] = record.get("Estado_Placa_Visible", st.session_state["vehicle_placa_visible"])
    st.session_state["vehicle_placa_pintura"] = record.get("Estado_Placa_Pintura", st.session_state["vehicle_placa_pintura"])
    st.session_state["vehicle_placa_legible"] = record.get("Estado_Placa_Legible", st.session_state["vehicle_placa_legible"])
    st.session_state["vehicle_soat_vencimiento"] = _safe_date(
        record.get("Fecha_Vencimiento_SOAT", ""),
        st.session_state["vehicle_soat_vencimiento"],
    )
    st.session_state["vehicle_tecnomecanica_vencimiento"] = _safe_date(
        record.get("Fecha_Vencimiento_Tecnomecanica", ""),
        st.session_state["vehicle_tecnomecanica_vencimiento"],
    )
    st.session_state["vehicle_extintor_vencimiento"] = _safe_date(
        record.get("Fecha_Vencimiento_Extintor", ""),
        st.session_state["vehicle_extintor_vencimiento"],
    )
    st.session_state["vehicle_cambio_aceite"] = _safe_date(
        record.get("Fecha_Ultimo_Cambio_Aceite", ""),
        st.session_state["vehicle_cambio_aceite"],
    )
    st.session_state["vehicle_mantenimiento_preventivo"] = _safe_date(
        record.get("Fecha_Ultimo_Mantenimiento_Preventivo", ""),
        st.session_state["vehicle_mantenimiento_preventivo"],
    )
    st.session_state["vehicle_fecha_inspeccion"] = current_colombia_datetime().date()

    for item_key, _ in VEHICLE_CHECK_ITEMS:
        header = CHECK_HEADER_BY_KEY[item_key]
        if record.get(header):
            st.session_state[f"vehicle_check_{item_key}"] = record[header]


def clear_daily_answers() -> None:
    st.session_state["vehicle_fecha_inspeccion"] = current_colombia_datetime().date()
    st.session_state["vehicle_responsable"] = RESPONSABLES[0]
    st.session_state["vehicle_responsable_otro"] = ""
    st.session_state["vehicle_placa_visible"] = "Bueno"
    st.session_state["vehicle_placa_pintura"] = "Bueno"
    st.session_state["vehicle_placa_legible"] = "Bueno"
    st.session_state["vehicle_licencia"] = "Sí"
    st.session_state["vehicle_medicamentos"] = "No"
    st.session_state["vehicle_descanso"] = "Si"
    st.session_state["vehicle_alcohol"] = "No"
    st.session_state["vehicle_tarjeta_propiedad"] = "Sí"
    st.session_state["vehicle_soat_vigente"] = "Sí"
    st.session_state["vehicle_tecnomecanica_vigente"] = "Sí"
    st.session_state["vehicle_extintor_vigente"] = "Si"
    st.session_state["vehicle_kilometraje"] = ""
    st.session_state["vehicle_fallas"] = ""
    st.session_state["vehicle_tratamiento_datos"] = "Sí"
    for item_key, _ in VEHICLE_CHECK_ITEMS:
        st.session_state[f"vehicle_check_{item_key}"] = "Bueno"


def consume_post_submit_reset() -> None:
    if not st.session_state.get("vehicle_reset_after_submit"):
        return
    clear_daily_answers()
    st.session_state["vehicle_reset_after_submit"] = False


def main() -> None:
    initialize_access_state()
    initialize_form_state()
    consume_post_submit_reset()
    inject_shared_css()
    inject_page_css()
    render_sidebar("Inspeccion vehiculos")
    render_brand_header(
        "Inspeccion preoperacional de vehiculos",
        "Formulario publico para vehiculos con perfil persistente, historial reusable y registro diario de inspeccion.",
    )

    st.markdown(
        """
        <div class="vehicle-shell">
            <div class="vehicle-title">Ferreinox inspeccion preoperacional a vehiculos 2026</div>
            <div>Verificacion e inspeccion de las condiciones de los vehiculos de la empresa Ferreinox.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="vehicle-note">
            Digita la cedula del conductor para cargar datos base, recuperar el perfil guardado del vehiculo y reutilizar respuestas con el boton de historial.
        </div>
        """,
        unsafe_allow_html=True,
    )

    cedula = st.text_input("Cedula del conductor", key="vehicle_cedula", placeholder="Ejemplo: 1088266407")

    try:
        employee = find_employee_by_cedula(cedula) if cedula else None
    except Exception as error:
        st.error(f"No se pudo leer la base de empleados: {error}")
        return

    if employee:
        sync_employee_defaults(employee)
        employee_summary_card(employee)
    elif cedula:
        st.warning("No se encontro un empleado con esa cedula en base_datos_empleados.xlsx.")

    profile = None
    worksheets = None
    history_warning = ""
    if cedula:
        try:
            worksheets = get_vehicle_inspection_worksheets()
            profile = get_vehicle_profile_by_cedula(worksheets["profiles"], cedula)
            sync_profile_defaults(profile)
        except Exception as error:
            history_warning = (
                "No se pudo cargar el perfil o historial automatico en este momento. "
                f"Puedes continuar diligenciando el formulario. Detalle: {error}"
            )

    action_cols = st.columns([1, 1.2, 2.4])
    with action_cols[0]:
        if st.button("Llenar respuestas con historial", use_container_width=True, disabled=not bool(cedula)):
            try:
                if worksheets is None:
                    worksheets = get_vehicle_inspection_worksheets()
                history_record = get_last_vehicle_inspection_record(
                    worksheets["records"],
                    cedula,
                    st.session_state.get("vehicle_placa", ""),
                )
                if history_record:
                    apply_history_record(history_record)
                    st.session_state["vehicle_history_message"] = "Se cargaron las respuestas del ultimo historial disponible."
                else:
                    st.session_state["vehicle_history_message"] = "No se encontro historial previo para esa cedula o placa."
                st.rerun()
            except Exception as error:
                st.error(f"No se pudo cargar el historial: {error}")
    with action_cols[1]:
        if st.button("Limpiar respuestas diarias", use_container_width=True):
            clear_daily_answers()
            st.rerun()
    with action_cols[2]:
        if st.session_state.get("vehicle_history_message"):
            st.info(st.session_state["vehicle_history_message"])

    if st.session_state.get("vehicle_submit_success"):
        st.success(st.session_state["vehicle_submit_success"])
        st.session_state["vehicle_submit_success"] = ""
    if st.session_state.get("vehicle_submit_warning"):
        st.warning(st.session_state["vehicle_submit_warning"])
        st.session_state["vehicle_submit_warning"] = ""

    if history_warning:
        st.warning(history_warning)

    if profile:
        st.caption(
            f"Perfil guardado encontrado para la placa {profile.get('Placa_Vehiculo', 'sin placa')} con SOAT {profile.get('Fecha_Vencimiento_SOAT', 'sin fecha')}, tecnomecanica {profile.get('Fecha_Vencimiento_Tecnomecanica', 'sin fecha')} y extintor {profile.get('Fecha_Vencimiento_Extintor', 'sin fecha')}."
        )

    with st.form("formulario_inspeccion_vehiculos"):
        st.subheader("Datos generales")
        c1, c2, c3 = st.columns(3)
        sede = c1.selectbox("Sede", options=SEDES, key="vehicle_sede")
        fecha_inspeccion = c2.date_input("Fecha", key="vehicle_fecha_inspeccion", format="DD/MM/YYYY")
        responsable = c3.selectbox("Responsable de la inspeccion", options=RESPONSABLES, key="vehicle_responsable")

        responsable_otro = ""
        if responsable == "Otros":
            responsable_otro = st.text_input("Indique otro responsable", key="vehicle_responsable_otro")

        st.subheader("Datos del conductor")
        c4, c5, c6 = st.columns(3)
        tipo_identificacion = c4.selectbox("Tipo de identificacion", options=IDENTIFICATION_TYPES, key="vehicle_tipo_identificacion")
        numero_identificacion = c5.text_input("Numero de identificacion", key="vehicle_numero_identificacion")
        nombre_conductor = c6.text_input("Nombre del conductor", key="vehicle_nombre_conductor")

        c7, c8, c9 = st.columns(3)
        numero_documento_conductor = c7.text_input("Numero de documento del conductor", key="vehicle_numero_documento_conductor")
        cargo = c8.selectbox("Cargo de la persona que maneja el vehiculo", options=CARGO_OPTIONS, key="vehicle_cargo")
        placa = c9.text_input("Digite la placa de vehiculo a inspeccionar", key="vehicle_placa")

        cargo_otro = ""
        if cargo == "Otros":
            cargo_otro = st.text_input("Indique otro cargo", key="vehicle_cargo_otro")

        st.subheader("Estado de la placa del vehiculo")
        p1, p2, p3 = st.columns(3)
        placa_visible = p1.selectbox("Visible", options=PLATE_STATUS_OPTIONS, key="vehicle_placa_visible")
        placa_pintura = p2.selectbox("Estado de la pintura", options=PLATE_STATUS_OPTIONS, key="vehicle_placa_pintura")
        placa_legible = p3.selectbox("Legible", options=PLATE_STATUS_OPTIONS, key="vehicle_placa_legible")

        st.subheader("Condiciones del conductor y documentos")
        q1, q2 = st.columns(2)
        licencia = q1.radio(
            "El conductor cuenta con la licencia de conduccion vigente y acorde al vehiculo que esta conduciendo",
            options=YES_NO_OPTIONS,
            key="vehicle_licencia",
            horizontal=True,
        )
        medicamentos = q2.radio(
            "En las ultimas 8 horas ha consumido medicamentos que le generen somnolencia",
            options=YES_NO_OPTIONS_PLAIN,
            key="vehicle_medicamentos",
            horizontal=True,
        )
        st.caption("Si responde afirmativo a medicamentos o alcohol, o negativo a descanso, debe reportarlo de inmediato a Gestion Humana o SST.")

        q3, q4 = st.columns(2)
        descanso = q3.radio(
            "Ha descansado minimo 6 horas continuas",
            options=YES_NO_OPTIONS_PLAIN,
            key="vehicle_descanso",
            horizontal=True,
        )
        alcohol = q4.radio(
            "Ha consumido bebidas alcoholicas o sustancias psicoactivas en las ultimas 12 horas",
            options=YES_NO_OPTIONS_PLAIN,
            key="vehicle_alcohol",
            horizontal=True,
        )

        d1, d2, d3 = st.columns(3)
        tarjeta_propiedad = d1.radio("Porta la tarjeta de propiedad del vehiculo", options=YES_NO_OPTIONS, key="vehicle_tarjeta_propiedad", horizontal=True)
        soat_vigente = d2.radio("El vehiculo cuenta con SOAT vigente", options=YES_NO_OPTIONS, key="vehicle_soat_vigente", horizontal=True)
        soat_vencimiento = d3.date_input("Fecha de vencimiento del SOAT", key="vehicle_soat_vencimiento", format="DD/MM/YYYY")

        d4, d5, d6 = st.columns(3)
        tecnomecanica_vigente = d4.radio(
            "El vehiculo cuenta con certificado de revision tecnico mecanica y de gases vigente",
            options=YES_NO_OPTIONS,
            key="vehicle_tecnomecanica_vigente",
            horizontal=True,
        )
        tecnomecanica_vencimiento = d5.date_input(
            "Fecha de vencimiento de la tecnico mecanica",
            key="vehicle_tecnomecanica_vencimiento",
            format="DD/MM/YYYY",
        )
        extintor_vigente = d6.radio("El vehiculo cuenta con extintor vigente", options=YES_NO_OPTIONS_PLAIN, key="vehicle_extintor_vigente", horizontal=True)

        d7, d8, d9 = st.columns(3)
        extintor_vencimiento = d7.date_input("Fecha de vencimiento del extintor", key="vehicle_extintor_vencimiento", format="DD/MM/YYYY")
        kilometraje = d8.text_input("Kilometraje actual del vehiculo", key="vehicle_kilometraje")
        cambio_aceite = d9.date_input("Fecha del ultimo cambio de aceite", key="vehicle_cambio_aceite", format="DD/MM/YYYY")

        mantenimiento_preventivo = st.date_input(
            "Fecha del ultimo mantenimiento preventivo",
            key="vehicle_mantenimiento_preventivo",
            format="DD/MM/YYYY",
        )

        st.subheader("Estado de las partes del vehiculo")
        left_col, right_col = st.columns(2)
        left_items = VEHICLE_CHECK_ITEMS[: (len(VEHICLE_CHECK_ITEMS) + 1) // 2]
        right_items = VEHICLE_CHECK_ITEMS[(len(VEHICLE_CHECK_ITEMS) + 1) // 2 :]
        for item_key, label in left_items:
            left_col.selectbox(label, options=CHECK_STATUS_OPTIONS, key=f"vehicle_check_{item_key}")
        for item_key, label in right_items:
            right_col.selectbox(label, options=CHECK_STATUS_OPTIONS, key=f"vehicle_check_{item_key}")

        fallas = st.text_area(
            "Especifique que fallas encontro en la revision y proponga el plan de accion a desarrollar",
            key="vehicle_fallas",
            height=120,
        )
        firma = st.file_uploader(
            "Firma o constancia de la persona que realizo la inspeccion",
            type=["pdf", "png", "jpg", "jpeg"],
            help="Sube 1 archivo compatible. Tamano maximo sugerido: 10 MB.",
        )
        tratamiento_datos = st.radio(
            "Tratamiento de datos",
            options=YES_NO_OPTIONS_PLAIN,
            key="vehicle_tratamiento_datos",
            horizontal=True,
        )

        submitted = st.form_submit_button("Guardar inspeccion", type="primary", use_container_width=True)

    if not submitted:
        return

    if not employee:
        st.error("Debe ingresar una cedula valida que exista en la base maestra antes de guardar la inspeccion.")
        return
    if responsable == "Otros" and not responsable_otro.strip():
        st.error("Debe indicar el nombre del responsable cuando seleccione Otros.")
        return
    if not numero_identificacion.strip() or not nombre_conductor.strip() or not numero_documento_conductor.strip():
        st.error("Complete la identificacion y el nombre del conductor.")
        return
    if cargo == "Otros" and not cargo_otro.strip():
        st.error("Debe indicar el cargo cuando seleccione Otros.")
        return
    if not placa.strip():
        st.error("Debe indicar la placa del vehiculo inspeccionado.")
        return
    if not kilometraje.strip():
        st.error("Debe indicar el kilometraje actual del vehiculo.")
        return
    if tratamiento_datos != "Si":
        st.error("Para enviar la inspeccion debe aceptar el tratamiento de datos.")
        return
    if worksheets is None:
        try:
            worksheets = get_vehicle_inspection_worksheets()
        except Exception as error:
            st.error(f"No se pudieron preparar las hojas de inspeccion: {error}")
            return

    inspection_id = generate_inspection_id("VEH", employee.get("cedula", ""), placa)
    timestamp = format_colombia_timestamp()
    cargo_value = cargo_otro.strip() if cargo == "Otros" else cargo
    upload_ok, upload_data = upload_request_attachment(firma, inspection_id)

    profile_record = {
        "Cedula": employee.get("cedula", ""),
        "Tipo_Identificacion": tipo_identificacion,
        "Numero_Identificacion": numero_identificacion.strip(),
        "Nombre_Conductor": nombre_conductor.strip(),
        "Numero_Documento_Conductor": numero_documento_conductor.strip(),
        "Cargo_Conductor": cargo_value.strip(),
        "Sede": sede,
        "Placa_Vehiculo": placa.strip().upper(),
        "Fecha_Vencimiento_SOAT": soat_vencimiento.strftime("%d/%m/%Y"),
        "Fecha_Vencimiento_Tecnomecanica": tecnomecanica_vencimiento.strftime("%d/%m/%Y"),
        "Fecha_Vencimiento_Extintor": extintor_vencimiento.strftime("%d/%m/%Y"),
        "Fecha_Ultimo_Cambio_Aceite": cambio_aceite.strftime("%d/%m/%Y"),
        "Fecha_Ultimo_Mantenimiento_Preventivo": mantenimiento_preventivo.strftime("%d/%m/%Y"),
        "Ultima_Actualizacion": timestamp,
    }

    record = {
        "Inspeccion_ID": inspection_id,
        "Fecha_Registro": timestamp,
        "Fecha_Inspeccion": fecha_inspeccion.strftime("%d/%m/%Y"),
        "Sede": sede,
        "Responsable_Inspeccion": responsable,
        "Responsable_Inspeccion_Otro": responsable_otro.strip(),
        "Tipo_Identificacion": tipo_identificacion,
        "Numero_Identificacion": numero_identificacion.strip(),
        "Cedula": employee.get("cedula", ""),
        "Numero_Empleado": employee.get("numero_empleado", ""),
        "Nombre_Conductor": nombre_conductor.strip(),
        "Numero_Documento_Conductor": numero_documento_conductor.strip(),
        "Cargo_Conductor": cargo_value.strip(),
        "Correo_Conductor": employee.get("correo", ""),
        "Telefono_Conductor": employee.get("telefono", ""),
        "Placa_Vehiculo": placa.strip().upper(),
        "Estado_Placa_Visible": placa_visible,
        "Estado_Placa_Pintura": placa_pintura,
        "Estado_Placa_Legible": placa_legible,
        "Licencia_Vigente": licencia,
        "Medicamentos_Somnolencia": medicamentos,
        "Descanso_Minimo_6_Horas": descanso,
        "Alcohol_O_Sustancias": alcohol,
        "Tarjeta_Propiedad": tarjeta_propiedad,
        "SOAT_Vigente": soat_vigente,
        "Fecha_Vencimiento_SOAT": soat_vencimiento.strftime("%d/%m/%Y"),
        "Certificado_Tecnomecanica": tecnomecanica_vigente,
        "Fecha_Vencimiento_Tecnomecanica": tecnomecanica_vencimiento.strftime("%d/%m/%Y"),
        "Extintor_Vigente": extintor_vigente,
        "Fecha_Vencimiento_Extintor": extintor_vencimiento.strftime("%d/%m/%Y"),
        "Kilometraje_Actual": kilometraje.strip(),
        "Fecha_Ultimo_Cambio_Aceite": cambio_aceite.strftime("%d/%m/%Y"),
        "Fecha_Ultimo_Mantenimiento_Preventivo": mantenimiento_preventivo.strftime("%d/%m/%Y"),
        "Fallas_Plan_Accion": fallas.strip(),
        "Firma_Nombre": upload_data.get("Adjunto_Nombre", ""),
        "Firma_URL": upload_data.get("Adjunto_URL", ""),
        "Firma_Storage": upload_data.get("Adjunto_Storage", ""),
        "Firma_Estado": upload_data.get("Adjunto_Estado", ""),
        "Tratamiento_Datos": tratamiento_datos,
        "Fuente_Registro": "App Inspeccion Vehiculos",
    }
    for item_key, _ in VEHICLE_CHECK_ITEMS:
        record[CHECK_HEADER_BY_KEY[item_key]] = st.session_state[f"vehicle_check_{item_key}"]

    try:
        upsert_vehicle_profile(worksheets["profiles"], profile_record)
        append_vehicle_inspection_record(worksheets["records"], record)
        st.session_state["vehicle_submit_success"] = f"Inspeccion {inspection_id} registrada correctamente."
        if firma is not None and upload_ok and record.get("Firma_URL"):
            st.session_state["vehicle_submit_warning"] = "La firma o constancia quedó cargada con enlace asociado al registro."
        elif firma is not None and not upload_ok:
            st.session_state["vehicle_submit_warning"] = (
                "La inspeccion quedó guardada, pero el archivo de firma no se pudo almacenar en Dropbox."
            )
        st.session_state["vehicle_reset_after_submit"] = True
        st.rerun()
    except Exception as error:
        st.error(f"No se pudo guardar la inspeccion: {error}")


if __name__ == "__main__":
    main()