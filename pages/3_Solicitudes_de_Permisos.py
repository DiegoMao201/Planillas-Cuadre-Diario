from datetime import datetime

import streamlit as st

from app_shared import (
    append_audit_log,
    append_novedad,
    append_request_record,
    current_colombia_datetime,
    format_colombia_timestamp,
    find_employee_by_cedula,
    generate_request_id,
    get_reason_metadata,
    get_solicitudes_worksheets,
    inject_shared_css,
    initialize_access_state,
    render_brand_header,
    render_sidebar,
    send_request_email,
    upload_request_attachment,
)


st.set_page_config(layout="wide", page_title="Solicitud de Permisos")


def inject_pdf_like_css() -> None:
    st.markdown(
        """
        <style>
        .pdf-shell {
            border: 1.5px solid #183b56;
            padding: 1rem;
            border-radius: 10px;
            background: #ffffff;
        }
        .pdf-header {
            display: grid;
            grid-template-columns: 130px 1fr 160px;
            gap: 0.9rem;
            align-items: center;
            border-bottom: 1.5px solid #183b56;
            padding-bottom: 0.9rem;
            margin-bottom: 1rem;
        }
        .pdf-title {
            text-align: center;
            font-weight: 800;
            color: #0b3954;
            letter-spacing: 0.06em;
            line-height: 1.35;
        }
        .pdf-box {
            border: 1px solid #183b56;
            min-height: 66px;
            padding: 0.45rem 0.55rem;
            border-radius: 6px;
            background: #f8fbfd;
        }
        .pdf-box strong {
            display: block;
            color: #0b3954;
            font-size: 0.82rem;
            margin-bottom: 0.2rem;
        }
        .pdf-section-title {
            margin: 1rem 0 0.6rem 0;
            padding: 0.45rem 0.7rem;
            background: #0b3954;
            color: #ffffff;
            border-radius: 6px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            font-size: 0.84rem;
        }
        .pdf-note {
            border: 1px dashed #557085;
            background: #f6f9fb;
            padding: 0.8rem;
            border-radius: 8px;
            color: #29465b;
            font-size: 0.92rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_form_state() -> None:
    colombia_now = current_colombia_datetime()
    defaults = {
        "permiso_fecha_solicitud": colombia_now.date(),
        "permiso_fecha_inicial": colombia_now.date(),
        "permiso_fecha_final": colombia_now.date(),
        "permiso_hora_salida": colombia_now.replace(hour=8, minute=0, second=0, microsecond=0).time(),
        "permiso_tiempo_total": "",
        "permiso_persona_cargo": "",
        "permiso_motivo": "1",
        "permiso_cual_licencia": "",
        "permiso_fecha_compensatorio": colombia_now.date(),
        "permiso_detalle": "",
        "permiso_autorizacion": False,
        "permiso_cedula": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_form() -> None:
    for key in [
        "permiso_fecha_solicitud",
        "permiso_fecha_inicial",
        "permiso_fecha_final",
        "permiso_hora_salida",
        "permiso_tiempo_total",
        "permiso_persona_cargo",
        "permiso_motivo",
        "permiso_cual_licencia",
        "permiso_fecha_compensatorio",
        "permiso_detalle",
        "permiso_autorizacion",
    ]:
        if key in st.session_state:
            del st.session_state[key]
    initialize_form_state()


def employee_summary_card(employee: dict[str, str]) -> None:
    st.markdown(
        f"""
        <div class="ferreinox-card">
            <span class="ferreinox-badge">Empleado validado</span>
            <div class="ferreinox-grid">
                <div class="ferreinox-field"><label>Nombre y apellidos</label><span>{employee.get('nombre_completo', '')}</span></div>
                <div class="ferreinox-field"><label>ID N.°</label><span>{employee.get('cedula', '')}</span></div>
                <div class="ferreinox-field"><label>N.° Empleado</label><span>{employee.get('numero_empleado', '')}</span></div>
                <div class="ferreinox-field"><label>Cargo</label><span>{employee.get('cargo', '')}</span></div>
                <div class="ferreinox-field"><label>Sede</label><span>{employee.get('sede', '')}</span></div>
                <div class="ferreinox-field"><label>Correo</label><span>{employee.get('correo', '')}</span></div>
                <div class="ferreinox-field"><label>Telefono</label><span>{employee.get('telefono', '')}</span></div>
                <div class="ferreinox-field"><label>Fecha de ingreso</label><span>{employee.get('fecha_ingreso', '')}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    initialize_access_state()
    initialize_form_state()
    inject_shared_css()
    inject_pdf_like_css()
    render_sidebar("Solicitud de permisos")
    render_brand_header(
        "Formato de Solicitud de Permisos, Vacaciones y Licencias",
        "El empleado solo ve este formulario. La informacion se completa automaticamente con la cedula y queda registrada en Google Sheets.",
    )

    st.info(
        "Digite la cedula del empleado. Si existe en base_datos_empleados.xlsx, el sistema completa sus datos y registra la solicitud con estructura lista para reportes de gerencia.",
        icon="ℹ️",
    )

    st.markdown(
        """
        <div class="pdf-shell">
            <div class="pdf-header">
                <div class="pdf-box">
                    <strong>Fecha solicitud</strong>
                    Dia / Mes / Ano
                </div>
                <div class="pdf-title">
                    FORMATO DE SOLICITUD<br>
                    PERMISOS - VACACIONES - LICENCIAS
                </div>
                <div class="pdf-box">
                    <strong>Uso interno</strong>
                    Aprobado por RR. HH.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cedula = st.text_input("Cedula del empleado", key="permiso_cedula", placeholder="Ejemplo: 1012345678")
    try:
        employee = find_employee_by_cedula(cedula) if cedula else None
    except Exception as error:
        st.error(f"No se pudo leer el archivo base_datos_empleados.xlsx: {error}")
        return

    if cedula and not employee:
        st.warning("No se encontro un empleado con esa cedula en base_datos_empleados.xlsx.")

    if employee:
        employee_summary_card(employee)

    st.write("")
    with st.form("formulario_solicitud_permiso"):
        st.markdown('<div class="pdf-section-title">Datos del empleado</div>', unsafe_allow_html=True)
        st.caption("Los datos salen de la base maestra al validar la cédula.")

        st.markdown('<div class="pdf-section-title">Datos de la solicitud</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        fecha_solicitud = c1.date_input("Fecha de solicitud", key="permiso_fecha_solicitud", format="DD/MM/YYYY")
        fecha_inicial = c2.date_input("Fecha inicial", key="permiso_fecha_inicial", format="DD/MM/YYYY")
        fecha_final = c3.date_input("Fecha final", key="permiso_fecha_final", format="DD/MM/YYYY")

        c4, c5, c6 = st.columns(3)
        hora_salida = c4.time_input("Hora de salida", key="permiso_hora_salida")
        tiempo_total = c5.text_input("Tiempo total", key="permiso_tiempo_total", placeholder="Ejemplo: 4 horas")
        persona_cargo = c6.text_input("Persona a cargo", key="permiso_persona_cargo", placeholder="Quien cubre la labor")

        reason_options = {item["codigo"]: f"{item['codigo']}. {item['nombre']}" for item in get_reason_options()}
        st.markdown('<div class="pdf-section-title">Senale con una X el motivo de la solicitud</div>', unsafe_allow_html=True)
        motivo = st.radio(
            "Motivo de la solicitud",
            options=list(reason_options.keys()),
            format_func=lambda value: reason_options[value],
            key="permiso_motivo",
        )

        cual_licencia = ""
        fecha_compensatorio = None
        if motivo == "3":
            cual_licencia = st.text_input("Cual licencia remunerada aplica", key="permiso_cual_licencia")
        if motivo == "7":
            fecha_compensatorio = st.date_input(
                "Fecha del dia trabajado para compensatorio",
                key="permiso_fecha_compensatorio",
                format="DD/MM/YYYY",
            )

        detalle = st.text_area(
            "Detalle de la solicitud",
            key="permiso_detalle",
            height=110,
            placeholder="Describa claramente el motivo, horario, destino o cualquier novedad que deba revisar talento humano.",
        )

        adjunto = st.file_uploader(
            "Adjuntar soporte opcional",
            type=["pdf", "png", "jpg", "jpeg", "doc", "docx"],
            help="Si configuras Dropbox en secrets, el soporte quedará guardado con enlace directo y trazabilidad en Google Sheets.",
        )

        autorizacion = st.checkbox(
            "Autorizo el descuento correspondiente cuando aplique para permisos voluntarios superiores a 4 horas y no compensados.",
            key="permiso_autorizacion",
        )

        st.markdown(
            '<div class="pdf-note">Para permisos voluntarios consistentes en diligencias personales, de orden familiar y similares, la empresa puede aplicar el descuento correspondiente cuando el tiempo sea superior a 4 horas y no sea compensado.</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="pdf-section-title">Espacio exclusivo empresa</div>', unsafe_allow_html=True)
        e1, e2, e3, e4 = st.columns(4)
        e1.text_input("Dias aprobados", value="Se diligencia en RR. HH.", disabled=True)
        e2.text_input("Correspondientes al periodo", value="Se diligencia en RR. HH.", disabled=True)
        e3.text_input("Dias pendientes del periodo", value="Se diligencia en RR. HH.", disabled=True)
        e4.text_input("Reincorporacion", value="Se diligencia en RR. HH.", disabled=True)

        submitted = st.form_submit_button("Enviar solicitud", type="primary", use_container_width=True)

    if not submitted:
        return

    if not employee:
        st.error("Debe ingresar una cedula valida antes de enviar la solicitud.")
        return
    if fecha_inicial > fecha_final:
        st.error("La fecha inicial no puede ser posterior a la fecha final.")
        return
    if not tiempo_total.strip():
        st.error("Debe indicar el tiempo total solicitado.")
        return
    if not persona_cargo.strip():
        st.error("Debe indicar la persona a cargo.")
        return
    if not detalle.strip():
        st.error("Debe escribir el detalle de la solicitud.")
        return
    if motivo == "2" and not autorizacion:
        st.error("Para permisos voluntarios debe aceptar la autorizacion de descuento cuando aplique.")
        return

    reason = get_reason_metadata(motivo)
    request_id = generate_request_id(employee.get("cedula", ""))
    timestamp = format_colombia_timestamp()

    attachment_ok, attachment_data = upload_request_attachment(adjunto, request_id)
    record = {
        "Solicitud_ID": request_id,
        "Fecha_Registro": timestamp,
        "Fecha_Solicitud": fecha_solicitud.strftime("%d/%m/%Y"),
        "Estado": "Pendiente",
        "Tipo_Solicitud": reason.get("tipo", "Permiso"),
        "Motivo_Codigo": reason.get("codigo", ""),
        "Motivo_Descripcion": reason.get("nombre", ""),
        "Cedula": employee.get("cedula", ""),
        "Numero_Empleado": employee.get("numero_empleado", ""),
        "Apellido": employee.get("apellido", ""),
        "Nombre_Completo": employee.get("nombre_completo", ""),
        "Cargo": employee.get("cargo", ""),
        "Sede": employee.get("sede", ""),
        "Tipo_Contrato": employee.get("tipo_contrato", ""),
        "Fecha_Ingreso": employee.get("fecha_ingreso", ""),
        "Correo_Empleado": employee.get("correo", ""),
        "Telefono_Empleado": employee.get("telefono", ""),
        "Fecha_Inicial": fecha_inicial.strftime("%d/%m/%Y"),
        "Fecha_Final": fecha_final.strftime("%d/%m/%Y"),
        "Hora_Salida": hora_salida.strftime("%H:%M"),
        "Tiempo_Total": tiempo_total.strip(),
        "Persona_A_Cargo": persona_cargo.strip(),
        "Cual_Licencia": cual_licencia.strip(),
        "Fecha_Dia_Trabajado": fecha_compensatorio.strftime("%d/%m/%Y") if fecha_compensatorio else "",
        "Detalle_Solicitud": detalle.strip(),
        "Autorizacion_Descuento": autorizacion,
        "Dias_Aprobados": "",
        "Periodo_Correspondiente": "",
        "Dias_Pendientes_Periodo": "",
        "Fecha_Reincorporacion": "",
        "Observaciones_RRHH": "",
        "Responsable_Revision": "",
        "Fecha_Respuesta": "",
        "Medio_Respuesta": "",
        "Correo_Enviado_A_RRHH": "NO",
        "Correo_Respuesta_Empleado": "NO",
        "Whatsapp_Listo": "NO",
        "Adjunto_Nombre": attachment_data.get("Adjunto_Nombre", ""),
        "Adjunto_URL": attachment_data.get("Adjunto_URL", ""),
        "Adjunto_Storage": attachment_data.get("Adjunto_Storage", ""),
        "Adjunto_Estado": attachment_data.get("Adjunto_Estado", ""),
        "Ultima_Actualizacion": timestamp,
        "Fuente_Registro": "App Empleado",
    }

    try:
        worksheets = get_solicitudes_worksheets()
        append_request_record(worksheets["registros"], record)
        append_audit_log(
            worksheets["auditoria"],
            request_id,
            "CREACION",
            employee.get("nombre_completo", "Empleado"),
            "Solicitud creada desde el formulario del empleado.",
        )
        append_novedad(
            worksheets["novedades"],
            record,
            "CREACION",
            "Solicitud recibida y pendiente de revision.",
            "APP",
            employee.get("nombre_completo", "Empleado"),
        )

        email_ok, email_message = send_request_email(record)
        if email_ok:
            record["Correo_Enviado_A_RRHH"] = "SI"
            record["Ultima_Actualizacion"] = format_colombia_timestamp()
            from app_shared import update_request_record

            update_request_record(worksheets["registros"], record["Solicitud_ID"], record)
            append_audit_log(
                worksheets["auditoria"],
                request_id,
                "NOTIFICACION_RRHH",
                "Sistema",
                "Correo enviado a coordinacion de recursos humanos.",
            )

        st.success(f"Solicitud {request_id} registrada correctamente.")
        if adjunto and attachment_ok and record.get("Adjunto_URL"):
            st.info("El soporte quedó cargado y vinculado a la solicitud.")
        elif adjunto and not attachment_ok:
            st.warning("La solicitud quedó guardada, pero el adjunto no se pudo almacenar. Revisa la configuración de Dropbox en secrets.")
        if email_ok:
            st.info("La solicitud ya fue enviada al correo de talentohumano@ferreinox.co.")
        else:
            st.warning(f"La solicitud quedo guardada, pero el correo no se pudo enviar: {email_message}")
        clear_form()
    except Exception as error:
        st.error(f"No se pudo guardar la solicitud: {error}")


def get_reason_options():
    return [
        {"codigo": "1", "nombre": "Cita medica, tratamiento medico o examen medico especializado"},
        {"codigo": "2", "nombre": "Permiso voluntario para diligencias personales, familiares o similares"},
        {"codigo": "3", "nombre": "Licencias obligatorias remuneradas por ley"},
        {"codigo": "4", "nombre": "Licencia no remunerada"},
        {"codigo": "5", "nombre": "Vacaciones"},
        {"codigo": "6", "nombre": "Beneficio de cumpleanos / jornada de familia"},
        {"codigo": "7", "nombre": "Compensatorio por dia trabajado"},
    ]


if __name__ == "__main__":
    main()
