from io import BytesIO
from datetime import datetime

import pandas as pd
import streamlit as st
from openpyxl.styles import Font, PatternFill

from app_shared import (
    AUDIT_HEADERS,
    NOVEDADES_HEADERS,
    append_audit_log,
    append_novedad,
    build_whatsapp_url,
    get_auxiliary_records,
    get_request_records,
    get_solicitudes_worksheets,
    inject_shared_css,
    initialize_access_state,
    refresh_management_report,
    render_brand_header,
    render_sidebar,
    require_access,
    send_employee_response_email,
    update_request_record,
)


st.set_page_config(layout="wide", page_title="Gestion de Solicitudes")


def generate_report_excel(report_df: pd.DataFrame) -> bytes:
    output = BytesIO()
    export_df = report_df.copy()
    columns = [
        "Solicitud_ID",
        "Fecha_Solicitud",
        "Estado",
        "Tipo_Solicitud",
        "Motivo_Descripcion",
        "Cedula",
        "Nombre_Completo",
        "Cargo",
        "Sede",
        "Fecha_Inicial",
        "Fecha_Final",
        "Tiempo_Total",
        "Responsable_Revision",
        "Fecha_Respuesta",
        "Observaciones_RRHH",
    ]
    for column in columns:
        if column not in export_df.columns:
            export_df[column] = ""
    export_df = export_df[columns]

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Solicitudes")
        worksheet = writer.sheets["Solicitudes"]

        header_fill = PatternFill(start_color="0B3954", end_color="0B3954", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font

        for column_cells in worksheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 4, 40)

    output.seek(0)
    return output.getvalue()


