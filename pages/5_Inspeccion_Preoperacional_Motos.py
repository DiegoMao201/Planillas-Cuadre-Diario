from __future__ import annotations

from datetime import date

import streamlit as st

from app_shared import (
    append_moto_inspection_record,
    current_colombia_datetime,
    find_employee_by_cedula,
    format_colombia_timestamp,
    generate_inspection_id,
    get_last_moto_inspection_record,
    get_moto_inspection_worksheets,
    get_moto_profile_by_cedula,
    initialize_access_state,
    inject_shared_css,
    render_brand_header,
    render_sidebar,
    upsert_moto_profile,
    upload_request_attachment,
)


st.set_page_config(layout="wide", page_title="Inspeccion preoperacional motos")

SEDES = ["SEDE CERRITOS", "SEDE OPALO", "SEDE OLAYA"]
RESPONSABLES = [
    "TANIA RESTREPO BENJUMEA",
    "JUAN FELIPE MARTINEZ BETANCUR",
    "SANTIAGO RUIZ VELEZ",
    "JOHAN SEBASTIAN GARCES GALLARDO",
    "JERSON ATEHORTUA OLARTE",
    "HERNAN DE JESUS RENDON RODRIGUEZ",
    "SANTIAGO CONTRERAS MARULANDA",
    "LEIVYN GRABIEL GARCIA",
    "LEDUYN MELGAREJO",
    "CAMILA MOSQUERA",
    "Otros",
]
IDENTIFICATION_TYPES = [
    "Cedula de ciudadania",
    "Cedula de extranjeria",
    "Pasaporte",
    "Permiso especial",
    "Otro",
]
CARGO_OPTIONS = [
    "MENSAJEROS",
    "ASESOR COMERCIAL EXTERNO",
    "VENDEDOR EXTERNO",
    "Otros",
]
YES_NO_OPTIONS = ["Sí", "No"]
YES_NO_OPTIONS_PLAIN = ["Si", "No"]
CHECK_STATUS_OPTIONS = ["Bueno", "Malo", "Regular", "N/A"]
CHECK_ITEMS = [
    ("presencia_fugas", "Presencia de fugas de aceite y/o gasolina"),
    ("nivel_liquido_frenos", "Nivel de liquido de frenos"),
    ("nivel_aceite_combustible", "Nivel de aceite y combustible"),
    ("suspension_delantera", "Suspension delantera"),
    ("suspension_trasera", "Suspension trasera"),
    ("freno_delantero", "Freno delantero (tension)"),
    ("freno_trasero", "Freno trasero (tension)"),
    ("presion_llantas", "Presion de aire en llanta delantera y trasera"),
    ("estado_llantas", "Estado llantas (sin perforaciones, huevos o deformidades)"),
    ("profundidad_labrado", "Profundidad de labrado de las llantas (mayor a 1,6 mm)"),
    ("luces_direccionales_delanteras", "Luces direccionales delanteras"),
    ("luces_direccionales_traseras", "Luces direccionales traseras"),
    ("luces_delanteras", "Luces delanteras (media y alta)"),
    ("luces_traseras", "Luces traseras (stop y freno)"),
    ("pito", "Pito"),
    ("protector_cadena", "Protector de cadena"),
    ("tablero", "Funcionamiento del tablero"),
    ("espejos", "Estado de los espejos"),
    ("sistema_carga", "Sistema de carga y elementos de sujecion"),
    ("gato_central_lateral", "Estado del gato central y/o lateral"),
    ("casco", "Estado del casco"),
]
CHECK_HEADER_BY_KEY = {
    "presencia_fugas": "Estado_Presencia_Fugas",
    "nivel_liquido_frenos": "Estado_Nivel_Liquido_Frenos",
    "nivel_aceite_combustible": "Estado_Nivel_Aceite_Combustible",
    "suspension_delantera": "Estado_Suspension_Delantera",
    "suspension_trasera": "Estado_Suspension_Trasera",
    "freno_delantero": "Estado_Freno_Delantero",
    "freno_trasero": "Estado_Freno_Trasero",
    "presion_llantas": "Estado_Presion_Aire_Llantas",
    "estado_llantas": "Estado_Llantas",
    "profundidad_labrado": "Estado_Profundidad_Labrado",
    "luces_direccionales_delanteras": "Estado_Luces_Direccionales_Delanteras",
    "luces_direccionales_traseras": "Estado_Luces_Direccionales_Traseras",
    "luces_delanteras": "Estado_Luces_Delanteras",
    "luces_traseras": "Estado_Luces_Traseras",
    "pito": "Estado_Pito",
    "protector_cadena": "Estado_Protector_Cadena",
    "tablero": "Estado_Tablero",
    "espejos": "Estado_Espejos",
    "sistema_carga": "Estado_Sistema_Carga",
    "gato_central_lateral": "Estado_Gato_Central_Lateral",
    "casco": "Estado_Casco",
}


def inject_page_css() -> None:
    st.markdown(
        """
        <style>
        .inspection-shell {
            border: 1px solid rgba(11, 57, 84, 0.12);
            border-radius: 22px;
            padding: 1.1rem;
            background:
                radial-gradient(circle at top right, rgba(142, 186, 56, 0.18), transparent 30%),
                linear-gradient(180deg, #ffffff 0%, #f6fbf7 100%);
            box-shadow: 0 16px 40px rgba(11, 57, 84, 0.07);
        }
        .inspection-title {
            font-weight: 800;
            color: #0b3954;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }
        .inspection-note {
            border-left: 4px solid #6b8f1a;
            background: #f7fbef;
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
        "moto_cedula": "",
        "moto_sede": SEDES[0],
        "moto_fecha_inspeccion": colombia_now.date(),
        "moto_responsable": RESPONSABLES[0],
        "moto_responsable_otro": "",
        "moto_tipo_identificacion": IDENTIFICATION_TYPES[0],
        "moto_numero_identificacion": "",
        "moto_nombre_conductor": "",
        "moto_numero_identificacion_conductor": "",
        "moto_cargo": CARGO_OPTIONS[0],
        "moto_cargo_otro": "",
        "moto_placa": "",
        "moto_medicamentos": "No",
        "moto_descanso": "Sí",
        "moto_alcohol": "No",
        "moto_licencia": "Sí",
        "moto_soat_vencimiento": colombia_now.date(),
        "moto_porta_soat": "Sí",
        "moto_tecnomecanica_certificado": "Sí",
        "moto_tecnomecanica_vencimiento": colombia_now.date(),
        "moto_tarjeta_propiedad": "Sí",
        "moto_herramientas": "Si",
        "moto_kilometraje": "",
        "moto_fallas": "",
        "moto_tratamiento_datos": "Sí",
        "moto_profile_loaded": "",
        "moto_employee_loaded": "",
    }
    for key, label in CHECK_ITEMS:
        defaults[f"moto_check_{key}"] = "Bueno"
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _safe_date(value: str, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return current_colombia_datetime().strptime(value, fmt).date()
        except ValueError:
            continue
    return fallback


def sync_employee_defaults(employee: dict[str, str] | None) -> None:
    if not employee:
        return

    lookup = employee.get("cedula_lookup") or employee.get("cedula", "")
    if st.session_state.get("moto_employee_loaded") == lookup:
        return

    st.session_state["moto_employee_loaded"] = lookup
    st.session_state["moto_cedula"] = employee.get("cedula", st.session_state.get("moto_cedula", ""))
    st.session_state["moto_numero_identificacion"] = employee.get("cedula", "")
    st.session_state["moto_nombre_conductor"] = employee.get("nombre_completo", "")
    st.session_state["moto_numero_identificacion_conductor"] = employee.get("cedula", "")
    employee_cargo = employee.get("cargo", "").upper().strip()
    if employee_cargo in CARGO_OPTIONS:
        st.session_state["moto_cargo"] = employee_cargo
        st.session_state["moto_cargo_otro"] = ""
    elif employee_cargo:
        st.session_state["moto_cargo"] = "Otros"
        st.session_state["moto_cargo_otro"] = employee.get("cargo", "")

    employee_sede = employee.get("sede", "").upper().strip()
    if employee_sede in SEDES:
        st.session_state["moto_sede"] = employee_sede


def sync_profile_defaults(profile: dict[str, str] | None) -> None:
    if not profile:
        return

    signature = "|".join(
        [
            profile.get("Cedula", ""),
            profile.get("Placa_Motocicleta", ""),
            profile.get("Fecha_Vencimiento_SOAT", ""),
            profile.get("Fecha_Vencimiento_Tecnomecanica", ""),
        ]
    )
    if st.session_state.get("moto_profile_loaded") == signature:
        return

    st.session_state["moto_profile_loaded"] = signature
    if profile.get("Tipo_Identificacion"):
        st.session_state["moto_tipo_identificacion"] = profile["Tipo_Identificacion"]
    if profile.get("Numero_Identificacion"):
        st.session_state["moto_numero_identificacion"] = profile["Numero_Identificacion"]
    if profile.get("Nombre_Conductor"):
        st.session_state["moto_nombre_conductor"] = profile["Nombre_Conductor"]
    if profile.get("Numero_Identificacion_Conductor"):
        st.session_state["moto_numero_identificacion_conductor"] = profile["Numero_Identificacion_Conductor"]
    if profile.get("Cargo_Conductor") in CARGO_OPTIONS:
        st.session_state["moto_cargo"] = profile["Cargo_Conductor"]
        st.session_state["moto_cargo_otro"] = ""
    elif profile.get("Cargo_Conductor"):
        st.session_state["moto_cargo"] = "Otros"
        st.session_state["moto_cargo_otro"] = profile["Cargo_Conductor"]
    if profile.get("Sede") in SEDES:
        st.session_state["moto_sede"] = profile["Sede"]
    if profile.get("Placa_Motocicleta"):
        st.session_state["moto_placa"] = profile["Placa_Motocicleta"]
    st.session_state["moto_soat_vencimiento"] = _safe_date(
        profile.get("Fecha_Vencimiento_SOAT", ""),
        st.session_state["moto_soat_vencimiento"],
    )
    st.session_state["moto_tecnomecanica_vencimiento"] = _safe_date(
        profile.get("Fecha_Vencimiento_Tecnomecanica", ""),
        st.session_state["moto_tecnomecanica_vencimiento"],
    )


def apply_history_record(record: dict[str, str]) -> None:
    mapping = {
        "moto_responsable": "Responsable_Inspeccion",
        "moto_responsable_otro": "Responsable_Inspeccion_Otro",
        "moto_tipo_identificacion": "Tipo_Identificacion",
        "moto_numero_identificacion": "Numero_Identificacion",
        "moto_nombre_conductor": "Nombre_Conductor",
        "moto_numero_identificacion_conductor": "Numero_Identificacion_Conductor",
        "moto_placa": "Placa_Motocicleta",
        "moto_medicamentos": "Medicamentos_Somnolencia",
        "moto_descanso": "Descanso_Minimo_6_Horas",
        "moto_alcohol": "Alcohol_O_Sustancias",
        "moto_licencia": "Licencia_Vigente",
        "moto_porta_soat": "Porta_SOAT_Vigente",
        "moto_tecnomecanica_certificado": "Certificado_Tecnomecanica",
        "moto_tarjeta_propiedad": "Tarjeta_Propiedad",
        "moto_herramientas": "Herramientas",
        "moto_kilometraje": "Kilometraje_Actual",
        "moto_fallas": "Fallas_Plan_Accion",
        "moto_tratamiento_datos": "Tratamiento_Datos",
    }
    for state_key, record_key in mapping.items():
        value = record.get(record_key, "")
        if value:
            st.session_state[state_key] = value

    recorded_sede = record.get("Sede", "")
    if recorded_sede in SEDES:
        st.session_state["moto_sede"] = recorded_sede

    recorded_cargo = record.get("Cargo_Conductor", "")
    if recorded_cargo in CARGO_OPTIONS:
        st.session_state["moto_cargo"] = recorded_cargo
        st.session_state["moto_cargo_otro"] = ""
    elif recorded_cargo:
        st.session_state["moto_cargo"] = "Otros"
        st.session_state["moto_cargo_otro"] = recorded_cargo

    st.session_state["moto_fecha_inspeccion"] = current_colombia_datetime().date()
    st.session_state["moto_soat_vencimiento"] = _safe_date(
        record.get("Fecha_Vencimiento_SOAT", ""),
        st.session_state["moto_soat_vencimiento"],
    )
    st.session_state["moto_tecnomecanica_vencimiento"] = _safe_date(
        record.get("Fecha_Vencimiento_Tecnomecanica", ""),
        st.session_state["moto_tecnomecanica_vencimiento"],
    )

    for item_key, _ in CHECK_ITEMS:
        record_key = CHECK_HEADER_BY_KEY[item_key]
        if record.get(record_key):
            st.session_state[f"moto_check_{item_key}"] = record[record_key]


def clear_daily_answers() -> None:
    st.session_state["moto_fecha_inspeccion"] = current_colombia_datetime().date()
    st.session_state["moto_responsable"] = RESPONSABLES[0]
    st.session_state["moto_responsable_otro"] = ""
    st.session_state["moto_medicamentos"] = "No"
    st.session_state["moto_descanso"] = "Sí"
    st.session_state["moto_alcohol"] = "No"
    st.session_state["moto_licencia"] = "Sí"
    st.session_state["moto_porta_soat"] = "Sí"
    st.session_state["moto_tecnomecanica_certificado"] = "Sí"
    st.session_state["moto_tarjeta_propiedad"] = "Sí"
    st.session_state["moto_herramientas"] = "Si"
    st.session_state["moto_kilometraje"] = ""
    st.session_state["moto_fallas"] = ""
    st.session_state["moto_tratamiento_datos"] = "Sí"
    for item_key, _ in CHECK_ITEMS:
        st.session_state[f"moto_check_{item_key}"] = "Bueno"


def main() -> None:
    initialize_access_state()
    initialize_form_state()
    inject_shared_css()
    inject_page_css()
    render_sidebar("Inspeccion motos")
    render_brand_header(
        "Inspeccion preoperacional de motocicletas",
        "Formulario publico para diligenciamiento diario con autocompletado por cedula, perfil persistente y carga desde historial.",
    )

    st.markdown(
        """
        <div class="inspection-shell">
            <div class="inspection-title">Ferreinox inspeccion preoperacional motos</div>
            <div>Verificacion e inspeccion de las condiciones de los vehiculos de la empresa FERREINOX S.A.S. BIC.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="inspection-note">
            Digita la cedula del conductor. El sistema busca sus datos en la base maestra, carga el perfil guardado una sola vez y te permite reutilizar respuestas anteriores con el boton de historial.
        </div>
        """,
        unsafe_allow_html=True,
    )

    cedula = st.text_input(
        "Cedula del conductor",
        key="moto_cedula",
        placeholder="Ejemplo: 1012345678",
    )

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
    history_record = None
    worksheets = None
    history_warning = ""
    if cedula:
        try:
            worksheets = get_moto_inspection_worksheets()
            profile = get_moto_profile_by_cedula(worksheets["profiles"], cedula)
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
                    worksheets = get_moto_inspection_worksheets()
                history_record = get_last_moto_inspection_record(
                    worksheets["records"],
                    cedula,
                    st.session_state.get("moto_placa", ""),
                )
                if history_record:
                    apply_history_record(history_record)
                    st.session_state["moto_history_message"] = "Se cargaron las respuestas del ultimo historial disponible."
                else:
                    st.session_state["moto_history_message"] = "No se encontro historial previo para esa cedula o placa."
                st.rerun()
            except Exception as error:
                st.error(f"No se pudo cargar el historial: {error}")
    with action_cols[1]:
        if st.button("Limpiar respuestas diarias", use_container_width=True):
            clear_daily_answers()
            st.rerun()
    with action_cols[2]:
        if st.session_state.get("moto_history_message"):
            st.info(st.session_state["moto_history_message"])

    if history_warning:
        st.warning(history_warning)

    if profile:
        st.caption(
            f"Perfil guardado encontrado para la placa {profile.get('Placa_Motocicleta', 'sin placa')} con SOAT {profile.get('Fecha_Vencimiento_SOAT', 'sin fecha')} y tecnomecanica {profile.get('Fecha_Vencimiento_Tecnomecanica', 'sin fecha')}."
        )

    with st.form("formulario_inspeccion_motos"):
        st.subheader("Datos generales")
        col1, col2, col3 = st.columns(3)
        sede = col1.selectbox("Sede", options=SEDES, key="moto_sede")
        fecha_inspeccion = col2.date_input("Fecha de la inspeccion", key="moto_fecha_inspeccion", format="DD/MM/YYYY")
        responsable = col3.selectbox("Responsable de la inspeccion", options=RESPONSABLES, key="moto_responsable")

        responsable_otro = ""
        if responsable == "Otros":
            responsable_otro = st.text_input("Indique otro responsable", key="moto_responsable_otro")

        st.subheader("Identificacion del conductor")
        col4, col5, col6 = st.columns(3)
        tipo_identificacion = col4.selectbox("Tipo de identificacion", options=IDENTIFICATION_TYPES, key="moto_tipo_identificacion")
        numero_identificacion = col5.text_input("Numero de identificacion", key="moto_numero_identificacion")
        nombre_conductor = col6.text_input("Nombre del conductor", key="moto_nombre_conductor")

        col7, col8, col9 = st.columns(3)
        numero_identificacion_conductor = col7.text_input(
            "Numero de identificacion del conductor",
            key="moto_numero_identificacion_conductor",
        )
        cargo = col8.selectbox("Cargo del conductor", options=CARGO_OPTIONS, key="moto_cargo")
        placa = col9.text_input("Placa de la motocicleta inspeccionada", key="moto_placa")

        cargo_otro = ""
        if cargo == "Otros":
            cargo_otro = st.text_input("Indique otro cargo", key="moto_cargo_otro")

        st.subheader("Validaciones del conductor y documentos")
        q1, q2, q3, q4 = st.columns(4)
        medicamentos = q1.radio(
            "En las ultimas 8 horas ha consumido medicamentos que generen somnolencia",
            options=YES_NO_OPTIONS_PLAIN,
            key="moto_medicamentos",
            horizontal=True,
        )
        descanso = q2.radio(
            "Ha descansado minimo 6 horas continuas",
            options=YES_NO_OPTIONS,
            key="moto_descanso",
            horizontal=True,
        )
        alcohol = q3.radio(
            "Ha consumido bebidas alcoholicas o sustancias psicoactivas en las ultimas 12 horas",
            options=YES_NO_OPTIONS,
            key="moto_alcohol",
            horizontal=True,
        )
        licencia = q4.radio(
            "Cuenta con licencia de conduccion vigente y acorde al vehiculo",
            options=YES_NO_OPTIONS,
            key="moto_licencia",
            horizontal=True,
        )

        d1, d2, d3 = st.columns(3)
        soat_vencimiento = d1.date_input("Fecha de vencimiento de SOAT", key="moto_soat_vencimiento", format="DD/MM/YYYY")
        porta_soat = d2.radio("Porta el SOAT vigente", options=YES_NO_OPTIONS, key="moto_porta_soat", horizontal=True)
        tecnomecanica_certificado = d3.radio(
            "Certificado de revision tecnico mecanica y de gases",
            options=YES_NO_OPTIONS,
            key="moto_tecnomecanica_certificado",
            horizontal=True,
        )

        d4, d5, d6 = st.columns(3)
        tecnomecanica_vencimiento = d4.date_input(
            "Fecha de vencimiento de revision tecnico mecanica",
            key="moto_tecnomecanica_vencimiento",
            format="DD/MM/YYYY",
        )
        tarjeta_propiedad = d5.radio(
            "Porta la tarjeta de propiedad del vehiculo",
            options=YES_NO_OPTIONS,
            key="moto_tarjeta_propiedad",
            horizontal=True,
        )
        herramientas = d6.radio(
            "Porta herramientas",
            options=YES_NO_OPTIONS_PLAIN,
            key="moto_herramientas",
            horizontal=True,
        )

        kilometraje = st.text_input("Kilometraje actual del vehiculo", key="moto_kilometraje")

        st.subheader("Estado de partes de la motocicleta")
        status_left, status_right = st.columns(2)
        left_items = CHECK_ITEMS[: (len(CHECK_ITEMS) + 1) // 2]
        right_items = CHECK_ITEMS[(len(CHECK_ITEMS) + 1) // 2 :]
        for item_key, label in left_items:
            status_left.selectbox(label, options=CHECK_STATUS_OPTIONS, key=f"moto_check_{item_key}")
        for item_key, label in right_items:
            status_right.selectbox(label, options=CHECK_STATUS_OPTIONS, key=f"moto_check_{item_key}")

        fallas = st.text_area(
            "Especifique las fallas encontradas y el plan de accion a desarrollar",
            key="moto_fallas",
            height=120,
        )
        firma = st.file_uploader(
            "Firma o constancia de quien realizo la inspeccion",
            type=["pdf", "png", "jpg", "jpeg"],
            help="Sube 1 archivo. Tamano maximo sugerido: 10 MB.",
        )
        tratamiento_datos = st.radio(
            "Autorizacion de tratamiento de datos",
            options=YES_NO_OPTIONS,
            key="moto_tratamiento_datos",
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
    if not numero_identificacion.strip() or not nombre_conductor.strip() or not numero_identificacion_conductor.strip():
        st.error("Complete la identificacion y el nombre del conductor.")
        return
    if not placa.strip():
        st.error("Debe indicar la placa de la motocicleta inspeccionada.")
        return
    if cargo == "Otros" and not cargo_otro.strip():
        st.error("Debe indicar el cargo cuando seleccione Otros.")
        return
    if not kilometraje.strip():
        st.error("Debe indicar el kilometraje actual del vehiculo.")
        return
    if tratamiento_datos != "Sí":
        st.error("Para enviar la inspeccion debe aceptar el tratamiento de datos.")
        return
    if firma is None:
        st.error("Debe adjuntar la firma o constancia de quien realizo la inspeccion.")
        return

    if worksheets is None:
        try:
            worksheets = get_moto_inspection_worksheets()
        except Exception as error:
            st.error(f"No se pudieron preparar las hojas de inspeccion: {error}")
            return

    inspection_id = generate_inspection_id("MOT", employee.get("cedula", ""), placa)
    timestamp = format_colombia_timestamp()
    cargo_value = cargo_otro.strip() if cargo == "Otros" else cargo

    upload_ok, upload_data = upload_request_attachment(firma, inspection_id)
    profile_record = {
        "Cedula": employee.get("cedula", ""),
        "Tipo_Identificacion": tipo_identificacion,
        "Numero_Identificacion": numero_identificacion.strip(),
        "Nombre_Conductor": nombre_conductor.strip(),
        "Numero_Identificacion_Conductor": numero_identificacion_conductor.strip(),
        "Cargo_Conductor": cargo_value.strip(),
        "Sede": sede,
        "Placa_Motocicleta": placa.strip().upper(),
        "Fecha_Vencimiento_SOAT": soat_vencimiento.strftime("%d/%m/%Y"),
        "Fecha_Vencimiento_Tecnomecanica": tecnomecanica_vencimiento.strftime("%d/%m/%Y"),
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
        "Numero_Identificacion_Conductor": numero_identificacion_conductor.strip(),
        "Cargo_Conductor": cargo_value.strip(),
        "Correo_Conductor": employee.get("correo", ""),
        "Telefono_Conductor": employee.get("telefono", ""),
        "Placa_Motocicleta": placa.strip().upper(),
        "Medicamentos_Somnolencia": medicamentos,
        "Descanso_Minimo_6_Horas": descanso,
        "Alcohol_O_Sustancias": alcohol,
        "Licencia_Vigente": licencia,
        "Fecha_Vencimiento_SOAT": soat_vencimiento.strftime("%d/%m/%Y"),
        "Porta_SOAT_Vigente": porta_soat,
        "Certificado_Tecnomecanica": tecnomecanica_certificado,
        "Fecha_Vencimiento_Tecnomecanica": tecnomecanica_vencimiento.strftime("%d/%m/%Y"),
        "Tarjeta_Propiedad": tarjeta_propiedad,
        "Herramientas": herramientas,
        "Kilometraje_Actual": kilometraje.strip(),
        "Fallas_Plan_Accion": fallas.strip(),
        "Firma_Nombre": upload_data.get("Adjunto_Nombre", ""),
        "Firma_URL": upload_data.get("Adjunto_URL", ""),
        "Firma_Storage": upload_data.get("Adjunto_Storage", ""),
        "Firma_Estado": upload_data.get("Adjunto_Estado", ""),
        "Tratamiento_Datos": tratamiento_datos,
        "Fuente_Registro": "App Inspeccion Motos",
    }
    for item_key, _ in CHECK_ITEMS:
        record[CHECK_HEADER_BY_KEY[item_key]] = st.session_state[f"moto_check_{item_key}"]

    try:
        upsert_moto_profile(worksheets["profiles"], profile_record)
        append_moto_inspection_record(worksheets["records"], record)
        st.success(f"Inspeccion {inspection_id} registrada correctamente.")
        if upload_ok and record.get("Firma_URL"):
            st.info("La firma o constancia quedó cargada con enlace asociado al registro.")
        elif not upload_ok:
            st.warning(
                "La inspeccion quedó guardada, pero el archivo de firma no se pudo almacenar en Dropbox. Revisa la configuracion de secrets."
            )
        clear_daily_answers()
    except Exception as error:
        st.error(f"No se pudo guardar la inspeccion: {error}")


if __name__ == "__main__":
    main()