def main() -> None:
    initialize_access_state()
    require_access(
        "admin",
        "Gestion administrativa de solicitudes",
        "Esta vista concentra la aprobacion, negacion, reportes y la salida por WhatsApp para talento humano.",
    )
    inject_shared_css()
    render_sidebar("Gestion de solicitudes")
    render_brand_header(
        "Gestion de Solicitudes y Reportes",
        "Aprobacion, seguimiento, novedades gerenciales y respuesta al empleado desde un solo punto.",
    )

    worksheets = get_solicitudes_worksheets()
    df = get_request_records(worksheets["registros"])
    novedades_df = get_auxiliary_records(worksheets["novedades"], NOVEDADES_HEADERS)
    audit_df = get_auxiliary_records(worksheets["auditoria"], AUDIT_HEADERS)
    refresh_management_report(worksheets["reporte"], df)

    if df.empty:
        st.info("Aun no existen solicitudes registradas.")
        return

    df["Fecha_Solicitud_dt"] = pd.to_datetime(df["Fecha_Solicitud"], format="%d/%m/%Y", errors="coerce")
    df["Fecha_Inicial_dt"] = pd.to_datetime(df["Fecha_Inicial"], format="%d/%m/%Y", errors="coerce")
    df["Fecha_Final_dt"] = pd.to_datetime(df["Fecha_Final"], format="%d/%m/%Y", errors="coerce")
    df.sort_values(by=["Fecha_Solicitud_dt", "Fecha_Registro"], ascending=[False, False], inplace=True)

    filter_cols = st.columns(5)
    status_options = ["Todos"] + sorted(df["Estado"].fillna("Pendiente").replace("", "Pendiente").unique().tolist())
    type_options = ["Todos"] + sorted(df["Tipo_Solicitud"].fillna("").replace("", "Sin tipo").unique().tolist())
    sede_options = ["Todas"] + sorted(df["Sede"].fillna("").replace("", "Sin sede").unique().tolist())
    status_filter = filter_cols[0].selectbox("Estado", status_options)
    type_filter = filter_cols[1].selectbox("Tipo", type_options)
    sede_filter = filter_cols[2].selectbox("Sede", sede_options)
    cedula_filter = filter_cols[3].text_input("Cedula", placeholder="Buscar por cedula")
    name_filter = filter_cols[4].text_input("Empleado", placeholder="Buscar por nombre")

    filtered_df = df.copy()
    if status_filter != "Todos":
        filtered_df = filtered_df[filtered_df["Estado"] == status_filter]
    if type_filter != "Todos":
        filtered_df = filtered_df[filtered_df["Tipo_Solicitud"] == type_filter]
    if sede_filter != "Todas":
        filtered_df = filtered_df[filtered_df["Sede"] == sede_filter]
    if cedula_filter.strip():
        filtered_df = filtered_df[filtered_df["Cedula"].astype(str).str.contains(cedula_filter.strip(), case=False, na=False)]
    if name_filter.strip():
        filtered_df = filtered_df[filtered_df["Nombre_Completo"].astype(str).str.contains(name_filter.strip(), case=False, na=False)]

    if filtered_df.empty:
        st.warning("No hay solicitudes que coincidan con los filtros seleccionados.")
        return

    metric_cols = st.columns(4)
    metric_cols[0].metric("Total solicitudes", len(filtered_df))
    metric_cols[1].metric("Pendientes", int((filtered_df["Estado"] == "Pendiente").sum()))
    metric_cols[2].metric("Aprobadas", int((filtered_df["Estado"] == "Aprobada").sum()))
    metric_cols[3].metric("Negadas", int((filtered_df["Estado"] == "Negada").sum()))

    st.caption("La hoja Solicitudes_Reporte_Gerencia se actualiza automaticamente cada vez que se abre esta vista administrativa.")

    report_data = filtered_df[
        [
            "Solicitud_ID",
            "Fecha_Solicitud",
            "Estado",
            "Tipo_Solicitud",
            "Nombre_Completo",
            "Cedula",
            "Sede",
            "Fecha_Inicial",
            "Fecha_Final",
        ]
    ].copy()
    st.dataframe(report_data, use_container_width=True, hide_index=True)

    report_excel = generate_report_excel(filtered_df)
    st.download_button(
        "Descargar reporte gerencial",
        data=report_excel,
        file_name=f"reporte_solicitudes_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    selectable = filtered_df[["Solicitud_ID", "Nombre_Completo", "Estado", "Tipo_Solicitud"]].copy()
    selectable["Etiqueta"] = selectable.apply(
        lambda row: f"{row['Solicitud_ID']} | {row['Nombre_Completo']} | {row['Tipo_Solicitud']} | {row['Estado']}",
        axis=1,
    )
    selected_label = st.selectbox("Seleccionar solicitud para gestionar", selectable["Etiqueta"].tolist())
    selected_id = selectable.loc[selectable["Etiqueta"] == selected_label, "Solicitud_ID"].iloc[0]
    selected_record = filtered_df[filtered_df["Solicitud_ID"] == selected_id].iloc[0].to_dict()

    st.markdown("### Detalle de la solicitud")
    d1, d2, d3, d4 = st.columns(4)
    d1.text_input("Empleado", value=selected_record.get("Nombre_Completo", ""), disabled=True)
    d2.text_input("Cedula", value=selected_record.get("Cedula", ""), disabled=True)
    d3.text_input("Cargo", value=selected_record.get("Cargo", ""), disabled=True)
    d4.text_input("Sede", value=selected_record.get("Sede", ""), disabled=True)

    d5, d6, d7, d8 = st.columns(4)
    d5.text_input("Tipo", value=selected_record.get("Tipo_Solicitud", ""), disabled=True)
    d6.text_input("Motivo", value=selected_record.get("Motivo_Descripcion", ""), disabled=True)
    d7.text_input("Fecha inicial", value=selected_record.get("Fecha_Inicial", ""), disabled=True)
    d8.text_input("Fecha final", value=selected_record.get("Fecha_Final", ""), disabled=True)
    st.text_area("Detalle registrado por el empleado", value=selected_record.get("Detalle_Solicitud", ""), disabled=True, height=100)

    attachment_url = selected_record.get("Adjunto_URL", "")
    attachment_name = selected_record.get("Adjunto_Nombre", "")
    attachment_status = selected_record.get("Adjunto_Estado", "")
    if attachment_url:
        st.link_button(f"Abrir adjunto: {attachment_name or 'soporte'}", attachment_url, use_container_width=True)
    elif attachment_status and attachment_status != "SIN_ADJUNTO":
        st.caption(f"Adjunto: {attachment_status}")

    st.markdown("### Respuesta administrativa")
    with st.form("gestion_respuesta_solicitud"):
        g1, g2, g3 = st.columns(3)
        estado = g1.selectbox("Estado", ["Pendiente", "En revision", "Aprobada", "Negada"], index=["Pendiente", "En revision", "Aprobada", "Negada"].index(selected_record.get("Estado", "Pendiente")))
        responsable = g2.text_input("Responsable de revision", value=selected_record.get("Responsable_Revision", ""), placeholder="Nombre de quien responde")
        medio = g3.selectbox("Medio de respuesta", ["WhatsApp", "Correo", "WhatsApp y Correo", "Interno"], index=["WhatsApp", "Correo", "WhatsApp y Correo", "Interno"].index(selected_record.get("Medio_Respuesta", "WhatsApp") if selected_record.get("Medio_Respuesta", "") in ["WhatsApp", "Correo", "WhatsApp y Correo", "Interno"] else "WhatsApp"))

        g4, g5, g6, g7 = st.columns(4)
        dias_aprobados = g4.text_input("Dias aprobados", value=selected_record.get("Dias_Aprobados", ""))
        periodo = g5.text_input("Periodo correspondiente", value=selected_record.get("Periodo_Correspondiente", ""))
        dias_pendientes = g6.text_input("Dias pendientes del periodo", value=selected_record.get("Dias_Pendientes_Periodo", ""))
        reincorporacion = g7.text_input("Fecha de reincorporacion", value=selected_record.get("Fecha_Reincorporacion", ""), placeholder="DD/MM/AAAA")

        observaciones = st.text_area("Observaciones de RR. HH.", value=selected_record.get("Observaciones_RRHH", ""), height=120)
        save_response = st.form_submit_button("Guardar respuesta", type="primary", use_container_width=True)

    if save_response:
        if not responsable.strip():
            st.error("Debe registrar el responsable de revision.")
        else:
            selected_record["Estado"] = estado
            selected_record["Responsable_Revision"] = responsable.strip()
            selected_record["Medio_Respuesta"] = medio
            selected_record["Dias_Aprobados"] = dias_aprobados.strip()
            selected_record["Periodo_Correspondiente"] = periodo.strip()
            selected_record["Dias_Pendientes_Periodo"] = dias_pendientes.strip()
            selected_record["Fecha_Reincorporacion"] = reincorporacion.strip()
            selected_record["Observaciones_RRHH"] = observaciones.strip()
            selected_record["Fecha_Respuesta"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            selected_record["Whatsapp_Listo"] = "SI" if medio in ["WhatsApp", "WhatsApp y Correo"] else "NO"
            selected_record["Ultima_Actualizacion"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

            update_request_record(worksheets["registros"], selected_id, selected_record)
            append_audit_log(
                worksheets["auditoria"],
                selected_id,
                "RESPUESTA_RRHH",
                responsable.strip(),
                f"Solicitud actualizada con estado {estado}.",
            )
            append_novedad(
                worksheets["novedades"],
                selected_record,
                "RESPUESTA_RRHH",
                observaciones.strip() or f"Solicitud marcada como {estado}.",
                medio,
                responsable.strip(),
            )
            st.success("La solicitud fue actualizada correctamente.")
            st.rerun()

    action_cols = st.columns(3)
    whatsapp_url = build_whatsapp_url(selected_record)
    if whatsapp_url:
        action_cols[0].link_button("Enviar respuesta por WhatsApp", whatsapp_url, use_container_width=True)
    else:
        action_cols[0].button("Enviar respuesta por WhatsApp", disabled=True, use_container_width=True)

    if action_cols[1].button("Enviar respuesta por correo", use_container_width=True):
        email_ok, email_message = send_employee_response_email(selected_record)
        if email_ok:
            selected_record["Correo_Respuesta_Empleado"] = "SI"
            selected_record["Ultima_Actualizacion"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            update_request_record(worksheets["registros"], selected_id, selected_record)
            append_audit_log(
                worksheets["auditoria"],
                selected_id,
                "EMAIL_RESPUESTA",
                selected_record.get("Responsable_Revision", "Sistema"),
                "Respuesta enviada por correo al empleado.",
            )
            st.success("Correo de respuesta enviado al empleado.")
            st.rerun()
        st.error(f"No se pudo enviar el correo: {email_message}")

    if action_cols[2].button("Marcar en revision", use_container_width=True):
        selected_record["Estado"] = "En revision"
        selected_record["Ultima_Actualizacion"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        update_request_record(worksheets["registros"], selected_id, selected_record)
        append_audit_log(worksheets["auditoria"], selected_id, "EN_REVISION", "Sistema", "Solicitud marcada manualmente en revision.")
        st.success("Estado actualizado a En revision.")
        st.rerun()

    st.markdown("### Trazabilidad")
    selected_novedades = novedades_df[novedades_df["Solicitud_ID"] == selected_id]
    selected_audit = audit_df[audit_df["Solicitud_ID"] == selected_id]
    t1, t2 = st.tabs(["Novedades", "Auditoria"])
    with t1:
        if selected_novedades.empty:
            st.caption("Sin novedades registradas.")
        else:
            st.dataframe(selected_novedades, use_container_width=True, hide_index=True)
    with t2:
        if selected_audit.empty:
            st.caption("Sin eventos de auditoria.")
        else:
            st.dataframe(selected_audit, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()